"""
Shipping Service - Handles delivery logistics and listens to payment events
Port: 5005
"""
from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
import pika
import json
import requests
import time
import threading

import logging
from pythonjsonlogger import jsonlogger
from flask import g
from prometheus_flask_exporter import PrometheusMetrics

import logstash

# Configure Structured Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console Handler (JSON)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(level)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Logstash Handler
logstash_handler = logstash.TCPLogstashHandler('logstash', 5000, version=1)
logger.addHandler(logstash_handler)

app = Flask(__name__)
metrics = PrometheusMetrics(app, path=None)

from prometheus_client import generate_latest

@app.route('/metrics')
def metrics_route():
    return generate_latest(), 200, {'Content-Type': 'text/plain; version=0.0.4'}

@app.before_request
def before_request():
    # Extract Correlation ID from header
    g.correlation_id = request.headers.get('X-Correlation-ID')
    if not g.correlation_id:
        g.correlation_id = "unknown"
        
    logger.info(f"Request received: {request.method} {request.path}", extra={
        'service': 'shipping-service',
        'correlation_id': g.correlation_id,
        'method': request.method,
        'path': request.path
    })

CORS(app)

RABBITMQ_HOST = 'rabbitmq'
RABBITMQ_PORT = 5672

def init_db():
    conn = sqlite3.connect('shipping.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS shipments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id INTEGER NOT NULL,
                  tracking_number TEXT,
                  status TEXT DEFAULT 'preparing',
                  carrier TEXT,
                  estimated_delivery TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def publish_event(event_type, data):
    """Publish event to RabbitMQ"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
        channel = connection.channel()
        channel.exchange_declare(exchange='order_events', exchange_type='topic', durable=True)
        
        message = json.dumps({'event': event_type, 'data': data})
        channel.basic_publish(
            exchange='order_events',
            routing_key=event_type,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        print(f"Published event: {event_type}")
    except Exception as e:
        print(f"Error publishing event: {str(e)}")

def process_shipping(payment_data):
    """Create shipment after payment is completed"""
    order_id = payment_data['order_id']
    
    logger.info(f"Processing shipment for order {order_id}", extra={'correlation_id': g.correlation_id})
    
    # Simulate shipping preparation
    time.sleep(2)
    
    # Create shipment record
    conn = sqlite3.connect('shipping.db')
    c = conn.cursor()
    tracking_number = f'TRACK-{order_id}-{int(time.time())}'
    c.execute('''INSERT INTO shipments (order_id, tracking_number, status, carrier, estimated_delivery)
                 VALUES (?, ?, ?, ?, ?)''',
              (order_id, tracking_number, 'shipped', 'DHL', '2024-12-10'))
    conn.commit()
    shipment_id = c.lastrowid
    conn.close()
    
    # Update order shipping status (synchronous call to Order Service)
    try:
        requests.put(
            f'http://order-service:5003/api/orders/{order_id}/shipping-status',
            json={'shipping_status': 'shipped'}
        )
    except Exception as e:
        print(f"Error updating order shipping status: {str(e)}")
    
    # Publish ShipmentCreated event (asynchronous)
    publish_event('shipment.created', {
        'shipment_id': shipment_id,
        'order_id': order_id,
        'tracking_number': tracking_number,
        'customer_id': payment_data['customer_id']
    })
    
    logger.info(f"Shipment created for order {order_id}, tracking: {tracking_number}", extra={'correlation_id': g.correlation_id})

def callback(ch, method, properties, body):
    """RabbitMQ message callback"""
    try:
        message = json.loads(body)
        event_type = message.get('event')
        data = message.get('data')
        
        logger.info(f"Received event: {event_type}", extra={'correlation_id': 'system'})
        
        if event_type == 'payment.completed':
            process_shipping(data)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", extra={'correlation_id': 'system'})
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consumer():
    """Start RabbitMQ consumer in separate thread"""
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
            channel = connection.channel()
            
            # Declare exchange and queue
            channel.exchange_declare(exchange='order_events', exchange_type='topic', durable=True)
            result = channel.queue_declare(queue='shipping_queue', durable=True)
            queue_name = result.method.queue
            
            # Bind queue to exchange with routing key
            channel.queue_bind(exchange='order_events', queue=queue_name, routing_key='payment.completed')
            
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            
            logger.info('Shipping Service: Waiting for payment events...', extra={'correlation_id': 'system'})
            channel.start_consuming()
        except Exception as e:
            logger.error(f"Consumer error: {str(e)}", extra={'correlation_id': 'system'})
            time.sleep(5)

# API endpoints
@app.route('/api/shipments', methods=['GET'])
def get_shipments():
    # Authorization is handled by Gateway
    # Get user context
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role')
    
    conn = sqlite3.connect('shipping.db')
    c = conn.cursor()
    
    # Customers see only their shipments
    if user_role == 'customer':
        c.execute('''SELECT s.* FROM shipments s
                     JOIN orders o ON s.order_id = o.id
                     WHERE o.customer_id = ?''', (user_id,))
    else:
        c.execute('SELECT * FROM shipments')
    
    shipments = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': s[0], 'order_id': s[1], 'tracking_number': s[2],
        'status': s[3], 'carrier': s[4], 'estimated_delivery': s[5], 'created_at': s[6]
    } for s in shipments]), 200

@app.route('/api/shipments/<int:shipment_id>', methods=['GET'])
def get_shipment(shipment_id):
    conn = sqlite3.connect('shipping.db')
    c = conn.cursor()
    c.execute('SELECT * FROM shipments WHERE id = ?', (shipment_id,))
    shipment = c.fetchone()
    conn.close()
    
    if shipment:
        return jsonify({
            'id': shipment[0], 'order_id': shipment[1], 'tracking_number': shipment[2],
            'status': shipment[3], 'carrier': shipment[4], 
            'estimated_delivery': shipment[5], 'created_at': shipment[6]
        }), 200
    return jsonify({'message': 'Shipment not found'}), 404

@app.route('/api/shipments/track/<tracking_number>', methods=['GET'])
def track_shipment(tracking_number):
    conn = sqlite3.connect('shipping.db')
    c = conn.cursor()
    c.execute('SELECT * FROM shipments WHERE tracking_number = ?', (tracking_number,))
    shipment = c.fetchone()
    conn.close()
    
    if shipment:
        return jsonify({
            'id': shipment[0], 'order_id': shipment[1], 'tracking_number': shipment[2],
            'status': shipment[3], 'carrier': shipment[4], 
            'estimated_delivery': shipment[5], 'created_at': shipment[6]
        }), 200
    return jsonify({'message': 'Shipment not found'}), 404

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'shipping-service'}), 200

if __name__ == '__main__':
    # Start RabbitMQ consumer in separate thread
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5005, debug=True)
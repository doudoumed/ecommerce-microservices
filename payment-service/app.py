"""
Payment Service - Processes payments and listens to order events
Port: 5004
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pika
import json
import requests
import time
import threading

app = Flask(__name__)
CORS(app)

RABBITMQ_HOST = 'rabbitmq'
RABBITMQ_PORT = 5672

def init_db():
    conn = sqlite3.connect('payments.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id INTEGER NOT NULL,
                  amount REAL NOT NULL,
                  status TEXT DEFAULT 'pending',
                  payment_method TEXT,
                  transaction_id TEXT,
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

# ... (previous code)

def process_payment_logic(order_data):
    """Core payment processing logic"""
    order_id = order_data['order_id']
    amount = order_data['total_price']
    customer_id = order_data.get('customer_id') # Handle potential missing key if called from different context
    
    print(f"Processing payment for order {order_id}, amount: {amount}")
    
    # Simulate payment processing
    time.sleep(2)
    
    # Save payment record
    conn = sqlite3.connect('payments.db')
    c = conn.cursor()
    c.execute('''INSERT INTO payments (order_id, amount, status, payment_method, transaction_id)
                 VALUES (?, ?, ?, ?, ?)''',
              (order_id, amount, 'completed', 'credit_card', f'TXN-{order_id}-{int(time.time())}'))
    conn.commit()
    payment_id = c.lastrowid
    conn.close()
    
    # Update order payment status (synchronous call to Order Service)
    try:
        requests.put(
            f'http://order-service:5003/api/orders/{order_id}/payment-status',
            json={'payment_status': 'completed'},
            timeout=5
        )
    except Exception as e:
        print(f"Error updating order payment status: {str(e)}")
    
    # Publish PaymentCompleted event (asynchronous)
    publish_event('payment.completed', {
        'payment_id': payment_id,
        'order_id': order_id,
        'amount': amount,
        'customer_id': customer_id
    })
    
    print(f"Payment completed for order {order_id}")
    return payment_id

def callback(ch, method, properties, body):
    """RabbitMQ message callback"""
    try:
        message = json.loads(body)
        event_type = message.get('event')
        data = message.get('data')
        
        print(f"Received event: {event_type}")
        
        if event_type == 'order.created':
            process_payment_logic(data)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Error processing message: {str(e)}")
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
            result = channel.queue_declare(queue='payment_queue', durable=True)
            queue_name = result.method.queue
            
            # Bind queue to exchange with routing key
            channel.queue_bind(exchange='order_events', queue=queue_name, routing_key='order.created')
            
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            
            print('Payment Service: Waiting for order events...')
            channel.start_consuming()
        except Exception as e:
            print(f"Consumer error: {str(e)}")
            time.sleep(5)

# API endpoints
@app.route('/api/payments/process', methods=['POST'])
def process_payment_endpoint():
    """Synchronous payment processing endpoint"""
    data = request.json
    try:
        payment_id = process_payment_logic(data)
        return jsonify({
            'message': 'Payment processed successfully',
            'payment_id': payment_id,
            'status': 'completed'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API endpoints
@app.route('/api/payments', methods=['GET'])
def get_payments():
    # Authorization is handled by Gateway
    # Get user context
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role')
    
    conn = sqlite3.connect('payments.db')
    c = conn.cursor()
    
    # Customers see only their payments
    if user_role == 'admin':
        c.execute('SELECT * FROM payments')
    
        payments = c.fetchall()
        conn.close()
    
        return jsonify([{
            'id': p[0], 'order_id': p[1], 'amount': p[2],
            'status': p[3], 'payment_method': p[4], 'transaction_id': p[5], 'created_at': p[6]
        } for p in payments]), 200
    return jsonify({'message': 'Payment not found'}), 404

@app.route('/api/payments/<int:payment_id>', methods=['GET'])
def get_payment(payment_id):
    # Authorization is handled by Gateway
    conn = sqlite3.connect('payments.db')
    c = conn.cursor()
    c.execute('SELECT * FROM payments WHERE id = ?', (payment_id,))
    payment = c.fetchone()
    conn.close()
    
    if payment:
        return jsonify({
            'id': payment[0], 'order_id': payment[1], 'amount': payment[2],
            'status': payment[3], 'payment_method': payment[4], 
            'transaction_id': payment[5], 'created_at': payment[6]
        }), 200
    return jsonify({'message': 'Payment not found'}), 404

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'payment-service'}), 200

if __name__ == '__main__':
    # Start RabbitMQ consumer in separate thread
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5004, debug=True)
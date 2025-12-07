"""
Notification Service - Sends notifications based on events
Port: 5006
"""
from flask import Flask, jsonify
from flask_cors import CORS
import sqlite3
import pika
import json
import time
import threading

app = Flask(__name__)
CORS(app)

RABBITMQ_HOST = 'rabbitmq'
RABBITMQ_PORT = 5672

def init_db():
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  customer_id INTEGER NOT NULL,
                  order_id INTEGER,
                  type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  status TEXT DEFAULT 'sent',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def send_notification(customer_id, order_id, notification_type, message):
    """Send notification (email/SMS) - simulated"""
    print(f"\n{'='*60}")
    print(f"NOTIFICATION SENT")
    print(f"To Customer: {customer_id}")
    print(f"Order ID: {order_id}")
    print(f"Type: {notification_type}")
    print(f"Message: {message}")
    print(f"{'='*60}\n")
    
    # Save notification to database
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('''INSERT INTO notifications (customer_id, order_id, type, message)
                 VALUES (?, ?, ?, ?)''',
              (customer_id, order_id, notification_type, message))
    conn.commit()
    conn.close()

def callback(ch, method, properties, body):
    """RabbitMQ message callback - listens to all order-related events"""
    try:
        message = json.loads(body)
        event_type = message.get('event')
        data = message.get('data')
        
        print(f"Notification Service received event: {event_type}")
        
        customer_id = data.get('customer_id')
        order_id = data.get('order_id')
        
        # Handle different event types
        if event_type == 'order.created':
            send_notification(
                customer_id, order_id, 'order_confirmation',
                f"Your order #{order_id} has been created successfully. Total: ${data.get('total_price')}"
            )
        
        elif event_type == 'payment.completed':
            send_notification(
                customer_id, order_id, 'payment_confirmation',
                f"Payment for order #{order_id} has been processed successfully. Amount: ${data.get('amount')}"
            )
        
        elif event_type == 'shipment.created':
            send_notification(
                customer_id, order_id, 'shipment_notification',
                f"Your order #{order_id} has been shipped! Tracking number: {data.get('tracking_number')}"
            )
        
        elif event_type == 'order.status.updated':
            send_notification(
                customer_id, order_id, 'status_update',
                f"Order #{order_id} status updated to: {data.get('status')}"
            )
        
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
            result = channel.queue_declare(queue='notification_queue', durable=True)
            queue_name = result.method.queue
            
            # Bind to multiple event types using wildcard
            channel.queue_bind(exchange='order_events', queue=queue_name, routing_key='order.*')
            channel.queue_bind(exchange='order_events', queue=queue_name, routing_key='payment.*')
            channel.queue_bind(exchange='order_events', queue=queue_name, routing_key='shipment.*')
            
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            
            print('Notification Service: Waiting for events...')
            channel.start_consuming()
        except Exception as e:
            print(f"Consumer error: {str(e)}")
            time.sleep(5)

# API endpoints
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    # Authorization is handled by Gateway
    # Get user context
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role')
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    # Customers see only their notifications
    if user_role == 'customer':
        c.execute('SELECT * FROM notifications WHERE customer_id = ? ORDER BY created_at DESC', 
                  (user_id,))
    else:
        c.execute('SELECT * FROM notifications ORDER BY created_at DESC')
    
    notifications = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': n[0], 'customer_id': n[1], 'order_id': n[2],
        'type': n[3], 'message': n[4], 'status': n[5], 'created_at': n[6]
    } for n in notifications]), 200

@app.route('/api/notifications/customer/<int:customer_id>', methods=['GET'])
def get_customer_notifications(customer_id):
    # Authorization is handled by Gateway
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('SELECT * FROM notifications WHERE customer_id = ? ORDER BY created_at DESC', 
              (customer_id,))
    notifications = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': n[0], 'customer_id': n[1], 'order_id': n[2],
        'type': n[3], 'message': n[4], 'status': n[5], 'created_at': n[6]
    } for n in notifications]), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'notification-service'}), 200

if __name__ == '__main__':
    # Start RabbitMQ consumer in separate thread
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5006, debug=True)
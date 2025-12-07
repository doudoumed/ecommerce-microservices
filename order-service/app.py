"""
Order Service - Orchestrates order creation and tracking
Port: 5003
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import jwt
from functools import wraps
import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests.exceptions

import pika
import json

app = Flask(__name__)
CORS(app)

# Circuit Breaker Configuration
payment_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,  # 50% failure rate approximation (simplified for pybreaker)
    reset_timeout=30
)

# Retry Configuration
retry_strategy = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout, requests.exceptions.ConnectionError))
)

def init_db():
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  customer_id INTEGER NOT NULL,
                  product_id INTEGER NOT NULL,
                  quantity INTEGER NOT NULL,
                  total_price REAL NOT NULL,
                  status TEXT NOT NULL,
                  payment_status TEXT DEFAULT 'pending',
                  shipping_status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

def publish_event(event_type, data):
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
        channel = connection.channel()
        channel.exchange_declare(exchange='order_events', exchange_type='topic', durable=True)
        
        event = {
            'event': event_type,
            'data': data
        }
        
        channel.basic_publish(
            exchange='order_events',
            routing_key=event_type,
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
    except Exception as e:
        print(f"Failed to publish event: {e}")

@retry_strategy
def check_customer(customer_id):
    response = requests.get(f'http://customer-service:5001/api/customers/{customer_id}', timeout=3)
    response.raise_for_status()
    return response

@retry_strategy
def check_inventory(product_id, quantity):
    response = requests.post(
        'http://inventory-service:5002/api/products/check-availability',
        json={'product_id': product_id, 'quantity': quantity},
        timeout=3
    )
    response.raise_for_status()
    return response.json()

@retry_strategy
def get_product_price(product_id):
    response = requests.get(f'http://inventory-service:5002/api/products/{product_id}', timeout=3)
    response.raise_for_status()
    return response.json()

@retry_strategy
def reserve_product(product_id, quantity):
    response = requests.post(
        'http://inventory-service:5002/api/products/reserve',
        json={'product_id': product_id, 'quantity': quantity},
        timeout=3
    )
    response.raise_for_status()
    return response

# Create order (orchestration)
@app.route('/api/orders', methods=['POST'])
def create_order():
    # Get user context from Gateway headers
    customer_id = request.headers.get('X-User-Id')
    
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    
    # Step 1: Verify customer exists (synchronous call to Customer Service)
    try:
        check_customer(customer_id)
    except Exception as e:
        return jsonify({'message': 'Customer service unavailable', 'error': str(e)}), 503
    
    # Step 2: Check product availability (synchronous call to Inventory Service)
    try:
        availability = check_inventory(product_id, quantity)
        if not availability.get('available'):
            return jsonify({'message': 'Product not available in requested quantity'}), 400
    except Exception as e:
        return jsonify({'message': 'Inventory service unavailable', 'error': str(e)}), 503
    
    # Step 3: Get product price
    try:
        product = get_product_price(product_id)
        total_price = product['price'] * quantity
    except Exception as e:
        return jsonify({'message': 'Cannot calculate price', 'error': str(e)}), 503
    
    # Step 4: Reserve product (reduce inventory)
    try:
        reserve_product(product_id, quantity)
    except Exception as e:
        return jsonify({'message': 'Cannot reserve product', 'error': str(e)}), 503
    
    # Step 5: Create order in database
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('''INSERT INTO orders (customer_id, product_id, quantity, total_price, status)
                 VALUES (?, ?, ?, ?, ?)''',
              (customer_id, product_id, quantity, total_price, 'pending'))
    conn.commit()
    order_id = c.lastrowid
    conn.close()
    
    # Step 6: Process Payment (Circuit Breaker Pattern)
    payment_successful = False
    try:
        # Define the synchronous payment call
        @payment_circuit_breaker
        def call_payment_service():
            resp = requests.post(
                'http://payment-service:5004/api/payments/process',
                json={
                    'order_id': order_id,
                    'total_price': total_price,
                    'customer_id': customer_id
                },
                timeout=5
            )
            resp.raise_for_status()
            return resp
            
        call_payment_service()
        payment_successful = True
        
    except pybreaker.CircuitBreakerError:
        print("Circuit Breaker OPEN: Payment Service is down. Fallback to async processing.")
    except Exception as e:
        print(f"Payment Service call failed: {str(e)}. Fallback to async processing.")
    
    # Step 7: Fallback / Async Processing
    # If synchronous payment failed (or CB open), we publish the event for later processing
    if not payment_successful:
        order_data = {
            'order_id': order_id,
            'customer_id': customer_id,
            'product_id': product_id,
            'quantity': quantity,
            'total_price': total_price
        }
        publish_event('order.created', order_data)
        message = f'Order created. Payment processing queued (Fallback). Order ID: {order_id}'
    else:
        message = 'Order created and payment processed successfully.'
    
    return jsonify({
        'message': message,
        'order_id': order_id,
        'total_price': total_price,
        'payment_status': 'completed' if payment_successful else 'pending'
    }), 201

# Get all orders
@app.route('/api/orders', methods=['GET'])
def get_orders():
    # Get user context from Gateway headers
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role')
    
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # Customers see only their orders, admin/staff see all
    if user_role == 'customer':
        c.execute('SELECT * FROM orders WHERE customer_id = ?', (user_id,))
    else:
        c.execute('SELECT * FROM orders')
    
    orders = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': o[0], 'customer_id': o[1], 'product_id': o[2],
        'quantity': o[3], 'total_price': o[4], 'status': o[5],
        'payment_status': o[6], 'shipping_status': o[7], 'created_at': o[8]
    } for o in orders]), 200

# Get single order
@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    # Get user context from Gateway headers
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role')
    
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    order = c.fetchone()
    conn.close()
    
    if not order:
        return jsonify({'message': 'Order not found'}), 404
    
    # Check authorization - customers only see their orders
    if user_role == 'customer' and str(order[1]) != str(user_id):
        return jsonify({'message': 'Unauthorized'}), 403
    
    return jsonify({
        'id': order[0], 'customer_id': order[1], 'product_id': order[2],
        'quantity': order[3], 'total_price': order[4], 'status': order[5],
        'payment_status': order[6], 'shipping_status': order[7], 'created_at': order[8]
    }), 200

# Update order status (for staff/admin)
@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    # Authorization is handled by Gateway
    data = request.json
    status = data.get('status')
    
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    conn.commit()
    conn.close()
    
    # Publish status update event
    publish_event('order.status.updated', {'order_id': order_id, 'status': status})
    
    return jsonify({'message': 'Order status updated'}), 200

# Internal endpoint to update payment status (called by Payment Service)
@app.route('/api/orders/<int:order_id>/payment-status', methods=['PUT'])
def update_payment_status(order_id):
    data = request.json
    payment_status = data.get('payment_status')
    
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('UPDATE orders SET payment_status = ? WHERE id = ?', (payment_status, order_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Payment status updated'}), 200

# Internal endpoint to update shipping status (called by Shipping Service)
@app.route('/api/orders/<int:order_id>/shipping-status', methods=['PUT'])
def update_shipping_status(order_id):
    data = request.json
    shipping_status = data.get('shipping_status')
    
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    c.execute('UPDATE orders SET shipping_status = ? WHERE id = ?', (shipping_status, order_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Shipping status updated'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'order-service'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
"""
Customer Service - Manages customer information
Port: 5001
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import jwt
import datetime
from functools import wraps
import hashlib

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
        'service': 'customer-service',
        'correlation_id': g.correlation_id,
        'method': request.method,
        'path': request.path
    })

CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Database initialization
def init_db():
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  phone TEXT,
                  address TEXT,
                  role TEXT DEFAULT 'customer',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# JWT Token verification decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            request.user = data
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(*args, **kwargs)
    return decorated

# Authentication endpoints
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    
    # Hash password
    hashed_password = hashlib.sha256(data['password'].encode()).hexdigest()
    
    try:
        c.execute('''INSERT INTO customers (name, email, password, phone, address, role)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (data['name'], data['email'], hashed_password, 
                   data.get('phone'), data.get('address'), data.get('role', 'customer')))
        conn.commit()
        customer_id = c.lastrowid
        conn.close()
        return jsonify({'message': 'Customer registered successfully', 'id': customer_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Email already exists'}), 400

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    
    hashed_password = hashlib.sha256(data['password'].encode()).hexdigest()
    c.execute('SELECT * FROM customers WHERE email = ? AND password = ?', 
              (data['email'], hashed_password))
    customer = c.fetchone()
    conn.close()
    
    if customer:
        token = jwt.encode({
            'user_id': customer[0],
            'email': customer[2],
            'role': customer[6],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'token': token,
            'user': {
                'id': customer[0],
                'name': customer[1],
                'email': customer[2],
                'role': customer[6]
            }
        }), 200
    return jsonify({'message': 'Invalid credentials'}), 401

# Customer CRUD operations
@app.route('/api/customers', methods=['GET'])
def get_customers():
    # Authorization is handled by Gateway (only admin can reach here)
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email, phone, address, role, created_at FROM customers')
    customers = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': c[0], 'name': c[1], 'email': c[2], 
        'phone': c[3], 'address': c[4], 'role': c[5], 'created_at': c[6]
    } for c in customers]), 200

@app.route('/api/customers/<int:customer_id>', methods=['GET'])
def get_customer(customer_id):
    # Authorization is handled by Gateway
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('SELECT id, name, email, phone, address, role, created_at FROM customers WHERE id = ?', 
              (customer_id,))
    customer = c.fetchone()
    conn.close()
    
    if customer:
        return jsonify({
            'id': customer[0], 'name': customer[1], 'email': customer[2],
            'phone': customer[3], 'address': customer[4], 'role': customer[5], 
            'created_at': customer[6]
        }), 200
    return jsonify({'message': 'Customer not found'}), 404

@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    # Authorization is handled by Gateway
    data = request.json
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('''UPDATE customers SET name = ?, phone = ?, address = ?
                 WHERE id = ?''',
              (data['name'], data.get('phone'), data.get('address'), customer_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Customer updated successfully'}), 200

@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    # Authorization is handled by Gateway (only admin can reach here)
    conn = sqlite3.connect('customers.db')
    c = conn.cursor()
    c.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Customer deleted successfully'}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'customer-service'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
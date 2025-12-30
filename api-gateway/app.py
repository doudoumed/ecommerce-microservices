"""
API Gateway - Single Entry Point with JWT Validation & RBAC
Port: 8080
"""
from flask import Flask, request, jsonify, Response
from flask import Flask, request, jsonify, Response, g
from flask_cors import CORS
import jwt
import requests
from functools import wraps
import time
import logging
from pythonjsonlogger import jsonlogger
import uuid
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

@app.route('/test')
def test_route():
    return "OK", 200
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

# Service URLs
SERVICES = {
    'customer': 'http://customer-service:5001',
    'inventory': 'http://inventory-service:5002',
    'order': 'http://order-service:5003',
    'payment': 'http://payment-service:5004',
    'shipping': 'http://shipping-service:5005',
    'notification': 'http://notification-service:5006'
}

# RBAC Configuration - Define permissions for each role
ROLE_PERMISSIONS = {
    'admin': {
        'customers': ['GET', 'POST', 'PUT', 'DELETE'],
        'products': ['GET', 'POST', 'PUT', 'DELETE'],
        'orders': ['GET', 'POST', 'PUT', 'DELETE'],
        'payments': ['GET'],
        'shipments': ['GET'],
        'notifications': ['GET']
    },
    'staff': {
        'customers': ['GET'],
        'products': ['GET', 'POST', 'PUT'],
        'orders': ['GET', 'PUT'],
        'payments': ['GET'],
        'shipments': ['GET'],
        'notifications': ['GET']
    },
    'customer': {
        'customers': ['GET', 'PUT'],  # Own data only
        'products': ['GET'],
        'orders': ['GET', 'POST'],  # Own orders only
        'payments': ['GET'],  # Own payments only
        'shipments': ['GET'],  # Own shipments only
        'notifications': ['GET']  # Own notifications only
    }
}

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ... (imports)



# Rate Limiter Configuration
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per 15 minutes"],
    storage_uri="memory://"
)

# ... (SERVICES, ROLE_PERMISSIONS)

# Helper to handle 429 errors
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': f'Rate limit exceeded: {e.description}'}), 429

def extract_token():
    """Extract JWT token from request"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    
    try:
        token = auth_header.replace('Bearer ', '')
        return token
    except:
        return None

def verify_token(token):
    """Verify JWT token and return decoded data"""
    try:
        decoded = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def check_permission(user_role, resource, method, user_id=None, resource_id=None):
    """Check if user role has permission for the resource and method"""
    # Check if role exists
    if user_role not in ROLE_PERMISSIONS:
        return False
    
    # Check if resource is allowed for this role
    if resource not in ROLE_PERMISSIONS[user_role]:
        return False
    
    # Check if method is allowed
    if method not in ROLE_PERMISSIONS[user_role][resource]:
        return False
    
    # Special check for customer role - only own resources
    if user_role == 'customer':
        # For customer-specific resources
        if resource == 'customers' and resource_id and str(resource_id) != str(user_id):
            return False
    
    return True

def proxy_request(service_url, path, method, headers, data=None, params=None):
    """Forward request to microservice"""
    url = f"{service_url}{path}"
    
    # Ensure Correlation ID
    correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())
    
    try:
        # Remove hop-by-hop headers
        headers_to_forward = {k: v for k, v in headers.items() 
                              if k.lower() not in ['host', 'connection']}
        
        # Add Correlation ID to downstream headers
        headers_to_forward['X-Correlation-ID'] = correlation_id
        
        logger.info(f"Proxying request to {url}", extra={
            'method': method,
            'service_url': url,
            'correlation_id': correlation_id
        })
        
        if method == 'GET':
            response = requests.get(url, headers=headers_to_forward, params=params, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers_to_forward, json=data, timeout=10)
        elif method == 'PUT':
            response = requests.put(url, headers=headers_to_forward, json=data, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers_to_forward, timeout=10)
        else:
            return jsonify({'error': 'Method not allowed'}), 405
        
        # Return response from microservice
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    except requests.exceptions.Timeout:
        logger.error(f"Service timeout: {url}", extra={'correlation_id': correlation_id})
        return jsonify({'error': 'Service timeout'}), 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Service unavailable: {url}", extra={'correlation_id': correlation_id})
        return jsonify({'error': 'Service unavailable'}), 503
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}", extra={'correlation_id': correlation_id, 'stack': str(e)})
        return jsonify({'error': str(e)}), 500

# Remove manual rate limiting middleware and check_rate_limit function
# @app.before_request is no longer needed for rate limiting, but we keep logging

@app.before_request
def before_request():
    """Access logging"""
    client_ip = request.remote_addr
    logger.info(f"Incoming request: {request.method} {request.path}", extra={'client_ip': client_ip})

# Apply specific limits to critical endpoints

# Order Service routes
@app.route('/api/orders', methods=['GET', 'POST'])
@app.route('/api/orders/<int:order_id>', methods=['GET', 'PUT', 'DELETE'])
@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@limiter.limit("50 per minute", methods=['POST'])  # Limit order creation
def orders_proxy(order_id=None):
    # Authentication required
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    # Check permissions
    if not check_permission(user['role'], 'orders', request.method):
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    # Add user context to headers for the service
    headers = dict(request.headers)
    headers['X-User-Id'] = str(user['user_id'])
    headers['X-User-Role'] = user['role']
    
    # Build path
    if '/status' in request.path:
        path = f"/api/orders/{order_id}/status"
    elif order_id:
        path = f"/api/orders/{order_id}"
    else:
        path = "/api/orders"
    
    return proxy_request(
        SERVICES['order'],
        path,
        request.method,
        headers,
        request.json
    )

# Payment Service routes
@app.route('/api/payments', methods=['GET'])
@app.route('/api/payments/<int:payment_id>', methods=['GET'])
@limiter.limit("5 per minute", methods=['POST'])
def payments_proxy(payment_id=None):
    # Authentication required
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    # Check permissions
    if not check_permission(user['role'], 'payments', request.method):
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    # Add user context
    headers = dict(request.headers)
    headers['X-User-Id'] = str(user['user_id'])
    headers['X-User-Role'] = user['role']
    
    path = f"/api/payments/{payment_id}" if payment_id else "/api/payments"
    return proxy_request(
        SERVICES['payment'],
        path,
        request.method,
        headers
    )

# Health check
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'api-gateway'}), 200

# Authentication endpoints (no JWT required)
@app.route('/auth/register', methods=['POST'])
def register():
    return proxy_request(
        SERVICES['customer'],
        '/auth/register',
        'POST',
        request.headers,
        request.json
    )

@app.route('/auth/login', methods=['POST'])
def login():
    return proxy_request(
        SERVICES['customer'],
        '/auth/login',
        'POST',
        request.headers,
        request.json
    )

# Customer Service routes
@app.route('/api/customers', methods=['GET', 'POST'])
@app.route('/api/customers/<int:customer_id>', methods=['GET', 'PUT', 'DELETE'])
def customers_proxy(customer_id=None):
    # 1. استخراج وتحقق التوكن
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    user_role = user['role']
    user_id = user['user_id']
    method = request.method
    
    # 2. تطبيق منطق التوجيه والتحقق من النطاق (Scoping Logic)

    # التحقق من الإذن العام أولاً (باستخدام القاموس ROLE_PERMISSIONS)
    # ملاحظة: دالة check_permission يجب أن تقبل customer_id و user_id في الحالات الأخرى
    if not check_permission(user_role, 'customers', method, user_id, customer_id):
        return jsonify({'error': 'Insufficient permissions (RBAC)'}), 403

    # منطق التوجيه: إذا كان GET على القائمة العامة (بدون ID)
    if method == 'GET' and customer_id is None:
        # إذا لم يكن المستخدم مديراً (admin)، قم بتوجيهه داخلياً إلى مورده الخاص
        if user_role != 'admin':
            # ⬅️ هذا هو التغيير الرئيسي: إعادة توجيه الطلب داخلياً إلى /api/customers/user_id
            customer_id = user_id 
            logger.warning(f"Non-admin role '{user_role}' accessing list endpoint. Coercing request to self-access: ID {customer_id}", extra={'correlation_id': request.headers.get('X-Correlation-ID')})

    # منطق النطاق (للتأكد من عدم وصول العميل إلى بيانات شخص آخر عبر /api/customers/{id})
    if method in ['GET', 'PUT', 'DELETE'] and customer_id is not None:
        # إذا كان عميلاً ويحاول الوصول إلى ID مختلف عن ID التوكن
        if user_role == 'customer' and int(customer_id) != int(user_id):
            return jsonify({'error': 'Access denied: Customer can only access self data'}), 403

    # 3. تمرير الطلب إلى الخدمة المصغرة
    path = f"/api/customers/{customer_id}" if customer_id else "/api/customers"

    # نضمن إرسال هوية المستخدم ودوره للخدمة المصغرة
    forward_headers = dict(request.headers)
    forward_headers['X-User-ID'] = str(user_id)
    forward_headers['X-User-Role'] = user_role
    
    return proxy_request(
        SERVICES['customer'],
        path,
        method,
        forward_headers,
        request.json
    )


# Inventory/Products Service routes
@app.route('/api/products', methods=['GET', 'POST'])
@app.route('/api/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
def products_proxy(product_id=None):
    # GET products is public (no token required)
    if request.method == 'GET':
        path = f"/api/products/{product_id}" if product_id else "/api/products"
        return proxy_request(
            SERVICES['inventory'],
            path,
            request.method,
            request.headers
        )
    
    # Other methods require authentication
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    # Check permissions
    if not check_permission(user['role'], 'products', request.method):
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    path = f"/api/products/{product_id}" if product_id else "/api/products"
    return proxy_request(
        SERVICES['inventory'],
        path,
        request.method,
        request.headers,
        request.json
    )



# Shipping Service routes
@app.route('/api/shipments', methods=['GET'])
@app.route('/api/shipments/<int:shipment_id>', methods=['GET'])
@app.route('/api/shipments/track/<tracking_number>', methods=['GET'])
def shipments_proxy(shipment_id=None, tracking_number=None):
    # Authentication required
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    # Check permissions
    if not check_permission(user['role'], 'shipments', request.method):
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    # Add user context
    headers = dict(request.headers)
    headers['X-User-Id'] = str(user['user_id'])
    headers['X-User-Role'] = user['role']
    
    # Build path
    if tracking_number:
        path = f"/api/shipments/track/{tracking_number}"
    elif shipment_id:
        path = f"/api/shipments/{shipment_id}"
    else:
        path = "/api/shipments"
    
    return proxy_request(
        SERVICES['shipping'],
        path,
        request.method,
        headers
    )

# Notification Service routes
@app.route('/api/notifications', methods=['GET'])
@app.route('/api/notifications/customer/<int:customer_id>', methods=['GET'])
def notifications_proxy(customer_id=None):
    # Authentication required
    token = extract_token()
    if not token:
        return jsonify({'error': 'Token required'}), 401
    
    user = verify_token(token)
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 401
    
    # Check permissions
    if not check_permission(user['role'], 'notifications', request.method):
        return jsonify({'error': 'Insufficient permissions'}), 403
    
    # Customers can only see their own notifications
    if user['role'] == 'customer' and customer_id and customer_id != user['user_id']:
        return jsonify({'error': 'Cannot access other customer notifications'}), 403
    
    # Add user context
    headers = dict(request.headers)
    headers['X-User-Id'] = str(user['user_id'])
    headers['X-User-Role'] = user['role']
    
    path = f"/api/notifications/customer/{customer_id}" if customer_id else "/api/notifications"
    return proxy_request(
        SERVICES['notification'],
        path,
        request.method,
        headers
    )

# 404 handler
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Route not found'}), 404

if __name__ == '__main__':
    print(app.url_map)
    app.run(host='0.0.0.0', port=8080, debug=True)
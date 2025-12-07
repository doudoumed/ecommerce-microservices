"""
Inventory Service - Manages product stock
Port: 5002
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'

def init_db():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  description TEXT,
                  price REAL NOT NULL,
                  quantity INTEGER NOT NULL,
                  sku TEXT UNIQUE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Insert sample products
    c.execute('SELECT COUNT(*) FROM products')
    if c.fetchone()[0] == 0:
        sample_products = [
            ('Laptop', 'High-performance laptop', 1200.00, 50, 'LAP001'),
            ('Mouse', 'Wireless mouse', 25.00, 200, 'MOU001'),
            ('Keyboard', 'Mechanical keyboard', 80.00, 150, 'KEY001'),
            ('Monitor', '27-inch 4K monitor', 350.00, 75, 'MON001'),
            ('Headphones', 'Noise-cancelling headphones', 150.00, 100, 'HEA001')
        ]
        c.executemany('INSERT INTO products (name, description, price, quantity, sku) VALUES (?, ?, ?, ?, ?)', 
                      sample_products)
    
    conn.commit()
    conn.close()

init_db()

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

# Product CRUD operations
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT * FROM products')
    products = c.fetchall()
    conn.close()
    
    return jsonify([{
        'id': p[0], 'name': p[1], 'description': p[2],
        'price': p[3], 'quantity': p[4], 'sku': p[5], 'created_at': p[6]
    } for p in products]), 200

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    product = c.fetchone()
    conn.close()
    
    if product:
        return jsonify({
            'id': product[0], 'name': product[1], 'description': product[2],
            'price': product[3], 'quantity': product[4], 'sku': product[5], 
            'created_at': product[6]
        }), 200
    return jsonify({'message': 'Product not found'}), 404

@app.route('/api/products', methods=['POST'])
def create_product():
    # Authorization is handled by Gateway (only admin/staff can reach here)
    data = request.json
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO products (name, description, price, quantity, sku)
                     VALUES (?, ?, ?, ?, ?)''',
                  (data['name'], data.get('description'), data['price'], 
                   data['quantity'], data.get('sku')))
        conn.commit()
        product_id = c.lastrowid
        conn.close()
        return jsonify({'message': 'Product created successfully', 'id': product_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({'message': 'SKU already exists'}), 400

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    # Authorization is handled by Gateway (only admin/staff can reach here)
    data = request.json
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('''UPDATE products SET name = ?, description = ?, price = ?, quantity = ?
                 WHERE id = ?''',
              (data['name'], data.get('description'), data['price'], 
               data['quantity'], product_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Product updated successfully'}), 200

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    # Authorization is handled by Gateway (only admin can reach here)
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Product deleted successfully'}), 200

# Check product availability (internal API for Order Service)
@app.route('/api/products/check-availability', methods=['POST'])
def check_availability():
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT quantity FROM products WHERE id = ?', (product_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] >= quantity:
        return jsonify({'available': True, 'current_quantity': result[0]}), 200
    return jsonify({'available': False, 'current_quantity': result[0] if result else 0}), 200

# Reserve product quantity (reduce stock)
@app.route('/api/products/reserve', methods=['POST'])
def reserve_product():
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity')
    
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT quantity FROM products WHERE id = ?', (product_id,))
    result = c.fetchone()
    
    if result and result[0] >= quantity:
        new_quantity = result[0] - quantity
        c.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, product_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Product reserved', 'new_quantity': new_quantity}), 200
    
    conn.close()
    return jsonify({'success': False, 'message': 'Insufficient stock'}), 400

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'inventory-service'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
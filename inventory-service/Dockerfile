# Use this Dockerfile in each service directory
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite databases
RUN mkdir -p /app/data

# Expose service port (change based on service)
# Customer: 5001, Inventory: 5002, Order: 5003, Payment: 5004, Shipping: 5005, Notification: 5006
EXPOSE 5002

# Run the application
CMD ["python", "app.py"]
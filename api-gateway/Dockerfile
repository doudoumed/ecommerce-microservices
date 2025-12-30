# Dockerfile for API Gateway
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

# Copy application code
COPY app.py .

# Expose gateway port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]
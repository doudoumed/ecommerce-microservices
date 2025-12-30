# Phase 6: Observability - Structured Logging Implementation Report

This document details the changes made to implement **Structured Logging** and **Distributed Tracing (Correlation IDs)** across the E-commerce Microservices architecture.

## 1. Implementation Details

### Goal
To transition from unstructured console logs (`print`) to structured JSON logs that can be easily parsed by log management systems (like ELK stack). Additionally, to trace a single user request across multiple microservices using a unique `Correlation ID`.

### Changes Made

#### A. Dependencies
- Added `python-json-logger==2.0.7` to `requirements.txt` for all services:
  - `api-gateway`
  - `order-service`
  - `payment-service`
  - `inventory-service`
  - `customer-service`
  - `shipping-service`
  - `notification-service`

#### B. API Gateway (`api-gateway/app.py`)
- **JSON Logger:** Configured to output logs in JSON format with timestamps and log levels.
- **Correlation ID Generation:**
  - Checks for `X-Correlation-ID` header in incoming requests.
  - If missing, generates a new UUID.
- **Propagation:** Passes the `X-Correlation-ID` header to all downstream services via `proxy_request`.
- **Logging:** Logs all incoming requests and proxy actions with the `correlation_id` field.

#### C. Microservices (All Services)
- **JSON Logger:** Configured identical to the Gateway.
- **Correlation ID Extraction:**
  - Middleware (`before_request`) extracts `X-Correlation-ID` from headers.
  - Stores it in Flask's global `g` object (`g.correlation_id`).
- **Propagation:** Helper function `get_headers()` injects the ID into any outgoing HTTP calls (e.g., Order -> Payment).
- **Logging:** All `print()` statements replaced with `logger.info()` or `logger.error()`, including `extra={'correlation_id': ...}` context.

---

## 2. Verification & Testing

### Prerequisites
Ensure the Docker containers are rebuilt and running with the latest changes:
```bash
sudo docker compose up --build -d
```

### Test Scenario: Create an Order
We will trace a request from the Gateway -> Order Service -> Inventory Service -> Payment Service -> Notification Service.

#### Step 0: Register Admin User (One-time setup)
```bash
curl -X POST http://localhost:8080/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Admin User", "email": "admin@example.com", "password": "admin", "role": "admin"}'
```

#### Step 1: Login (Get Token)
```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin"}'
```

*Copy the `token` from the response.*

#### Step 2: Create Order
Replace `YOUR_TOKEN` with the actual token.
```bash
curl -X POST http://localhost:8080/api/orders \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 2, "quantity": 1}'
```

### Step 3: Verify Logs
Check the logs for each service to see the JSON structure and the matching `correlation_id`.

**1. API Gateway Logs:**
```bash
sudo docker compose logs --tail=20 api-gateway
```
*Look for:* `{"message": "Proxying request...", "correlation_id": "abc-123...", ...}`

**2. Order Service Logs:**
```bash
sudo docker compose logs --tail=20 order-service
```
*Look for:* `{"message": "Request received...", "correlation_id": "abc-123...", ...}`
*Look for:* `{"message": "Checking inventory...", "correlation_id": "abc-123...", ...}`

**3. Payment Service Logs:**
```bash
sudo docker compose logs --tail=20 payment-service
```
*Look for:* `{"message": "Processing payment...", "correlation_id": "abc-123...", ...}`

**4. Notification Service Logs:**
```bash
sudo docker compose logs --tail=20 notification-service
```
*Look for:* `{"message": "Notification Service received event...", "correlation_id": "abc-123...", ...}`

### Expected Result
You should see that **all logs** related to this single order creation share the **same** `correlation_id` (UUID), proving that distributed tracing is working correctly. The logs should also be in valid JSON format.

---

## 3. Testing ELK Stack & Prometheus

Once the services are running, you can access the observability tools in your browser.

### A. ELK Stack (Centralized Logging)

1.  **Access Kibana:** Open [http://localhost:5601](http://localhost:5601) in your browser.
2.  **Create Index Pattern:**
    *   Go to **Stack Management** > **Index Patterns**.
    *   Click **Create index pattern**.
    *   Enter `microservices-logs-*` as the pattern name.
    *   Select `@timestamp` as the Time field.
    *   Click **Create index pattern**.
3.  **View Logs:**
    *   Go to **Discover** (Compass icon).
    *   You should see logs from all services streaming in.
4.  **Trace a Request:**
    *   Copy a `correlation_id` from your terminal logs (or from a log entry in Kibana).
    *   In the search bar, type: `correlation_id: "YOUR_UUID_HERE"`.
    *   You will see the full journey of that request across all microservices.

### B. Prometheus & Grafana (Metrics)

1.  **Access Prometheus:** Open [http://localhost:9091](http://localhost:9091).
    *   Click **Status** > **Targets** to verify all microservices are being scraped (UP state).
    *   In the search bar, type `flask_http_request_total` and click **Execute** to see request counts.

2.  **Access Grafana:** Open [http://localhost:3000](http://localhost:3000).
    *   **Login:** Default user/pass is `admin` / `admin`.
    *   **Add Data Source:**
        *   Go to **Configuration** (Gear icon) > **Data Sources**.
        *   Click **Add data source** > Select **Prometheus**.
        *   URL: `http://prometheus:9090`.
        *   Click **Save & Test**.
    *   **Create Dashboard:**
        *   Click **Create** (+) > **Dashboard**.
        *   Add a panel and query `rate(flask_http_request_total[1m])` to see requests per second.

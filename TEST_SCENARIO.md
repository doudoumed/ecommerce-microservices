# Observability Test Scenario

Follow this guide to verify that Logging, Tracing, and Metrics are working correctly.

## Prerequisites
Ensure all services are running:
```bash
sudo docker compose up --build -d
```

---

## Scenario 1: The "Happy Path" (Successful Order)

**Goal:** Verify that a request is traced across 4 services.

### 1. Generate Traffic
Run these commands in your terminal:

```bash
# 1. Login to get a token
TOKEN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin"}' | jq -r .token)

# 2. Create an Order (Product ID 2 exists)
curl -v -X POST http://localhost:8080/api/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 2, "quantity": 1}'
```

### 2. Verify in Kibana (Logs & Tracing)
1.  Open [http://localhost:5601](http://localhost:5601).
2.  Go to **Discover**.
3.  In the search bar, enter: `message: "Proxying request"`
4.  Expand the latest log from `api-gateway`.
5.  Find the `correlation_id` field (e.g., `abc-123...`).
6.  **Filter by this ID:** Click the `+` magnifying glass next to the `correlation_id`.
7.  **Result:** You should see logs from **Gateway**, **Order**, **Inventory**, and **Payment** services, all grouped together.

### 3. Verify in Grafana (Metrics)
1.  Open [http://localhost:3000](http://localhost:3000) (admin/admin).
2.  Go to **Explore**.
3.  Select **Prometheus** as the data source.
4.  Enter query: `flask_http_request_total{status="201"}`
5.  **Result:** You should see the counter increase for the `order-service`.

---

## Scenario 2: The "Failure Path" (Error Handling)

**Goal:** Verify that errors are logged and metrics capture the failure.

### 1. Generate Error
Try to order a non-existent product (ID 999):

```bash
curl -v -X POST http://localhost:8080/api/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 999, "quantity": 1}'
```

### 2. Verify in Kibana
1.  Search for `level: ERROR` or `status: 404`.
2.  You should see an error log from `inventory-service` saying "Product not found".
3.  The `correlation_id` will still link the Gateway's request to the Inventory's error.

### 3. Verify in Grafana
1.  Query: `flask_http_request_total{status="404"}`
2.  **Result:** You should see a spike in 404 errors.

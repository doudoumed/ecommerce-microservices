# Observability Stack Guide: ELK & Prometheus

This guide explains the tools we are adding to the E-commerce Microservices project and how to use them.

## 1. ELK Stack (Logging)

The **ELK Stack** is used for **Centralized Logging**. Instead of checking logs container-by-container, all logs are collected in one place.

### Components
*   **Elasticsearch:** The database that stores the logs. It allows for fast searching.
*   **Logstash:** The pipeline that receives logs from our microservices, processes them (e.g., parses JSON), and sends them to Elasticsearch.
*   **Kibana:** The web interface (UI) where you visualize and search the logs.

### How We Will Use It
1.  **Sending Logs:** We will configure our Docker containers to send logs to Logstash (using the `gelf` driver or TCP).
2.  **Viewing Logs:** You will open Kibana in your browser (e.g., `http://localhost:5601`).
3.  **Searching:** You can search for a specific `Correlation ID` (e.g., `correlation_id: "abc-123"`) to see all logs related to a specific order across *all* services (Gateway -> Order -> Payment).
4.  **Debugging:** If an order fails, you can filter by `level: "ERROR"` to instantly find the failing service.

---

## 2. Prometheus & Grafana (Metrics)

**Prometheus** and **Grafana** are used for **Monitoring Metrics**. Logs tell you *what* happened; metrics tell you *how* the system is performing.

### Components
*   **Prometheus:** A time-series database that "scrapes" (collects) metrics from our services every few seconds.
*   **Grafana:** The dashboard tool that visualizes the data from Prometheus.

### How We Will Use It
1.  **Exposing Metrics:** We will add a `/metrics` endpoint to each microservice (using `prometheus-flask-exporter`). This endpoint shows data like:
    *   Number of requests per second.
    *   Average response time (latency).
    *   Number of HTTP 500 errors.
2.  **Scraping:** Prometheus will visit `http://order-service:5003/metrics` periodically to save this data.
3.  **Dashboards:** You will open Grafana (e.g., `http://localhost:3000`) to see charts like:
    *   "Orders Created per Minute"
    *   "API Gateway Latency"
    *   "System Error Rate"
4.  **Alerting:** We can set up rules (e.g., "If error rate > 5%, send an alert").

---

## Summary of Workflow

| Goal | Tool | Action |
| :--- | :--- | :--- |
| **"Why did this specific request fail?"** | **Kibana (ELK)** | Search by `Correlation ID` to see the error log. |
| **"Is the system slow right now?"** | **Grafana** | Check the "Latency" graph. |
| **"Are we getting many orders?"** | **Grafana** | Check the "Order Rate" graph. |

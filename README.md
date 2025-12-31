# E-Commerce Microservices System

A robust, scalable e-commerce backend built with **Python (Flask)**, **Docker**, **RabbitMQ**, and a full **Observability Stack (ELK + Prometheus/Grafana)**. This project demonstrates modern microservices patterns including event-driven architecture, circuit breakers, rate limiting, and distributed tracing.

## 🚀 Features

*   **Microservices Architecture**: 7 decoupled services (Gateway, Order, Payment, Inventory, Shipping, Notification, Customer).
*   **Event-Driven**: Asynchronous communication using **RabbitMQ**.
*   **Resilience**: Implements **Circuit Breaker** (PyBreaker) and **Rate Limiting**.
*   **Security**: **JWT** Authentication and Role-Based Access Control (**RBAC**).
*   **Observability**:
    *   **Centralized Logging**: Elasticsearch, Logstash, Kibana (ELK).
    *   **Metrics**: Prometheus and Grafana.
    *   **Distributed Tracing**: Correlation IDs propagated across all services.
*   **Containerization**: Fully Dockerized with `docker-compose`.

## 🛠️ Tech Stack

*   **Language**: Python 3.9
*   **Framework**: Flask
*   **Database**: SQLite (per service)
*   **Message Broker**: RabbitMQ
*   **Logging**: ELK Stack (Elasticsearch 7.17, Logstash, Kibana)
*   **Monitoring**: Prometheus, Grafana
*   **Orchestration**: Kubernetes (Minikube), Docker Compose
*   **Tools**: Docker, kubectl, Helm

## 🏗️ Architecture

The system consists of the following services:

1.  **API Gateway** (`:8080`): Entry point, Auth, Routing, Rate Limiting.
2.  **Customer Service** (`:5001`): User management & JWT issuance.
3.  **Inventory Service** (`:5002`): Product stock management.
4.  **Order Service** (`:5003`): Order placement & orchestration.
5.  **Payment Service** (`:5004`): Payment processing (simulated).
6.  **Shipping Service** (`:5005`): Delivery scheduling.
7.  **Notification Service** (`:5006`): User alerts (simulated).

## ☸️ Kubernetes Deployment (New!)

We have migrated to **Kubernetes** for production-grade orchestration.

### Key Features:
*   **Self-Healing**: Automatic restart of failed pods.
*   **Auto-Scaling (HPA)**: Scales services based on CPU usage.
*   **Ingress**: NGINX Ingress Controller for routing.
*   **Config Management**: Uses ConfigMaps and Secrets.

### Quick Start (K8s):
```bash
# 1. Start Minikube
minikube start --addons=ingress,metrics-server

# 2. Apply Manifests
kubectl apply -f k8s/namespaces.yaml
kubectl apply -f k8s/base/
kubectl apply -f k8s/infra/
kubectl apply -f k8s/services/

# 3. Verify
kubectl get pods -n ecommerce-services
```

## 📋 Prerequisites

*   Docker
*   Docker Compose
*   Minikube & kubectl (for K8s)

## 🚀 Getting Started

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <your-repo-url>
    cd ecommerce-microservices
    ```

2.  **Build and Start Services**:
    ```bash
    sudo docker compose up --build -d
    ```
    *Wait a few minutes for all services (especially Elasticsearch and RabbitMQ) to start.*

3.  **Verify Status**:
    ```bash
    sudo docker compose ps
    ```

## 🔍 Observability & Monitoring

| Tool | URL | Credentials (Default) |
| :--- | :--- | :--- |
| **API Gateway** | `http://localhost:8080` | - |
| **Kibana (Logs)** | `http://localhost:5601` | - |
| **Grafana (Metrics)** | `http://localhost:3000` | `admin` / `admin` |
| **Prometheus** | `http://localhost:9091` | - |
| **RabbitMQ UI** | `http://localhost:15672` | `guest` / `guest` |

### Key Metrics to Watch
*   **`flask_http_request_total`**: Total request count per service.
*   **`flask_http_request_duration_seconds`**: Latency distribution.

## 🧪 Testing

### 1. Run Automated Resilience Tests
We have a script to test Rate Limiting and Circuit Breakers:
```bash
python3 resilience_test.py
```

### 2. Manual API Testing
**Register a User:**
```bash
curl -X POST http://localhost:8080/auth/register \
     -H "Content-Type: application/json" \
     -d '{"name": "John Doe", "email": "john@example.com", "password": "password123", "role": "admin"}'
```

**Login (Get Token):**
```bash
curl -X POST http://localhost:8080/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "john@example.com", "password": "password123"}'
```

**Create Order:**
```bash
curl -X POST http://localhost:8080/api/orders \
     -H "Authorization: Bearer <YOUR_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"product_id": 1, "quantity": 1}'
```

## 📂 Project Structure

```
├── api-gateway/             # Gateway Service
├── customer-service/        # Customer Service
├── inventory-service/       # Inventory Service
├── order-service/           # Order Service
├── payment-service/         # Payment Service
├── shipping-service/        # Shipping Service
├── notification-service/    # Notification Service
├── logstash/                # Logstash Configuration
├── docker-compose.yml       # Orchestration
├── prometheus.yml           # Prometheus Config
└── resilience_test.py       # Test Script
```

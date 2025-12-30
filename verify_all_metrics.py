import requests

services = [
    ("api-gateway", 8080),
    ("customer-service", 5001),
    ("inventory-service", 5002),
    ("order-service", 5003),
    ("payment-service", 5004),
    ("shipping-service", 5005),
    ("notification-service", 5006)
]

print(f"{'Service':<20} | {'Port':<5} | {'Status':<10} | {'Metrics Found'}")
print("-" * 60)

for name, port in services:
    url = f"http://localhost:{port}/metrics"
    try:
        response = requests.get(url, timeout=2)
        status = response.status_code
        has_metrics = "flask_http_request_total" in response.text
        print(f"{name:<20} | {port:<5} | {status:<10} | {has_metrics}")
    except Exception as e:
        print(f"{name:<20} | {port:<5} | {'ERROR':<10} | {str(e)}")

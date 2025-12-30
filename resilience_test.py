import requests
import time
import threading

BASE_URL = "http://localhost:8080"
ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjozLCJlbWFpbCI6ImFkbWluQGNvbXBhbnkuY29tIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzY1MTQ4OTM5fQ.JjwbI-cAefeDSR0AHeswhC01gMdfao22GxFB42P9rUE"
CUSTOMER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo2LCJlbWFpbCI6ImFkbWluQGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzY1Nzk2MjMzfQ.3o_OqJFLdbgCQv_K9tCqUUJ-wlBCQV9MaM1o_krljms"
def test_rate_limiting():   
    print("\n--- Testing Rate Limiting ---")
    print("Sending 100 requests to /api/orders (Limit: 10/min)...")
    
    for i in range(1, 100):
        response = requests.post(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"},
            json={"product_id": 2, "quantity": 1}
        )
        print(f"Request {i}: Status {response.status_code}")
        if response.status_code == 429:
            print("✅ Rate limit hit as expected!")
            return
        time.sleep(0.1)
    
    print("❌ Rate limit NOT hit (unexpected)")

def test_circuit_breaker():
    print("\n--- Testing Circuit Breaker Lifecycle ---")
    print("This test verifies the full cycle: CLOSED -> OPEN -> HALF-OPEN -> CLOSED")
    
    # Step 1: Normal Operation (CLOSED)
    print("\n[Step 1] Sending 5 successful requests (Circuit should be CLOSED)...")
    print("Ensure Payment Service is RUNNING.")
    input("Press Enter to start Step 1...")
    
    for i in range(1, 6):
        try:
            response = requests.post(
                f"{BASE_URL}/api/orders",
                headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"},
                json={"product_id": 1, "quantity": 1}
            )
            print(f"Request {i}: Status {response.status_code} (Success)")
        except Exception as e:
            print(f"Request {i} failed: {e}")
        time.sleep(0.5)

    # Step 2: Trigger Failure (OPEN)
    print("\n[Step 2] Triggering Failures (Circuit should OPEN)...")
    print("Please STOP the Payment Service now:")
    print("  docker-compose stop payment-service")
    input("Press Enter after stopping payment-service...")
    
    print("Sending requests to trip the breaker...")
    for i in range(1, 15):
        try:
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/api/orders",
                headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"},
                json={"product_id": 1, "quantity": 1}
            )
            duration = time.time() - start_time
            
            if response.status_code == 201:
                data = response.json()
                if "Fallback" in data['message']:
                    print(f"Request {i}: ✅ {data['message']} (Fast fail: {duration:.2f}s)")
                else:
                    print(f"Request {i}: ⚠️ Unexpected success")
        except Exception as e:
            print(f"Request {i} failed: {e}")
        time.sleep(0.5)

    # Step 3: Wait for Reset Timeout (HALF-OPEN)
    print("\n[Step 3] Waiting for Circuit to Reset (30 seconds)...")
    for i in range(30, 0, -1):
        print(f"Waiting... {i}s", end='\r')
        time.sleep(1)
    print("\nCircuit should now be HALF-OPEN.")

    # Step 4: Recovery (CLOSED)
    print("\n[Step 4] Recovery (Circuit should CLOSE)...")
    print("Please START the Payment Service now:")
    print("  docker-compose start payment-service")
    input("Press Enter after starting payment-service...")
    
    print("Sending request to close the circuit...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"},
            json={"product_id": 1, "quantity": 1}
        )
        if response.status_code == 201 and "Fallback" not in response.json()['message']:
            print("✅ Request succeeded! Circuit is now CLOSED.")
        else:
            print(f"⚠️ Request result: {response.json()['message']}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Ensure services are up
    try:
        requests.get(f"{BASE_URL}/health")
        print("System is reachable.")
    except:
        print("❌ System is down. Please start docker-compose.")
        exit(1)

def test_retry_logic():
    print("\n--- Testing Retry Logic (Exponential Backoff) ---")
    print("This test verifies that Order Service retries connecting to Customer Service.")
    print("1. Open a new terminal and run: docker-compose stop customer-service")
    print("2. Run: docker-compose logs -f order-service")
    print("3. You should see multiple attempts to connect with increasing delays.")
    input("Press Enter after stopping customer-service to send a request...")
    
    try:
        print("Sending order request...")
        response = requests.post(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"},
            json={"product_id": 1, "quantity": 1}
        )
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.json()}")
    except Exception as e:
        print(f"Request failed: {e}")

def test_queue_recovery():
    print("\n--- Testing Queue Recovery (Payment Processing) ---")
    print("This test verifies that queued payments are processed when Payment Service recovers.")
    print("1. Open a new terminal and run: docker-compose start payment-service")
    print("2. Run: docker-compose logs -f payment-service (to see processing logs)")
    
    order_id = input("Enter the Order ID you want to check (from previous test): ")
    
    print(f"Checking status for Order {order_id}...")
    for i in range(10):
        try:
            response = requests.get(
                f"{BASE_URL}/api/orders/{order_id}",
                headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}", "Content-Type": "application/json"}
            )
            if response.status_code == 200:
                data = response.json()
                print(f"Order Status: {data['status']}")
                print(f"Payment Status: {data['payment_status']}")
                
                if data['payment_status'] == 'completed':
                    print("✅ Payment processed successfully (Recovery confirmed)!")
                    return
            else:
                print(f"Failed to get order: {response.status_code}")
                try:
                    print(f"Response Body: {response.text}")
                except:
                    pass
        except Exception as e:
            print(f"Error: {e}")
        
        print("Waiting for processing...")
        time.sleep(2)
    
    print("⚠️ Payment status did not change to 'completed' within timeout.")

if __name__ == "__main__":
    # Ensure services are up (except for specific tests)
    try:
        requests.get(f"{BASE_URL}/health")
        print("System is reachable.")
    except:
        print("⚠️ System might be down or partial (expected if testing retries).")

    while True:
        print("\n--- Resilience Test Menu ---")
        print("1. Test Rate Limiting")
        print("2. Test Circuit Breaker")
        print("3. Test Retry Logic")
        print("4. Test Queue Recovery")
        print("5. Exit")
        
        choice = input("Enter your choice (1-5): ")
        
        if choice == '1':
            test_rate_limiting()
        elif choice == '2':
            test_circuit_breaker()
        elif choice == '3':
            test_retry_logic()
        elif choice == '4':
            test_queue_recovery()
        elif choice == '5':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

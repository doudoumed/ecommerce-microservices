import requests
import sys

try:
    response = requests.get('http://localhost:8080/metrics')
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Metrics content sample:")
        print(response.text[:500])  # Print first 500 chars
        if 'flask_http_request_total' in response.text:
            print("\nSUCCESS: Found 'flask_http_request_total' metric.")
        else:
            print("\nWARNING: 'flask_http_request_total' metric NOT found in output.")
    else:
        print("Failed to fetch metrics.")
except Exception as e:
    print(f"Error: {e}")

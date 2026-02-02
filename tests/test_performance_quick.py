#!/usr/bin/env python3
"""Quick Performance Test for CRUD Operations"""

import time
import requests
import statistics
import json
from datetime import datetime

BASE_URL = "http://localhost:8080"
AUTH_TOKEN = "dev-user-1"
HEADERS = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

def measure_request(method, url, **kwargs):
    """Measure a single request's latency"""
    start_time = time.perf_counter()
    response = requests.request(method, url, headers=HEADERS, **kwargs)
    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000
    return latency_ms, response.status_code, response

def run_test(name, method, url, iterations=10, **kwargs):
    """Run multiple iterations and calculate statistics"""
    print(f"\nTesting: {name}")
    latencies = []

    for i in range(iterations):
        latency, status, response = measure_request(method, url, **kwargs)
        latencies.append(latency)

        if i == 0:  # Store first response for reference
            if method == "POST" and status == 201:
                data = response.json()
                if "id" in data:
                    test_id = data["id"]

    print(f"  Iterations: {iterations}")
    print(f"  Min: {min(latencies):.2f} ms")
    print(f"  Max: {max(latencies):.2f} ms")
    print(f"  Mean: {statistics.mean(latencies):.2f} ms")
    print(f"  Median: {statistics.median(latencies):.2f} ms")

    return latencies

print("="*60)
print("NUTRIWEALTH BACKEND - QUICK PERFORMANCE TEST")
print("="*60)
print(f"Backend: {BASE_URL}")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Test CREATE
create_payload = {
    "description": "Test food entry",
    "calories": 250,
    "total_protein": 20,
    "total_carbohydrates": 30,
    "total_fats": 10
}
create_latencies = run_test(
    "CREATE - Food Entry",
    "POST",
    f"{BASE_URL}/v1/food_entries",
    iterations=20,
    json=create_payload
)

# Test READ (List)
list_latencies = run_test(
    "READ - List Food Entries",
    "GET",
    f"{BASE_URL}/v1/food_entries?limit=10",
    iterations=20
)

# Create a test item for UPDATE and DELETE
response = requests.post(
    f"{BASE_URL}/v1/food_entries",
    headers=HEADERS,
    json={"description": "Item to update", "calories": 100}
)
test_id = response.json().get("id")

# Test UPDATE
update_payload = {"calories": 150, "notes": "Updated"}
update_latencies = run_test(
    "UPDATE - Food Entry",
    "PUT",
    f"{BASE_URL}/v1/food_entries/{test_id}",
    iterations=20,
    json=update_payload
)

# Test READ (By ID)
get_latencies = run_test(
    "READ - Get by ID",
    "GET",
    f"{BASE_URL}/v1/food_entries/{test_id}",
    iterations=20
)

# Test DELETE
delete_latencies = run_test(
    "DELETE - Food Entry",
    "DELETE",
    f"{BASE_URL}/v1/food_entries/{test_id}",
    iterations=10
)

print("\n" + "="*60)
print("SUMMARY - Average Latencies (ms)")
print("="*60)
print(f"CREATE: {statistics.mean(create_latencies):.2f} ms")
print(f"READ (List): {statistics.mean(list_latencies):.2f} ms")
print(f"READ (By ID): {statistics.mean(get_latencies):.2f} ms")
print(f"UPDATE: {statistics.mean(update_latencies):.2f} ms")
print(f"DELETE: {statistics.mean(delete_latencies):.2f} ms")

# Calculate overall statistics
all_latencies = create_latencies + list_latencies + get_latencies + update_latencies + delete_latencies
print(f"\nOverall Average: {statistics.mean(all_latencies):.2f} ms")
print(f"Overall P95: {sorted(all_latencies)[int(len(all_latencies) * 0.95)]:.2f} ms")
print(f"Overall P99: {sorted(all_latencies)[int(len(all_latencies) * 0.99)]:.2f} ms")

print("\n✅ Performance test completed!")
print("="*60)
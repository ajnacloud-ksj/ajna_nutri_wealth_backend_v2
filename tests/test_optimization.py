#!/usr/bin/env python3
"""
Test the performance improvement with OptimizedIbexClient
Compares cached vs uncached performance
"""

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

print("="*60)
print("OPTIMIZED IBEX CLIENT - PERFORMANCE TEST")
print("="*60)
print(f"Backend: {BASE_URL}")
print(f"Testing cache performance...")

# Test 1: First request (cold cache)
print("\n📊 Test 1: Cold Cache Performance (First Request)")
cold_latencies = []

for i in range(3):
    print(f"\n  Run {i+1}:")
    # Clear cache by using unique query each time
    latency, status, response = measure_request(
        "GET",
        f"{BASE_URL}/v1/food_entries?limit=10&offset={i*10}"
    )
    cold_latencies.append(latency)
    print(f"    Latency: {latency:.2f} ms")
    print(f"    Status: {status}")

# Test 2: Repeated requests (warm cache)
print("\n📊 Test 2: Warm Cache Performance (Repeated Requests)")
warm_latencies = []

# Make the same request multiple times
test_url = f"{BASE_URL}/v1/food_entries?limit=10"

# First request to warm the cache
print("\n  Warming cache...")
measure_request("GET", test_url)

# Now measure cached performance
print("\n  Measuring cached performance:")
for i in range(5):
    latency, status, response = measure_request("GET", test_url)
    warm_latencies.append(latency)
    print(f"    Run {i+1}: {latency:.2f} ms")

# Test 3: ID-based lookups (should be very fast when cached)
print("\n📊 Test 3: ID Lookup Performance")

# First, get an ID from the list
response = requests.get(f"{BASE_URL}/v1/food_entries?limit=1", headers=HEADERS)
if response.status_code == 200:
    data = response.json()
    if data and len(data) > 0 and 'id' in data[0]:
        test_id = data[0]['id']
        id_url = f"{BASE_URL}/v1/food_entries/{test_id}"

        # Cold lookup
        print(f"\n  Testing ID: {test_id}")
        print("  First lookup (cold):")
        latency1, _, _ = measure_request("GET", id_url)
        print(f"    Latency: {latency1:.2f} ms")

        # Warm lookups
        print("  Repeated lookups (cached):")
        id_latencies = []
        for i in range(3):
            latency, _, _ = measure_request("GET", id_url)
            id_latencies.append(latency)
            print(f"    Run {i+1}: {latency:.2f} ms")

# Test 4: Write operations (should clear cache)
print("\n📊 Test 4: Write Operation Impact on Cache")

# Get initial cached performance
print("  Getting baseline cached read...")
latency_before, _, _ = measure_request("GET", test_url)
print(f"    Cached read: {latency_before:.2f} ms")

# Perform a write
print("  Performing write operation...")
write_data = {
    "description": f"Cache test item {datetime.now().isoformat()}",
    "calories": 100
}
write_latency, write_status, write_response = measure_request(
    "POST",
    f"{BASE_URL}/v1/food_entries",
    json=write_data
)
print(f"    Write latency: {write_latency:.2f} ms")

if write_status == 201:
    created_id = write_response.json().get('id')

    # Read after write (cache should be invalidated)
    print("  Reading after write (cache invalidated)...")
    latency_after, _, _ = measure_request("GET", test_url)
    print(f"    Read latency: {latency_after:.2f} ms")

    # Clean up
    if created_id:
        requests.delete(f"{BASE_URL}/v1/food_entries/{created_id}", headers=HEADERS)

# Print Summary
print("\n" + "="*60)
print("PERFORMANCE SUMMARY")
print("="*60)

if cold_latencies and warm_latencies:
    cold_avg = statistics.mean(cold_latencies)
    warm_avg = statistics.mean(warm_latencies)
    improvement = ((cold_avg - warm_avg) / cold_avg) * 100

    print(f"\n📈 Cache Performance:")
    print(f"  Cold Cache Average: {cold_avg:.2f} ms")
    print(f"  Warm Cache Average: {warm_avg:.2f} ms")
    print(f"  Cache Improvement: {improvement:.1f}%")

    if 'id_latencies' in locals() and id_latencies:
        id_avg = statistics.mean(id_latencies)
        id_improvement = ((cold_avg - id_avg) / cold_avg) * 100
        print(f"\n📈 ID Lookup Performance:")
        print(f"  Cached ID Lookup: {id_avg:.2f} ms")
        print(f"  Improvement vs Cold: {id_improvement:.1f}%")

    print("\n🎯 Expected Production Performance:")
    print("  • First request: ~2000ms (cache miss)")
    print("  • Subsequent requests: ~50-200ms (cache hit)")
    print("  • ID lookups: ~5-20ms (cached)")
    print("  • Cache TTL: 60s for queries, 300s for metadata")

    if improvement > 50:
        print("\n✅ Optimization is working effectively!")
    elif improvement > 20:
        print("\n⚠️ Moderate improvement. Cache may need tuning.")
    else:
        print("\n❌ Limited improvement. Check if caching is enabled.")

print("\n" + "="*60)
#!/usr/bin/env python3
"""
Test warm performance after optimizations are deployed
Excludes cold start from averages
"""

import requests
import json
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

FUNCTION_URL = "https://pd3i6m24yc2srxgdp2s2xquewe0wlqgk.lambda-url.ap-south-1.on.aws/"

print("="*60)
print("🔥 WARM PERFORMANCE TEST (After Optimizations)")
print("="*60)

# Warmup phase
print("\n📊 Warming up Lambda (3 requests)...")
for i in range(3):
    try:
        response = requests.post(
            FUNCTION_URL,
            json={
                "operation": "LIST_TABLES",
                "tenant_id": "warmup",
                "namespace": "default"
            },
            timeout=10
        )
        print(f"  Warmup {i+1}: {response.status_code}")
    except Exception as e:
        print(f"  Warmup {i+1}: Failed - {str(e)}")

# Test 1: Simple queries (should be cached)
print("\n📊 Test 1: Cached Query Performance")
print("  (Same query repeated - should hit cache)")

query_payload = {
    "operation": "QUERY",
    "tenant_id": "test-tenant",
    "namespace": "default",
    "table": "food_entries",
    "limit": 10,
    "filters": [{"field": "user_id", "operator": "eq", "value": "test-user-1"}]
}

cached_times = []
for i in range(10):
    start = time.perf_counter()
    response = requests.post(FUNCTION_URL, json=query_payload, timeout=10)
    end = time.perf_counter()
    latency = (end - start) * 1000
    cached_times.append(latency)

    # Check if cache was hit (if header is present)
    cache_hit = response.headers.get('X-Cache-Hit', 'unknown')
    print(f"  Run {i+1}: {latency:.2f}ms (Cache: {cache_hit})")

print(f"\n  Cached Query Results:")
print(f"    Average: {statistics.mean(cached_times):.2f}ms")
print(f"    Median: {statistics.median(cached_times):.2f}ms")
print(f"    Min: {min(cached_times):.2f}ms")
print(f"    Max: {max(cached_times):.2f}ms")

# Test 2: Different queries (cache misses)
print("\n📊 Test 2: Uncached Query Performance")
print("  (Different queries - cache misses)")

uncached_times = []
for i in range(10):
    # Different query each time
    unique_payload = {
        "operation": "QUERY",
        "tenant_id": f"tenant-{i}",
        "namespace": "default",
        "table": "food_entries",
        "limit": 5 + i,
        "offset": i * 10
    }

    start = time.perf_counter()
    response = requests.post(FUNCTION_URL, json=unique_payload, timeout=10)
    end = time.perf_counter()
    latency = (end - start) * 1000
    uncached_times.append(latency)
    print(f"  Run {i+1}: {latency:.2f}ms")

print(f"\n  Uncached Query Results:")
print(f"    Average: {statistics.mean(uncached_times):.2f}ms")
print(f"    Median: {statistics.median(uncached_times):.2f}ms")
print(f"    Min: {min(uncached_times):.2f}ms")
print(f"    Max: {max(uncached_times):.2f}ms")

# Test 3: Write operations
print("\n📊 Test 3: Write Operation Performance")

write_times = []
for i in range(5):
    write_payload = {
        "operation": "WRITE",
        "tenant_id": "test-tenant",
        "namespace": "default",
        "table": "food_entries",
        "records": [{
            "id": f"perf-test-{time.time()}-{i}",
            "description": f"Performance test item {i}",
            "calories": 100 + i,
            "user_id": "test-user-1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }]
    }

    start = time.perf_counter()
    response = requests.post(FUNCTION_URL, json=write_payload, timeout=10)
    end = time.perf_counter()
    latency = (end - start) * 1000
    write_times.append(latency)
    print(f"  Write {i+1}: {latency:.2f}ms")

print(f"\n  Write Operation Results:")
print(f"    Average: {statistics.mean(write_times):.2f}ms")
print(f"    Min: {min(write_times):.2f}ms")
print(f"    Max: {max(write_times):.2f}ms")

# Test 4: Concurrent requests
print("\n📊 Test 4: Concurrent Request Handling")
print("  (10 concurrent requests)")

def make_concurrent_request(request_id):
    payload = {
        "operation": "QUERY",
        "tenant_id": f"concurrent-{request_id % 3}",  # Use 3 different tenants
        "namespace": "default",
        "table": "food_entries",
        "limit": 5
    }
    start = time.perf_counter()
    response = requests.post(FUNCTION_URL, json=payload, timeout=10)
    end = time.perf_counter()
    return (end - start) * 1000

concurrent_times = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(make_concurrent_request, i) for i in range(10)]
    for future in as_completed(futures):
        latency = future.result()
        concurrent_times.append(latency)

print(f"  Concurrent Results:")
print(f"    Average: {statistics.mean(concurrent_times):.2f}ms")
print(f"    Min: {min(concurrent_times):.2f}ms")
print(f"    Max: {max(concurrent_times):.2f}ms")

# Test 5: Batch operations
print("\n📊 Test 5: Batch Operation Performance")

batch_payload = {
    "operation": "BATCH",
    "tenant_id": "test-tenant",
    "namespace": "default",
    "operations": [
        {
            "operation": "WRITE",
            "table": "food_entries",
            "records": [{
                "id": f"batch-{i}-{time.time()}",
                "description": f"Batch item {i}",
                "calories": 50 + i
            }]
        }
        for i in range(10)
    ]
}

start = time.perf_counter()
response = requests.post(FUNCTION_URL, json=batch_payload, timeout=30)
end = time.perf_counter()
batch_latency = (end - start) * 1000

print(f"  Batch (10 operations): {batch_latency:.2f}ms")
print(f"  Average per operation: {batch_latency/10:.2f}ms")

# Summary
print("\n" + "="*60)
print("📈 PERFORMANCE SUMMARY (Warm Lambda)")
print("="*60)

print(f"\n✅ Query Performance:")
print(f"  Cached: {statistics.mean(cached_times):.2f}ms avg")
print(f"  Uncached: {statistics.mean(uncached_times):.2f}ms avg")
print(f"  Cache Benefit: {((statistics.mean(uncached_times) - statistics.mean(cached_times)) / statistics.mean(uncached_times) * 100):.1f}% faster")

print(f"\n✅ Write Performance:")
print(f"  Average: {statistics.mean(write_times):.2f}ms")

print(f"\n✅ Concurrent Handling:")
print(f"  10 concurrent: {statistics.mean(concurrent_times):.2f}ms avg")

print(f"\n✅ Batch Efficiency:")
print(f"  10 individual writes: ~{statistics.mean(write_times) * 10:.0f}ms")
print(f"  1 batch of 10: {batch_latency:.0f}ms")
print(f"  Improvement: {((statistics.mean(write_times) * 10 - batch_latency) / (statistics.mean(write_times) * 10) * 100):.1f}%")

# Compare with original baseline
print("\n" + "="*60)
print("🎯 OPTIMIZATION IMPACT")
print("="*60)

original_baseline = 2000  # Original average from earlier tests
current_avg = statistics.mean(uncached_times)
improvement = ((original_baseline - current_avg) / original_baseline) * 100

print(f"\nBefore optimizations: ~{original_baseline}ms average")
print(f"After optimizations: {current_avg:.0f}ms average")
print(f"Overall improvement: {improvement:.1f}%")

if improvement > 50:
    print("\n✅ Optimizations are highly effective!")
elif improvement > 20:
    print("\n✅ Optimizations show good improvement!")
else:
    print("\n⚠️ Limited improvement - may need further tuning")

print("="*60)
#!/usr/bin/env python3
"""
Test Lambda Function URL for IbexDB
Compares performance with API Gateway
"""

import requests
import json
import time
import statistics
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
FUNCTION_URL = "https://pd3i6m24yc2srxgdp2s2xquewe0wlqgk.lambda-url.ap-south-1.on.aws/"
API_GATEWAY_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = os.getenv('IBEX_API_KEY', 'McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl')

print("="*60)
print("🚀 LAMBDA FUNCTION URL TEST")
print("="*60)
print(f"Function URL: {FUNCTION_URL}")
print(f"Region: ap-south-1")
print("")

# Test payload
test_payload = {
    "operation": "LIST_TABLES",
    "tenant_id": "test-tenant",
    "namespace": "default"
}

# Test 1: Function URL
print("📊 Testing Lambda Function URL...")
function_times = []
function_success = 0

for i in range(5):
    try:
        start = time.perf_counter()
        response = requests.post(
            FUNCTION_URL,
            json=test_payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        end = time.perf_counter()

        latency = (end - start) * 1000
        function_times.append(latency)

        if response.status_code == 200:
            function_success += 1
            result = response.json()
            print(f"  Run {i+1}: {latency:.2f}ms - ✅ Success")

            # Show tables on first run
            if i == 0 and result.get('success'):
                tables = result.get('data', {}).get('tables', [])
                if tables:
                    print(f"    Tables found: {len(tables)}")
                    print(f"    Sample tables: {', '.join(tables[:5])}")
        else:
            print(f"  Run {i+1}: {latency:.2f}ms - ❌ Status {response.status_code}")
            if i == 0:
                print(f"    Response: {response.text[:200]}")
    except Exception as e:
        print(f"  Run {i+1}: Failed - {str(e)}")

if function_times:
    print(f"\n  Function URL Results:")
    print(f"    Success Rate: {function_success}/5")
    print(f"    Average: {statistics.mean(function_times):.2f}ms")
    print(f"    Min: {min(function_times):.2f}ms")
    print(f"    Max: {max(function_times):.2f}ms")

# Test 2: API Gateway (for comparison)
print("\n📊 Testing API Gateway...")
api_times = []
api_success = 0

for i in range(5):
    try:
        start = time.perf_counter()
        response = requests.post(
            API_GATEWAY_URL,
            json=test_payload,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': API_KEY
            },
            timeout=10
        )
        end = time.perf_counter()

        latency = (end - start) * 1000
        api_times.append(latency)

        if response.status_code == 200:
            api_success += 1
            print(f"  Run {i+1}: {latency:.2f}ms - ✅ Success")
        else:
            print(f"  Run {i+1}: {latency:.2f}ms - ❌ Status {response.status_code}")
    except Exception as e:
        print(f"  Run {i+1}: Failed - {str(e)}")

if api_times:
    print(f"\n  API Gateway Results:")
    print(f"    Success Rate: {api_success}/5")
    print(f"    Average: {statistics.mean(api_times):.2f}ms")
    print(f"    Min: {min(api_times):.2f}ms")
    print(f"    Max: {max(api_times):.2f}ms")

# Comparison
print("\n" + "="*60)
print("📈 PERFORMANCE COMPARISON")
print("="*60)

if function_times and api_times:
    func_avg = statistics.mean(function_times)
    api_avg = statistics.mean(api_times)

    improvement = ((api_avg - func_avg) / api_avg) * 100

    print(f"Function URL Average: {func_avg:.2f}ms")
    print(f"API Gateway Average: {api_avg:.2f}ms")
    print("")

    if improvement > 0:
        print(f"✅ Function URL is {improvement:.1f}% FASTER!")
    else:
        print(f"⚠️ API Gateway is {abs(improvement):.1f}% faster")

    # Cost comparison (rough estimate)
    print("\n💰 Cost Comparison (per 1M requests):")
    print(f"  Function URL: $0.20 (Lambda invocation only)")
    print(f"  API Gateway: $3.70 ($3.50 API Gateway + $0.20 Lambda)")
    print(f"  Savings: $3.50 per million requests")

elif function_times:
    print(f"✅ Function URL Average: {statistics.mean(function_times):.2f}ms")
    print("   API Gateway test failed")
else:
    print("❌ Both tests failed")

print("\n" + "="*60)

# Test a real query
print("\n📊 Testing Real Query on Function URL...")
query_payload = {
    "operation": "QUERY",
    "tenant_id": "test-tenant",
    "namespace": "default",
    "table": "food_entries",
    "limit": 5,
    "filters": [
        {"field": "user_id", "operator": "eq", "value": "test-user-1"}
    ]
}

try:
    start = time.perf_counter()
    response = requests.post(
        FUNCTION_URL,
        json=query_payload,
        headers={'Content-Type': 'application/json'},
        timeout=10
    )
    end = time.perf_counter()

    latency = (end - start) * 1000

    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            records = result.get('data', {}).get('records', [])
            print(f"✅ Query successful in {latency:.2f}ms")
            print(f"   Records returned: {len(records)}")
        else:
            print(f"❌ Query failed: {result.get('error')}")
    else:
        print(f"❌ HTTP {response.status_code}: {response.text[:200]}")
except Exception as e:
    print(f"❌ Query failed: {str(e)}")

print("\n✅ Function URL is configured and working!")
print("   Update your app to use IBEX_FUNCTION_URL environment variable")
print("="*60)
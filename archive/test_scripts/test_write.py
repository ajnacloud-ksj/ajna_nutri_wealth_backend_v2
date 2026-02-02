#!/usr/bin/env python3
"""
Test Ibex write operation
"""

import requests
import json
from datetime import datetime

# Configuration
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

# Test write to api_usage_log
print("=== Testing Write to api_usage_log ===")

test_record = {
    "id": f"test-{datetime.utcnow().isoformat()}",
    "user_id": "local-dev-user",
    "endpoint": "/v1/ai/analyze",
    "method": "POST",
    "status_code": 200,
    "model_used": "mock",
    "input_tokens": 100,
    "output_tokens": 200,
    "total_tokens": 300,
    "cost": 0.001,
    "response_time_ms": 1500,
    "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
}

payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "WRITE",
    "table": "api_usage_log",
    "records": [test_record]
}

print(f"Sending: {json.dumps(test_record, indent=2)}")

response = requests.post(API_URL, headers=headers, json=payload)
print(f"Response status: {response.status_code}")

if response.ok:
    data = response.json()
    print(f"Success: {data.get('success')}")
    if data.get('data'):
        print(f"Records written: {len(data.get('data', {}).get('records', []))}")
else:
    print(f"Error: {response.text}")

# Check what fields are causing issues
print("\n=== Checking api_usage_log schema ===")

# Query existing records to see structure
query_payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "api_usage_log",
    "limit": 1
}

response2 = requests.post(API_URL, headers=headers, json=query_payload)
if response2.ok:
    data = response2.json()
    records = data.get('data', {}).get('records', [])
    if records:
        print("Existing record structure:")
        for key in records[0].keys():
            if not key.startswith('_'):
                print(f"  - {key}: {type(records[0][key]).__name__}")
    else:
        print("No existing records to check structure")
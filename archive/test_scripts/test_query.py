#!/usr/bin/env python3
"""
Test Ibex query formats
"""

import requests
import json

# Configuration
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

def test_query(table_name, filters=None):
    """Test different query formats"""

    # Test 1: Simple query without filters
    print(f"\n=== Test 1: Query {table_name} without filters ===")
    payload1 = {
        "tenant_id": TENANT_ID,
        "namespace": NAMESPACE,
        "operation": "QUERY",
        "table": table_name,
        "limit": 2
    }

    response1 = requests.post(API_URL, headers=headers, json=payload1)
    print(f"Request: {json.dumps(payload1, indent=2)}")
    print(f"Response status: {response1.status_code}")
    if response1.ok:
        data = response1.json()
        records = data.get('data', {}).get('records', [])
        print(f"Records returned: {len(records)}")
        if records:
            print(f"First record keys: {list(records[0].keys())}")
    else:
        print(f"Error: {response1.text}")

    # Test 2: Query with filter using the exact format from error
    if filters:
        print(f"\n=== Test 2: Query {table_name} with filters ===")
        payload2 = {
            "tenant_id": TENANT_ID,
            "namespace": NAMESPACE,
            "operation": "QUERY",
            "table": table_name,
            "filters": filters,
            "limit": 2
        }

        response2 = requests.post(API_URL, headers=headers, json=payload2)
        print(f"Request: {json.dumps(payload2, indent=2)}")
        print(f"Response status: {response2.status_code}")
        if response2.ok:
            data = response2.json()
            records = data.get('data', {}).get('records', [])
            print(f"Records returned: {len(records)}")
        else:
            print(f"Error: {response2.text}")

    # Test 3: Try with filter condition format (Ibex might expect this)
    print(f"\n=== Test 3: Query with filter_condition ===")
    payload3 = {
        "tenant_id": TENANT_ID,
        "namespace": NAMESPACE,
        "operation": "QUERY",
        "table": table_name,
        "filter_condition": "user_id = 'local-dev-user'",
        "limit": 2
    }

    response3 = requests.post(API_URL, headers=headers, json=payload3)
    print(f"Request: {json.dumps(payload3, indent=2)}")
    print(f"Response status: {response3.status_code}")
    if response3.ok:
        data = response3.json()
        records = data.get('data', {}).get('records', [])
        print(f"Records returned: {len(records)}")
    else:
        print(f"Error: {response3.text}")

# Test with food_entries table
print("=== Testing Ibex Query Formats ===")
test_query("food_entries", filters=[{"field": "user_id", "operator": "eq", "value": "local-dev-user"}])

# Test with users table (currently empty)
test_query("users")
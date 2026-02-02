#!/usr/bin/env python3
"""
Debug users table issue
"""

import requests
import json
import re

# Configuration
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

print("=== Debugging Users Table ===\n")

# 1. Query all users without any filters
print("1. Query all users (no filters):")
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "users",
    "limit": 5
}

response = requests.post(API_URL, headers=headers, json=payload)
if response.ok:
    # Handle NaN values
    response_text = re.sub(r'\bNaN\b', 'null', response.text)
    response_text = re.sub(r'"NaT"', 'null', response_text)
    data = json.loads(response_text)

    records = data.get('data', {}).get('records', [])
    print(f"✓ Found {len(records)} users")

    if records:
        # Show available columns
        first_record = records[0]
        columns = [k for k in first_record.keys() if not k.startswith('_')]
        print(f"Available columns: {columns}")
        print(f"\nFirst user:")
        for key in columns:
            print(f"  {key}: {first_record.get(key)}")
else:
    print(f"✗ Query failed: {response.status_code}")
    print(response.text)

# 2. Query with id filter
print("\n2. Query users with id filter:")
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "users",
    "filters": [{"field": "id", "operator": "eq", "value": "local-dev-user"}],
    "limit": 1
}

response = requests.post(API_URL, headers=headers, json=payload)
if response.ok:
    response_text = re.sub(r'\bNaN\b', 'null', response.text)
    response_text = re.sub(r'"NaT"', 'null', response_text)
    data = json.loads(response_text)

    records = data.get('data', {}).get('records', [])
    if records:
        print(f"✓ Found user with id=local-dev-user")
        user = records[0]
        print(f"  Email: {user.get('email')}")
        print(f"  Full name: {user.get('full_name')}")
    else:
        print("✗ No user found with id=local-dev-user")
else:
    print(f"✗ Query failed: {response.status_code}")
    print(response.text)

# 3. Try query with non-existent field (this should fail)
print("\n3. Test query with non-existent field (should fail):")
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "users",
    "filters": [{"field": "user_id", "operator": "eq", "value": "test"}],
    "limit": 1
}

response = requests.post(API_URL, headers=headers, json=payload)
if response.ok:
    print("✗ Unexpected success - should have failed")
else:
    print(f"✓ Expected failure: {response.status_code}")
    error_data = response.json()
    error_msg = error_data.get('error', {}).get('message', 'Unknown error')
    if 'user_id' in error_msg:
        print("✓ Error correctly mentions 'user_id' field doesn't exist")
        # Extract available columns from error
        import re
        match = re.search(r'Candidate bindings: (.+)', error_msg)
        if match:
            candidates = match.group(1)
            print(f"  Available columns from error: {candidates}")

print("\n=== Analysis ===")
print("The users table exists and can be queried.")
print("The 'user_id' field does NOT exist in the users table (correct - it has 'id' instead).")
print("The backend handler must be adding a user_id filter incorrectly.")
#!/usr/bin/env python3
"""
Test querying app_models table
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

# Query app_models
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "app_models",
    "filters": [
        {"field": "is_active", "operator": "eq", "value": True},
        {"field": "is_default", "operator": "eq", "value": True}
    ],
    "limit": 1
}

print("Querying app_models for default model...")
response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
result = response.json()

if result.get('success'):
    data = result.get('data', {})
    records = data.get('records', [])
    print(f"Found {len(records)} records")
    if records:
        print("Model found:")
        print(json.dumps(records[0], indent=2))
    else:
        print("No default model found")
else:
    print(f"Error: {result.get('error')}")
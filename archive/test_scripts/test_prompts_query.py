#!/usr/bin/env python3
"""
Test querying app_prompts table
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

# Query app_prompts
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "app_prompts",
    "filters": [
        {"field": "category", "operator": "eq", "value": "food"},
        {"field": "is_active", "operator": "eq", "value": True}
    ],
    "limit": 1
}

print("Querying app_prompts for food category...")
response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
result = response.json()

if result.get('success'):
    data = result.get('data', {})
    records = data.get('records', [])
    print(f"Found {len(records)} records")
    if records:
        print("Prompt found:")
        print(json.dumps(records[0], indent=2))
    else:
        print("No food prompts found")
else:
    print(f"Error: {result.get('error')}")
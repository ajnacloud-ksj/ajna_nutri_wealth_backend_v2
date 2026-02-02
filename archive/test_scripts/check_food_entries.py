#!/usr/bin/env python3
"""
Check food entries in the database to see if Chicken Biryani was stored
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

# Query app_food_entries table
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "app_food_entries",
    "limit": 10,
    "sort": [{"field": "_timestamp", "order": "desc"}]
}

print("=== Checking Food Entries in Database ===\n")
response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
result = response.json()

if result.get('success'):
    data = result.get('data', {})
    records = data.get('records', [])
    print(f"Found {len(records)} food entries\n")

    for i, record in enumerate(records, 1):
        # Clean record
        clean_record = {k: v for k, v in record.items() if not k.startswith('_')}
        print(f"Entry #{i}:")
        print(f"  Description: {clean_record.get('description', 'N/A')}")
        print(f"  Meal Type: {clean_record.get('meal_type', 'N/A')}")
        print(f"  Calories: {clean_record.get('calories', 'N/A')}")
        print(f"  Date: {clean_record.get('meal_date', 'N/A')}")
        print(f"  User ID: {clean_record.get('user_id', 'N/A')}")
        print(f"  Created: {record.get('_timestamp', 'N/A')}")
        print("")
else:
    print(f"Error querying database: {result.get('error')}")

# Also check pending_analyses table
print("\n=== Checking Pending Analyses ===\n")
payload2 = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "app_pending_analyses",
    "limit": 10
}

response2 = requests.post(API_URL, headers=headers, json=payload2, timeout=30)
result2 = response2.json()

if result2.get('success'):
    data2 = result2.get('data', {})
    records2 = data2.get('records', [])
    print(f"Found {len(records2)} pending analyses")

    for record in records2:
        clean = {k: v for k, v in record.items() if not k.startswith('_')}
        print(f"  - {clean.get('description', 'N/A')} (Status: {clean.get('status', 'N/A')})")
else:
    print(f"Error: {result2.get('error')}")
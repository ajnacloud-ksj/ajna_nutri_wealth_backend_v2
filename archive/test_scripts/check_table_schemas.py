#!/usr/bin/env python3
"""
Check actual schemas of Ibex tables
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

def call_ibex(operation_payload):
    """Make a call to Ibex API"""
    payload = {
        "tenant_id": TENANT_ID,
        "namespace": NAMESPACE,
        **operation_payload
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

# Check table schemas by querying a single record
tables_to_check = ["food_entries", "pending_analyses", "meal_summaries", "workouts", "receipts"]

for table in tables_to_check:
    print(f"\n=== Checking {table} ===")
    
    # Query one record to see the fields
    result = call_ibex({
        "operation": "QUERY",
        "table": table,
        "limit": 1
    })
    
    if result and result.get('success'):
        records = result.get('data', {}).get('records', [])
        if records:
            # Show the fields
            record = records[0]
            fields = [k for k in record.keys() if not k.startswith('_')]
            print(f"Fields: {fields}")
        else:
            print("No records found")
    else:
        print(f"Failed to query table")


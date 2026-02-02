#!/usr/bin/env python3
"""
Fix app_users table with test user
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
        print(f"Ibex Error: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                print(f"Details: {e.response.json()}")
            except:
                print(f"Response: {e.response.text}")
        return None

# Create app_users_v2 table without created_at/updated_at
table_schema = {
    "fields": {
        "id": {"type": "string", "required": True},
        "email": {"type": "string", "required": False},
        "full_name": {"type": "string", "required": False},
        "role": {"type": "string", "required": False},
        "user_type": {"type": "string", "required": False},
        "is_subscribed": {"type": "boolean", "required": False},
        "trial_used_today": {"type": "boolean", "required": False}
    }
}

print("Creating app_users_v2 table...")
result = call_ibex({
    "operation": "CREATE_TABLE",
    "table": "app_users_v2",
    "schema": table_schema
})

if result and result.get('success'):
    print("✓ Created app_users_v2 table")
else:
    print("⚠️ Table may already exist")

# Add test user
user_record = {
    "id": "local-dev-user",
    "email": "test@example.com",
    "full_name": "Test User",
    "role": "user",
    "user_type": "participant",
    "is_subscribed": False,
    "trial_used_today": False
}

result = call_ibex({
    "operation": "WRITE",
    "table": "app_users_v2",
    "records": [user_record]
})

if result and result.get('success'):
    print("✓ Created test user successfully")
    print(f"  ID: {user_record['id']}")
    print(f"  Email: {user_record['email']}")
else:
    print(f"Error: {result.get('error')}")
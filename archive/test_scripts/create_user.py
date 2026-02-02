#!/usr/bin/env python3
"""
Create a user in the users table
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

# Create user record
user_record = {
    "id": "local-dev-user",
    "email": "test@example.com",
    "full_name": "Test User",
    "role": "user",
    "user_type": "participant",
    "subscription_id": None,
    "is_subscribed": True,  # Set to true for development
    "trial_used_today": False,
    "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
    "updated_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
}

payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "WRITE",
    "table": "users",
    "records": [user_record]
}

print("Creating user record...")
print(json.dumps(user_record, indent=2))

response = requests.post(API_URL, headers=headers, json=payload)

if response.ok:
    print("✓ User created successfully")
    result = response.json()
    if result.get('data', {}).get('records'):
        print("Created user:", result['data']['records'][0])
else:
    print(f"Error: {response.status_code}")
    print(response.text)
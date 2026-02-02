#!/usr/bin/env python3
"""
Add test user to app_users table
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

user_record = {
    "id": "local-dev-user",
    "email": "test@example.com",
    "full_name": "Test User",
    "role": "user",
    "user_type": "participant",
    "is_subscribed": False,
    "trial_used_today": False
}

payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "WRITE",
    "table": "app_users",
    "records": [user_record]
}

response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
result = response.json()

if result.get('success'):
    print("✓ Created test user successfully")
    print(f"  ID: {user_record['id']}")
    print(f"  Email: {user_record['email']}")
else:
    print(f"Error: {result.get('error')}")
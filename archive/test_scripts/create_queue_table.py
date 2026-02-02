#!/usr/bin/env python3
"""
Create analysis_queue table for background job processing
"""

import requests
import json
from datetime import datetime
import uuid

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

def create_queue_table():
    """Create the app_analysis_queue table"""
    table_name = "app_analysis_queue"

    # Create initial record to establish table
    init_record = {
        "id": "init_" + str(uuid.uuid4()),
        "user_id": "system",
        "status": "completed",
        "description": "Table initialization",
        "progress": 100,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    print(f"Creating table: {table_name}")

    # Write initial record to create table
    result = call_ibex({
        "operation": "write",
        "table": table_name,
        "records": [init_record]
    })

    if result and result.get("success"):
        print(f"✅ Table '{table_name}' created successfully!")

        # Verify table exists
        verify_result = call_ibex({
            "operation": "query",
            "table": table_name,
            "filters": [],
            "limit": 1
        })

        if verify_result and verify_result.get("success"):
            print(f"✅ Verified: Table exists with {len(verify_result.get('data', []))} record(s)")
            if verify_result.get('data'):
                print(f"   Sample record ID: {verify_result['data'][0].get('id')}")
        else:
            print(f"⚠️  Could not verify table")
    else:
        print(f"❌ Failed to create table")
        if result:
            print(f"   Error: {result.get('error')}")

def main():
    print("=== Creating Analysis Queue Table ===")
    create_queue_table()
    print("\n✅ Queue table setup complete!")

if __name__ == "__main__":
    main()
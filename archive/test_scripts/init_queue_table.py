#!/usr/bin/env python3
"""
Initialize app_analysis_queue table by writing a test record
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex_client import IbexClient
from datetime import datetime
import uuid

# Initialize Ibex client
client = IbexClient(
    api_url="https://smartlink.ajna.cloud/ibexdb",
    api_key="McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl",
    tenant_id="test-tenant",
    namespace="default"
)

# Create initial record to establish table (without image_url for now)
init_record = {
    "id": str(uuid.uuid4()),
    "user_id": "system",
    "status": "completed",
    "description": "Table initialization",
    "progress": 100,
    "created_at": datetime.utcnow().isoformat(),
    "updated_at": datetime.utcnow().isoformat()
}

print("Checking app_analysis_queue table...")

# First check what's in the table
try:
    # Try to query the table first
    try:
        query_result = client.query("app_analysis_queue", limit=1)
        print(f"Table exists with {len(query_result.get('data', []))} records")
        if query_result.get('data'):
            print(f"Sample record: {query_result['data'][0]}")
    except Exception as e:
        print(f"Table doesn't exist or error querying: {e}")

    # Now try to create or use the table
    # Create table with schema
    schema = {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "description": {"type": "string", "required": False},
            "image_url": {"type": "string", "required": False},
            "status": {"type": "string", "required": True},
            "progress": {"type": "number", "required": False},
            "result": {"type": "string", "required": False},
            "error": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": True},
            "updated_at": {"type": "string", "required": False},
            "completed_at": {"type": "string", "required": False}
        }
    }

    create_result = client.create_table("app_analysis_queue", schema)
    print(f"Create table result: {create_result}")

    # Check if table was created or already existed
    if create_result.get('data', {}).get('table_existed'):
        print("ℹ️  Table already exists, writing record...")
    elif create_result.get('data', {}).get('table_created'):
        print("✅ Table created successfully!")

    # Then write initial record
    result = client.write("app_analysis_queue", [init_record])
    if result.get("success"):
        print("✅ Initial record written successfully!")

        # Verify it exists
        query_result = client.query("app_analysis_queue", limit=1)
        if query_result.get("success"):
            print(f"✅ Verified: Table has {len(query_result.get('data', []))} record(s)")
    else:
        print(f"❌ Failed to write: {result.get('error')}")
except Exception as e:
    print(f"❌ Error: {e}")
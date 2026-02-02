#!/usr/bin/env python3
"""
Query the app_analysis_queue table directly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex_client import IbexClient
import json

# Initialize Ibex client
client = IbexClient(
    api_url="https://smartlink.ajna.cloud/ibexdb",
    api_key="McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl",
    tenant_id="test-tenant",
    namespace="default"
)

print("Querying app_analysis_queue table...")

try:
    # Query all records
    result = client.query("app_analysis_queue", limit=10)
    print(f"Query result: {json.dumps(result, indent=2)}")

    if result.get("success"):
        data = result.get('data', {})
        records = data.get('records', []) if isinstance(data, dict) else data

        print(f"\n✅ Found {len(records)} records")
        for record in records:
            print(f"  - {record.get('id')}: {record.get('status')} - {record.get('description')}")
    else:
        print(f"❌ Query failed: {result}")
except Exception as e:
    print(f"❌ Error: {e}")
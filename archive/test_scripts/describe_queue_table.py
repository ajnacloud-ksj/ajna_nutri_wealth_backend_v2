#!/usr/bin/env python3
"""
Describe the app_analysis_queue table schema
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

print("Describing app_analysis_queue table...")

try:
    result = client.describe_table("app_analysis_queue")
    if result.get("success"):
        print("✅ Table schema:")
        print(json.dumps(result.get("data", {}), indent=2))
    else:
        print(f"❌ Failed: {result}")
except Exception as e:
    print(f"❌ Error: {e}")
#!/usr/bin/env python3
"""
Test queue table directly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex_client import IbexClient
from datetime import datetime
import uuid
import json

# Initialize Ibex client
client = IbexClient(
    api_url="https://smartlink.ajna.cloud/ibexdb",
    api_key="McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl",
    tenant_id="test-tenant",
    namespace="default"
)

# Try to write a simple record with all fields
test_record = {
    "id": str(uuid.uuid4()),
    "user_id": "test-user",
    "description": "Test chicken biryani",
    "image_url": "",  # Include empty image_url
    "status": "pending",
    "result": "",  # Include empty result
    "error": "",  # Include empty error
    "created_at": datetime.utcnow().isoformat(),
    "updated_at": datetime.utcnow().isoformat(),
    "completed_at": "",  # Include empty completed_at
    "progress": 0
}

print(f"Writing record: {json.dumps(test_record, indent=2)}")

try:
    result = client.write("app_analysis_queue", [test_record])
    if result.get("success"):
        print("✅ Write successful!")
        print(f"Result: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ Write failed: {result}")
except Exception as e:
    print(f"❌ Error: {e}")
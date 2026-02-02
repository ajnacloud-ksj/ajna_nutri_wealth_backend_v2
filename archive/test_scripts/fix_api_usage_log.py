#!/usr/bin/env python3
"""
Fix api_usage_log table schema
"""

import requests
import json
from pathlib import Path

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
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"Error details: {json.dumps(error_detail, indent=2)}")
            except:
                print(f"Error response: {e.response.text}")
        return None

def main():
    print("=== Fixing api_usage_log table ===")

    # Load the correct schema
    schema_file = Path(__file__).parent / "src" / "schemas" / "api_usage_log.json"
    with open(schema_file, 'r') as f:
        schema = json.load(f)

    # Convert our schema format to Ibex format
    ibex_schema = {"fields": {}}

    for field_name, field_config in schema.get("fields", {}).items():
        field_type = field_config.get("type", "string")

        # Map our types to Ibex types
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "boolean": "boolean",
            "timestamp": "string",
            "text": "string",
            "double": "double",
            "long": "long"
        }

        ibex_type = type_mapping.get(field_type, "string")
        ibex_schema["fields"][field_name] = {
            "type": ibex_type,
            "required": field_config.get("required", False)
        }

    print("Schema to create:")
    print(json.dumps(ibex_schema, indent=2))

    # Drop the existing table
    print("\n1. Dropping existing api_usage_log table...")
    result = call_ibex({
        "operation": "DROP_TABLE",
        "table": "api_usage_log"
    })
    if result and result.get('success'):
        print("✓ Table dropped successfully")
    else:
        print("✗ Failed to drop table (may not exist)")

    # Create the table with correct schema
    print("\n2. Creating api_usage_log table with correct schema...")
    result = call_ibex({
        "operation": "CREATE_TABLE",
        "table": "api_usage_log",
        "schema": ibex_schema
    })

    if result and result.get('success'):
        print("✓ Table created successfully")
    else:
        print("✗ Failed to create table")

    # Test write
    print("\n3. Testing write operation...")
    from datetime import datetime
    test_record = {
        "id": f"test-{datetime.utcnow().isoformat()}",
        "user_id": "local-dev-user",
        "endpoint": "/v1/ai/analyze",
        "method": "POST",
        "status_code": 200,
        "model_used": "mock",
        "input_tokens": 100,
        "output_tokens": 200,
        "total_tokens": 300,
        "cost": 0.001,
        "response_time_ms": 1500,
        "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "usage_date": datetime.utcnow().strftime('%Y-%m-%d')
    }

    result = call_ibex({
        "operation": "WRITE",
        "table": "api_usage_log",
        "records": [test_record]
    })

    if result and result.get('success'):
        print("✓ Test write successful")
    else:
        print("✗ Test write failed")

if __name__ == "__main__":
    main()
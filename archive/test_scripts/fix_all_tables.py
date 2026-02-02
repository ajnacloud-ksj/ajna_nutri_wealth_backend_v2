#!/usr/bin/env python3
"""
Fix all Ibex tables to match schemas
"""

import requests
import json
import os
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
    except Exception as e:
        print(f"Ibex Error: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                print(f"Details: {e.response.json()}")
            except:
                print(f"Response: {e.response.text}")
        return None

print("=== Checking and Creating All Tables ===\n")

# Load all schemas
schema_dir = Path(__file__).parent / "src" / "schemas"
schemas = {}

for schema_file in schema_dir.glob("*.json"):
    table_name = schema_file.stem
    with open(schema_file, 'r') as f:
        schemas[table_name] = json.load(f)

print(f"Loaded {len(schemas)} schemas")

# Get existing tables
result = call_ibex({"operation": "LIST_TABLES"})
existing = set()
if result and result.get('success'):
    existing = set(result.get('data', {}).get('tables', []))
    print(f"Found {len(existing)} existing tables\n")

# Process each schema
for table_name, schema in schemas.items():
    if table_name not in existing:
        print(f"Creating table: {table_name}")

        # Convert schema to Ibex format
        ibex_schema = {"fields": {}}

        type_mapping = {
            "string": "string",
            "integer": "integer",
            "boolean": "boolean",
            "timestamp": "string",
            "text": "string",
            "double": "double",
            "long": "long",
            "float": "double"
        }

        for field_name, field_config in schema.get("fields", {}).items():
            field_type = field_config.get("type", "string")
            ibex_type = type_mapping.get(field_type, "string")
            ibex_schema["fields"][field_name] = {
                "type": ibex_type,
                "required": field_config.get("required", False)
            }

        result = call_ibex({
            "operation": "CREATE_TABLE",
            "table": table_name,
            "schema": ibex_schema
        })

        if result and result.get('success'):
            print(f"  ✓ Created {table_name}")
        else:
            print(f"  ✗ Failed to create {table_name}")
    else:
        print(f"✓ Table exists: {table_name}")

print("\nDone!")
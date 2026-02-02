#!/usr/bin/env python3
"""
Test the backend handler directly to debug the issue
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex import IbexClient
import json

# Initialize Ibex client
IBEX_API_URL = "https://smartlink.ajna.cloud/ibexdb"
IBEX_API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

db = IbexClient(IBEX_API_URL, IBEX_API_KEY, TENANT_ID, NAMESPACE)

# Load schemas
schemas_dir = os.path.join(os.path.dirname(__file__), 'src', 'schemas')
schemas = {}
for filename in os.listdir(schemas_dir):
    if filename.endswith('.json'):
        table_name = filename[:-5]
        with open(os.path.join(schemas_dir, filename), 'r') as f:
            schemas[table_name] = json.load(f)

print("=== Testing query with id filter ===")

# Simulate what the handler does
table_name = "users"
query_params = {"id": "local-dev-user"}

# Check if table exists in schemas
if table_name not in schemas:
    print(f"Table {table_name} not in schemas")
else:
    schema_fields = schemas[table_name].get('fields', {})
    print(f"Schema fields: {list(schema_fields.keys())}")

    # Build filters from query parameters
    filters = []
    for key, value in query_params.items():
        # Skip special parameters
        if key in ['limit', 'order_by', 'order_dir', 'sort']:
            continue
        # Only add filter if the field exists in the schema
        if key in schema_fields:
            filters.append({"field": key, "operator": "eq", "value": value})
            print(f"Added filter: field={key}, operator=eq, value={value}")
        else:
            print(f"Field {key} not in schema, skipping")

    print(f"\nFilters to send: {filters}")

    try:
        # Try the query
        print("\nExecuting query...")
        result = db.query(table_name, filters=filters, limit=50)
        print(f"Success: {result.get('success')}")
        if result.get('data'):
            records = result.get('data', {}).get('records', [])
            print(f"Records returned: {len(records)}")
            if records:
                print(f"First record: {json.dumps(records[0], indent=2, default=str)}")
    except Exception as e:
        print(f"Error: {e}")
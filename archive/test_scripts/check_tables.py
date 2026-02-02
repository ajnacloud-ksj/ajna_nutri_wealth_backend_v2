#!/usr/bin/env python3
"""
Check Ibex database table structures
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

def describe_table(table_name):
    """Describe a table structure"""
    print(f"\n=== Table: {table_name} ===")
    result = call_ibex({
        "operation": "DESCRIBE_TABLE",
        "table": table_name
    })

    if result and result.get('success'):
        schema = result.get('data', {}).get('schema', {})
        fields = schema.get('fields', {})
        if fields:
            print(f"Fields in {table_name}:")
            for field_name, field_info in fields.items():
                print(f"  - {field_name}: {field_info.get('type', 'unknown')}")
        else:
            print(f"No schema information available for {table_name}")
        return fields
    else:
        print(f"Could not describe table {table_name}")
    return {}

def query_sample(table_name):
    """Query a sample record from the table"""
    print(f"\nQuerying sample from {table_name}...")
    result = call_ibex({
        "operation": "QUERY",
        "table": table_name,
        "limit": 1
    })

    if result and result.get('success'):
        data = result.get('data', {})
        records = data.get('records', [])
        if records:
            print(f"Sample record: {json.dumps(records[0], indent=2)}")
        else:
            print(f"No records in {table_name}")
    else:
        print(f"Could not query {table_name}")

def main():
    """Check specific tables that are causing issues"""
    print("=== Checking Ibex Table Structures ===")

    # Tables that are causing issues
    critical_tables = ['food_entries', 'users', 'food_items', 'meal_summaries']

    # Load expected schemas
    schema_dir = Path(__file__).parent / "src" / "schemas"

    for table in critical_tables:
        # Check actual table structure
        actual_fields = describe_table(table)

        # Load expected schema
        schema_file = schema_dir / f"{table}.json"
        if schema_file.exists():
            with open(schema_file, 'r') as f:
                expected_schema = json.load(f)
                expected_fields = expected_schema.get('fields', {})

            print(f"\nExpected fields for {table}:")
            for field_name in expected_fields.keys():
                print(f"  - {field_name}")

            # Compare
            print(f"\nComparison for {table}:")
            missing_in_db = set(expected_fields.keys()) - set(actual_fields.keys())
            extra_in_db = set(actual_fields.keys()) - set(expected_fields.keys())

            if missing_in_db:
                print(f"  Missing in DB: {list(missing_in_db)}")
            if extra_in_db:
                print(f"  Extra in DB: {list(extra_in_db)}")
            if not missing_in_db and not extra_in_db:
                print("  ✓ Schema matches!")

        # Query sample
        query_sample(table)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Initialize Ibex database tables based on schema files
"""

import requests
import json
import os
from pathlib import Path

# Configuration - Update these with your actual values
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"  # From Insomnia file
TENANT_ID = "test-tenant"
NAMESPACE = "default"

# Headers for API calls
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

def list_tables():
    """List all existing tables"""
    print("\n=== Listing existing tables ===")
    result = call_ibex({"operation": "LIST_TABLES"})
    if result and result.get('success'):
        tables = result.get('data', {}).get('tables', [])
        print(f"Found {len(tables)} tables: {tables}")
        return tables
    return []

def create_table(table_name, schema):
    """Create a table with the given schema"""
    print(f"\n=== Creating table: {table_name} ===")

    # Convert our schema format to Ibex format
    ibex_schema = {"fields": {}}

    for field_name, field_config in schema.get("fields", {}).items():
        field_type = field_config.get("type", "string")

        # Map our types to Ibex types
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "boolean": "boolean",
            "timestamp": "string",  # Store timestamps as strings
            "text": "string",
            "double": "double",
            "long": "long"
        }

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
        print(f"✓ Table {table_name} created successfully")
        return True
    else:
        print(f"✗ Failed to create table {table_name}")
        return False

def drop_table(table_name):
    """Drop a table"""
    print(f"Dropping table: {table_name}")
    result = call_ibex({
        "operation": "DROP_TABLE",
        "table": table_name
    })
    if result and result.get('success'):
        print(f"✓ Table {table_name} dropped")
        return True
    return False

def main():
    """Main initialization function"""
    print("=== Ibex Database Initialization ===")

    # Load all schema files
    schema_dir = Path(__file__).parent / "src" / "schemas"
    schemas = {}

    print(f"\nLoading schemas from {schema_dir}")
    for schema_file in schema_dir.glob("*.json"):
        table_name = schema_file.stem
        with open(schema_file, 'r') as f:
            schemas[table_name] = json.load(f)
            print(f"  Loaded schema for {table_name}")

    # List existing tables
    existing_tables = list_tables()

    # Automatically create only missing tables (option 1)
    choice = "1"
    print("\n=== Automatically creating missing tables ===")

    if choice == "2":
        # Drop all existing tables
        print("\n=== Dropping existing tables ===")
        for table in existing_tables:
            drop_table(table)

    # Create tables
    print("\n=== Creating tables ===")
    success_count = 0
    fail_count = 0

    for table_name, schema in schemas.items():
        if choice == "1" and table_name in existing_tables:
            print(f"Skipping {table_name} (already exists)")
            continue

        if create_table(table_name, schema):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print("\n=== Summary ===")
    print(f"✓ Successfully created {success_count} tables")
    if fail_count > 0:
        print(f"✗ Failed to create {fail_count} tables")

    # List final state
    list_tables()

if __name__ == "__main__":
    main()
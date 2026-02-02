#!/usr/bin/env python3
"""
Check the actual schema of app_food_entries table in Ibex
"""

import os
import sys
import json
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex_client import IbexClient

load_dotenv()

def main():
    # Initialize Ibex client
    client = IbexClient(
        api_url='https://smartlink.ajna.cloud/ibexdb',
        api_key=os.getenv('IBEX_API_KEY'),
        tenant_id='test-tenant',
        namespace='default'
    )

    print("Checking Ibex tables...")

    # List all tables
    tables_response = client.list_tables()
    if tables_response.get('success'):
        tables = tables_response.get('data', {}).get('tables', [])
        print(f"\nFound {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")

    # Try to get schema for app_food_entries
    print("\nTrying to get schema for app_food_entries...")

    # Try a simple query to see what fields exist
    try:
        result = client.query("app_food_entries", limit=1)
        if result.get('success'):
            data = result.get('data', {})
            records = data.get('records', []) if isinstance(data, dict) else data
            if records:
                print("\nSample record fields:")
                for key in records[0].keys():
                    print(f"  - {key}: {type(records[0][key]).__name__}")
            else:
                print("No records found in table")
        else:
            print(f"Query failed: {result}")
    except Exception as e:
        print(f"Error querying table: {e}")

    # Try to write a minimal record
    print("\nTrying to write a minimal record...")
    test_record = {
        "id": "test-schema-check",
        "user_id": "test-user",
        "description": "Schema test",
        "meal_type": "snack",
        "meal_date": "2026-01-26",
        "meal_time": "12:00",
        "calories": 0,
        "total_protein": 0,
        "total_carbohydrates": 0,
        "total_fats": 0,
        "total_fiber": 0,
        "total_sodium": 0,
        "image_url": "",
        "created_at": "2026-01-26T12:00:00Z",
        "updated_at": "2026-01-26T12:00:00Z"
    }

    try:
        result = client.write("app_food_entries", [test_record])
        if result.get('success'):
            print("✅ Successfully wrote record WITHOUT ingredients field")
            # Clean up
            client.delete("app_food_entries", "test-schema-check")
        else:
            print(f"❌ Failed to write: {result}")
    except Exception as e:
        print(f"❌ Error writing: {e}")

    # Try with each problematic field one at a time
    problematic_fields = ["ingredients", "extracted_nutrients", "confidence_score"]

    for field in problematic_fields:
        print(f"\nTrying to write a record WITH {field} field...")
        test_with_field = test_record.copy()

        if field == "ingredients":
            test_with_field[field] = "[]"
        elif field == "extracted_nutrients":
            test_with_field[field] = "{}"
        elif field == "confidence_score":
            test_with_field[field] = 0.95

        try:
            result = client.write("app_food_entries", [test_with_field])
            if result.get('success'):
                print(f"✅ Successfully wrote record WITH {field} field")
                # Clean up
                client.delete("app_food_entries", "test-schema-check")
            else:
                print(f"❌ Failed to write with {field}: {result}")
        except Exception as e:
            print(f"❌ Error writing with {field}: {e}")

if __name__ == "__main__":
    main()
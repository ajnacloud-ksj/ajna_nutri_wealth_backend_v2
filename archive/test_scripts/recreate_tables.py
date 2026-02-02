#!/usr/bin/env python3
"""
Recreate Ibex tables with correct schemas
Since Ibex doesn't support DROP, we'll create tables with a new suffix
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
    except Exception as e:
        print(f"Ibex Error: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                print(f"Details: {e.response.json()}")
            except:
                print(f"Response: {e.response.text}")
        return None

# Key tables that need fixing
tables_to_fix = {
    "food_entries": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "description": {"type": "string", "required": False},
            "meal_type": {"type": "string", "required": False},
            "meal_date": {"type": "string", "required": False},
            "meal_time": {"type": "string", "required": False},
            "calories": {"type": "double", "required": False},
            "total_protein": {"type": "double", "required": False},
            "total_carbohydrates": {"type": "double", "required": False},
            "total_fats": {"type": "double", "required": False},
            "total_fiber": {"type": "double", "required": False},
            "total_sodium": {"type": "double", "required": False},
            "ingredients": {"type": "string", "required": False},
            "extracted_nutrients": {"type": "string", "required": False},
            "confidence_score": {"type": "double", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "pending_analyses": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "status": {"type": "string", "required": False},
            "category": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "meal_summaries": {
        "fields": {
            "id": {"type": "string", "required": True},
            "food_entry_id": {"type": "string", "required": True},
            "dish_names": {"type": "string", "required": False},
            "meal_suggestion": {"type": "string", "required": False},
            "classification_confidence": {"type": "double", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "workouts": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "workout_name": {"type": "string", "required": False},
            "workout_type": {"type": "string", "required": False},
            "duration_minutes": {"type": "integer", "required": False},
            "calories_burned": {"type": "double", "required": False},
            "workout_date": {"type": "string", "required": False},
            "notes": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "receipts": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "merchant_name": {"type": "string", "required": False},
            "receipt_date": {"type": "string", "required": False},
            "total_amount": {"type": "double", "required": False},
            "tax_amount": {"type": "double", "required": False},
            "category": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "users": {
        "fields": {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": False},
            "full_name": {"type": "string", "required": False},
            "role": {"type": "string", "required": False},
            "user_type": {"type": "string", "required": False},
            "is_subscribed": {"type": "boolean", "required": False},
            "trial_used_today": {"type": "boolean", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    }
}

print("=== Creating/Updating Tables with Correct Schemas ===\n")

for table_name, schema in tables_to_fix.items():
    print(f"Processing {table_name}...")

    # Try to create the table with the correct schema
    # If it already exists, Ibex will return an error but that's OK
    result = call_ibex({
        "operation": "CREATE_TABLE",
        "table": table_name,
        "schema": schema
    })

    if result and result.get('success'):
        print(f"  ✓ Created {table_name}")
    else:
        # Table might already exist, let's try to use the new schema
        # by creating a new version
        new_table_name = f"{table_name}_v2"
        result = call_ibex({
            "operation": "CREATE_TABLE",
            "table": new_table_name,
            "schema": schema
        })

        if result and result.get('success'):
            print(f"  ✓ Created {new_table_name} (since {table_name} already exists)")

            # Copy any existing data
            query_result = call_ibex({
                "operation": "QUERY",
                "table": table_name,
                "limit": 1000
            })

            if query_result and query_result.get('success'):
                records = query_result.get('data', {}).get('records', [])
                if records:
                    # Clean records and copy to new table
                    cleaned_records = []
                    for record in records:
                        cleaned = {}
                        for field in schema['fields'].keys():
                            if field in record:
                                cleaned[field] = record[field]
                        if cleaned.get('id'):  # Only add if has ID
                            cleaned_records.append(cleaned)

                    if cleaned_records:
                        write_result = call_ibex({
                            "operation": "WRITE",
                            "table": new_table_name,
                            "records": cleaned_records
                        })

                        if write_result and write_result.get('success'):
                            print(f"    Copied {len(cleaned_records)} records to {new_table_name}")
        else:
            print(f"  ⚠️  Table {table_name} already exists with current schema")

print("\n=== Testing Write Operations ===\n")

# Test writing to food_entries
test_record = {
    "id": "test-food-entry-1",
    "user_id": "test-user",
    "description": "Test meal",
    "meal_type": "lunch",
    "calories": 500.0,
    "created_at": "2026-01-26 12:00:00"
}

result = call_ibex({
    "operation": "WRITE",
    "table": "food_entries",
    "records": [test_record]
})

if result and result.get('success'):
    print("✓ Successfully wrote to food_entries")
else:
    # Try the v2 table
    result = call_ibex({
        "operation": "WRITE",
        "table": "food_entries_v2",
        "records": [test_record]
    })

    if result and result.get('success'):
        print("✓ Successfully wrote to food_entries_v2")
        print("  Note: You may need to update the backend to use v2 tables")
    else:
        print("✗ Failed to write test record")

print("\nDone!")
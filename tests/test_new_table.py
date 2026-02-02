#!/usr/bin/env python3
"""
Try creating a new simplified table for food entries
"""

import os
import sys
import json
from datetime import datetime
import uuid
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

    print("Attempting to create a new simplified table...")

    # Define a simple schema without problematic fields
    simple_schema = {
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
            "image_url": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    }

    table_name = "app_food_entries_v2"

    # Try to create the table
    try:
        create_result = client.create_table(table_name, simple_schema)
        if create_result.get('success'):
            print(f"✅ Successfully created table: {table_name}")
        else:
            print(f"Table creation result: {create_result}")
    except Exception as e:
        print(f"Table creation error (may already exist): {e}")

    # Now try to write to the new table
    print(f"\nTrying to write to {table_name}...")

    entry_id = str(uuid.uuid4())
    food_entry = {
        "id": entry_id,
        "user_id": "test-user",
        "description": "Test chicken salad",
        "meal_type": "lunch",
        "meal_date": datetime.utcnow().strftime('%Y-%m-%d'),
        "meal_time": datetime.utcnow().strftime('%H:%M'),
        "calories": 350,
        "total_protein": 25,
        "total_carbohydrates": 15,
        "total_fats": 20,
        "total_fiber": 5,
        "total_sodium": 500,
        "image_url": "",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    try:
        result = client.write(table_name, [food_entry])
        if result.get('success'):
            print(f"✅ Successfully wrote to {table_name}!")
            print(f"   Entry ID: {entry_id}")

            # Try to read it back
            query_result = client.query(
                table_name,
                filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                limit=1
            )
            if query_result.get('success'):
                data = query_result.get('data', {})
                records = data.get('records', [])
                if records:
                    print(f"\n📖 Read back entry:")
                    for key, value in records[0].items():
                        if not key.startswith('_'):
                            print(f"   {key}: {value}")
        else:
            print(f"❌ Failed to write: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
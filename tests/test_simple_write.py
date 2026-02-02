#!/usr/bin/env python3
"""
Test writing a simple food entry directly
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

    print("Testing simplified food entry write...")

    # Create a simple food entry - NO problematic fields
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

    print(f"\nWriting entry: {entry_id}")
    print(f"Fields: {list(food_entry.keys())}")

    try:
        result = client.write("app_food_entries", [food_entry])
        if result.get('success'):
            print(f"✅ Successfully wrote food entry!")
            print(f"   Entry ID: {entry_id}")

            # Try to read it back
            query_result = client.query(
                "app_food_entries",
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
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
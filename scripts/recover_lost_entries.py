#!/usr/bin/env python3
"""
Recovery script for food entries that were processed but not saved.
This fixes the data loss bug where entries were marked completed but not stored.
"""

import sys
import os
import json
import boto3
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.ibex_client import IbexClient

# Configuration
COGNITO_USER_ID = '11e37d4a-0061-7046-1feb-7c3e7e9c2516'
USER_EMAIL = 'sbpraonalla@gmail.com'
REGION = 'ap-south-1'
LAMBDA_FUNCTION = 'ajna_nutri_wealth_backend_v2'

def recover_lost_entries():
    """Find and recover food entries that were processed but not saved"""

    print("=" * 70)
    print("RECOVERING LOST FOOD ENTRIES")
    print("=" * 70)

    # Initialize IBEX client
    db = IbexClient(
        api_url=os.environ.get('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb'),
        api_key=os.environ.get('IBEX_API_KEY'),
        tenant_id='default',
        namespace='production'
    )

    # Enable direct Lambda if available
    lambda_name = os.environ.get('IBEX_LAMBDA_NAME', 'ibex-db-lambda')
    if hasattr(db, 'enable_direct_lambda'):
        db.enable_direct_lambda(lambda_name)

    # Initialize Lambda client for invoking backend
    lambda_client = boto3.client('lambda', region_name=REGION)

    print(f"\nTarget User: {USER_EMAIL}")
    print(f"Cognito ID: {COGNITO_USER_ID}\n")

    # 1. Find all pending_analyses entries with status "completed"
    print("1. Querying for completed analyses...")
    pending_result = db.query("app_pending_analyses",
                            filters=[
                                {"field": "status", "operator": "eq", "value": "completed"},
                                {"field": "user_id", "operator": "eq", "value": COGNITO_USER_ID}
                            ])

    if not pending_result.get('success'):
        print(f"   ❌ Failed to query pending_analyses: {pending_result.get('error')}")
        return

    completed_entries = pending_result.get('data', {}).get('records', [])
    print(f"   Found {len(completed_entries)} completed analyses")

    if not completed_entries:
        # Also check without user_id filter
        print("\n   Checking all completed entries (no user filter)...")
        all_pending = db.query("app_pending_analyses",
                              filters=[
                                  {"field": "status", "operator": "eq", "value": "completed"}
                              ])
        if all_pending.get('success'):
            all_completed = all_pending.get('data', {}).get('records', [])
            print(f"   Found {len(all_completed)} total completed entries")
            for entry in all_completed[:5]:  # Show first 5
                print(f"     - ID: {entry.get('id')}, User: {entry.get('user_id', 'NONE')}, Category: {entry.get('category')}")

    # 2. Check each completed entry to see if it exists in food_entries
    lost_entries = []
    for entry in completed_entries:
        entry_id = entry.get('id')
        category = entry.get('category', 'food')

        if category == 'food':
            # Check if exists in food_entries
            check_result = db.query("app_food_entries_v2",
                                   filters=[
                                       {"field": "id", "operator": "eq", "value": entry_id}
                                   ],
                                   limit=1)

            if check_result.get('success'):
                records = check_result.get('data', {}).get('records', [])
                if not records:
                    print(f"   ⚠️ Lost entry found: {entry_id}")
                    lost_entries.append(entry)
                else:
                    print(f"   ✅ Entry {entry_id} exists in food_entries")
            else:
                print(f"   ❌ Error checking entry {entry_id}: {check_result.get('error')}")

    # 3. Special check for the known missing entry
    KNOWN_MISSING_ID = "7e0d3435-a866-41c7-b08e-82460e73f08d"
    print(f"\n2. Checking for known missing entry: {KNOWN_MISSING_ID}")

    # Check pending_analyses
    pending_check = db.query("app_pending_analyses",
                            filters=[
                                {"field": "id", "operator": "eq", "value": KNOWN_MISSING_ID}
                            ],
                            limit=1)

    if pending_check.get('success') and pending_check.get('data', {}).get('records'):
        pending_record = pending_check['data']['records'][0]
        print(f"   Found in pending_analyses: status={pending_record.get('status')}, category={pending_record.get('category')}")

        # Check if in food_entries
        food_check = db.query("app_food_entries_v2",
                             filters=[
                                 {"field": "id", "operator": "eq", "value": KNOWN_MISSING_ID}
                             ],
                             limit=1)

        if food_check.get('success') and not food_check.get('data', {}).get('records'):
            print(f"   ⚠️ NOT in food_entries - this entry was lost!")
            if pending_record not in lost_entries:
                lost_entries.append(pending_record)

    # 4. Recover lost entries
    if lost_entries:
        print(f"\n3. Found {len(lost_entries)} lost entries to recover")

        for entry in lost_entries:
            entry_id = entry.get('id')
            user_id = entry.get('user_id', COGNITO_USER_ID)
            image_url = entry.get('image_url', '')
            description = entry.get('description', 'Recovered food entry')

            print(f"\n   Recovering entry {entry_id}...")

            # Create a basic food entry with default values
            food_entry = {
                "id": entry_id,
                "user_id": user_id or COGNITO_USER_ID,  # Use our known user if missing
                "description": description,
                "meal_type": "snack",
                "calories": 200,  # Default estimate
                "total_protein": 10,
                "total_carbohydrates": 25,
                "total_fats": 8,
                "total_fiber": 2,
                "total_sodium": 100,
                "image_url": image_url,
                "extracted_nutrients": json.dumps({
                    "food_items": [
                        {
                            "name": description or "Recovered food item",
                            "calories": 200,
                            "protein": 10,
                            "carbohydrates": 25,
                            "fats": 8,
                            "fiber": 2,
                            "sodium": 100,
                            "quantity": 1
                        }
                    ],
                    "meal_type": "snack",
                    "recovered": True,
                    "recovery_note": "Entry recovered after processing but not being saved"
                }),
                "analysis_status": "completed",
                "created_at": entry.get('created_at', datetime.utcnow().isoformat()),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Try to store the recovered entry
            result = db.write("app_food_entries_v2", [food_entry])

            if result.get('success'):
                print(f"   ✅ Successfully recovered entry {entry_id}")

                # Verify it was saved
                verify = db.query("app_food_entries_v2",
                                filters=[
                                    {"field": "id", "operator": "eq", "value": entry_id}
                                ],
                                limit=1)

                if verify.get('success') and verify.get('data', {}).get('records'):
                    print(f"   ✅ Verified: Entry now exists in database")
                else:
                    print(f"   ⚠️ Warning: Verification failed")
            else:
                print(f"   ❌ Failed to recover: {result.get('error')}")

                # Try upsert as fallback
                print(f"   Trying upsert...")
                upsert_result = db.upsert("app_food_entries_v2", [food_entry], conflict_fields=["id"])

                if upsert_result.get('success'):
                    print(f"   ✅ Recovered via upsert")
                else:
                    print(f"   ❌ Upsert also failed: {upsert_result.get('error')}")

    else:
        print("\n✅ No lost entries found - all completed entries are properly stored")

    # 5. Final verification - query user's food entries
    print("\n4. Final verification - querying user's food entries...")
    user_entries = db.query("app_food_entries_v2",
                           filters=[
                               {"field": "user_id", "operator": "eq", "value": COGNITO_USER_ID}
                           ])

    if user_entries.get('success'):
        records = user_entries.get('data', {}).get('records', [])
        print(f"   User now has {len(records)} food entries")

        for entry in records[-3:]:  # Show last 3
            print(f"\n   Entry: {entry.get('id')}")
            print(f"     Description: {entry.get('description')}")
            print(f"     Calories: {entry.get('calories')}")
            print(f"     Created: {entry.get('created_at')}")

    print("\n" + "=" * 70)
    print("RECOVERY COMPLETE")
    print("=" * 70)
    print("\nThe async handler has been fixed to prevent future data loss.")
    print("Any lost entries have been recovered with default nutritional values.")
    print("Users should re-analyze images for accurate nutritional data.")

if __name__ == "__main__":
    recover_lost_entries()
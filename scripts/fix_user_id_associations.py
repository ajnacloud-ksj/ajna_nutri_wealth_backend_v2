#!/usr/bin/env python3
"""
Permanent fix for Cognito sub ID association issues.
This script updates existing food entries to have the correct user_id.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.ibex_client import IbexClient
import json

# Configuration
COGNITO_USER_ID = '11e37d4a-0061-7046-1feb-7c3e7e9c2516'
USER_EMAIL = 'sbpraonalla@gmail.com'

def fix_user_associations():
    """Fix user_id associations for existing food entries"""

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

    print("=" * 70)
    print("FIXING USER ID ASSOCIATIONS")
    print("=" * 70)
    print(f"\nTarget Cognito User ID: {COGNITO_USER_ID}")
    print(f"User Email: {USER_EMAIL}\n")

    # 1. Find all food entries without correct user_id
    print("1. Querying for entries with missing or incorrect user_id...")
    all_entries = db.query("app_food_entries_v2")

    if all_entries.get('success'):
        records = all_entries.get('data', {}).get('records', [])
        print(f"   Found {len(records)} total food entries")

        entries_to_fix = []
        for record in records:
            current_user_id = record.get('user_id')
            if not current_user_id or current_user_id != COGNITO_USER_ID:
                entries_to_fix.append(record)
                print(f"   - Entry {record.get('id')}: user_id={current_user_id or 'NONE'}")

        if entries_to_fix:
            print(f"\n2. Found {len(entries_to_fix)} entries that need fixing")

            # Update each entry
            fixed_count = 0
            for entry in entries_to_fix:
                entry_id = entry.get('id')
                print(f"   Updating entry {entry_id}...", end="")

                result = db.update(
                    "app_food_entries_v2",
                    filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                    updates={"user_id": COGNITO_USER_ID}
                )

                if result.get('success'):
                    print(" ✅ Fixed")
                    fixed_count += 1
                else:
                    print(f" ❌ Failed: {result.get('error')}")

            print(f"\n3. Successfully fixed {fixed_count} out of {len(entries_to_fix)} entries")
        else:
            print("\n✅ All entries already have correct user_id!")
    else:
        print(f"   ❌ Failed to query food entries: {all_entries.get('error')}")

    # 4. Also fix pending_analyses entries
    print("\n4. Checking pending_analyses table...")
    pending = db.query("app_pending_analyses")

    if pending.get('success'):
        records = pending.get('data', {}).get('records', [])
        print(f"   Found {len(records)} pending analyses")

        for record in records:
            current_user_id = record.get('user_id')
            if not current_user_id or current_user_id != COGNITO_USER_ID:
                entry_id = record.get('id')
                print(f"   Updating pending entry {entry_id}...", end="")

                result = db.update(
                    "app_pending_analyses",
                    filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                    updates={"user_id": COGNITO_USER_ID}
                )

                if result.get('success'):
                    print(" ✅ Fixed")
                else:
                    print(f" ❌ Failed")

    print("\n" + "=" * 70)
    print("FIX COMPLETE")
    print("=" * 70)
    print("\nAll entries should now be associated with the correct Cognito user ID.")
    print("The UI should display food entries properly after refreshing.")

if __name__ == "__main__":
    fix_user_associations()
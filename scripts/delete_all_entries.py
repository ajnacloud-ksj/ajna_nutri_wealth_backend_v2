#!/usr/bin/env python3
"""
Script to delete all food entries for a specific user
Run with: python3 scripts/delete_all_entries.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.lib.ibex_client_function_url import FunctionURLIbexClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def delete_all_entries():
    """Delete all food entries for dev-user-1"""

    # Get the Lambda URL from environment
    lambda_url = os.getenv('IBEX_API_URL')
    if not lambda_url:
        print("❌ IBEX_API_URL not set in environment")
        return False

    # Initialize Ibex client with Lambda URL
    ibex = FunctionURLIbexClient(function_url=lambda_url)

    user_id = "dev-user-1"
    print(f"Deleting all food entries for user: {user_id}")

    try:
        # First, fetch all entries for this user to get their IDs
        print("Fetching existing entries...")
        result = ibex.query(
            "food_entries",
            filters=[{"field": "user_id", "operator": "eq", "value": user_id}],
            limit=1000  # Get all entries
        )

        if result.get('success') and result.get('data', {}).get('records'):
            entries = result['data']['records']
            print(f"Found {len(entries)} entries to delete")

            # Delete each entry
            deleted_count = 0
            failed_count = 0
            for entry in entries:
                entry_id = entry.get('id')
                if entry_id:
                    print(f"Deleting entry {entry_id}...")
                    delete_result = ibex.delete(
                        "food_entries",
                        filters=[
                            {"field": "id", "operator": "eq", "value": entry_id},
                            {"field": "user_id", "operator": "eq", "value": user_id}
                        ]
                    )
                    if delete_result.get('success'):
                        deleted_count += 1
                        print(f"  ✓ Deleted {entry_id}")
                    else:
                        failed_count += 1
                        print(f"  ✗ Failed to delete {entry_id}: {delete_result.get('error')}")

            print(f"\n📊 Results:")
            print(f"  ✅ Successfully deleted: {deleted_count}")
            if failed_count > 0:
                print(f"  ❌ Failed to delete: {failed_count}")
        else:
            print("No entries found for this user")

        # Verify deletion
        print("\nVerifying deletion...")
        verify_result = ibex.query(
            "food_entries",
            filters=[{"field": "user_id", "operator": "eq", "value": user_id}],
            limit=10
        )

        if verify_result.get('success'):
            remaining = len(verify_result.get('data', {}).get('records', []))
            if remaining == 0:
                print("✅ All entries successfully deleted!")
                print("\n🎉 Database is clean and ready for fresh data!")
            else:
                print(f"⚠️  {remaining} entries still remain")
                print("Remaining entries:")
                for record in verify_result['data']['records'][:5]:
                    print(f"  - {record.get('id')}: {record.get('description', 'No description')}")

    except Exception as e:
        print(f"❌ Error deleting entries: {e}")
        return False

    return True

if __name__ == "__main__":
    # Run the function
    success = delete_all_entries()
    sys.exit(0 if success else 1)
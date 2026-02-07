#!/usr/bin/env python3
"""
Script to grant admin role to a user
Usage: python make_user_admin.py --email user@example.com
"""

import argparse
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lib.ibex_client_optimized import OptimizedIbexClient

def make_user_admin(email: str, api_url: str = None):
    """
    Update user role to admin in the database

    Args:
        email: User's email address
        api_url: IBEX API URL (optional, uses env var if not provided)
    """
    try:
        # Initialize IBEX client
        ibex_url = api_url or os.environ.get('IBEX_API_URL', 'https://qo34glxdv2ltion76gjfvhvdp40dcscb.lambda-url.ap-south-1.on.aws/')
        api_key = os.environ.get('IBEX_API_KEY', 'McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl')

        print(f"🔌 Connecting to IBEX: {ibex_url}")
        db = OptimizedIbexClient(ibex_url, api_key, tenant_id="app_")

        # Query for user by email
        print(f"🔍 Looking for user with email: {email}")
        result = db.query(
            "users_v4",
            filters=[{"field": "email", "operator": "eq", "value": email}],
            limit=1
        )

        if not result or not result.get('success'):
            print(f"❌ Failed to query users table")
            return False

        data = result.get('data', {})
        records = data.get('records', [])

        if not records:
            print(f"❌ User not found with email: {email}")
            print("\n💡 Tip: User must exist in the database first.")
            print("   If user exists in Cognito but not in DB, they need to log in once")
            print("   or run the user sync script.")
            return False

        user = records[0]
        user_id = user.get('id')
        current_role = user.get('role', 'participant')

        print(f"✅ Found user: {user.get('full_name', 'Unknown')} (ID: {user_id})")
        print(f"   Current role: {current_role}")

        if current_role == 'admin':
            print(f"ℹ️  User is already an admin")
            return True

        # Update user role to admin
        print(f"🔄 Updating role to admin...")
        update_result = db.update(
            "users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            updates={
                "role": "admin",
                "updated_at": datetime.utcnow().isoformat()
            }
        )

        if update_result and update_result.get('success'):
            print(f"🎉 Successfully granted admin role to {email}")
            print(f"\n✨ User {email} can now access:")
            print(f"   - Admin dashboard at /admin")
            print(f"   - User management")
            print(f"   - Model configuration")
            print(f"   - Cost analytics")
            return True
        else:
            print(f"❌ Failed to update user role")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def list_all_users(api_url: str = None):
    """List all users and their roles"""
    try:
        ibex_url = api_url or os.environ.get('IBEX_API_URL', 'https://qo34glxdv2ltion76gjfvhvdp40dcscb.lambda-url.ap-south-1.on.aws/')
        api_key = os.environ.get('IBEX_API_KEY', 'McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl')

        db = OptimizedIbexClient(ibex_url, api_key, tenant_id="app_")

        result = db.query("users_v4", limit=100)

        if not result or not result.get('success'):
            print("❌ Failed to query users table")
            return

        data = result.get('data', {})
        records = data.get('records', [])

        if not records:
            print("No users found in database")
            return

        print("\n📋 All Users:")
        print("-" * 80)
        print(f"{'Email':<40} {'Role':<15} {'Type':<15} {'ID':<20}")
        print("-" * 80)

        admins = []
        participants = []
        caretakers = []

        for user in records:
            email = user.get('email', 'N/A')
            role = user.get('role', 'participant')
            user_type = user.get('user_type', 'regular')
            user_id = user.get('id', 'N/A')

            print(f"{email:<40} {role:<15} {user_type:<15} {user_id:<20}")

            if role == 'admin':
                admins.append(email)
            elif role == 'caretaker':
                caretakers.append(email)
            else:
                participants.append(email)

        print("-" * 80)
        print(f"\n📊 Summary:")
        print(f"   Admins: {len(admins)}")
        print(f"   Participants: {len(participants)}")
        print(f"   Caretakers: {len(caretakers)}")
        print(f"   Total: {len(records)}")

        if admins:
            print(f"\n👑 Current Admins:")
            for admin in admins:
                print(f"   - {admin}")

    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Manage user admin roles')
    parser.add_argument('--email', help='Email of user to make admin')
    parser.add_argument('--list', action='store_true', help='List all users and their roles')
    parser.add_argument('--api-url', help='IBEX API URL (optional)')

    args = parser.parse_args()

    if args.list:
        list_all_users(args.api_url)
    elif args.email:
        success = make_user_admin(args.email, args.api_url)
        sys.exit(0 if success else 1)
    else:
        print("Usage:")
        print("  Make user admin:  python make_user_admin.py --email user@example.com")
        print("  List all users:   python make_user_admin.py --list")
        sys.exit(1)

if __name__ == "__main__":
    main()
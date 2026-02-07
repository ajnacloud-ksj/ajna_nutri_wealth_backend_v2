#!/usr/bin/env python3
"""
Make sbpraonalla@gmail.com an admin using IBEX API with authentication
"""

import requests
import json
from datetime import datetime

# Configuration
IBEX_API_URL = "https://qo34glxdv2ltion76gjfvhvdp40dcscb.lambda-url.ap-south-1.on.aws"
IBEX_API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
USER_EMAIL = "sbpraonalla@gmail.com"

def make_user_admin():
    """
    Update user role to admin in IBEX database
    """
    print("=" * 60)
    print("  MAKING sbpraonalla@gmail.com ADMIN")
    print("=" * 60)
    print()

    # Headers with API key
    headers = {
        "Content-Type": "application/json",
        "x-api-key": IBEX_API_KEY
    }

    # Step 1: Query for the user
    print("🔍 Step 1: Looking for user in database...")

    query_payload = {
        "operation": "query",
        "table_name": "app_users_v4",
        "filters": [
            {
                "field": "email",
                "operator": "eq",
                "value": USER_EMAIL
            }
        ],
        "limit": 1
    }

    try:
        response = requests.post(
            IBEX_API_URL,
            headers=headers,
            json=query_payload,
            timeout=30
        )

        print(f"   Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success') and result.get('data', {}).get('records'):
                user = result['data']['records'][0]
                user_id = user.get('id')
                current_role = user.get('role', 'participant')

                print(f"✅ Found user!")
                print(f"   ID: {user_id}")
                print(f"   Current role: {current_role}")

                if current_role == 'admin':
                    print(f"ℹ️  User is already an admin!")
                    return True

                # Step 2: Update user role to admin
                print(f"\n🔄 Step 2: Updating role to admin...")

                update_payload = {
                    "operation": "update",
                    "table_name": "app_users_v4",
                    "filters": [
                        {
                            "field": "id",
                            "operator": "eq",
                            "value": user_id
                        }
                    ],
                    "updates": {
                        "role": "admin",
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }

                update_response = requests.post(
                    IBEX_API_URL,
                    headers=headers,
                    json=update_payload,
                    timeout=30
                )

                if update_response.status_code == 200:
                    update_result = update_response.json()
                    if update_result.get('success'):
                        print(f"🎉 SUCCESS! User role updated to admin")
                        return True
                    else:
                        print(f"❌ Update failed: {update_result}")
                else:
                    print(f"❌ Update failed with status: {update_response.status_code}")
                    print(f"   Response: {update_response.text}")

            else:
                print(f"❌ User not found in database")
                print(f"\n📝 Creating new admin user...")

                # Create the user as admin
                create_payload = {
                    "operation": "write",
                    "table_name": "app_users_v4",
                    "data": [
                        {
                            "id": f"cognito-{USER_EMAIL.replace('@', '-').replace('.', '-')}",
                            "email": USER_EMAIL,
                            "full_name": "SB Prao Nalla",
                            "role": "admin",
                            "user_type": "regular",
                            "is_subscribed": False,
                            "trial_used_today": 0,
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat()
                        }
                    ]
                }

                create_response = requests.post(
                    IBEX_API_URL,
                    headers=headers,
                    json=create_payload,
                    timeout=30
                )

                if create_response.status_code == 200:
                    create_result = create_response.json()
                    if create_result.get('success'):
                        print(f"✅ Admin user created successfully!")
                        return True
                    else:
                        print(f"❌ Create failed: {create_result}")
                else:
                    print(f"❌ Create failed with status: {create_response.status_code}")
                    print(f"   Response: {create_response.text}")

        else:
            print(f"❌ Query failed with status: {response.status_code}")
            print(f"   Response: {response.text}")

    except requests.exceptions.Timeout:
        print(f"❌ Request timeout - IBEX API might be slow")
    except Exception as e:
        print(f"❌ Error: {e}")

    return False

def verify_instructions():
    """
    Instructions for verifying admin access
    """
    print("\n" + "=" * 60)
    print("  HOW TO VERIFY ADMIN ACCESS")
    print("=" * 60)
    print()
    print("1. Go to: https://aro.triviz.cloud")
    print("2. Log in with: sbpraonalla@gmail.com")
    print("3. After login, look for 'Admin' in the sidebar")
    print("4. Click on Admin to access the admin dashboard")
    print()
    print("Admin Dashboard Features:")
    print("  • User Management - View and manage all users")
    print("  • Cost Analytics - Track API usage costs")
    print("  • AI Models - Configure AI providers and models")
    print()
    print("If you don't see the Admin option:")
    print("  1. Log out and log back in")
    print("  2. Hard refresh the page (Ctrl+Shift+R or Cmd+Shift+R)")
    print("  3. Clear browser cache if needed")

if __name__ == "__main__":
    success = make_user_admin()

    if success:
        print("\n✅ sbpraonalla@gmail.com now has admin access!")
        verify_instructions()
    else:
        print("\n⚠️  Could not complete the admin setup")
        print("\nAlternative approach:")
        print("1. The user might need to log in first to create their record")
        print("2. Then run this script again")
        print("3. Or manually update in AWS Console")
#!/usr/bin/env python3
"""
Direct script to grant admin role to sbpraonalla@gmail.com
This bypasses the API and updates the database directly
"""

import json
import requests
import os

def grant_admin_via_lambda():
    """
    Grant admin role by calling the Lambda function directly
    """
    # Lambda function URL
    LAMBDA_URL = "https://u5m63wnxrakgzxggb5ppfccuju0bkyvg.lambda-url.ap-south-1.on.aws"

    # User details
    USER_EMAIL = "sbpraonalla@gmail.com"

    print("=" * 60)
    print("  GRANTING ADMIN ROLE TO sbpraonalla@gmail.com")
    print("=" * 60)
    print()

    # Step 1: First, create/update the user in the database
    print("📝 Step 1: Ensuring user exists in database...")

    user_data = {
        "email": USER_EMAIL,
        "full_name": "SB Prao Nalla",
        "role": "admin",  # Set admin role directly
        "user_type": "regular",
        "is_subscribed": False,
        "trial_used_today": 0
    }

    headers = {
        "Content-Type": "application/json",
        "x-user-id": "admin-setup"  # Temporary user ID for setup
    }

    # Try to create/update the user
    try:
        response = requests.post(
            f"{LAMBDA_URL}/v1/users",
            headers=headers,
            json=user_data,
            timeout=10
        )

        if response.status_code in [200, 201]:
            print(f"✅ User created/updated successfully with admin role")
            print(f"   Response: {response.status_code}")
            return True
        elif response.status_code == 409:
            print(f"ℹ️  User already exists, attempting update...")
            # User exists, try to update instead
            return update_existing_user(LAMBDA_URL, USER_EMAIL, headers)
        else:
            print(f"⚠️  Unexpected response: {response.status_code}")
            print(f"   Body: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def update_existing_user(lambda_url, email, headers):
    """
    Update existing user to admin role
    """
    print("📝 Step 2: Updating existing user role to admin...")

    # First, get the user ID
    try:
        response = requests.get(
            f"{lambda_url}/v1/users?email={email}",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            users = response.json()
            if users and len(users) > 0:
                user_id = users[0].get('id')

                # Update the user role
                update_data = {
                    "role": "admin"
                }

                update_response = requests.put(
                    f"{lambda_url}/v1/users/{user_id}",
                    headers=headers,
                    json=update_data,
                    timeout=10
                )

                if update_response.status_code == 200:
                    print(f"✅ User role updated to admin successfully")
                    return True
                else:
                    print(f"❌ Failed to update user: {update_response.status_code}")
                    print(f"   Body: {update_response.text}")
                    return False

    except Exception as e:
        print(f"❌ Error updating user: {e}")
        return False

    return False

def verify_admin_access():
    """
    Provide instructions for verifying admin access
    """
    print("\n" + "=" * 60)
    print("  VERIFICATION STEPS")
    print("=" * 60)
    print()
    print("To verify admin access:")
    print("1. Log in to the application at: https://aro.triviz.cloud")
    print("2. Use email: sbpraonalla@gmail.com")
    print("3. Navigate to: https://aro.triviz.cloud/admin")
    print("4. You should see the admin dashboard with:")
    print("   - User Management")
    print("   - Cost Analytics")
    print("   - AI Model Configuration")
    print()
    print("If you don't see the Admin option in the sidebar:")
    print("1. Log out and log back in")
    print("2. Clear browser cache")
    print("3. The system may need a few minutes to sync")

if __name__ == "__main__":
    success = grant_admin_via_lambda()

    if success:
        print("\n🎉 SUCCESS! sbpraonalla@gmail.com should now have admin access")
        verify_admin_access()
    else:
        print("\n⚠️  Could not grant admin access automatically")
        print("\n📋 MANUAL STEPS REQUIRED:")
        print("1. Access the database directly through AWS Console")
        print("2. Find the users table (app_users_v4)")
        print("3. Locate user with email: sbpraonalla@gmail.com")
        print("4. Update the 'role' field to: admin")
        print("5. Save the changes")
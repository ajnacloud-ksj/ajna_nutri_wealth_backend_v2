#!/usr/bin/env python3
"""
Setup NutriWealth database with correct tenant configuration
This replaces test-tenant with nutriwealth
"""

import os
import sys
import json
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from lib.ibex_client_optimized import OptimizedIbexClient as IbexClient
except ImportError:
    from lib.ibex_client import IbexClient

def setup_nutriwealth_database():
    print("="*60)
    print("  NUTRIWEALTH DATABASE SETUP")
    print("="*60)

    # Load env
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    # Configuration - Use nutriwealth instead of test-tenant
    TENANT_ID = "nutriwealth"
    NAMESPACE = "default"

    api_url = os.environ.get('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb')
    api_key = os.environ.get('IBEX_API_KEY', '')

    if not api_url:
        print("❌ IBEX_API_URL not set")
        return False

    print(f"\n📋 Configuration:")
    print(f"   API URL: {api_url}")
    print(f"   Tenant: {TENANT_ID}")
    print(f"   Namespace: {NAMESPACE}")
    print(f"   Database: {TENANT_ID}_{NAMESPACE}")

    # Initialize client with nutriwealth tenant
    print(f"\n🔌 Connecting to IBEX...")
    client = IbexClient(api_url, api_key, TENANT_ID, NAMESPACE)

    # Enable direct lambda if available
    lambda_name = os.environ.get('IBEX_LAMBDA_NAME', 'ibex-db-lambda')
    if hasattr(client, 'enable_direct_lambda'):
        client.enable_direct_lambda(lambda_name)
        print(f"   Using direct Lambda: {lambda_name}")

    # Schema directory
    schema_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'schemas')
    if not os.path.exists(schema_dir):
        print(f"❌ Schema directory not found: {schema_dir}")
        return False

    # List existing tables
    print(f"\n📊 Checking existing tables...")
    try:
        existing_res = client.list_tables()
        existing_tables = existing_res.get('data', {}).get('tables', [])
        print(f"   Found {len(existing_tables)} existing tables")
    except Exception as e:
        print(f"⚠️  Could not list tables: {e}")
        existing_tables = []

    # Create tables from schemas
    print(f"\n🏗️  Creating tables...")
    created = 0
    skipped = 0
    failed = 0

    # Priority tables (create these first)
    priority_tables = ['users_v4', 'pending_analyses', 'food_entries_v2']

    # Process all schema files
    schema_files = [f for f in os.listdir(schema_dir) if f.endswith('.json')]

    # Sort so priority tables come first
    schema_files.sort(key=lambda x: 0 if x[:-5] in priority_tables else 1)

    for filename in schema_files:
        table_name = filename[:-5]  # Remove .json
        full_table_name = f"app_{table_name}"

        try:
            with open(os.path.join(schema_dir, filename), 'r') as f:
                schema = json.load(f)

            if full_table_name in existing_tables:
                print(f"   ⏭️  {full_table_name} - Already exists")
                skipped += 1
            else:
                print(f"   🔨 Creating {full_table_name}...")
                res = client.create_table(full_table_name, schema, if_not_exists=True)

                if res.get('success'):
                    print(f"   ✅ Created {full_table_name}")
                    created += 1
                else:
                    error = res.get('error', 'Unknown error')
                    if 'already exists' in str(error).lower():
                        print(f"   ⏭️  {full_table_name} - Already exists")
                        skipped += 1
                    else:
                        print(f"   ❌ Failed to create {full_table_name}: {error}")
                        failed += 1

        except Exception as e:
            print(f"   ❌ Error processing {filename}: {e}")
            failed += 1

    # Create test user
    print(f"\n👤 Creating test user...")
    test_user_id = "11e37d4a-0061-7046-1feb-7c3e7e9c2516"
    test_user_email = "sbpraonalla@gmail.com"

    try:
        # Check if user exists
        user_result = client.query("app_users_v4",
                                  filters=[
                                      {"field": "id", "operator": "eq", "value": test_user_id}
                                  ],
                                  limit=1)

        if user_result.get('success') and not user_result.get('data', {}).get('records'):
            # Create the user
            user_data = {
                "id": test_user_id,
                "email": test_user_email,
                "name": "Test User",
                "role": "admin",
                "created_at": "2024-01-01T00:00:00Z",
                "profile": json.dumps({
                    "preferences": {},
                    "settings": {"is_admin": True}
                })
            }

            write_result = client.write("app_users_v4", [user_data])

            if write_result.get('success'):
                print(f"   ✅ Created test user: {test_user_email}")
            else:
                print(f"   ❌ Failed to create user: {write_result.get('error')}")
        else:
            print(f"   ⏭️  User already exists: {test_user_email}")
    except Exception as e:
        print(f"   ⚠️  Could not check/create user: {e}")

    # Summary
    print("\n" + "="*60)
    print("  SETUP COMPLETE")
    print("="*60)
    print(f"\n📊 Summary:")
    print(f"   Database: {TENANT_ID}_{NAMESPACE}")
    print(f"   Tables created: {created}")
    print(f"   Tables skipped: {skipped}")
    print(f"   Tables failed: {failed}")

    if failed == 0:
        print("\n✅ Database setup successful!")
        print("\n🚀 Next steps:")
        print("   1. Commit and push the tenants.json changes")
        print("   2. Deploy the backend")
        print("   3. Test async processing")
        return True
    else:
        print(f"\n⚠️  Setup completed with {failed} failures")
        return False

if __name__ == "__main__":
    success = setup_nutriwealth_database()
    sys.exit(0 if success else 1)
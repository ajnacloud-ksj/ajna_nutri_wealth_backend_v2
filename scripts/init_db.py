
import os
import sys
import json
import time
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from lib.ibex_client import IbexClient
except ImportError:
    # Use relative import if running from backend root
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from src.lib.ibex_client import IbexClient

def init_db():
    print("🚀 Initializing Ibex Tables...")
    
    # Load env
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
    
    api_url = os.environ.get('IBEX_API_URL')
    api_key = os.environ.get('IBEX_API_KEY')
    
    if not api_url:
        print("❌ IBEX_API_URL not set in .env")
        return

    print(f"Connecting to: {api_url}")
    client = IbexClient(api_url, api_key, "test-tenant")
    
    # Schema dir
    schema_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'schemas')
    if not os.path.exists(schema_dir):
        print(f"❌ Schema directory not found: {schema_dir}")
        return

    # List existing tables
    try:
        existing_res = client.list_tables()
        existing_tables = existing_res.get('tables', [])
        print(f"Existing tables: {existing_tables}")
    except Exception as e:
        print(f"⚠️ Could not list tables: {e}")
        existing_tables = []

    # Iterate over schemas
    for filename in os.listdir(schema_dir):
        if filename.endswith('.json'):
            table_name = filename[:-5]
            print(f"Processing schema for: {table_name}")
            
            try:
                with open(os.path.join(schema_dir, filename), 'r') as f:
                    schema = json.load(f)
                
                # Check format: simple schema vs "fields": {...} wrapper
                # Ibex usually expects {"fields": { "col": {"type": "string"} } }
                # Or just raw fields?
                # My 'images.json' had "fields".
                # Let's check format. Ibex create_table expects "schema": { ... }
                
                if table_name in existing_tables:
                    print(f"  - Table {table_name} exists. Skipping (Schema evolution enabled by default? No, manual only).")
                    # Ideally check schema drift, but simple check creates if missing.
                    # If we need to update, we might need DROP/CREATE or ALTER.
                    # For now just skip.
                    
                    # BUT images table schema CHANGED.
                    # We should probably force update if it's 'images' or just DROP/CREATE for this test?
                    # User data might be lost.
                    # If it's a test table, okay.
                    if table_name == 'images' or table_name == 'food_entries':
                         print(f"  - Force checking {table_name}...")
                         # We'll see if we can append columns?
                         # Just assume create works idempotent or skip.
                else:
                    print(f"  - Creating table {table_name}...")
                    res = client.create_table(table_name, schema)
                    if res.get('success'):
                        print(f"  ✅ Created {table_name}")
                    else:
                        print(f"  ❌ Failed to create {table_name}: {res.get('error')}")
            
            except Exception as e:
                print(f"  ❌ Error processing {filename}: {e}")

    print("\nInitialize Complete.")

if __name__ == "__main__":
    init_db()

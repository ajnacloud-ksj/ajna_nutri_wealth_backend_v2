import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.join(os.getcwd(), 'backend/src'))

from lib.ibex_client import IbexClient

def setup_tables():
    api_url = os.environ.get('IBEX_API_URL')
    api_key = os.environ.get('IBEX_API_KEY')
    client = IbexClient(api_url, api_key, "test-tenant", "default")
    
    tables = {
        "receipts.json": "app_receipts",
        "receipt_items.json": "app_receipt_items",
        "workouts.json": "app_workouts",
        "workout_exercises.json": "app_workout_exercises"
    }
    
    schemas_dir = os.path.join(os.getcwd(), 'backend/src/schemas')
    
    for filename, table_name in tables.items():
        schema_path = os.path.join(schemas_dir, filename)
        if not os.path.exists(schema_path):
            print(f"Skipping {filename} (not found)")
            continue
            
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            
        print(f"Creating table {table_name}...")
        res = client.create_table(table_name, schema)
        print(f"Result: {res}")

if __name__ == "__main__":
    setup_tables()

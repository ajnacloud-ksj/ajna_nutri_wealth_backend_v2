#!/usr/bin/env python3
"""
Clean NaN values from food_entries table
"""

import requests
import json
from datetime import datetime

# Configuration
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

# Query all food_entries
payload = {
    "tenant_id": TENANT_ID,
    "namespace": NAMESPACE,
    "operation": "QUERY",
    "table": "food_entries",
    "limit": 100
}

print("Querying food_entries...")
response = requests.post(API_URL, headers=headers, json=payload)

if response.ok:
    # Parse with NaN handling
    import re
    response_text = re.sub(r'\bNaN\b', 'null', response.text)
    data = json.loads(response_text)

    records = data.get('data', {}).get('records', [])
    print(f"Found {len(records)} records")

    # Clean up records - replace None/null with proper defaults
    for record in records:
        needs_update = False

        # Replace null/None with 0 for numeric fields
        numeric_fields = ['total_carbohydrates', 'total_fats', 'total_fiber', 'total_sodium', 'confidence_score']
        for field in numeric_fields:
            if record.get(field) is None:
                record[field] = 0
                needs_update = True

        if needs_update:
            # Update the record
            update_payload = {
                "tenant_id": TENANT_ID,
                "namespace": NAMESPACE,
                "operation": "UPDATE",
                "table": "food_entries",
                "filters": [{"field": "id", "operator": "eq", "value": record['id']}],
                "updates": {field: record[field] for field in numeric_fields}
            }

            print(f"Updating record {record['id']}...")
            update_response = requests.post(API_URL, headers=headers, json=update_payload)
            if update_response.ok:
                print(f"✓ Updated {record['id']}")
            else:
                print(f"✗ Failed to update {record['id']}: {update_response.text}")

    print("Done!")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
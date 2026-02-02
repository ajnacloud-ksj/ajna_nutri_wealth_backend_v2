#!/bin/bash
API_URL="http://localhost:8000"

echo "=== Testing Receipt Analysis ==="

# Minimal test receipt description
DESC="Receipt from Walmart. Milk \$4.50, Bread \$3.25, Eggs \$5.99. Total: \$13.74"

cat <<EOF > payload_receipt.json
{
  "description": "$DESC"
}
EOF

echo "Sending receipt analysis request..."
RESP=$(curl -s -X POST "$API_URL/v1/analyze" \
  -H "Content-Type: application/json" \
  -d @payload_receipt.json)

echo "Response: $RESP"

ENTRY_ID=$(echo "$RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('entry_id', ''))" 2>/dev/null)

if [ -z "$ENTRY_ID" ]; then
    echo "❌ Failed to create receipt"
    exit 1
fi

echo "✅ Receipt created with ID: $ENTRY_ID"

# Check if items were created
echo ""
echo "Checking receipt items..."
sleep 2

python3 -c "
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.append('backend/src')

from lib.ibex_client import IbexClient

api_url = os.environ.get('IBEX_API_URL')
api_key = os.environ.get('IBEX_API_KEY')
client = IbexClient(api_url, api_key, 'test-tenant', 'default')

# Query receipt
result = client.query('app_receipts', filters=[{'field': 'id', 'operator': 'eq', 'value': '$ENTRY_ID'}], limit=1)
if result.get('success'):
    receipts = result.get('data', {}).get('records', [])
    if receipts:
        receipt = receipts[0]
        print(f\"✅ Receipt found: {receipt.get('vendor')} - Total: \\\${receipt.get('total_amount')}\")
    else:
        print('❌ Receipt not found')
else:
    print('❌ Query failed')

# Query items
items_result = client.query('app_receipt_items', filters=[{'field': 'receipt_id', 'operator': 'eq', 'value': '$ENTRY_ID'}], limit=10)
if items_result.get('success'):
    items = items_result.get('data', {}).get('records', [])
    print(f\"✅ Found {len(items)} receipt items:\")
    for item in items:
        print(f\"   - {item.get('name')}: \\\${item.get('price')} x {item.get('quantity')}\")
else:
    print('❌ Items query failed')
"

rm payload_receipt.json

#!/usr/bin/env python3
"""
Local E2E test for food and receipt analysis.
Invokes the Lambda handler directly (no API Gateway, no Docker).
Uses AUTH_MODE=local so no Cognito token needed.
Connects to cloud IbexDB via API Gateway.
"""

import os
import sys
import json
import base64
import time

# Setup environment BEFORE importing app
os.environ['AUTH_MODE'] = 'local'
os.environ['ENVIRONMENT'] = 'development'
os.environ['ENABLE_SQS'] = 'false'
os.environ['ENABLE_LAMBDA_ASYNC'] = 'false'

# Load .env for API keys
env_file = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in ('AUTH_MODE', 'ENVIRONMENT', 'ENABLE_SQS', 'ENABLE_LAMBDA_ASYNC'):
                    os.environ.setdefault(key, value.strip('"').strip("'"))

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app import lambda_handler


class FakeContext:
    aws_request_id = 'local-test-001'


def make_event(method, path, body=None, user_id='test-user-local'):
    event = {
        'httpMethod': method,
        'path': path,
        'headers': {
            'Content-Type': 'application/json',
            'X-User-ID': user_id,
        },
        'queryStringParameters': {},
        'body': json.dumps(body) if body else None,
    }
    return event


def test_health():
    print("\n=== Test: Health Check ===")
    event = make_event('GET', '/health')
    result = lambda_handler(event, FakeContext())
    body = json.loads(result['body'])
    print(f"Status: {result['statusCode']}, Body: {json.dumps(body, indent=2)}")
    assert result['statusCode'] == 200, f"Health check failed: {body}"
    print("PASS")


def test_food_text():
    print("\n=== Test: Food Analysis (text only) ===")
    event = make_event('POST', '/v1/analyze', {
        'description': 'chicken caesar salad with croutons and parmesan cheese, about 350 calories'
    })
    start = time.time()
    result = lambda_handler(event, FakeContext())
    elapsed = time.time() - start
    body = json.loads(result['body'])
    print(f"Status: {result['statusCode']} ({elapsed:.1f}s)")
    print(f"Category: {body.get('category')}")
    print(f"Entry ID: {body.get('entry_id')}")
    if body.get('data'):
        data = body['data']
        print(f"Food items: {len(data.get('food_items', []))}")
        print(f"Total calories: {data.get('total_calories')}")
    if not body.get('success'):
        print(f"ERROR: {body.get('error')}")
    else:
        print("PASS")
    return body


def test_food_image(image_path):
    print(f"\n=== Test: Food Analysis (image: {os.path.basename(image_path)}) ===")
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    event = make_event('POST', '/v1/analyze', {
        'description': 'What food is this?',
        'image_url': f'data:image/jpeg;base64,{b64}'
    })
    start = time.time()
    result = lambda_handler(event, FakeContext())
    elapsed = time.time() - start
    body = json.loads(result['body'])
    print(f"Status: {result['statusCode']} ({elapsed:.1f}s)")
    print(f"Category: {body.get('category')}")
    print(f"Entry ID: {body.get('entry_id')}")
    if body.get('data'):
        data = body['data']
        print(f"Food items: {len(data.get('food_items', []))}")
        for item in data.get('food_items', [])[:5]:
            print(f"  - {item.get('name')}: {item.get('calories')} cal")
        print(f"Total calories: {data.get('total_calories')}")
    if not body.get('success'):
        print(f"ERROR: {body.get('error')}")
    else:
        print("PASS")
    return body


def test_receipt_image(image_path):
    print(f"\n=== Test: Receipt Analysis (image: {os.path.basename(image_path)}) ===")
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    event = make_event('POST', '/v1/analyze', {
        'description': 'grocery receipt',
        'image_url': f'data:image/jpeg;base64,{b64}'
    })
    start = time.time()
    result = lambda_handler(event, FakeContext())
    elapsed = time.time() - start
    body = json.loads(result['body'])
    print(f"Status: {result['statusCode']} ({elapsed:.1f}s)")
    print(f"Category: {body.get('category')}")
    print(f"Entry ID: {body.get('entry_id')}")
    if body.get('summary'):
        s = body['summary']
        print(f"Merchant: {s.get('merchant')}")
        print(f"Total: ${s.get('total')}")
        print(f"Items: {s.get('items')}")
    if body.get('data'):
        data = body['data']
        if data.get('items'):
            print(f"Receipt items ({len(data['items'])}):")
            for item in data['items'][:5]:
                print(f"  - {item.get('name')}: ${item.get('total_price', item.get('price', 'N/A'))}")
    if not body.get('success'):
        print(f"ERROR: {body.get('error')}")
    else:
        print("PASS")
    return body


def _extract_records(body):
    """Extract records from various response formats."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        data = body.get('data', body)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get('records', [])
    return []


def test_query_food_entries():
    print("\n=== Test: Query Food Entries ===")
    event = make_event('GET', '/v1/app_food_entries_v2')
    event['queryStringParameters'] = {'limit': '5'}
    result = lambda_handler(event, FakeContext())
    body = json.loads(result['body'])
    records = _extract_records(body)
    print(f"Status: {result['statusCode']}, Records: {len(records)}")
    for r in records[:3]:
        if isinstance(r, dict):
            print(f"  - {r.get('id', 'N/A')[:8]}... {r.get('description', 'N/A')[:40]}")
    print("PASS")


def test_query_receipts():
    print("\n=== Test: Query Receipts ===")
    event = make_event('GET', '/v1/app_receipts')
    event['queryStringParameters'] = {'limit': '5'}
    result = lambda_handler(event, FakeContext())
    body = json.loads(result['body'])
    records = _extract_records(body)
    print(f"Status: {result['statusCode']}, Records: {len(records)}")
    for r in records[:3]:
        print(f"  - {r.get('vendor', 'N/A')} ${r.get('total_amount', 'N/A')}")
    print("PASS")


def test_natural_text(description, expected_category=None):
    """Test natural language input — let AI classify and process."""
    print(f"\n=== Test: Natural Text ===")
    print(f"Input: \"{description}\"")
    event = make_event('POST', '/v1/analyze', {'description': description})
    start = time.time()
    result = lambda_handler(event, FakeContext())
    elapsed = time.time() - start
    body = json.loads(result['body'])
    category = body.get('category')
    print(f"Status: {result['statusCode']} ({elapsed:.1f}s)")
    print(f"Category: {category}")
    if category == 'food':
        print(f"Summary: {body.get('summary', {}).get('description')} | {body.get('summary', {}).get('calories')} cal | {body.get('summary', {}).get('meal_type')}")
    elif category == 'receipt':
        s = body.get('summary', {})
        print(f"Merchant: {s.get('merchant')} | Total: ${s.get('total')} | Items: {s.get('items')}")
    elif category == 'workout':
        s = body.get('summary', body.get('data', {}))
        print(f"Type: {s.get('workout_type', s.get('type', '?'))} | Duration: {s.get('duration_minutes', s.get('duration', '?'))} min | Calories: {s.get('calories_burned', s.get('calories', '?'))}")
    if not body.get('success'):
        print(f"ERROR: {body.get('error')}")
        print(f"Full response: {json.dumps(body, indent=2, default=str)[:500]}")
    else:
        if expected_category and category != expected_category:
            print(f"WARNING: Expected category '{expected_category}', got '{category}'")
        print("PASS")
    return body


if __name__ == '__main__':
    print("=" * 60)
    print("NutriWealth Local E2E Test")
    print("=" * 60)

    test_health()

    # Natural language tests
    test_natural_text("I ate biryani with salad", "food")
    test_natural_text("purchased 1 coffee for 5$ by cash", "receipt")
    test_natural_text("worked out cycling for 20 mins", "workout")

    # Image tests
    food_img = '/Users/pnalla/Downloads/Receipts/fried_rice.jpg'
    if os.path.exists(food_img):
        test_food_image(food_img)

    receipt_img = '/Users/pnalla/Downloads/Receipts/walmart.jpg'
    if os.path.exists(receipt_img):
        test_receipt_image(receipt_img)

    # Query stored data
    test_query_food_entries()
    test_query_receipts()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

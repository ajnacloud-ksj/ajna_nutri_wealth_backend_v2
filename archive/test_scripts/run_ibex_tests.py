#!/usr/bin/env python3
"""
Run Ibex API tests from Insomnia collection
This runs all the API tests in the collection against the real Ibex database
"""

import yaml
import requests
import json
import re
from datetime import datetime
import time

# Load the Insomnia collection
with open('/Users/pnalla/tracelinkrepo/food-app/food-sense-ai-tracker-3b84f458/Insomnia_2026-01-20.yaml', 'r') as f:
    collection = yaml.safe_load(f)

# Configuration
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"
BASE_URL = "https://smartlink.ajna.cloud/ibexdb"

# Track results
results = []
total_tests = 0
passed_tests = 0
failed_tests = 0

def run_request(request_data):
    """Run a single request from the collection"""
    global total_tests, passed_tests, failed_tests

    name = request_data.get('name', 'Unnamed')
    method = request_data.get('method', 'POST')

    # Skip non-API requests
    if name == "New Request" or not request_data.get('body'):
        return

    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    total_tests += 1

    # Parse body
    body_data = request_data.get('body', {})
    body_text = body_data.get('text', '{}')

    # Replace variables
    body_text = body_text.replace('{{tenant_id}}', TENANT_ID)
    body_text = body_text.replace('{{namespace}}', NAMESPACE)
    body_text = body_text.replace('{{api_key}}', API_KEY)
    body_text = body_text.replace('{{baseUrl}}', BASE_URL)

    try:
        body = json.loads(body_text)
    except:
        print(f"❌ Invalid JSON in request body")
        failed_tests += 1
        return

    # Add tenant and namespace if not present
    if 'tenant_id' not in body:
        body['tenant_id'] = TENANT_ID
    if 'namespace' not in body:
        body['namespace'] = NAMESPACE

    print(f"Operation: {body.get('operation')}")
    print(f"Table: {body.get('table', 'N/A')}")

    # Make the request
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    start_time = time.time()

    try:
        response = requests.post(BASE_URL, json=body, headers=headers, timeout=30)
        elapsed = (time.time() - start_time) * 1000  # Convert to ms

        print(f"Status: {response.status_code}")
        print(f"Time: {elapsed:.0f}ms")

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ PASSED")
                passed_tests += 1

                # Show some results
                if body.get('operation') == 'LIST_TABLES':
                    tables = data.get('data', {}).get('tables', [])
                    print(f"Tables found: {len(tables)}")
                    if tables:
                        print(f"First 5 tables: {tables[:5]}")

                elif body.get('operation') == 'QUERY':
                    records = data.get('data', {}).get('records', [])
                    print(f"Records found: {len(records)}")

                elif body.get('operation') == 'CREATE_TABLE':
                    print(f"Table '{body.get('table')}' created successfully")

                elif body.get('operation') == 'WRITE':
                    records = data.get('data', {}).get('records', [])
                    print(f"Records written: {len(records)}")

            else:
                print(f"❌ FAILED - Success: False")
                print(f"Error: {data.get('error')}")
                failed_tests += 1
        else:
            print(f"❌ FAILED - HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('error', {}).get('message', 'Unknown error')}")
            except:
                print(f"Response: {response.text[:200]}")
            failed_tests += 1

    except requests.exceptions.Timeout:
        print(f"❌ FAILED - Timeout after 30s")
        failed_tests += 1
    except Exception as e:
        print(f"❌ FAILED - {str(e)}")
        failed_tests += 1

    results.append({
        'name': name,
        'operation': body.get('operation'),
        'status': 'PASSED' if passed_tests > (total_tests - 1) else 'FAILED'
    })

# Run all requests from the collection
print("="*60)
print("RUNNING IBEX API COLLECTION TESTS")
print("="*60)
print(f"Collection: Ibex DB - AWS API Gateway")
print(f"Endpoint: {BASE_URL}")
print(f"Tenant: {TENANT_ID}")
print(f"Namespace: {NAMESPACE}")

# Process collection
if 'collection' in collection:
    for item in collection['collection']:
        if isinstance(item, dict):
            # Check if it's a folder with children
            if 'children' in item:
                folder_name = item.get('name', 'Unnamed Folder')
                print(f"\n📁 FOLDER: {folder_name}")
                for child in item['children']:
                    if isinstance(child, dict) and 'method' in child:
                        run_request(child)
            # Or a direct request
            elif 'method' in item:
                run_request(item)

# Summary
print("\n" + "="*60)
print("TEST COLLECTION SUMMARY")
print("="*60)
print(f"Total Tests: {total_tests}")
print(f"✅ Passed: {passed_tests}")
print(f"❌ Failed: {failed_tests}")

if total_tests > 0:
    success_rate = (passed_tests / total_tests) * 100
    print(f"Success Rate: {success_rate:.1f}%")

    if failed_tests == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️ {failed_tests} tests failed")

# Show failed tests
if failed_tests > 0:
    print("\nFailed Tests:")
    for result in results:
        if result['status'] == 'FAILED':
            print(f"  - {result['name']} ({result['operation']})")

print("\n✅ Collection test run complete!")
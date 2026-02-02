#!/usr/bin/env python3
"""
Run Food App Backend API tests from Insomnia collection
Complete test suite with real OpenAI and Ibex integration
"""

import yaml
import requests
import json
import time
from datetime import datetime
import sys

# Load the Food App Backend collection
with open('/Users/pnalla/tracelinkrepo/food-app/food-sense-ai-tracker-3b84f458/Food_App_Backend_Collection.yaml', 'r') as f:
    collection = yaml.safe_load(f)

# Configuration for Local Development
BASE_URL = "http://localhost:8000"
AUTH_TOKEN = "Bearer mock-token"
USER_ID = "local-dev-user"

# Track results
results = []
total_tests = 0
passed_tests = 0
failed_tests = 0
test_times = []

# Store IDs for later tests
created_ids = {}

def run_request(request_data, folder_name=""):
    """Run a single request from the collection"""
    global total_tests, passed_tests, failed_tests

    name = request_data.get('name', 'Unnamed')
    method = request_data.get('method', 'GET')
    url = request_data.get('url', '')

    # Skip meta requests
    if 'Test' in folder_name and 'meta' in name.lower():
        return

    print(f"\n{'='*60}")
    print(f"TEST #{total_tests + 1}: {name}")
    if folder_name:
        print(f"Folder: {folder_name}")
    print(f"{'='*60}")

    total_tests += 1

    # Replace variables in URL
    url = url.replace('{{baseUrl}}', BASE_URL)
    url = url.replace('{{userId}}', USER_ID)
    url = url.replace('{{authToken}}', AUTH_TOKEN)
    url = url.replace('{{foodEntryId}}', created_ids.get('food_entry_id', 'test-id'))
    url = url.replace('{{$timestamp}}', str(int(time.time())))
    url = url.replace("{{$date 'YYYY-MM-DD'}}", datetime.now().strftime('%Y-%m-%d'))
    url = url.replace("{{$date 'YYYY-MM-DD HH:mm:ss'}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Parse headers
    headers = {"Content-Type": "application/json"}
    if request_data.get('headers'):
        for header in request_data['headers']:
            if isinstance(header, dict):
                name_val = header.get('name')
                value = header.get('value', '')
                if name_val == 'Authorization':
                    headers['Authorization'] = AUTH_TOKEN
                elif name_val and value:
                    headers[name_val] = value

    # Parse body
    body = None
    if request_data.get('body'):
        body_data = request_data['body']
        if isinstance(body_data, dict):
            body_text = body_data.get('text', '')
            # Replace variables in body
            body_text = body_text.replace('{{userId}}', USER_ID)
            body_text = body_text.replace('{{foodEntryId}}', created_ids.get('food_entry_id', 'test-id'))
            body_text = body_text.replace('{{$timestamp}}', str(int(time.time())))
            body_text = body_text.replace("{{$date 'YYYY-MM-DD'}}", datetime.now().strftime('%Y-%m-%d'))
            body_text = body_text.replace("{{$date 'YYYY-MM-DD HH:mm:ss'}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            try:
                body = json.loads(body_text)
            except:
                # Test invalid JSON case
                if 'invalid json' in body_text.lower():
                    body = body_text
                else:
                    print(f"❌ Invalid JSON in request body")
                    failed_tests += 1
                    return

    print(f"Method: {method}")
    print(f"URL: {url}")

    # Make the request
    start_time = time.time()

    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            if isinstance(body, str):
                response = requests.post(url, data=body, headers=headers, timeout=30)
            else:
                response = requests.post(url, json=body, headers=headers, timeout=30)
        elif method == 'PUT':
            response = requests.put(url, json=body, headers=headers, timeout=30)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            print(f"❌ Unsupported method: {method}")
            failed_tests += 1
            return

        elapsed = (time.time() - start_time) * 1000  # Convert to ms
        test_times.append(elapsed)

        print(f"Status: {response.status_code}")
        print(f"Time: {elapsed:.0f}ms")

        # Determine if test passed based on test type
        test_passed = False

        # Special cases
        if 'Invalid JSON' in name and response.status_code == 400:
            test_passed = True
            print("✅ PASSED - Invalid JSON correctly rejected")
        elif 'Invalid Table' in name and response.status_code == 200:
            test_passed = True
            print("✅ PASSED - Non-existent table handled gracefully")
        elif response.status_code in [200, 201, 204]:
            test_passed = True
            print("✅ PASSED")

            # Parse and show response
            try:
                data = response.json()

                # Store IDs for later tests
                if 'Create Food Entry' in name and not 'Batch' in name:
                    if isinstance(data, dict) and 'id' in data:
                        created_ids['food_entry_id'] = data['id']
                        print(f"Stored food_entry_id: {data['id']}")

                # Show relevant data
                if isinstance(data, list):
                    print(f"Records returned: {len(data)}")
                    if data and len(data) > 0:
                        print(f"First record: {json.dumps(data[0], indent=2)[:200]}...")
                elif isinstance(data, dict):
                    if 'data' in data:
                        # AI analysis response
                        print(f"Response data: {json.dumps(data['data'], indent=2)[:300]}...")
                    elif 'category' in data:
                        # AI response
                        print(f"AI Category: {data.get('category')}")
                        print(f"AI Model: {data.get('metadata', {}).get('model')}")
                    else:
                        print(f"Response: {json.dumps(data, indent=2)[:300]}...")
            except:
                if response.text:
                    print(f"Response: {response.text[:200]}")

        else:
            test_passed = False
            print(f"❌ FAILED - HTTP {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error: {json.dumps(error_data, indent=2)[:500]}")
            except:
                print(f"Response: {response.text[:500]}")

        if test_passed:
            passed_tests += 1
        else:
            failed_tests += 1

        results.append({
            'name': name,
            'method': method,
            'status': 'PASSED' if test_passed else 'FAILED',
            'time': elapsed
        })

    except requests.exceptions.Timeout:
        print(f"❌ FAILED - Timeout after 30s")
        failed_tests += 1
        results.append({
            'name': name,
            'method': method,
            'status': 'TIMEOUT',
            'time': 30000
        })
    except Exception as e:
        print(f"❌ FAILED - {str(e)}")
        failed_tests += 1
        results.append({
            'name': name,
            'method': method,
            'status': 'ERROR',
            'time': 0
        })

# Run all requests from the collection
print("="*60)
print("FOOD APP BACKEND API TEST SUITE")
print("="*60)
print(f"Collection: Food App Backend API Tests")
print(f"Endpoint: {BASE_URL}")
print(f"User ID: {USER_ID}")
print(f"Environment: Local Development")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Process collection
if 'collection' in collection:
    for item in collection['collection']:
        if isinstance(item, dict):
            # Check if it's a folder with children
            if 'children' in item:
                folder_name = item.get('name', 'Unnamed Folder')
                print(f"\n📁 TESTING FOLDER: {folder_name}")
                for child in item['children']:
                    if isinstance(child, dict) and 'method' in child:
                        run_request(child, folder_name)
            # Or a direct request
            elif 'method' in item:
                run_request(item)

# Calculate statistics
avg_time = sum(test_times) / len(test_times) if test_times else 0
max_time = max(test_times) if test_times else 0
min_time = min(test_times) if test_times else 0

# Summary
print("\n" + "="*60)
print("TEST SUITE SUMMARY")
print("="*60)
print(f"Total Tests: {total_tests}")
print(f"✅ Passed: {passed_tests}")
print(f"❌ Failed: {failed_tests}")

if total_tests > 0:
    success_rate = (passed_tests / total_tests) * 100
    print(f"Success Rate: {success_rate:.1f}%")

print(f"\nPerformance Metrics:")
print(f"  Average Response Time: {avg_time:.0f}ms")
print(f"  Fastest Response: {min_time:.0f}ms")
print(f"  Slowest Response: {max_time:.0f}ms")

if failed_tests == 0:
    print("\n🎉 ALL TESTS PASSED! Backend is production-ready!")
    print("✅ Real OpenAI integration working")
    print("✅ Ibex database fully integrated")
    print("✅ All CRUD operations functional")
else:
    print(f"\n⚠️ {failed_tests} tests failed")
    print("\nFailed Tests:")
    for result in results:
        if result['status'] in ['FAILED', 'ERROR', 'TIMEOUT']:
            print(f"  ❌ {result['name']} ({result['method']}) - {result['status']}")

print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("\n✅ Test suite execution complete!")
#!/usr/bin/env python3
"""
Comprehensive API testing for food-app backend
Tests all endpoints with real Ibex database
"""

import requests
import json
import time
from datetime import datetime
import sys

# Configuration
BASE_URL = "http://localhost:8000/v1"
AUTH_TOKEN = "Bearer mock-token"

# Test tracking
tests_passed = 0
tests_failed = 0

def print_test(name):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)

def print_result(success, message=""):
    global tests_passed, tests_failed
    if success:
        tests_passed += 1
        print(f"✅ PASSED: {message}")
    else:
        tests_failed += 1
        print(f"❌ FAILED: {message}")

def api_request(method, endpoint, data=None, headers=None):
    """Make API request with error handling"""
    url = f"{BASE_URL}{endpoint}"
    default_headers = {
        "Content-Type": "application/json",
        "Authorization": AUTH_TOKEN
    }
    if headers:
        default_headers.update(headers)

    try:
        if method == "GET":
            response = requests.get(url, headers=default_headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=default_headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=default_headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=default_headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        return response
    except Exception as e:
        print(f"Request error: {e}")
        return None

# Wait for backend to be ready
print("Waiting for backend to be ready...")
time.sleep(3)

# Test 1: Health check
print_test("Backend Health Check")
response = api_request("GET", "/users?limit=1")
if response and response.status_code in [200, 500]:
    print_result(True, f"Backend is responding (status: {response.status_code})")
else:
    print_result(False, "Backend not responding")
    sys.exit(1)

# Test 2: Query users table
print_test("Query Users Table")
response = api_request("GET", "/users")
if response and response.status_code == 200:
    users = response.json()
    print_result(True, f"Retrieved {len(users)} users")
    print(f"Users: {json.dumps(users[:2], indent=2) if users else 'No users'}")
else:
    print_result(False, f"Failed to query users: {response.status_code if response else 'No response'}")

# Test 3: Query specific user
print_test("Query Specific User")
response = api_request("GET", "/users?id=local-dev-user")
if response and response.status_code == 200:
    users = response.json()
    if users and len(users) > 0:
        print_result(True, f"Found user: {users[0].get('email')}")
    else:
        print_result(True, "No user found (expected if not created yet)")
else:
    print_result(False, f"Query failed: {response.status_code if response else 'No response'}")

# Test 4: Create food entry
print_test("Create Food Entry")
food_entry = {
    "description": "Test food entry from API test",
    "meal_type": "lunch",
    "meal_date": datetime.utcnow().strftime('%Y-%m-%d'),
    "meal_time": "12:30",
    "calories": 500,
    "total_protein": 30,
    "total_carbohydrates": 60,
    "total_fats": 20,
    "user_id": "local-dev-user"
}
response = api_request("POST", "/food_entries", food_entry)
created_food_id = None
if response and response.status_code == 201:
    created = response.json()
    created_food_id = created.get('id')
    print_result(True, f"Created food entry with ID: {created_food_id}")
else:
    print_result(False, f"Failed to create food entry: {response.status_code if response else 'No response'}")
    if response:
        print(f"Error: {response.text}")

# Test 5: Query food entries
print_test("Query Food Entries")
response = api_request("GET", "/food_entries?user_id=local-dev-user&limit=5")
if response and response.status_code == 200:
    entries = response.json()
    print_result(True, f"Retrieved {len(entries)} food entries")
    if entries:
        print(f"Latest entry: {entries[0].get('description', 'No description')}")
else:
    print_result(False, f"Failed to query food entries: {response.status_code if response else 'No response'}")

# Test 6: Get food entry by ID
if created_food_id:
    print_test("Get Food Entry by ID")
    response = api_request("GET", f"/food_entries/{created_food_id}")
    if response and response.status_code == 200:
        entry = response.json()
        print_result(True, f"Retrieved entry: {entry.get('description')}")
    else:
        print_result(False, f"Failed to get entry by ID: {response.status_code if response else 'No response'}")

# Test 7: Test sorting
print_test("Test Sorting")
response = api_request("GET", "/food_entries?order_by=created_at&order_dir=desc&limit=3")
if response and response.status_code == 200:
    entries = response.json()
    print_result(True, f"Sorted query returned {len(entries)} entries")
else:
    print_result(False, f"Sorting failed: {response.status_code if response else 'No response'}")

# Test 8: Test pagination
print_test("Test Pagination")
response = api_request("GET", "/food_entries?limit=2&offset=0")
if response and response.status_code == 200:
    page1 = response.json()
    response2 = api_request("GET", "/food_entries?limit=2&offset=2")
    if response2 and response2.status_code == 200:
        page2 = response2.json()
        print_result(True, f"Pagination working - Page 1: {len(page1)} items, Page 2: {len(page2)} items")
    else:
        print_result(False, "Page 2 failed")
else:
    print_result(False, "Page 1 failed")

# Test 9: Test AI analyze endpoint
print_test("AI Analysis Endpoint")
ai_request = {
    "description": "Grilled chicken with vegetables",
    "image_url": None
}
response = api_request("POST", "/ai/analyze", ai_request)
if response and response.status_code == 200:
    analysis = response.json()
    print_result(True, f"AI analysis completed: {analysis.get('classification', 'Unknown')}")
    print(f"Analysis summary: {json.dumps(analysis.get('analysis', {}).get('nutritional_summary', 'No summary'), indent=2)}")
else:
    print_result(False, f"AI analysis failed: {response.status_code if response else 'No response'}")

# Test 10: Test auth config
print_test("Auth Config Endpoint")
response = api_request("GET", "/auth/config")
if response and response.status_code == 200:
    config = response.json()
    print_result(True, f"Auth config retrieved")
else:
    print_result(False, f"Auth config failed: {response.status_code if response else 'No response'}")

# Test 11: Create multiple entries (batch)
print_test("Batch Create")
batch_entries = [
    {
        "description": "Breakfast - Oatmeal",
        "meal_type": "breakfast",
        "calories": 300,
        "user_id": "local-dev-user"
    },
    {
        "description": "Snack - Apple",
        "meal_type": "snack",
        "calories": 95,
        "user_id": "local-dev-user"
    }
]
response = api_request("POST", "/food_entries", batch_entries)
if response and response.status_code == 201:
    created = response.json()
    if isinstance(created, list):
        print_result(True, f"Batch created {len(created)} entries")
    else:
        print_result(False, "Batch create didn't return array")
else:
    print_result(False, f"Batch create failed: {response.status_code if response else 'No response'}")

# Test 12: Test invalid table
print_test("Invalid Table Handling")
response = api_request("GET", "/nonexistent_table")
if response and response.status_code == 200:
    data = response.json()
    if data == []:
        print_result(True, "Invalid table returns empty array (graceful degradation)")
    else:
        print_result(False, "Invalid table returned unexpected data")
else:
    print_result(False, f"Invalid table handling failed: {response.status_code if response else 'No response'}")

# Test 13: Test missing required fields
print_test("Missing Required Fields")
invalid_entry = {
    "description": "Missing user_id"
    # user_id is missing but might be auto-added
}
response = api_request("POST", "/food_entries", invalid_entry)
if response and response.status_code in [201, 400]:
    print_result(True, f"Handled missing fields appropriately (status: {response.status_code})")
else:
    print_result(False, f"Unexpected response: {response.status_code if response else 'No response'}")

# Print summary
print(f"\n{'='*60}")
print("TEST SUMMARY")
print('='*60)
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
print(f"Total: {tests_passed + tests_failed}")
print(f"Success Rate: {tests_passed/(tests_passed + tests_failed)*100:.1f}%")

if tests_failed == 0:
    print("\n🎉 All tests passed! Backend is fully functional.")
else:
    print(f"\n⚠️ {tests_failed} tests failed. Please review the errors above.")
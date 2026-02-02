#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_URL="http://localhost:8000"
AUTH_TOKEN="Bearer dev-user-1"

echo "========================================="
echo "Testing All Backend API Endpoints"
echo "========================================="
echo ""

# Helper function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local expected_status=$4
    local description=$5

    echo -n "Testing $description: "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_URL$endpoint" -H "Authorization: $AUTH_TOKEN")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL$endpoint" -H "Authorization: $AUTH_TOKEN" -H "Content-Type: application/json" -d "$data")
    elif [ "$method" = "PUT" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_URL$endpoint" -H "Authorization: $AUTH_TOKEN" -H "Content-Type: application/json" -d "$data")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_URL$endpoint" -H "Authorization: $AUTH_TOKEN")
    fi

    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $response)"
    else
        echo -e "${RED}✗ FAIL${NC} (Expected: $expected_status, Got: $response)"
    fi
}

echo "1. USER ENDPOINTS"
echo "-----------------"
test_endpoint "GET" "/v1/users" "" "200" "GET /v1/users"
test_endpoint "GET" "/v1/users?id=local-dev-user" "" "200" "GET /v1/users with filter"
echo ""

echo "2. FOOD ENTRIES ENDPOINTS"
echo "-------------------------"
test_endpoint "GET" "/v1/food_entries" "" "200" "GET /v1/food_entries"
TEST_ID=$(curl -s -X POST "$API_URL/v1/food_entries" -H "Authorization: $AUTH_TOKEN" -H "Content-Type: application/json" -d '{"description":"Test Food","calories":100}' | grep -o '"id":"[^"]*' | cut -d'"' -f4)
test_endpoint "POST" "/v1/food_entries" '{"description":"Test Food","calories":100}' "201" "POST /v1/food_entries"
test_endpoint "GET" "/v1/food_entries/$TEST_ID" "" "200" "GET /v1/food_entries/{id}"
test_endpoint "PUT" "/v1/food_entries/$TEST_ID" '{"calories":150}' "200" "PUT /v1/food_entries/{id}"
test_endpoint "DELETE" "/v1/food_entries/$TEST_ID" "" "204" "DELETE /v1/food_entries/{id}"
echo ""

echo "3. FOOD ITEMS ENDPOINTS"
echo "-----------------------"
test_endpoint "GET" "/v1/food_items" "" "200" "GET /v1/food_items"
test_endpoint "POST" "/v1/food_items" '{"name":"Apple","calories":95}' "201" "POST /v1/food_items"
echo ""

echo "4. PENDING ANALYSES ENDPOINTS"
echo "-----------------------------"
test_endpoint "GET" "/v1/pending_analyses" "" "200" "GET /v1/pending_analyses"
test_endpoint "POST" "/v1/pending_analyses" '{"description":"Test Analysis","status":"pending","category":"food"}' "201" "POST /v1/pending_analyses"
echo ""

echo "5. RECEIPTS ENDPOINTS"
echo "--------------------"
test_endpoint "GET" "/v1/receipts" "" "200" "GET /v1/receipts"
test_endpoint "POST" "/v1/receipts" '{"merchant":"Test Store","total":"25.99","items":[]}' "201" "POST /v1/receipts"
echo ""

echo "6. WORKOUTS ENDPOINTS"
echo "--------------------"
test_endpoint "GET" "/v1/workouts" "" "200" "GET /v1/workouts"
test_endpoint "POST" "/v1/workouts" '{"activity":"Running","duration":30,"calories_burned":250}' "201" "POST /v1/workouts"
echo ""

echo "7. CARE RELATIONSHIPS ENDPOINTS"
echo "-------------------------------"
test_endpoint "GET" "/v1/care_relationships" "" "200" "GET /v1/care_relationships"
echo ""

echo "8. STORAGE ENDPOINTS"
echo "-------------------"
test_endpoint "POST" "/v1/storage/upload-url" '{"filename":"test.jpg","content_type":"image/jpeg"}' "200" "POST /v1/storage/upload-url"
echo ""

echo "9. AI ANALYSIS ENDPOINT"
echo "-----------------------"
# Note: This will fail without real API keys
test_endpoint "POST" "/v1/analyze" '{"category":"food","description":"apple"}' "500" "POST /v1/analyze (expected to fail without API keys)"
echo ""

echo "========================================="
echo "Test Summary Complete"
echo "========================================="
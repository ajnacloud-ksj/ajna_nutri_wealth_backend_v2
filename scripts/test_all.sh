#!/bin/bash

# Comprehensive Local Testing Script
# Tests all endpoints and functionality

set -e

echo "🧪 Running Comprehensive Tests"
echo "=============================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Base URL
BASE_URL="http://localhost:8080"
AUTH_HEADER="Authorization: Bearer dev-user-1"

# Test counter
PASSED=0
FAILED=0

# Function to test endpoint
test_endpoint() {
    local name=$1
    local method=$2
    local path=$3
    local data=$4
    local expected=$5

    echo -n "Testing $name... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -X GET "$BASE_URL$path" -H "$AUTH_HEADER" 2>/dev/null || echo "FAILED")
    else
        response=$(curl -s -X POST "$BASE_URL$path" \
            -H "$AUTH_HEADER" \
            -H "Content-Type: application/json" \
            -d "$data" \
            --max-time 35 2>/dev/null || echo "FAILED")
    fi

    if [[ "$response" == *"$expected"* ]]; then
        echo -e "${GREEN}✅ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ FAILED${NC}"
        echo "  Expected: $expected"
        echo "  Got: ${response:0:100}..."
        ((FAILED++))
    fi
}

echo "1️⃣ Testing Core Endpoints"
echo "--------------------------"

# Test model configuration
test_endpoint "Model Config List" "GET" "/v1/models/config" "" "configs"
test_endpoint "Model Config Get" "GET" "/v1/models/config/food" "" "use_case"
test_endpoint "Models Available" "GET" "/v1/models/available" "" "openai"

echo ""
echo "2️⃣ Testing Analysis Endpoints"
echo "------------------------------"

# Test food analysis
test_endpoint "Analyze Food" "POST" "/v1/analyze" '{"description":"Apple"}' "success"
test_endpoint "Async Analysis" "POST" "/v1/analyze/async" '{"description":"Banana"}' "entry_id"

echo ""
echo "3️⃣ Testing Data Endpoints"
echo "--------------------------"

# Test receipts
test_endpoint "List Receipts" "GET" "/v1/receipts?limit=2" "" "receipts"

# Test food entries
test_endpoint "List Food Entries" "GET" "/v1/app_food_entries_v2?limit=2" "" "records"

echo ""
echo "4️⃣ Testing With Images"
echo "-----------------------"

# Test with base64 image (if test image exists)
if [ -f "test_assets/test-biryani.jpg" ]; then
    IMAGE_B64=$(base64 -i test_assets/test-biryani.jpg 2>/dev/null || echo "")
    if [ -n "$IMAGE_B64" ]; then
        test_endpoint "Analyze with Image" "POST" "/v1/analyze/async" \
            "{\"description\":\"Biryani\",\"image_url\":\"data:image/jpeg;base64,${IMAGE_B64:0:100}...\"}" \
            "entry_id"
    fi
fi

echo ""
echo "5️⃣ Testing Health & System"
echo "---------------------------"

# Test system endpoints
test_endpoint "Auth Config" "GET" "/v1/auth/config" "" "mode"

echo ""
echo "📊 Test Summary"
echo "==============="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
fi
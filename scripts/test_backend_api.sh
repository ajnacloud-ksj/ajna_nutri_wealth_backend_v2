#!/bin/bash

echo "=== Backend API Testing Suite ==="
echo ""

# Test 1: Get Users
echo "1. Testing GET /v1/users (should return local-dev-user)"
curl -s http://localhost:8000/v1/users | jq .
echo ""

# Test 2: Get specific user
echo "2. Testing GET /v1/users/local-dev-user"
curl -s http://localhost:8000/v1/users/local-dev-user | jq .
echo ""

# Test 3: Create a pending analysis
echo "3. Testing POST /v1/pending_analyses (create analysis)"
ANALYSIS_RESPONSE=$(curl -s -X POST http://localhost:8000/v1/pending_analyses \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "local-dev-user",
    "description": "Test food entry via API",
    "image_url": null,
    "status": "processing",
    "category": "food"
  }')
echo "$ANALYSIS_RESPONSE" | jq .
echo ""

# Extract ID if successful
ANALYSIS_ID=$(echo "$ANALYSIS_RESPONSE" | jq -r '.id // empty')

if [ -n "$ANALYSIS_ID" ]; then
  echo "✅ Analysis created with ID: $ANALYSIS_ID"
  echo ""
  
  # Test 4: Retrieve the created analysis
  echo "4. Testing GET /v1/pending_analyses/$ANALYSIS_ID"
  curl -s "http://localhost:8000/v1/pending_analyses/$ANALYSIS_ID" | jq .
  echo ""
  
  # Test 5: List all pending analyses
  echo "5. Testing GET /v1/pending_analyses (list all)"
  curl -s "http://localhost:8000/v1/pending_analyses" | jq .
  echo ""
else
  echo "❌ Failed to create analysis"
  echo "Response: $ANALYSIS_RESPONSE"
fi

echo "=== Test Complete ==="

#!/bin/bash

# Quick test script for the improved backend
# This tests the auth system and basic functionality

echo "🚀 Testing Improved Backend System"
echo "=================================="

# Set environment variables
export ENVIRONMENT=development
export AUTH_MODE=local
export USE_OPTIMIZED_AI=true
export LOG_LEVEL=INFO

# Start the secure server in background
echo "Starting secure local server..."
python3 local_server_secure.py &
SERVER_PID=$!

# Wait for server to start
sleep 2

# Test endpoints
echo -e "\n📝 Testing endpoints..."

# Test 1: Health check
echo -e "\n1. Testing basic connectivity..."
curl -s http://localhost:8080/v1/auth/config | python3 -m json.tool

# Test 2: Test with default user
echo -e "\n2. Testing with default user (dev-user-1)..."
curl -s -X GET http://localhost:8080/v1/food_entries \
  -H "Content-Type: application/json" | head -c 200

# Test 3: Test with specific user
echo -e "\n3. Testing with specific user (test-user-1)..."
curl -s -X GET http://localhost:8080/v1/food_entries \
  -H "X-User-Id: test-user-1" \
  -H "Content-Type: application/json" | head -c 200

# Test 4: Test validation (should fail)
echo -e "\n4. Testing input validation..."
curl -s -X POST http://localhost:8080/v1/food_entries \
  -H "Content-Type: application/json" \
  -d '{"invalid_field": "test"}' | python3 -m json.tool

# Kill the server
echo -e "\n\nStopping server..."
kill $SERVER_PID 2>/dev/null

echo -e "\n✅ Tests complete!"
echo "=================================="
echo "To run the secure server manually:"
echo "  AUTH_MODE=local python3 local_server_secure.py"
echo ""
echo "To run all tests:"
echo "  python3 test_improvements.py"
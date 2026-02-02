#!/bin/bash

# Backend Test Runner
# This script starts the server and runs comprehensive tests

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  NutriWealth Backend Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if server is already running
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${YELLOW}⚠️  Server is already running on port 8080${NC}"
    echo "Proceeding with tests..."
    SERVER_PID=""
else
    # Start server in background
    echo -e "${GREEN}Starting backend server...${NC}"

    # Set environment variables
    export AUTH_MODE=local
    export ENVIRONMENT=development
    export LOG_LEVEL=INFO
    export USE_OPTIMIZED_AI=true

    # Start server
    python3 local_server_secure.py > server.log 2>&1 &
    SERVER_PID=$!

    echo "Server starting with PID: $SERVER_PID"
    echo "Waiting for server to be ready..."

    # Wait for server to start
    for i in {1..10}; do
        if curl -s http://localhost:8080/v1/auth/config >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Server is ready!${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done

    if ! curl -s http://localhost:8080/v1/auth/config >/dev/null 2>&1; then
        echo -e "${RED}❌ Server failed to start${NC}"
        echo "Check server.log for details"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}Running comprehensive API tests...${NC}"
echo "========================================="

# Run the test suite
python3 test_all_endpoints.py

# Store test exit code
TEST_EXIT_CODE=$?

# Kill server if we started it
if [ ! -z "$SERVER_PID" ]; then
    echo ""
    echo -e "${YELLOW}Stopping server (PID: $SERVER_PID)...${NC}"
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
    echo -e "${GREEN}Server stopped${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests completed successfully!${NC}"
else
    echo -e "${RED}❌ Some tests failed${NC}"
fi
echo -e "${GREEN}========================================${NC}"

# Additional info
echo ""
echo "📝 Additional Testing Options:"
echo "  • Import NutriWealth_API.postman_collection.json into Postman"
echo "  • Run individual tests: python3 test_improvements.py"
echo "  • Check server logs: tail -f server.log"
echo "  • Test with AI: export OPENAI_API_KEY=your-key"

exit $TEST_EXIT_CODE
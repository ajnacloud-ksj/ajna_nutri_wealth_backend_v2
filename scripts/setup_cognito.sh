#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Usage: ./setup_cognito.sh [POOL_NAME] [CLIENT_NAME]
COGNITO_POOL_NAME=${1:-"food-sense-ai-users"}
COGNITO_APP_CLIENT_NAME=${2:-"food-sense-web"}

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Using defaults: Pool=$COGNITO_POOL_NAME, Client=$COGNITO_APP_CLIENT_NAME"
    echo "To customize, run: ./setup_cognito.sh <pool_name> <client_name>"
fi

echo -e "${GREEN}=== NutriWealth Cognito Setup ===${NC}"
echo "Pool Name: $COGNITO_POOL_NAME"
echo "Client Name: $COGNITO_APP_CLIENT_NAME"

# 1. Check for AWS Credentials
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo -e "${RED}Error: AWS credentials not found or invalid.${NC}"
    echo "Please configure your AWS credentials using:"
    echo "  aws configure"
    echo "Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
    exit 1
fi
echo -e "${GREEN}AWS credentials found.${NC}"

# 2. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

# 3. Setup Virtual Environment (Optional but recommended)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# 4. Install Dependencies
echo "Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
else
    pip install boto3 > /dev/null 2>&1
fi

# 5. Run Python Setup Script
echo "Running Cognito setup script..."
python3 scripts/setup_auth.py --pool-name "$COGNITO_POOL_NAME" --client-name "$COGNITO_APP_CLIENT_NAME"

echo -e "${GREEN}=== Setup Complete ===${NC}"
echo "Please copy the User Pool ID and Client ID from the output above"
echo "and update your configuration (e.g., in .env or Lambda environment variables)."

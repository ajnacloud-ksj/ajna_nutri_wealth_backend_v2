#!/bin/bash

# Configuration
IMAGE_NAME="food-sense-backend"
PORT=3000

# Check for .env file or variables
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is not set."
    echo "Please export it or create a .env file."
    exit 1
fi

echo "Building Docker image..."
docker build -t $IMAGE_NAME .

echo "Starting container on port $PORT..."
echo "Press Ctrl+C to stop."

# Run with environment variables
# We align with local .env if present
ENV_ARGS=""
if [ -f .env ]; then
    ENV_ARGS="--env-file .env"
fi

docker run --rm -it \
    -p $PORT:$PORT \
    $ENV_ARGS \
    -e IBEX_API_URL=$IBEX_API_URL \
    -e IBEX_API_KEY=$IBEX_API_KEY \
    -e OPENAI_API_KEY=$OPENAI_API_KEY \
    -e COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID \
    -e COGNITO_CLIENT_ID=$COGNITO_CLIENT_ID \
    -e COGNITO_REGION=$COGNITO_REGION \
    --entrypoint python \
    $IMAGE_NAME \
    local_server.py

#!/usr/bin/env python3
"""
Local development server for the food-app backend
Supports both local and cloud authentication modes
"""

import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file FIRST if it exists
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    print(f"Loading environment from {env_file}")
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Override any existing values with .env values
                os.environ[key] = value.strip('"').strip("'")

# Set default environment variables for local development (only if not set by .env)
os.environ.setdefault('ENVIRONMENT', 'development')
os.environ.setdefault('AUTH_MODE', 'local')  # local, cognito, or test
os.environ.setdefault('IBEX_API_KEY', 'local-dev-key')
os.environ.setdefault('OPENAI_API_KEY', 'sk-local-dev')

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

# Import the Lambda handler
from app_optimized import lambda_handler as handler

# Create FastAPI app
app = FastAPI(title="NutriWealth Backend API")

# Add GZip compression middleware (reduces response size by 60-80%)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Only compress responses > 1KB

# Configure CORS for both local and cloud environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8081",
        "http://localhost:8082",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8081",
        "http://127.0.0.1:8082",
        "http://10.0.0.17:8081",  # Network IP
        "http://10.80.229.62:8081",  # Network IP
        "https://app.nutriwealth.com",
        "https://www.nutriwealth.com",
        "https://staging.nutriwealth.com",
        "*"  # Allow all origins in development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
async def lambda_handler_wrapper(path: str, request: Request):
    """
    Wrapper to convert FastAPI requests to Lambda event format
    """
    # Build Lambda event
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body_bytes = await request.body()
            if body_bytes:
                body = body_bytes.decode('utf-8')
        except:
            pass

    # Get headers
    headers = dict(request.headers)

    # Build query parameters
    query_params = dict(request.query_params)

    # Create Lambda event
    event = {
        "httpMethod": request.method,
        "path": f"/{path}",
        "headers": headers,
        "queryStringParameters": query_params if query_params else None,
        "body": body,
        "requestContext": {
            "authorizer": {
                "claims": {}  # Will be populated by auth_provider
            }
        }
    }

    # Call Lambda handler
    context = {}  # Mock context
    response = handler(event, context)

    # Convert Lambda response to FastAPI response
    status_code = response.get("statusCode", 200)
    response_headers = response.get("headers", {})
    response_body = response.get("body", "")

    # Parse body if it's JSON
    try:
        response_data = json.loads(response_body) if response_body else {}
    except:
        response_data = response_body

    return JSONResponse(
        status_code=status_code,
        content=response_data,
        headers=response_headers
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        "auth_mode": os.environ.get("AUTH_MODE", "unknown")
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n🚀 Starting NutriWealth Backend Server")
    print(f"   Environment: {os.environ.get('ENVIRONMENT', 'development')}")
    print(f"   Auth Mode: {os.environ.get('AUTH_MODE', 'local')}")
    print(f"   Server: http://localhost:{port}")
    print(f"   API Docs: http://localhost:{port}/docs")
    print(f"\n   For cloud mode with Cognito, set AUTH_MODE=cognito")
    print(f"   and provide COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID\n")

    # Use string import for reload to work properly
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
        reload_dirs=["src"]
    )
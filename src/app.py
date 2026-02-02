"""
NutriWealth Backend API
Modern, secure Lambda handler with AI-powered food analysis
"""

import json
import os
import sys
from typing import Dict, Any

# Ensure src/ is in path
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Import core services
from lib.ibex_client import IbexClient
from lib.ai_optimized import OptimizedAIService
from lib.tenant_manager import TenantManager
from lib.logger import logger
from config.settings import settings
import router


# Load Schemas
def load_schemas() -> Dict[str, Any]:
    """Load all schema definitions"""
    schemas = {}
    schema_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schemas')

    if os.path.exists(schema_dir):
        for filename in os.listdir(schema_dir):
            if filename.endswith('.json'):
                table_name = filename[:-5]
                try:
                    with open(os.path.join(schema_dir, filename), 'r') as f:
                        schemas[table_name] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading schema {filename}: {e}")

    return schemas


# Initialize services
SCHEMAS = load_schemas()

# Database configuration from settings
db_config = settings.config.database
IBEX_API_URL = db_config.api_url
IBEX_API_KEY = db_config.api_key
TENANT_ID = db_config.tenant_id
NAMESPACE = db_config.namespace

# Initialize database client
try:
    db = IbexClient(IBEX_API_URL, IBEX_API_KEY, TENANT_ID, NAMESPACE)
    logger.info("Database client initialized successfully")
except Exception as e:
    logger.critical(f"Database initialization failed: {e}")
    db = None
    raise

# Initialize AI service (always use optimized version)
try:
    if db:
        ai_service = OptimizedAIService(db)
        logger.info("Optimized AI Service initialized (two-stage processing)")
    else:
        ai_service = None
        logger.error("AI Service not initialized - database unavailable")
except Exception as e:
    logger.critical(f"AI Service initialization failed: {e}")
    ai_service = None
    raise


def lambda_handler(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main Lambda handler with multi-tenant support

    Args:
        event: Lambda event containing HTTP request data
        context: Lambda context with runtime information

    Returns:
        HTTP response with status code, headers, and body
    """
    # Add request ID to logger context
    request_id = context.get('request_id') or event.get('requestContext', {}).get('requestId')

    try:
        # Get tenant configuration from request
        tenant_config = TenantManager.get_tenant_from_request(event)

        logger.info(
            "Processing request",
            tenant_id=tenant_config['tenant_id'],
            tenant_name=tenant_config['display_name'],
            request_id=request_id
        )

        # Create tenant-specific database client
        tenant_db = TenantManager.create_ibex_client(tenant_config)
        logger.debug(f"Tenant DB initialized for namespace: {tenant_config['namespace']}")

        # Create tenant-specific AI service
        tenant_ai_service = OptimizedAIService(tenant_db)
        logger.debug("Tenant AI Service initialized")

        # Build context for handlers
        handler_context = {
            "db": tenant_db,
            "ai_service": tenant_ai_service,
            "schemas": SCHEMAS,
            "settings": settings,
            "tenant": tenant_config,
            "request_id": request_id
        }

        # Route request to appropriate handler
        return router.route_request(event, handler_context)

    except Exception as e:
        logger.exception(
            "Request processing failed",
            error=str(e),
            request_id=request_id
        )

        # Return error response
        from utils.http import respond
        return respond(500, {
            "error": "Internal server error",
            "request_id": request_id
        }, event=event)

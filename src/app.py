"""
NutriWealth Backend API
Modern, secure Lambda handler with AI-powered food analysis
"""

import json
import os
import sys
from typing import Dict, Any

# Import core services using absolute imports from src package
from src.lib.ibex_client_optimized import OptimizedIbexClient as IbexClient
from src.lib.ai_optimized import OptimizedAIService
from src.lib.tenant_manager import TenantManager
from src.lib.logger import logger
from src.config.settings import settings
import src.router as router


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
IBEX_LAMBDA_NAME = os.environ.get('IBEX_LAMBDA_NAME')

# Initialize database client
try:
    db = IbexClient(IBEX_API_URL, IBEX_API_KEY, TENANT_ID, NAMESPACE)
    
    # Enable Direct Lambda Invocation if configured (bypasses API Gateway 403 issues)
    if IBEX_LAMBDA_NAME:
        db.enable_direct_lambda(function_name=IBEX_LAMBDA_NAME, use_for_writes_only=False)
        logger.info(f"Enabled Direct Lambda Invocation for Ibex: {IBEX_LAMBDA_NAME}")
        
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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler with multi-tenant support

    Args:
        event: Lambda event containing HTTP request data
        context: Lambda context with runtime information

    Returns:
        HTTP response with status code, headers, and body
    """
    # Add request ID to logger context (Safely handle context object)
    request_id = getattr(context, 'aws_request_id', None) or event.get('requestContext', {}).get('requestId')

    try:
        # CRITICAL: Check if this is an SQS event FIRST
        if event.get('Records') and len(event.get('Records', [])) > 0:
            first_record = event['Records'][0]
            event_source = first_record.get('eventSource')

            if event_source == 'aws:sqs':
                logger.info(f"Processing {len(event['Records'])} SQS messages")

                # Extract tenant info from the first message
                try:
                    import json
                    message_body = json.loads(first_record.get('body', '{}'))
                    tenant_config = {
                        'tenant_id': message_body.get('tenant_id', TENANT_ID),
                        'namespace': message_body.get('namespace', NAMESPACE),
                        'display_name': 'SQS Processing'
                    }
                except Exception as e:
                    logger.warning(f"Could not extract tenant from SQS message: {e}")
                    tenant_config = {
                        'tenant_id': TENANT_ID,
                        'namespace': NAMESPACE,
                        'display_name': 'Default'
                    }

                # Create database client for SQS processing
                tenant_db = TenantManager.create_ibex_client(tenant_config, client_class=IbexClient)

                # Enable Direct Lambda if configured
                if IBEX_LAMBDA_NAME:
                    tenant_db.enable_direct_lambda(function_name=IBEX_LAMBDA_NAME, use_for_writes_only=False)

                # Build context for SQS handler
                handler_context = {
                    "db": tenant_db,
                    "tenant": tenant_config,
                    "request_id": request_id
                }

                # Process SQS messages
                from src.handlers import analyze_async
                return analyze_async.process_sqs_messages(event, handler_context)

        # Check if this is an async processing request (legacy Lambda invoke)
        if event.get('source') == 'async-processing':
            logger.info("Processing async Lambda invocation (legacy)")
            from src.handlers import analyze_async
            return analyze_async.process_async_request(event, context)
        
        # Get tenant configuration from request
        tenant_config = TenantManager.get_tenant_from_request(event)

        logger.info(
            "Processing request",
            tenant_id=tenant_config['tenant_id'],
            tenant_name=tenant_config['display_name'],
            request_id=request_id
        )

        # Create tenant-specific database client
        # Create tenant-specific database client with Optimized Client
        tenant_db = TenantManager.create_ibex_client(tenant_config, client_class=IbexClient)
        
        # Enable Direct Lambda Invocation for tenant client
        # This is CRITICAL because we are not using API Keys
        if IBEX_LAMBDA_NAME:
            tenant_db.enable_direct_lambda(function_name=IBEX_LAMBDA_NAME, use_for_writes_only=False)
            logger.debug(f"Direct Lambda Invocation enabled for tenant DB: {IBEX_LAMBDA_NAME}")

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

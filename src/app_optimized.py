"""
Food App Lambda Handler - Optimized Version
Uses OptimizedIbexClient for better performance
"""

import json
import os
import sys
from typing import Dict, Any

# Ensure src/ is in path
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Import core services
try:
    # Try to use optimized client
    from lib.ibex_client_optimized import OptimizedIbexClient as IbexClient
    print("Using OptimizedIbexClient with caching")
except ImportError:
    # Fallback to original client
    from lib.ibex_client import IbexClient
    print("Using standard IbexClient")

from lib.ai_optimized import OptimizedAIService
from lib.tenant_manager import TenantManager
from lib.logger import logger
from config.settings import settings
import router

# Force import of SQS handler to ensure it's included in Docker build
try:
    from handlers import sqs_handler
    logger.info("SQS handler module imported successfully")
except Exception as e:
    logger.warning(f"Could not import SQS handler: {e}")


# Load Schemas
def load_schemas() -> Dict[str, Any]:
    """Load all schema definitions"""
    schemas = {}
    schema_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schemas')

    if os.path.exists(schema_dir):
        for filename in os.listdir(schema_dir):
            if filename.endswith('.json'):
                table_name = filename.replace('.json', '')
                try:
                    with open(os.path.join(schema_dir, filename), 'r') as f:
                        schemas[table_name] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading schema {filename}: {e}")

    return schemas


# Initialize services
SCHEMAS = load_schemas()

# Database configuration from settings
DB_CONFIG = {
    "api_url": settings.config.database.api_url,
    "api_key": settings.config.database.api_key,
    "tenant_id": settings.config.database.tenant_id,
    "namespace": settings.config.database.namespace
}

# TenantManager is used as a class with static methods

# AI service doesn't need config - it reads from environment


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler
    Routes requests to appropriate handlers
    """
    try:
        # Check if this is an SQS event
        if event.get('Records') and len(event.get('Records', [])) > 0:
            # Check if it's from SQS
            first_record = event['Records'][0]
            if first_record.get('eventSource') == 'aws:sqs':
                logger.info("Processing SQS messages")

                # For SQS, we need to set up the database context
                # Extract tenant info from the first message (all messages in batch should be from same tenant)
                try:
                    import json
                    message_body = json.loads(first_record.get('body', '{}'))
                    # Get tenant info from message payload
                    tenant_config = {
                        'tenant_id': message_body.get('tenant_id', 'default'),
                        'namespace': message_body.get('namespace', 'default')
                    }
                except Exception as e:
                    logger.warning(f"Could not extract tenant from SQS message: {e}")
                    # Fallback to default if message parsing fails
                    tenant_config = {
                        'tenant_id': 'default',
                        'namespace': 'default'
                    }

                # Create database client for SQS processing with proper tenant
                tenant_db = TenantManager.create_ibex_client(tenant_config, client_class=IbexClient)

                # Add to context
                context = context or {}
                context['db'] = tenant_db
                context['tenant'] = tenant_config

                from handlers import analyze_async
                return analyze_async.process_sqs_messages(event, context)

        # Check if this is a direct async processing request (legacy)
        if event.get('source') == 'async-processing':
            logger.info("Processing async Lambda Event invocation (legacy)")
            from handlers import analyze_async
            return analyze_async.process_async_request(event, context)
        
        # Get tenant configuration
        tenant_config = TenantManager.get_tenant_config(event)
        tenant_id = tenant_config['tenant_id'] # Keep tenant_id extraction for later use
        user_id = event.get('headers', {}).get('x-user-id') # Keep user_id extraction for prefetch

        # Create tenant-specific database client
        tenant_db = TenantManager.create_ibex_client(tenant_config, client_class=IbexClient)
        
        # Enable direct Lambda invocation if configured
        lambda_name = os.environ.get('IBEX_LAMBDA_NAME') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        if hasattr(tenant_db, 'enable_direct_lambda') and lambda_name:
            tenant_db.enable_direct_lambda(lambda_name)
            logger.info(f"Direct Lambda invocation enabled for: {lambda_name}")

        # If user_id is provided and we have OptimizedIbexClient, prefetch user data
        if user_id and hasattr(tenant_db, 'prefetch_user_data'):
            # Prefetch user data in background (non-blocking)
            import threading
            prefetch_thread = threading.Thread(target=lambda: tenant_db.prefetch_user_data(user_id))
            prefetch_thread.daemon = True
            prefetch_thread.start()

        # Get or create tenant-specific AI service
        tenant_ai_service = OptimizedAIService(tenant_db)

        # Log request (excluding sensitive data)
        logger.info(f"Request received", extra={
            "tenant_id": tenant_id,
            "path": event.get('path'),
            "method": event.get('httpMethod'),
            "user_id": user_id
        })

        # Build context with services and configs
        enhanced_context = {
            **context,
            "db": tenant_db,
            "ai_service": tenant_ai_service,
            "schemas": SCHEMAS,
            "settings": settings,
            "tenant": tenant_config,
        }

        # Route the request
        response = router.route_request(event, enhanced_context)

        # Log performance stats if using OptimizedIbexClient
        if hasattr(tenant_db, 'get_stats'):
            stats = tenant_db.get_stats()
            if stats.get('cache_hit_rate', 0) > 0:
                logger.info(f"Cache performance", extra={
                    "cache_hit_rate": f"{stats.get('cache_hit_rate', 0)*100:.1f}%",
                    "total_requests": stats.get('total_requests', 0),
                    "cached_responses": stats.get('cached_responses', 0)
                })

        return response

    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"})
        }
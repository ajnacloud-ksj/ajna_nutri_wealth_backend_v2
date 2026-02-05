"""
Modern API Router with Clean Handler Imports
"""

import re
from typing import Dict, Any
from src.utils.http import respond

# Import modernized handlers
from src.handlers import data  # Now using modernized data handler
from src.handlers import auth, storage, receipts
from src.handlers import analyze  # Using improved analyze handler
from src.handlers import analyze_async  # Async analysis with SQS
from src.handlers import model_config  # Model configuration management

# Note: Using improved analyze handler with two-stage AI processing

# Route Definition
# (Method, PathPattern, Handler)
ROUTES = [
    # System
    ('POST', r'^/v1/system/create-database$', data.create_database),
    ('POST', r'^/v1/system/initialize-schemas$', data.initialize_schemas),
    ('POST', r'^/v1/system/reset-database$', data.reset_database),

    # Auth
    ('GET', r'^/v1/auth/config$', auth.get_config),
    ('POST', r'^/v1/auth/invitations/redeem$', auth.redeem_invitation),

    # Receipts (before generic data routes)
    ('GET', r'^/v1/receipts/(?P<id>[a-zA-Z0-9-]+)$', receipts.get_receipt_with_items),
    ('GET', r'^/v1/receipts$', receipts.list_receipts),

    # AI - Optimized two-stage analysis
    ('POST', r'^/v1/analyze$', analyze.analyze_food),
    ('POST', r'^/v1/ai/analyze$', analyze.analyze_food),  # Legacy route

    # Async Analysis (with SQS)
    ('POST', r'^/v1/analyze/async$', analyze_async.submit_analysis),
    ('GET', r'^/v1/analyze/status/(?P<entry_id>[a-zA-Z0-9-]+)$', analyze_async.get_analysis_status),

    # Model Configuration
    ('GET', r'^/v1/models/config$', model_config.list_model_configs),
    ('GET', r'^/v1/models/config/(?P<use_case>[a-zA-Z0-9_]+)$', model_config.get_model_config),
    ('PUT', r'^/v1/models/config/(?P<use_case>[a-zA-Z0-9_]+)$', model_config.update_model_config),
    ('GET', r'^/v1/models/available$', model_config.list_available_models),
    ('POST', r'^/v1/models/test$', model_config.test_model),

    # Storage
    ('POST', r'^/storage/upload$', storage.upload_file),
    ('POST', r'^/v1/storage/upload-url$', storage.get_upload_url_endpoint), # New: Get Presigned URL
    ('GET', r'^/v1/storage/(?P<path>.+)$', storage.get_file),

    # Generic Data (Last to avoid collisions)
    ('GET', r'^/v1/(?P<table>[a-zA-Z0-9_]+)$', data.list_data),
    ('POST', r'^/v1/(?P<table>[a-zA-Z0-9_]+)$', data.create_data),
    ('GET', r'^/v1/(?P<table>[a-zA-Z0-9_]+)/(?P<id>[a-zA-Z0-9-]+)$', data.get_data_by_id),
    ('PUT', r'^/v1/(?P<table>[a-zA-Z0-9_]+)/(?P<id>[a-zA-Z0-9-]+)$', data.update_data),
    ('DELETE', r'^/v1/(?P<table>[a-zA-Z0-9_]+)/(?P<id>[a-zA-Z0-9-]+)$', data.delete_data),
]

def route_request(event, context):
    """
    Matches method and path to a handler.
    """
    # Support both API Gateway (v1) and Function URL (v2) event formats
    path = event.get('rawPath') or event.get('path', '')

    # Normalize Path: Replace multiple slashes with single slash (e.g. //v1 -> /v1)
    # This handles frontend config errors where API_URL has trailing slash
    path = re.sub(r'//+', '/', path)
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')

    # Handle OPTIONS requests for CORS (Pre-flight)
    # Since AWS handles headers, we just need to return 200 OK
    if method == 'OPTIONS':
        return respond(200, {})

    # Remove trailing slash for consistency
    if path.endswith('/') and len(path) > 1:
        path = path[:-1]

    print(f"Router: {method} {path}")

    for route_method, route_pattern, handler in ROUTES:
        if route_method == method:
            match = re.match(route_pattern, path)
            if match:
                # Add path parameters to event
                if not event.get('pathParameters'):
                    event['pathParameters'] = {}

                event['pathParameters'].update(match.groupdict())

                # Execute Handler
                return handler(event, context)

    return {
        "statusCode": 404,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": '{"error": "Route not found"}'
    }

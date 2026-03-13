"""
Modern API Router with Clean Handler Imports
"""

import re
from typing import Dict, Any
from ajna_cloud import respond

# Import modernized handlers
from src.handlers import data  # Now using modernized data handler
from src.handlers import auth, storage, receipts
from src.handlers import analyze  # Using improved analyze handler
from src.handlers import analyze_async  # Async analysis with SQS
from src.handlers import model_config  # Model configuration management
from src.handlers import health  # Health check endpoints
from src.handlers import database_admin  # Database setup and cleanup
from src.handlers import shopping  # Shopping list management
from src.handlers import analytics  # Cross-table analytics via EXECUTE_SQL
from src.handlers import voice  # Voice transcription via Whisper
from src.handlers import bank_statements  # Bank statement CSV upload & transactions
from src.handlers import reconciliation  # Financial reconciliation
from src.handlers import caretaker  # Caretaker data access
from src.handlers import invitations  # Invitation code management
from src.handlers import relationships  # Relationship management
from src.handlers import permissions_mgmt  # Permissions management
# from src.handlers import user  # User profile management - COMMENTED OUT UNTIL DEPLOYED

# Note: Using improved analyze handler with two-stage AI processing

# Route Definition
# (Method, PathPattern, Handler)
ROUTES = [
    # Health Check (at the top for monitoring priority)
    ('GET', r'^/health$', health.check),
    ('GET', r'^/ready$', health.ready),
    ('GET', r'^/status$', health.status),

    # System
    ('POST', r'^/v1/system/create-database$', data.create_database),
    ('POST', r'^/v1/system/initialize-schemas$', data.initialize_schemas),
    ('POST', r'^/v1/system/reset-database$', data.reset_database),

    # Database Admin (for setup and cleanup)
    ('POST', r'^/v1/admin/database/setup$', database_admin.setup_database),
    ('DELETE', r'^/v1/admin/database/cleanup$', database_admin.cleanup_database),
    ('POST', r'^/v1/admin/database/reset$', database_admin.reset_database),
    ('GET', r'^/v1/admin/database/health$', database_admin.database_health_check),

    # Auth
    ('GET', r'^/v1/auth/config$', auth.get_config),

    # Shopping Lists (before generic data routes)
    ('POST', r'^/v1/shopping-lists$', shopping.create_list),
    ('GET', r'^/v1/shopping-lists$', shopping.list_lists),
    ('GET', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)$', shopping.get_list),
    ('PUT', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)$', shopping.update_list),
    ('DELETE', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)$', shopping.delete_list),
    ('POST', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)/items$', shopping.add_items),
    ('PUT', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)/items/(?P<item_id>[a-zA-Z0-9-]+)$', shopping.update_item),
    ('DELETE', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)/items/(?P<item_id>[a-zA-Z0-9-]+)$', shopping.delete_item),
    ('POST', r'^/v1/shopping-lists/(?P<id>[a-zA-Z0-9-]+)/prepare$', shopping.prepare_list),

    # Bank Statements (before generic data routes)
    ('POST', r'^/v1/bank-statements/upload$', bank_statements.upload_csv),
    ('GET', r'^/v1/bank-statements/dashboard$', bank_statements.get_dashboard_data),
    ('DELETE', r'^/v1/bank-statements/batch/(?P<batch_id>[a-zA-Z0-9-]+)$', bank_statements.delete_batch),
    ('GET', r'^/v1/bank-transactions$', bank_statements.list_transactions),
    ('GET', r'^/v1/bank-accounts$', bank_statements.list_accounts),

    # Reconciliation
    ('POST', r'^/v1/reconciliation/run$', reconciliation.run_reconciliation),
    ('GET', r'^/v1/reconciliation/summary$', reconciliation.get_reconciliation_summary),
    ('GET', r'^/v1/reconciliation/transfers$', reconciliation.get_transfer_matches),
    ('GET', r'^/v1/reconciliation/receipts$', reconciliation.get_receipt_matches),

    # Analytics (cross-table insights via EXECUTE_SQL)
    ('GET', r'^/v1/analytics/dashboard$', analytics.dashboard_summary),
    ('GET', r'^/v1/analytics/spending/vendors$', analytics.spending_by_vendor),
    ('GET', r'^/v1/analytics/spending/trend$', analytics.spending_trend),
    ('GET', r'^/v1/analytics/nutrition/trend$', analytics.nutrition_trend),

    # Caretaker Access
    ('GET',  r'^/v1/caretaker/participants$', caretaker.list_participants),
    ('GET',  r'^/v1/caretaker/participants/(?P<participant_id>[a-zA-Z0-9-]+)/permissions$', caretaker.get_permissions),
    ('GET',  r'^/v1/caretaker/participants/(?P<participant_id>[a-zA-Z0-9-]+)/analytics/dashboard$', caretaker.get_participant_dashboard),
    ('POST', r'^/v1/caretaker/participants/(?P<participant_id>[a-zA-Z0-9-]+)/notes$', caretaker.add_note),
    ('POST', r'^/v1/caretaker/participants/(?P<participant_id>[a-zA-Z0-9-]+)/comments$', caretaker.add_comment),
    ('GET',  r'^/v1/caretaker/participants/(?P<participant_id>[a-zA-Z0-9-]+)/(?P<category>[a-zA-Z0-9_]+)$', caretaker.get_participant_data),

    # Invitations
    ('POST', r'^/v1/invitations/create$', invitations.create_invitation),
    ('GET',  r'^/v1/invitations$', invitations.list_invitations),
    ('DELETE', r'^/v1/invitations/(?P<id>[a-zA-Z0-9-]+)$', invitations.revoke_invitation),
    ('POST', r'^/v1/invitations/redeem$', invitations.redeem_invitation),

    # Relationships
    ('GET',  r'^/v1/relationships$', relationships.list_relationships),
    ('PUT',  r'^/v1/relationships/(?P<id>[a-zA-Z0-9-]+)$', relationships.update_relationship),
    ('DELETE', r'^/v1/relationships/(?P<id>[a-zA-Z0-9-]+)$', relationships.revoke_relationship),

    # Permissions Management
    ('GET',  r'^/v1/permissions$', permissions_mgmt.list_permissions),
    ('PUT',  r'^/v1/permissions/(?P<id>[a-zA-Z0-9-]+)$', permissions_mgmt.update_permission),
    ('POST', r'^/v1/permissions/bulk$', permissions_mgmt.bulk_update),

    # Access Log
    ('GET',  r'^/v1/access-log$', caretaker.get_access_log),

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

    # Voice (STT + TTS)
    ('POST', r'^/v1/voice/transcribe$', voice.transcribe),
    ('POST', r'^/v1/voice/tts$', voice.text_to_speech),

    # Storage
    ('POST', r'^/storage/upload$', storage.upload_file),
    ('POST', r'^/v1/storage/upload-url$', storage.get_upload_url_endpoint),
    ('POST', r'^/v1/storage/download-url$', storage.get_download_url),
    ('GET', r'^/v1/storage/(?P<path>.+)$', storage.get_file),

    # User Profile (before generic data routes) - COMMENTED OUT UNTIL DEPLOYED
    # ('GET', r'^/v1/user/profile$', user.get_current_user),
    # ('GET', r'^/v1/user/(?P<id>[a-zA-Z0-9-]+)$', user.get_user_by_id),

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

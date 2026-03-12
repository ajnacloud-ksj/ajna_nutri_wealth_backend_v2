"""
HTTP utilities for Lambda handlers — powered by ajna-cloud-sdk

Re-exports SDK http components and adds NutriWealth-specific get_user_id
that delegates to the configured auth provider.
"""

import os
from typing import Any, Dict

from ajna_cloud.http import (
    respond,
    get_cors_headers,
    parse_body,
    get_query_params,
)

__all__ = [
    'respond',
    'get_cors_headers',
    'get_user_id',
    'get_allowed_origins',
    'parse_body',
    'get_query_params',
]


def get_allowed_origins():
    """Get allowed CORS origins from environment"""
    env = os.environ.get('ENVIRONMENT', 'development')

    if env == 'production':
        return [
            'https://app.nutriwealth.com',
            'https://www.nutriwealth.com',
        ]
    elif env == 'staging':
        return [
            'https://staging.nutriwealth.com',
            'http://localhost:5173',
        ]
    else:
        return [
            'http://localhost:5173',
            'http://localhost:5174',
            'http://localhost:3000',
            'http://localhost:8081',
            'http://127.0.0.1:5173',
        ]


def get_user_id(event):
    """
    Get user ID from event using the configured auth provider.

    This delegates to ajna_cloud.auth.get_user_id which checks:
    1. Cognito authorizer claims (production)
    2. X-User-ID header (development)
    3. Falls back to 'local-dev-user'
    """
    try:
        from lib.auth_provider import get_user_id as _sdk_get_user_id
        return _sdk_get_user_id(event)
    except Exception as e:
        print(f"Error getting user ID: {e}")
        return None

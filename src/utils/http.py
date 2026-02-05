"""
HTTP utilities for Lambda handlers with improved auth and CORS
"""

import json
import os
from typing import Any, Dict, Optional, Union


def get_allowed_origins():
    """Get allowed CORS origins from environment"""
    # Default origins for different environments
    env = os.environ.get('ENVIRONMENT', 'development')

    if env == 'production':
        # Production domains
        return [
            'https://app.nutriwealth.com',
            'https://www.nutriwealth.com'
        ]
    elif env == 'staging':
        return [
            'https://staging.nutriwealth.com',
            'http://localhost:5173'  # Still allow local frontend in staging
        ]
    else:  # development
        return [
            'http://localhost:5173',
            'http://localhost:5174',
            'http://localhost:3000',
            'http://localhost:8081',  # Frontend running on port 8081
            'http://127.0.0.1:5173'
        ]


def get_cors_headers(event: Dict[str, Any] = None) -> Dict[str, str]:
    # AWS Lambda Function URL handles CORS (configured to return *)
    # We must NOT return duplicate headers, or browsers will block the request.
    return {}


def respond(status_code, body, is_base64=False, event=None):
    """
    Create a Lambda response with proper CORS headers

    Args:
        status_code: HTTP status code
        body: Response body (dict, list, string, or None)
        is_base64: Whether body is base64 encoded
        event: Original event (for CORS origin detection)
    """
    # Get CORS headers
    cors_headers = get_cors_headers(event)

    # Add content type if not base64
    if not is_base64:
        cors_headers['Content-Type'] = 'application/json'
    else:
        cors_headers['Content-Type'] = 'application/octet-stream'

    # Format body
    if body is None:
        formatted_body = ''
    elif isinstance(body, (dict, list)):
        formatted_body = json.dumps(body, default=str)
    else:
        formatted_body = body

    return {
        "statusCode": status_code,
        "headers": cors_headers,
        "body": formatted_body if is_base64 else formatted_body,
        "isBase64Encoded": is_base64
    }


def get_user_id(event):
    """
    Get user ID from event using the configured auth provider

    This function acts as a bridge to the auth provider system
    """
    try:
        # Import here to avoid circular dependencies
        from lib.auth_provider import AuthFactory
        provider = AuthFactory.get_provider()
        return provider.get_user_id(event)
    except ImportError:
        # Fallback to old behavior if auth_provider not available
        print("Warning: auth_provider not available, using legacy auth")

        # Try Cognito claims first
        try:
            claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
            if 'sub' in claims:
                return claims['sub']
        except:
            pass

        # Try headers
        try:
            headers = event.get('headers', {})
            user_id = headers.get('X-User-ID') or headers.get('x-user-id')
            if user_id:
                return user_id
        except:
            pass

        # No user ID found - return None instead of hardcoded value
        return None
    except Exception as e:
        print(f"Error getting user ID: {e}")
        return None

"""
Enhanced Authentication Provider with User Sync and Role-Based Access
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from functools import wraps
from datetime import datetime

from lib.auth_sync import ensure_user_exists, get_user_role, is_admin

logger = logging.getLogger(__name__)

class EnhancedCognitoAuthProvider:
    """Cognito auth provider with automatic user sync and role checking"""

    def __init__(self):
        self.user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
        self.client_id = os.environ.get('COGNITO_CLIENT_ID')
        self.region = os.environ.get('COGNITO_REGION', 'ap-south-1')

        if not self.user_pool_id or not self.client_id:
            raise ValueError("Cognito configuration missing")

        logger.info(f"Enhanced Cognito Auth initialized for pool {self.user_pool_id}")

    def verify_token_and_sync(self, token: str, db) -> Optional[Dict[str, Any]]:
        """
        Verify Cognito JWT token and sync user to database

        Args:
            token: JWT token from Cognito
            db: IbexClient instance

        Returns:
            User info dict with role from database
        """
        try:
            import jwt
            from jwt import PyJWKClient

            # Get public keys from Cognito
            jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url)

            # Decode and verify token
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                leeway=60,
                options={"verify_exp": True}
            )

            user_id = decoded.get('sub')
            if not user_id:
                return None

            # Ensure user exists in database
            ensure_user_exists(user_id, decoded, db)

            # Get user role from database (not from token)
            role = get_user_role(user_id, db) or 'participant'

            return {
                "id": user_id,
                "email": decoded.get('email'),
                "name": decoded.get('name'),
                "role": role,  # Role from database, not token
                "tenant_id": decoded.get('custom:tenant_id', 'default')
            }

        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    def get_user_from_event(self, event: Dict[str, Any], db) -> Optional[Dict[str, Any]]:
        """
        Extract and verify user from Lambda event

        Args:
            event: Lambda event
            db: IbexClient instance

        Returns:
            User info with role from database
        """
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization') or ''

        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header[7:]
        return self.verify_token_and_sync(token, db)

    def require_auth(self, func):
        """Decorator to require valid authentication with user sync"""
        @wraps(func)
        def wrapper(event, context):
            db = context.get('db')
            if not db:
                return {
                    "statusCode": 500,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Database not initialized"})
                }

            user = self.get_user_from_event(event, db)
            if not user:
                return {
                    "statusCode": 401,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Unauthorized"})
                }

            # Add user info to event context
            event['requestContext'] = event.get('requestContext', {})
            event['requestContext']['authorizer'] = {
                'userId': user['id'],
                'claims': user
            }

            return func(event, context)
        return wrapper

    def require_admin(self, func):
        """Decorator to require admin role"""
        @wraps(func)
        def wrapper(event, context):
            db = context.get('db')
            if not db:
                return {
                    "statusCode": 500,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Database not initialized"})
                }

            user = self.get_user_from_event(event, db)
            if not user:
                return {
                    "statusCode": 401,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Unauthorized"})
                }

            # Check if user is admin
            if user.get('role') != 'admin':
                return {
                    "statusCode": 403,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Admin access required"})
                }

            # Add user info to event context
            event['requestContext'] = event.get('requestContext', {})
            event['requestContext']['authorizer'] = {
                'userId': user['id'],
                'claims': user
            }

            return func(event, context)
        return wrapper

def get_enhanced_auth_provider():
    """Get the enhanced auth provider based on environment"""
    auth_mode = os.environ.get('AUTH_MODE', 'local').lower()

    if auth_mode == 'cognito':
        return EnhancedCognitoAuthProvider()
    else:
        # Return existing local auth provider
        from lib.auth_provider import LocalAuthProvider
        return LocalAuthProvider()

# Convenience decorators
def require_auth_with_sync(func):
    """Decorator that requires auth and syncs user"""
    provider = get_enhanced_auth_provider()
    return provider.require_auth(func)

def require_admin_role(func):
    """Decorator that requires admin role"""
    provider = get_enhanced_auth_provider()
    if hasattr(provider, 'require_admin'):
        return provider.require_admin(func)
    else:
        # Fallback for local auth
        return func
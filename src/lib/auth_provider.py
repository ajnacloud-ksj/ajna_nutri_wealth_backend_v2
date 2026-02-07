"""
Authentication Provider System
Supports multiple auth backends: Local (dev), Cognito (prod), Testing
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
from functools import wraps

logger = logging.getLogger(__name__)


class AuthProvider(ABC):
    """Abstract base class for authentication providers"""

    @abstractmethod
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a token and return user info or None if invalid"""
        pass

    @abstractmethod
    def get_user_id(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract user ID from Lambda event"""
        pass

    @abstractmethod
    def require_auth(self, func):
        """Decorator to require authentication for a handler"""
        pass


class LocalAuthProvider(AuthProvider):
    """Local development auth provider with mock users"""

    def __init__(self):
        # Mock users for local development
        self.mock_users = {
            "dev-user-1": {
                "id": "dev-user-1",
                "email": "developer@local.test",
                "name": "Local Developer",
                "role": "admin",
                "tenant_id": "nutriwealth"
            },
            "test-user-1": {
                "id": "test-user-1",
                "email": "testuser@local.test",
                "name": "Test User",
                "role": "participant",
                "tenant_id": "nutriwealth"
            },
            "caretaker-1": {
                "id": "caretaker-1",
                "email": "caretaker@local.test",
                "name": "Test Caretaker",
                "role": "caretaker",
                "tenant_id": "nutriwealth"
            }
        }
        self.default_user_id = "dev-user-1"
        logger.info("LocalAuthProvider initialized with mock users")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """In local mode, accept any token and return mock user"""
        # Token format for local: "local:user_id" or just use default
        if token and token.startswith("local:"):
            user_id = token.split(":")[1]
            return self.mock_users.get(user_id, self.mock_users[self.default_user_id])
        return self.mock_users[self.default_user_id]

    def get_user_id(self, event: Dict[str, Any]) -> Optional[str]:
        """Get user ID from event headers or use default for local dev"""
        headers = event.get('headers', {})

        # Check for user ID in various headers
        user_id = (
            headers.get('x-user-id') or
            headers.get('X-User-Id') or
            headers.get('x-authenticated-userid') or
            event.get('requestContext', {}).get('authorizer', {}).get('userId')
        )

        # In local dev, if no user specified, use default
        if not user_id:
            logger.debug(f"No user ID in request, using default: {self.default_user_id}")
            user_id = self.default_user_id

        return user_id

    def require_auth(self, func):
        """Decorator that always passes in local mode"""
        @wraps(func)
        def wrapper(event, context):
            # Always inject default user for local dev
            if 'authorizer' not in event.get('requestContext', {}):
                event['requestContext'] = event.get('requestContext', {})
                event['requestContext']['authorizer'] = {
                    'userId': self.default_user_id,
                    'claims': self.mock_users[self.default_user_id]
                }
            return func(event, context)
        return wrapper


class CognitoAuthProvider(AuthProvider):
    """AWS Cognito authentication provider for production"""

    def __init__(self):
        self.user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
        self.client_id = os.environ.get('COGNITO_CLIENT_ID')
        self.region = os.environ.get('COGNITO_REGION', 'us-east-1')

        if not self.user_pool_id or not self.client_id:
            raise ValueError("Cognito configuration missing. Set COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID")

        # Import boto3 only when using Cognito
        import boto3
        self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
        logger.info(f"CognitoAuthProvider initialized for pool {self.user_pool_id}")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Cognito JWT token"""
        try:
            # In production, you'd verify the JWT signature
            # For now, decode without verification (add proper JWT verification)
            import jwt
            from jwt import PyJWKClient

            # Get public keys from Cognito
            jwks_url = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url)

            # Decode and verify token
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            # Decode and verify token with 60s leeway for clock drift
            decoded = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                leeway=60,
                options={"verify_exp": True}
            )

            return {
                "id": decoded.get('sub'),
                "email": decoded.get('email'),
                "name": decoded.get('name'),
                "role": decoded.get('custom:role', 'participant'),
                "tenant_id": decoded.get('custom:tenant_id', 'default')
            }

        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    def get_user_id(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract user ID from Cognito authorizer in Lambda event"""
        # Lambda authorizer adds user info to requestContext
        authorizer = event.get('requestContext', {}).get('authorizer', {})

        # Try different possible locations based on authorizer type
        user_id = (
            authorizer.get('userId') or
            authorizer.get('claims', {}).get('sub') or
            authorizer.get('sub')
        )

        if not user_id:
            # Try to get from Authorization header and verify
            headers = event.get('headers', {})
            auth_header = headers.get('Authorization') or headers.get('authorization') or ''
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                user_info = self.verify_token(token)
                if user_info:
                    user_id = user_info['id']

        return user_id

    def require_auth(self, func):
        """Decorator to require valid Cognito authentication"""
        @wraps(func)
        def wrapper(event, context):
            user_id = self.get_user_id(event)
            if not user_id:
                return {
                    "statusCode": 401,
                    "headers": {"Access-Control-Allow-Origin": "*"},
                    "body": json.dumps({"error": "Unauthorized"})
                }

            # Add user info to context for handler use
            event['requestContext'] = event.get('requestContext', {})
            event['requestContext']['authorizer'] = event['requestContext'].get('authorizer', {})
            event['requestContext']['authorizer']['userId'] = user_id

            return func(event, context)
        return wrapper


class TestAuthProvider(AuthProvider):
    """Test auth provider for unit tests"""

    def __init__(self, test_user_id: str = "test-user"):
        self.test_user_id = test_user_id
        self.test_user = {
            "id": test_user_id,
            "email": "test@test.com",
            "name": "Test User",
            "role": "admin",
            "tenant_id": "nutriwealth"
        }

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Always return test user"""
        return self.test_user

    def get_user_id(self, event: Dict[str, Any]) -> Optional[str]:
        """Always return test user ID"""
        return self.test_user_id

    def require_auth(self, func):
        """Always allow for testing"""
        return func


class AuthFactory:
    """Factory to create appropriate auth provider based on environment"""

    _instance = None
    _provider = None

    @classmethod
    def get_provider(cls) -> AuthProvider:
        """Get singleton auth provider instance"""
        if cls._provider is None:
            auth_mode = os.environ.get('AUTH_MODE', 'local').lower()

            if auth_mode == 'cognito':
                cls._provider = CognitoAuthProvider()
            elif auth_mode == 'test':
                cls._provider = TestAuthProvider()
            else:  # Default to local
                cls._provider = LocalAuthProvider()

            logger.info(f"Using auth provider: {cls._provider.__class__.__name__}")

        return cls._provider

    @classmethod
    def reset(cls):
        """Reset provider (useful for testing)"""
        cls._provider = None


# Convenience functions
def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Get user ID from event using configured auth provider"""
    provider = AuthFactory.get_provider()
    return provider.get_user_id(event)


def require_auth(func):
    """Decorator to require authentication using configured provider"""
    provider = AuthFactory.get_provider()
    return provider.require_auth(func)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify token using configured auth provider"""
    provider = AuthFactory.get_provider()
    return provider.verify_token(token)
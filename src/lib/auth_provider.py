"""
Authentication Provider — powered by ajna-cloud-sdk

Re-exports SDK auth components so existing handler imports continue to work:
    from lib.auth_provider import require_auth, get_user_id, require_roles
"""

from ajna_cloud.auth import (
    AuthFactory,
    AuthProvider,
    LocalAuthProvider,
    CognitoAuthProvider,
    TestAuthProvider,
    AuthError,
    require_auth,
    require_roles,
    require_admin,
    require_scopes,
    get_user_id,
)

__all__ = [
    'AuthFactory',
    'AuthProvider',
    'LocalAuthProvider',
    'CognitoAuthProvider',
    'TestAuthProvider',
    'AuthError',
    'require_auth',
    'require_roles',
    'require_admin',
    'require_scopes',
    'get_user_id',
]


def verify_token(token: str):
    """Verify token using configured auth provider (convenience wrapper)."""
    provider = AuthFactory.get_provider()
    if hasattr(provider, 'authenticate'):
        # SDK providers use authenticate(event), not verify_token
        # Build a minimal event with the token in Authorization header
        event = {'headers': {'Authorization': f'Bearer {token}'}}
        try:
            return provider.authenticate(event)
        except AuthError:
            return None
    return None

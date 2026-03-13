"""
Authentication Provider — powered by ajna-cloud-sdk

Re-exports SDK auth components so existing handler imports continue to work:
    from lib.auth_provider import require_auth, get_user_id, require_roles
"""

from functools import wraps
from typing import Dict, Any, Optional

from ajna_cloud.auth import (
    AuthFactory,
    AuthProvider,
    LocalAuthProvider,
    CognitoAuthProvider,
    TestAuthProvider,
    AuthError,
    require_auth as _sdk_require_auth,
    require_roles,
    require_admin,
    require_scopes,
    get_user_id as _sdk_get_user_id,
)
from ajna_cloud import logger


def _inject_claims_into_event(event: Dict[str, Any], user_info: Dict[str, Any]):
    """Inject authenticated user claims into event so get_user_id(event) works.

    The SDK's require_auth stores user_info in context['auth'], but
    get_user_id(event) looks for requestContext.authorizer.claims.sub in the
    event.  When Lambda does its own JWT verification (not API Gateway authorizer),
    those claims are missing.  This bridges the gap.
    """
    if 'requestContext' not in event:
        event['requestContext'] = {}
    if 'authorizer' not in event['requestContext']:
        event['requestContext']['authorizer'] = {}
    if 'claims' not in event['requestContext']['authorizer']:
        event['requestContext']['authorizer']['claims'] = {}

    claims = event['requestContext']['authorizer']['claims']
    if 'sub' not in claims and user_info.get('user_id'):
        claims['sub'] = user_info['user_id']
    if 'email' not in claims and user_info.get('email'):
        claims['email'] = user_info['email']


def require_auth(func):
    """Enhanced require_auth that injects claims into the event for get_user_id
    and syncs user to database on every authenticated request."""
    @wraps(func)
    def wrapper(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        provider = AuthFactory.get_provider()
        try:
            from ajna_cloud.http import respond
        except ImportError:
            from utils.http import respond

        try:
            user_info = provider.authenticate(event)
            context['auth'] = user_info
            _inject_claims_into_event(event, user_info)

            # Auto-sync user to database (creates on first visit, updates last_usage_date)
            db = context.get('db')
            if db and user_info.get('user_id'):
                try:
                    from lib.auth_sync import ensure_user_exists
                    ensure_user_exists(user_info['user_id'], user_info.get('claims', user_info), db)
                except Exception as sync_err:
                    logger.warning(f"User sync failed (non-blocking): {sync_err}")

            return func(event, context)
        except AuthError as e:
            return respond(e.status_code, {'error': e.message})
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return respond(401, {'error': 'Authentication failed'})

    return wrapper


def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from event — checks injected claims, then SDK fallback."""
    # First try the standard SDK path (checks requestContext.authorizer.claims.sub)
    uid = _sdk_get_user_id(event)
    if uid:
        return uid
    # Fallback: check headers directly
    headers = event.get('headers', {}) or {}
    return headers.get('X-User-ID') or headers.get('x-user-id')


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
        event = {'headers': {'Authorization': f'Bearer {token}'}}
        try:
            return provider.authenticate(event)
        except AuthError:
            return None
    return None

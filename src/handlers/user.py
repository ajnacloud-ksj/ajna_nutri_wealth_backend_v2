"""
User Profile Handler
Provides endpoints for user profile management and role information
"""

from typing import Dict, Any
from lib.auth_provider import require_auth, get_user_id
from lib.auth_sync import sync_user_from_token
from lib.logger import logger, log_handler
from utils.http import respond


@log_handler
@require_auth
def get_current_user(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/user/profile - Get current user's profile with role information
    """
    user_id = get_user_id(event)
    db = context['db']

    logger.info(f"Getting user profile for {user_id}")

    # Try to sync user from token first (in case role was updated externally)
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization') or headers.get('authorization') or ''
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        sync_user_from_token(token, db)

    try:
        # Query user from database with their role
        result = db.query(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            limit=1,
            use_cache=False  # Always get fresh data for user profile
        )

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])

            if records:
                user_data = records[0]
                # Clean internal fields
                cleaned_user = {k: v for k, v in user_data.items() if not k.startswith('_')}

                logger.info(f"User profile retrieved: {user_data.get('email')} with role: {user_data.get('role', 'participant')}")

                return respond(200, cleaned_user, event=event)
            else:
                # User not found in database - should not happen if auth sync works
                logger.warning(f"User {user_id} not found in database")
                return respond(404, {"error": "User not found"}, event=event)
        else:
            error_msg = result.get('error', 'Unknown error') if result else 'Database query failed'
            logger.error(f"Failed to query user: {error_msg}")
            return respond(500, {"error": "Failed to retrieve user profile"}, event=event)

    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}", user_id=user_id, error=str(e))
        return respond(500, {"error": "Internal server error"}, event=event)


@log_handler
@require_auth
def get_user_by_id(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/user/{id} - Get a specific user by ID (for compatibility with UI)
    """
    current_user_id = get_user_id(event)
    requested_user_id = event['pathParameters'].get('id')
    db = context['db']

    # Users can only fetch their own profile unless they're admin
    if current_user_id != requested_user_id:
        # Check if current user is admin
        admin_check = db.query(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": current_user_id}],
            limit=1,
            use_cache=False
        )

        if admin_check and admin_check.get('success'):
            admin_records = admin_check.get('data', {}).get('records', [])
            if not admin_records or admin_records[0].get('role') != 'admin':
                return respond(403, {"error": "Forbidden"}, event=event)

    try:
        # Query requested user
        result = db.query(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": requested_user_id}],
            limit=1,
            use_cache=False
        )

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])

            if records:
                user_data = records[0]
                # Clean internal fields
                cleaned_user = {k: v for k, v in user_data.items() if not k.startswith('_')}

                return respond(200, cleaned_user, event=event)
            else:
                return respond(404, {"error": "User not found"}, event=event)
        else:
            return respond(500, {"error": "Failed to retrieve user"}, event=event)

    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}", error=str(e))
        return respond(500, {"error": "Internal server error"}, event=event)
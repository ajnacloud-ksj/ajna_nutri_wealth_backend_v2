"""
Admin-only endpoints for user and system management
"""

import os
import json
from typing import Dict, Any

from utils.timestamps import utc_now

from lib.auth_provider_enhanced import require_admin_role
from lib.logger import logger, log_handler
from utils.http import respond

@log_handler
@require_admin_role
def list_users_admin(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/admin/users - List all users with full details (admin only)
    """
    try:
        db = context['db']

        # Get query parameters for pagination
        query_params = event.get('queryStringParameters') or {}
        limit = min(int(query_params.get('limit', 50)), 100)
        offset = int(query_params.get('offset', 0))
        role_filter = query_params.get('role')  # Optional: filter by role

        # Build query
        kwargs = {"limit": limit, "offset": offset}
        if role_filter:
            kwargs["filters"] = [{"field": "role", "operator": "eq", "value": role_filter}]

        # Show ALL users including archived/deleted for admin view
        # include_deleted=False in db.query means "exclude deleted" — we default to showing all
        show_deleted = query_params.get('include_deleted', 'true').lower() == 'true'
        result = db.query("app_users_v4", use_cache=False, include_deleted=show_deleted, **kwargs)

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])

            # Include all user fields for admin view
            # Actual app_users_v4 fields: id, email, name, role, created_at, updated_at
            users = []
            for record in records:
                users.append({
                    "id": record.get('id'),
                    "email": record.get('email'),
                    "name": record.get('name', ''),
                    "role": record.get('role', 'participant'),
                    "subscription_tier": record.get('subscription_tier', 'free'),
                    "is_archived": record.get('_deleted', False),
                    "created_at": record.get('created_at'),
                    "updated_at": record.get('updated_at')
                })

            return respond(200, {
                "users": users,
                "total": len(users),
                "limit": limit,
                "offset": offset
            }, event=event)

        return respond(200, {"users": [], "total": 0}, event=event)

    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return respond(500, {"error": "Failed to list users"}, event=event)

@log_handler
@require_admin_role
def update_user_role(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/admin/users/{user_id}/role - Update user role (admin only)
    """
    try:
        db = context['db']
        user_id = event.get('pathParameters', {}).get('user_id')

        if not user_id:
            return respond(400, {"error": "User ID required"}, event=event)

        body = json.loads(event.get('body', '{}'))
        new_role = body.get('role')

        if not new_role:
            return respond(400, {"error": "Role required"}, event=event)

        # Validate role
        valid_roles = ['admin', 'participant', 'caretaker']
        if new_role not in valid_roles:
            return respond(400, {
                "error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            }, event=event)

        # Get requesting user (admin)
        admin_id = event['requestContext']['authorizer']['userId']

        # Prevent admin from removing their own admin role
        if user_id == admin_id and new_role != 'admin':
            return respond(400, {
                "error": "Cannot remove your own admin role"
            }, event=event)

        # Update user role
        result = db.update(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            updates={
                "role": new_role,
                "updated_at": utc_now()
            }
        )

        if result and result.get('success'):
            logger.info(f"Admin {admin_id} updated user {user_id} role to {new_role}")
            return respond(200, {
                "message": "User role updated successfully",
                "user_id": user_id,
                "new_role": new_role
            }, event=event)
        else:
            return respond(500, {"error": "Failed to update user role"}, event=event)

    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        return respond(500, {"error": "Failed to update user role"}, event=event)

@log_handler
@require_admin_role
def toggle_user_status(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/admin/users/{user_id}/status - Enable/disable user (admin only)
    """
    try:
        db = context['db']
        user_id = event.get('pathParameters', {}).get('user_id')

        if not user_id:
            return respond(400, {"error": "User ID required"}, event=event)

        body = json.loads(event.get('body', '{}'))
        is_active = body.get('is_active')

        if is_active is None:
            return respond(400, {"error": "is_active status required"}, event=event)

        # Update user status
        result = db.update(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            updates={
                "is_active": is_active,
                "updated_at": utc_now()
            }
        )

        if result and result.get('success'):
            status = "enabled" if is_active else "disabled"
            logger.info(f"User {user_id} {status}")
            return respond(200, {
                "message": f"User {status} successfully",
                "user_id": user_id,
                "is_active": is_active
            }, event=event)
        else:
            return respond(500, {"error": "Failed to update user status"}, event=event)

    except Exception as e:
        logger.error(f"Error updating user status: {e}")
        return respond(500, {"error": "Failed to update user status"}, event=event)

@log_handler
@require_admin_role
def get_system_stats(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/admin/stats - Get system statistics (admin only)
    """
    try:
        db = context['db']

        # Get user counts by role
        users_result = db.query("app_users_v4", limit=1000, use_cache=False, include_deleted=False)
        user_stats = {
            "total": 0,
            "admins": 0,
            "participants": 0,
            "caretakers": 0,
            "active": 0
        }

        if users_result and users_result.get('success'):
            users = users_result.get('data', {}).get('records', [])
            user_stats['total'] = len(users)

            for user in users:
                role = user.get('role', 'participant')
                if role == 'admin':
                    user_stats['admins'] += 1
                elif role == 'caretaker':
                    user_stats['caretakers'] += 1
                else:
                    user_stats['participants'] += 1

                if user.get('is_active', True):
                    user_stats['active'] += 1

        # Get entry counts
        tables = ['food_entries_v2', 'receipts', 'workouts']
        entry_stats = {}

        for table in tables:
            try:
                result = db.query(f"app_{table}", limit=1, include_deleted=False)
                if result and result.get('success'):
                    # Since we can't get total count easily, we'll estimate
                    entry_stats[table] = "Available"
                else:
                    entry_stats[table] = "Not available"
            except:
                entry_stats[table] = "Error"

        # Get recent activity (last 24 hours)
        from datetime import datetime, timezone, timedelta
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')

        recent_entries = 0
        try:
            result = db.query(
                "food_entries_v2",
                filters=[{"field": "created_at", "operator": "gte", "value": yesterday}],
                limit=100,
                include_deleted=False
            )
            if result and result.get('success'):
                recent_entries = len(result.get('data', {}).get('records', []))
        except:
            pass

        return respond(200, {
            "users": user_stats,
            "entries": entry_stats,
            "recent_activity": {
                "last_24h_entries": recent_entries
            },
            "system": {
                "database": "IBEX",
                "auth_mode": os.environ.get('AUTH_MODE', 'local'),
                "region": os.environ.get('AWS_REGION', 'ap-south-1')
            }
        }, event=event)

    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return respond(500, {"error": "Failed to get system stats"}, event=event)

@log_handler
@require_admin_role
def update_model_config_admin(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/admin/models/config/{use_case} - Update model configuration (admin only)
    Replaces the weak auth check in model_config.py
    """
    try:
        use_case = event.get('pathParameters', {}).get('use_case')
        if not use_case:
            return respond(400, {"error": "Use case required"}, event=event)

        body = json.loads(event.get('body', '{}'))
        if not body:
            return respond(400, {"error": "Request body required"}, event=event)

        db = context.get('db')
        from lib.model_manager import get_model_manager
        model_manager = get_model_manager(db)

        # Prepare updates
        updates = {}
        allowed_fields = [
            'provider', 'model_name', 'temperature', 'max_tokens',
            'timeout_seconds', 'cost_per_1k_tokens',
            'fallback_provider', 'fallback_model'
        ]

        for field in allowed_fields:
            if field in body:
                updates[field] = body[field]

        if not updates:
            return respond(400, {"error": "No valid fields to update"}, event=event)

        # Update the configuration
        success = model_manager.update_model_config(use_case, updates)

        if success:
            config = model_manager.get_model_config(use_case)

            admin_id = event['requestContext']['authorizer']['userId']
            logger.info(f"Admin {admin_id} updated model config for {use_case}")

            return respond(200, {
                "message": "Configuration updated successfully",
                "use_case": use_case,
                "provider": config.provider,
                "model": config.model_name
            }, event=event)
        else:
            return respond(500, {"error": "Failed to update configuration"}, event=event)

    except Exception as e:
        logger.error(f"Error updating model config: {e}")
        return respond(500, {"error": str(e)}, event=event)


# Allowed API key env vars that can be managed from admin UI
MANAGED_API_KEYS = {
    'OPENAI_API_KEY': 'OpenAI',
    'GROQ_API_KEY': 'Groq',
    'SARVAM_API_KEY': 'Sarvam',
    'ANTHROPIC_API_KEY': 'Anthropic',
    'TOGETHER_API_KEY': 'Together AI',
}

@log_handler
@require_admin_role
def get_api_keys(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/admin/api-keys - List configured API keys (masked) (admin only)
    """
    try:
        keys = []
        for env_var, provider_name in MANAGED_API_KEYS.items():
            value = os.environ.get(env_var, '')
            keys.append({
                "env_var": env_var,
                "provider": provider_name,
                "is_set": bool(value),
                "masked_value": f"{value[:4]}...{value[-4:]}" if len(value) > 8 else ("****" if value else ""),
            })

        return respond(200, {"api_keys": keys}, event=event)

    except Exception as e:
        logger.error(f"Error getting API keys: {e}")
        return respond(500, {"error": "Failed to get API keys"}, event=event)

@log_handler
@require_admin_role
def update_api_keys(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/admin/api-keys - Update API keys on Lambda env vars (admin only)
    Body: { "keys": { "OPENAI_API_KEY": "sk-...", "GROQ_API_KEY": "gsk_..." } }
    """
    try:
        import boto3

        body = json.loads(event.get('body', '{}'))
        keys_to_update = body.get('keys', {})

        if not keys_to_update:
            return respond(400, {"error": "No keys provided"}, event=event)

        # Validate only allowed keys
        for key in keys_to_update:
            if key not in MANAGED_API_KEYS:
                return respond(400, {
                    "error": f"Invalid key: {key}. Allowed: {', '.join(MANAGED_API_KEYS.keys())}"
                }, event=event)

        # Get current Lambda function name
        function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        if not function_name:
            return respond(500, {"error": "Cannot determine Lambda function name"}, event=event)

        # Update Lambda environment variables
        lambda_client = boto3.client('lambda', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))

        # Get current config
        current_config = lambda_client.get_function_configuration(FunctionName=function_name)
        current_env = current_config.get('Environment', {}).get('Variables', {})

        # Merge new keys (only update provided ones, keep others)
        updated_env = {**current_env}
        updated_keys = []
        for key, value in keys_to_update.items():
            if value:  # Don't set empty values
                updated_env[key] = value
                updated_keys.append(key)

        # Apply update
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': updated_env}
        )

        # Also update os.environ for the current invocation
        for key, value in keys_to_update.items():
            if value:
                os.environ[key] = value

        admin_id = event.get('requestContext', {}).get('authorizer', {}).get('userId', 'unknown')
        logger.info(f"Admin {admin_id} updated API keys: {updated_keys}")

        return respond(200, {
            "message": f"Updated {len(updated_keys)} API key(s)",
            "updated_keys": updated_keys
        }, event=event)

    except Exception as e:
        logger.error(f"Error updating API keys: {e}")
        return respond(500, {"error": str(e)}, event=event)
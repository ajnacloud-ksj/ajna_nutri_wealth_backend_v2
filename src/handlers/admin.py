"""
Admin-only endpoints for user and system management
"""

import os
import json
from datetime import datetime
from typing import Dict, Any

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

        result = db.query("users_v4", use_cache=False, **kwargs)

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])

            # Include all user fields for admin view
            users = []
            for record in records:
                users.append({
                    "id": record.get('id'),
                    "email": record.get('email'),
                    "full_name": record.get('full_name'),
                    "role": record.get('role', 'participant'),
                    "user_type": record.get('user_type', 'regular'),
                    "is_subscribed": record.get('is_subscribed', False),
                    "trial_used_today": record.get('trial_used_today', 0),
                    "last_usage_date": record.get('last_usage_date'),
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
            "users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            updates={
                "role": new_role,
                "updated_at": datetime.utcnow().isoformat()
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
            "users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            updates={
                "is_active": is_active,
                "updated_at": datetime.utcnow().isoformat()
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
        users_result = db.query("users_v4", limit=1000, use_cache=False)
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
                result = db.query(f"app_{table}", limit=1)
                if result and result.get('success'):
                    # Since we can't get total count easily, we'll estimate
                    entry_stats[table] = "Available"
                else:
                    entry_stats[table] = "Not available"
            except:
                entry_stats[table] = "Error"

        # Get recent activity (last 24 hours)
        from datetime import datetime, timedelta
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()

        recent_entries = 0
        try:
            result = db.query(
                "food_entries_v2",
                filters=[{"field": "created_at", "operator": "gte", "value": yesterday}],
                limit=100
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
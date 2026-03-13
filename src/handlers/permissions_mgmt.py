"""
Permissions Management Handlers

Allows participants to view and manage the data access permissions
they have granted to caretakers.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger


@require_auth
def list_permissions(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/permissions
    Participant lists all permissions they have granted.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        result = db.query(
            'app_participant_permissions',
            filters=[
                {"field": "participant_id", "operator": "eq", "value": user_id},
            ],
            sort=[{"field": "updated_at", "order": "desc"}],
            limit=200,
            use_cache=False,
            include_deleted=False,
        )

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            cleaned = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]
            return respond(200, cleaned)

        return respond(200, [])

    except Exception as e:
        logger.error(f"Error listing permissions: {e}")
        return respond(500, {"error": "Failed to list permissions"})


@require_auth
def update_permission(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/permissions/{id}
    Participant toggles a specific permission. Only the participant can modify.
    """
    db = context['db']
    user_id = get_user_id(event)
    permission_id = event.get('pathParameters', {}).get('id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    try:
        # Fetch the permission and verify ownership
        result = db.query(
            'app_participant_permissions',
            filters=[
                {"field": "id", "operator": "eq", "value": permission_id},
                {"field": "participant_id", "operator": "eq", "value": user_id},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(404, {"error": "Permission not found"})

        records = result.get('data', {}).get('records', [])
        if not records:
            return respond(404, {"error": "Permission not found or not authorized"})

        # Build updates
        updates = {}
        if 'is_granted' in body:
            updates['is_granted'] = body['is_granted']
        if 'access_level' in body:
            updates['notes'] = body['access_level']  # Store access_level in notes field

        if not updates:
            return respond(400, {"error": "No valid updates provided"})

        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        updates['updated_at'] = now

        if updates.get('is_granted'):
            updates['granted_at'] = now

        update_result = db.update(
            'app_participant_permissions',
            filters=[{"field": "id", "operator": "eq", "value": permission_id}],
            updates=updates,
        )

        if update_result and update_result.get('success'):
            return respond(200, {"id": permission_id, "updated": True, **updates})

        return respond(500, {"error": "Failed to update permission"})

    except Exception as e:
        logger.error(f"Error updating permission: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def bulk_update(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/permissions/bulk
    Participant bulk-updates permissions for a caretaker.
    Body: {caretaker_id, permissions: [{category, is_granted, access_level}]}
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    caretaker_id = body.get('caretaker_id')
    permissions = body.get('permissions', [])

    if not caretaker_id:
        return respond(400, {"error": "caretaker_id is required"})
    if not permissions:
        return respond(400, {"error": "permissions array is required"})

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    results = []

    for perm_update in permissions:
        category = perm_update.get('category')
        is_granted = perm_update.get('is_granted', False)

        if not category:
            continue

        try:
            # Check if permission already exists
            existing = db.query(
                'app_participant_permissions',
                filters=[
                    {"field": "participant_id", "operator": "eq", "value": user_id},
                    {"field": "caretaker_id", "operator": "eq", "value": caretaker_id},
                    {"field": "category", "operator": "eq", "value": category},
                ],
                limit=1,
                use_cache=False,
                include_deleted=False,
            )

            if existing and existing.get('success') and existing.get('data', {}).get('records'):
                # Update existing
                perm_id = existing['data']['records'][0]['id']
                updates = {"is_granted": is_granted, "updated_at": now}
                if is_granted:
                    updates['granted_at'] = now

                db.update(
                    'app_participant_permissions',
                    filters=[{"field": "id", "operator": "eq", "value": perm_id}],
                    updates=updates,
                )
                results.append({"category": category, "action": "updated", "is_granted": is_granted})
            else:
                # Create new
                import uuid
                new_perm = {
                    "id": str(uuid.uuid4()),
                    "participant_id": user_id,
                    "caretaker_id": caretaker_id,
                    "category": category,
                    "is_granted": is_granted,
                    "granted_at": now if is_granted else None,
                    "updated_at": now,
                }
                db.write('app_participant_permissions', [new_perm])
                results.append({"category": category, "action": "created", "is_granted": is_granted})

        except Exception as e:
            logger.error(f"Error updating permission for category {category}: {e}")
            results.append({"category": category, "action": "error", "error": str(e)})

    return respond(200, {"results": results})

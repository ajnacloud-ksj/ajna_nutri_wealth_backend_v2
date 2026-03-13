"""
Relationship Management Handlers

Manages care relationships between participants and caretakers.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger


@require_auth
def list_relationships(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/relationships
    Returns all relationships for the authenticated user (as participant OR caretaker).
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    relationships = []

    try:
        # Relationships where user is participant
        as_participant = db.query(
            'app_care_relationships',
            filters=[
                {"field": "user_id", "operator": "eq", "value": user_id},
            ],
            limit=100,
            use_cache=False,
            include_deleted=False,
        )
        if as_participant and as_participant.get('success'):
            for rel in as_participant.get('data', {}).get('records', []):
                cleaned = {k: v for k, v in rel.items() if not k.startswith('_')}
                cleaned['role'] = 'participant'
                relationships.append(cleaned)

        # Relationships where user is caretaker
        as_caretaker = db.query(
            'app_care_relationships',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": user_id},
            ],
            limit=100,
            use_cache=False,
            include_deleted=False,
        )
        if as_caretaker and as_caretaker.get('success'):
            for rel in as_caretaker.get('data', {}).get('records', []):
                cleaned = {k: v for k, v in rel.items() if not k.startswith('_')}
                cleaned['role'] = 'caretaker'
                relationships.append(cleaned)

        return respond(200, relationships)

    except Exception as e:
        logger.error(f"Error listing relationships: {e}")
        return respond(500, {"error": "Failed to list relationships"})


@require_auth
def update_relationship(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/relationships/{id}
    Participant updates relationship settings. Only the participant (user_id) can update.
    """
    db = context['db']
    user_id = get_user_id(event)
    relationship_id = event.get('pathParameters', {}).get('id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    try:
        # Fetch the relationship and verify ownership (participant only)
        result = db.query(
            'app_care_relationships',
            filters=[
                {"field": "id", "operator": "eq", "value": relationship_id},
                {"field": "user_id", "operator": "eq", "value": user_id},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(404, {"error": "Relationship not found"})

        records = result.get('data', {}).get('records', [])
        if not records:
            return respond(404, {"error": "Relationship not found or not authorized"})

        # Build updates from allowed fields
        updates = {}
        allowed_fields = ['permission_level', 'exclude_private_from_stats', 'expires_at']
        for field in allowed_fields:
            if field in body:
                updates[field] = body[field]

        if not updates:
            return respond(400, {"error": "No valid updates provided"})

        updates['updated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

        update_result = db.update(
            'app_care_relationships',
            filters=[{"field": "id", "operator": "eq", "value": relationship_id}],
            updates=updates,
        )

        if update_result and update_result.get('success'):
            return respond(200, {"id": relationship_id, "updated": True, **updates})

        return respond(500, {"error": "Failed to update relationship"})

    except Exception as e:
        logger.error(f"Error updating relationship: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def revoke_relationship(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/relationships/{id}
    Participant or caretaker can revoke a relationship.
    Sets status to 'revoked' and disables all permissions.
    """
    db = context['db']
    user_id = get_user_id(event)
    relationship_id = event.get('pathParameters', {}).get('id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        # Fetch the relationship — either participant or caretaker can revoke
        result = db.query(
            'app_care_relationships',
            filters=[
                {"field": "id", "operator": "eq", "value": relationship_id},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(404, {"error": "Relationship not found"})

        records = result.get('data', {}).get('records', [])
        if not records:
            return respond(404, {"error": "Relationship not found"})

        relationship = records[0]

        # Verify the user is either the participant or the caretaker
        if relationship.get('user_id') != user_id and relationship.get('caretaker_id') != user_id:
            return respond(403, {"error": "Not authorized to revoke this relationship"})

        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

        # Revoke the relationship
        db.update(
            'app_care_relationships',
            filters=[{"field": "id", "operator": "eq", "value": relationship_id}],
            updates={"status": "revoked", "updated_at": now},
        )

        # Disable all permissions for this relationship
        participant_id = relationship.get('user_id')
        caretaker_id = relationship.get('caretaker_id')

        try:
            perms_result = db.query(
                'app_participant_permissions',
                filters=[
                    {"field": "participant_id", "operator": "eq", "value": participant_id},
                    {"field": "caretaker_id", "operator": "eq", "value": caretaker_id},
                ],
                limit=100,
                use_cache=False,
                include_deleted=False,
            )

            if perms_result and perms_result.get('success'):
                for perm in perms_result.get('data', {}).get('records', []):
                    db.update(
                        'app_participant_permissions',
                        filters=[{"field": "id", "operator": "eq", "value": perm['id']}],
                        updates={"is_granted": False, "updated_at": now},
                    )
        except Exception as e:
            logger.warning(f"Failed to revoke permissions for relationship {relationship_id}: {e}")

        return respond(200, {"message": "Relationship revoked", "id": relationship_id})

    except Exception as e:
        logger.error(f"Error revoking relationship: {e}")
        return respond(500, {"error": str(e)})

"""
Invitation Code Handlers

Manages the invitation flow for establishing caretaker-participant relationships.
Participants create invitation codes, caretakers redeem them.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.caretaker_utils import generate_invitation_code


@require_auth
def create_invitation(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/invitations/create
    Participant creates an invitation for a caretaker.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    caretaker_type = body.get('caretaker_type', 'family')
    permission_level = body.get('permission_level', 'view')
    categories = body.get('categories', [])
    expires_in_hours = int(body.get('expires_in_hours', 72))

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=expires_in_hours)).isoformat()
    code = generate_invitation_code()

    invitation = {
        "id": str(uuid.uuid4()),
        "code": code,
        "created_by": user_id,
        "permission_level": permission_level,
        "caretaker_type": caretaker_type,
        "default_permissions": json.dumps(categories) if categories else '[]',
        "max_uses": 1,
        "current_uses": 0,
        "expires_at": expires_at,
        "created_at": now.isoformat(),
    }

    try:
        result = db.write('app_invitation_codes', [invitation])
        if result and result.get('success'):
            return respond(201, {
                "code": code,
                "expires_at": expires_at,
                "id": invitation['id'],
            })
        return respond(500, {"error": "Failed to create invitation"})
    except Exception as e:
        logger.error(f"Error creating invitation: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def list_invitations(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/invitations
    List participant's invitations.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        result = db.query(
            'app_invitation_codes',
            filters=[
                {"field": "created_by", "operator": "eq", "value": user_id},
            ],
            sort=[{"field": "created_at", "order": "desc"}],
            limit=50,
            use_cache=False,
            include_deleted=False,
        )

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            cleaned = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]
            return respond(200, cleaned)

        return respond(200, [])

    except Exception as e:
        logger.error(f"Error listing invitations: {e}")
        return respond(500, {"error": "Failed to list invitations"})


@require_auth
def revoke_invitation(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/invitations/{id}
    Participant revokes an unused invitation.
    """
    db = context['db']
    user_id = get_user_id(event)
    invitation_id = event.get('pathParameters', {}).get('id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        # Fetch the invitation and validate ownership
        result = db.query(
            'app_invitation_codes',
            filters=[
                {"field": "id", "operator": "eq", "value": invitation_id},
                {"field": "created_by", "operator": "eq", "value": user_id},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(404, {"error": "Invitation not found"})

        records = result.get('data', {}).get('records', [])
        if not records:
            return respond(404, {"error": "Invitation not found"})

        invitation = records[0]
        if invitation.get('used_by'):
            return respond(400, {"error": "Cannot revoke an already-used invitation"})

        # Soft-delete via update (set expires_at to past)
        update_result = db.update(
            'app_invitation_codes',
            filters=[{"field": "id", "operator": "eq", "value": invitation_id}],
            updates={"expires_at": "2000-01-01T00:00:00Z"},
        )

        if update_result and update_result.get('success'):
            return respond(200, {"message": "Invitation revoked"})

        return respond(500, {"error": "Failed to revoke invitation"})

    except Exception as e:
        logger.error(f"Error revoking invitation: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def redeem_invitation(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/invitations/redeem
    Caretaker redeems an invitation code to establish a care relationship.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    code = body.get('code', '').strip().upper()
    if not code:
        return respond(400, {"error": "code is required"})

    try:
        # Look up the invitation
        result = db.query(
            'app_invitation_codes',
            filters=[
                {"field": "code", "operator": "eq", "value": code},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(404, {"error": "Invalid invitation code"})

        records = result.get('data', {}).get('records', [])
        if not records:
            return respond(404, {"error": "Invalid invitation code"})

        invitation = records[0]

        # Validate not expired
        expires_at = invitation.get('expires_at', '')
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if exp_dt < datetime.now(timezone.utc):
                    return respond(400, {"error": "Invitation code has expired"})
            except (ValueError, TypeError):
                pass

        # Validate max uses
        max_uses = int(invitation.get('max_uses', 1) or 1)
        current_uses = int(invitation.get('current_uses', 0) or 0)
        if current_uses >= max_uses:
            return respond(400, {"error": "Invitation code has already been used"})

        # Cannot redeem your own invitation
        participant_id = invitation.get('created_by')
        if participant_id == user_id:
            return respond(400, {"error": "Cannot redeem your own invitation"})

        # Check if relationship already exists
        existing = db.query(
            'app_care_relationships',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": user_id},
                {"field": "user_id", "operator": "eq", "value": participant_id},
                {"field": "status", "operator": "eq", "value": "active"},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )
        if existing and existing.get('success'):
            existing_records = existing.get('data', {}).get('records', [])
            if existing_records:
                return respond(400, {"error": "Active relationship already exists with this participant"})

        now = datetime.now(timezone.utc).isoformat()

        # Create care relationship
        relationship_id = str(uuid.uuid4())
        relationship = {
            "id": relationship_id,
            "user_id": participant_id,
            "caretaker_id": user_id,
            "caretaker_type": invitation.get('caretaker_type', 'family'),
            "status": "active",
            "permission_level": invitation.get('permission_level', 'view'),
            "relationship_type": invitation.get('caretaker_type', 'family'),
            "invited_by": participant_id,
            "invited_at": now,
            "approved_at": now,
            "created_at": now,
            "updated_at": now,
        }

        rel_result = db.write('app_care_relationships', [relationship])
        if not (rel_result and rel_result.get('success')):
            return respond(500, {"error": "Failed to create relationship"})

        # Create participant_permissions based on invitation categories
        categories = []
        default_perms = invitation.get('default_permissions', '[]')
        try:
            categories = json.loads(default_perms) if default_perms else []
        except (json.JSONDecodeError, TypeError):
            categories = []

        # If no specific categories, grant all
        if not categories:
            categories = ['food_entries', 'workouts', 'receipts', 'bank_transactions']

        permissions_created = []
        for cat in categories:
            perm = {
                "id": str(uuid.uuid4()),
                "participant_id": participant_id,
                "caretaker_id": user_id,
                "category": cat,
                "is_granted": True,
                "granted_at": now,
                "updated_at": now,
            }
            try:
                db.write('app_participant_permissions', [perm])
                permissions_created.append(cat)
            except Exception as e:
                logger.error(f"Failed to create permission for category {cat}: {e}")

        # Mark invitation as used
        db.update(
            'app_invitation_codes',
            filters=[{"field": "id", "operator": "eq", "value": invitation['id']}],
            updates={
                "used_by": user_id,
                "used_at": now,
                "current_uses": current_uses + 1,
            },
        )

        # Get participant name for response
        participant_name = ''
        try:
            user_result = db.query(
                'app_users_v4',
                filters=[{"field": "id", "operator": "eq", "value": participant_id}],
                limit=1,
                use_cache=False,
                include_deleted=False,
            )
            if user_result and user_result.get('success'):
                users = user_result.get('data', {}).get('records', [])
                if users:
                    participant_name = users[0].get('name', '')
        except Exception:
            pass

        return respond(200, {
            "relationship_id": relationship_id,
            "participant_name": participant_name,
            "permissions": permissions_created,
        })

    except Exception as e:
        logger.error(f"Error redeeming invitation: {e}")
        return respond(500, {"error": str(e)})

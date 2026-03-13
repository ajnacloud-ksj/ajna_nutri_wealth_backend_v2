"""
Caretaker Data Access Handlers

Provides endpoints for caretakers to view participant data, add notes/comments,
and for participants to view their access logs.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.caretaker_utils import (
    validate_caretaker_relationship,
    check_category_permission,
    log_access,
)


# Maps category path param to actual DB table name
CATEGORY_TABLE_MAP = {
    'food_entries': 'app_food_entries_v2',
    'workouts': 'app_workouts',
    'receipts': 'app_receipts',
    'bank_transactions': 'app_bank_transactions',
}


@require_auth
def list_participants(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/caretaker/participants
    Returns list of participants the authenticated caretaker has active relationships with.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    try:
        # Get active relationships where user is the caretaker
        result = db.query(
            'app_care_relationships',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": user_id},
                {"field": "status", "operator": "eq", "value": "active"},
            ],
            limit=100,
            use_cache=False,
            include_deleted=False,
        )

        if not (result and result.get('success')):
            return respond(200, [])

        relationships = result.get('data', {}).get('records', [])
        if not relationships:
            return respond(200, [])

        # Enrich with participant info from app_users_v4
        participants = []
        for rel in relationships:
            participant_id = rel.get('user_id')
            participant_info = {"participant_id": participant_id}

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
                        participant_info['name'] = users[0].get('name', '')
                        participant_info['email'] = users[0].get('email', '')
            except Exception as e:
                logger.warning(f"Could not fetch user info for {participant_id}: {e}")
                participant_info['name'] = ''
                participant_info['email'] = ''

            participant_info['caretaker_type'] = rel.get('caretaker_type', '')
            participant_info['permission_level'] = rel.get('permission_level', '')
            participant_info['created_at'] = rel.get('created_at', '')

            participants.append(participant_info)

        return respond(200, participants)

    except Exception as e:
        logger.error(f"Error listing participants: {e}")
        return respond(500, {"error": "Failed to list participants"})


@require_auth
def get_permissions(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/caretaker/participants/{participant_id}/permissions
    Returns the caretaker's permissions for a specific participant.
    """
    db = context['db']
    user_id = get_user_id(event)
    participant_id = event.get('pathParameters', {}).get('participant_id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    # Validate active relationship
    relationship = validate_caretaker_relationship(db, user_id, participant_id)
    if not relationship:
        return respond(403, {"error": "No active care relationship found"})

    try:
        result = db.query(
            'app_participant_permissions',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": user_id},
                {"field": "participant_id", "operator": "eq", "value": participant_id},
            ],
            limit=50,
            use_cache=False,
            include_deleted=False,
        )

        if result and result.get('success'):
            permissions = result.get('data', {}).get('records', [])
            cleaned = [{k: v for k, v in p.items() if not k.startswith('_')} for p in permissions]
            return respond(200, cleaned)

        return respond(200, [])

    except Exception as e:
        logger.error(f"Error getting permissions: {e}")
        return respond(500, {"error": "Failed to get permissions"})


@require_auth
def get_participant_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/caretaker/participants/{participant_id}/{category}
    Caretaker views participant's data for a specific category.
    """
    db = context['db']
    user_id = get_user_id(event)
    participant_id = event.get('pathParameters', {}).get('participant_id')
    category = event.get('pathParameters', {}).get('category')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    # Validate category
    if category not in CATEGORY_TABLE_MAP:
        return respond(400, {"error": f"Invalid category: {category}. Must be one of: {', '.join(CATEGORY_TABLE_MAP.keys())}"})

    # Validate active relationship
    relationship = validate_caretaker_relationship(db, user_id, participant_id)
    if not relationship:
        return respond(403, {"error": "No active care relationship found"})

    # Check category permission
    if not check_category_permission(db, user_id, participant_id, category):
        return respond(403, {"error": f"Permission denied for category: {category}"})

    # Get query params
    query_params = event.get('queryStringParameters') or {}
    limit = min(int(query_params.get('limit', 50)), 1000)
    offset = int(query_params.get('offset', 0))
    order_by = query_params.get('order_by', 'created_at')
    order_dir = query_params.get('order_dir', 'desc')

    table_name = CATEGORY_TABLE_MAP[category]

    try:
        filters = [
            {"field": "user_id", "operator": "eq", "value": participant_id},
        ]

        sort = [{"field": order_by, "order": order_dir}]

        kwargs = {
            "filters": filters,
            "limit": limit,
            "sort": sort,
            "use_cache": False,
            "include_deleted": False,
        }
        if offset > 0:
            kwargs["offset"] = offset

        result = db.query(table_name, **kwargs)

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])

            # Filter out private entries if is_private field exists
            records = [r for r in records if not r.get('is_private', False)]

            # Clean internal fields
            cleaned = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]

            # Log access
            log_access(
                db, user_id, participant_id,
                action='view',
                resource_type=category,
                category=category,
                event=event,
                record_count=len(cleaned),
            )

            return respond(200, cleaned)

        return respond(200, [])

    except Exception as e:
        logger.error(f"Error getting participant data ({category}): {e}")
        return respond(500, {"error": f"Failed to get {category} data"})


@require_auth
def get_participant_dashboard(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/caretaker/participants/{participant_id}/analytics/dashboard
    Returns summary analytics for a participant (last 30 days).
    """
    db = context['db']
    user_id = get_user_id(event)
    participant_id = event.get('pathParameters', {}).get('participant_id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    # Validate active relationship
    relationship = validate_caretaker_relationship(db, user_id, participant_id)
    if not relationship:
        return respond(403, {"error": "No active care relationship found"})

    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')
    dashboard = {}

    # Food entries summary
    try:
        food_result = db.execute_sql(
            "SELECT COUNT(*) as total_entries, "
            "COALESCE(AVG(CAST(json_extract_string(extracted_nutrients, '$.total_calories') AS DOUBLE)), 0) as avg_calories "
            "FROM app_food_entries_v2 "
            "WHERE user_id = ? AND _deleted = false AND created_at >= ?",
            params=[participant_id, since]
        )
        if food_result.get('data', {}).get('records'):
            dashboard['food'] = food_result['data']['records'][0]
    except Exception as e:
        logger.warning(f"Food analytics failed for participant {participant_id}: {e}")
        dashboard['food'] = {}

    # Workouts summary
    try:
        workout_result = db.execute_sql(
            "SELECT COUNT(*) as total_workouts "
            "FROM app_workouts "
            "WHERE user_id = ? AND _deleted = false AND created_at >= ?",
            params=[participant_id, since]
        )
        if workout_result.get('data', {}).get('records'):
            dashboard['workouts'] = workout_result['data']['records'][0]
    except Exception as e:
        logger.warning(f"Workout analytics failed for participant {participant_id}: {e}")
        dashboard['workouts'] = {}

    # Receipts summary
    try:
        receipt_result = db.execute_sql(
            "SELECT COUNT(*) as total_receipts, "
            "COALESCE(SUM(total_amount), 0) as total_spent "
            "FROM app_receipts "
            "WHERE user_id = ? AND _deleted = false AND created_at >= ?",
            params=[participant_id, since]
        )
        if receipt_result.get('data', {}).get('records'):
            dashboard['receipts'] = receipt_result['data']['records'][0]
    except Exception as e:
        logger.warning(f"Receipt analytics failed for participant {participant_id}: {e}")
        dashboard['receipts'] = {}

    dashboard['period_days'] = 30

    # Log access
    log_access(
        db, user_id, participant_id,
        action='view_dashboard',
        resource_type='analytics',
        category='dashboard',
        event=event,
    )

    return respond(200, dashboard)


@require_auth
def add_note(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/caretaker/participants/{participant_id}/notes
    Caretaker adds a note about a participant.
    """
    db = context['db']
    user_id = get_user_id(event)
    participant_id = event.get('pathParameters', {}).get('participant_id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    # Validate active relationship
    relationship = validate_caretaker_relationship(db, user_id, participant_id)
    if not relationship:
        return respond(403, {"error": "No active care relationship found"})

    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    content = body.get('content')
    if not content:
        return respond(400, {"error": "content is required"})

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    note = {
        "id": str(uuid.uuid4()),
        "care_relationship_id": relationship.get('id', ''),
        "author_id": user_id,
        "note_text": content,
        "note_type": body.get('category', 'general'),
        "is_visible_to_user": True,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = db.write('app_caretaker_notes', [note])
        if result and result.get('success'):
            return respond(201, note)
        return respond(500, {"error": "Failed to create note"})
    except Exception as e:
        logger.error(f"Error creating note: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def add_comment(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/caretaker/participants/{participant_id}/comments
    Caretaker adds a comment on a specific entry.
    """
    db = context['db']
    user_id = get_user_id(event)
    participant_id = event.get('pathParameters', {}).get('participant_id')

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    # Validate active relationship
    relationship = validate_caretaker_relationship(db, user_id, participant_id)
    if not relationship:
        return respond(403, {"error": "No active care relationship found"})

    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"})

    content = body.get('content')
    entry_id = body.get('entry_id')
    entry_type = body.get('entry_type')

    if not content:
        return respond(400, {"error": "content is required"})
    if not entry_id or not entry_type:
        return respond(400, {"error": "entry_id and entry_type are required"})

    # Validate permission for the entry's category
    if not check_category_permission(db, user_id, participant_id, entry_type):
        return respond(403, {"error": f"Permission denied for category: {entry_type}"})

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    comment = {
        "id": str(uuid.uuid4()),
        "participant_id": participant_id,
        "caretaker_id": user_id,
        "author_type": "caretaker",
        "content_type": entry_type,
        "content_id": entry_id,
        "comment_text": content,
        "is_visible_to_participant": True,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = db.write('app_participant_comments', [comment])
        if result and result.get('success'):
            return respond(201, comment)
        return respond(500, {"error": "Failed to create comment"})
    except Exception as e:
        logger.error(f"Error creating comment: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def get_access_log(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/access-log
    Participant views who accessed their data. Only returns logs where
    participant_id matches the authenticated user.
    """
    db = context['db']
    user_id = get_user_id(event)

    if not user_id:
        return respond(401, {"error": "Authentication required"})

    query_params = event.get('queryStringParameters') or {}
    limit = min(int(query_params.get('limit', 50)), 1000)
    offset = int(query_params.get('offset', 0))

    filters = [
        {"field": "participant_id", "operator": "eq", "value": user_id},
    ]

    # Optional filters
    if query_params.get('caretaker_id'):
        filters.append({"field": "caretaker_id", "operator": "eq", "value": query_params['caretaker_id']})
    if query_params.get('category'):
        filters.append({"field": "category", "operator": "eq", "value": query_params['category']})

    try:
        kwargs = {
            "filters": filters,
            "limit": limit,
            "sort": [{"field": "created_at", "order": "desc"}],
            "use_cache": False,
            "include_deleted": False,
        }
        if offset > 0:
            kwargs["offset"] = offset

        result = db.query('app_access_log', **kwargs)

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            cleaned = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]
            return respond(200, cleaned)

        return respond(200, [])

    except Exception as e:
        logger.error(f"Error getting access log: {e}")
        return respond(500, {"error": "Failed to get access log"})

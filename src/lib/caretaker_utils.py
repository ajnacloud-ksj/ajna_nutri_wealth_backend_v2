"""
Caretaker Access shared utilities.

Provides validation helpers, access logging, and invitation code generation
used across caretaker, invitations, relationships, and permissions handlers.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from lib.logger import logger


# Alphanumeric characters without ambiguous ones (0/O, 1/l/I)
SAFE_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def validate_caretaker_relationship(db, caretaker_id: str, participant_id: str) -> Optional[dict]:
    """
    Validate that an active care relationship exists between caretaker and participant.
    Returns the relationship dict if found, or None.
    """
    try:
        result = db.query(
            'app_care_relationships',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": caretaker_id},
                {"field": "user_id", "operator": "eq", "value": participant_id},
                {"field": "status", "operator": "eq", "value": "active"},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )
        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            return records[0] if records else None
    except Exception as e:
        logger.error(f"Error validating caretaker relationship: {e}")
    return None


def check_category_permission(db, caretaker_id: str, participant_id: str, category: str) -> bool:
    """
    Check if caretaker has permission for a specific data category.
    Returns True if permission is granted, False otherwise.
    """
    try:
        result = db.query(
            'app_participant_permissions',
            filters=[
                {"field": "caretaker_id", "operator": "eq", "value": caretaker_id},
                {"field": "participant_id", "operator": "eq", "value": participant_id},
                {"field": "category", "operator": "eq", "value": category},
                {"field": "is_granted", "operator": "eq", "value": True},
            ],
            limit=1,
            use_cache=False,
            include_deleted=False,
        )
        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            return len(records) > 0
    except Exception as e:
        logger.error(f"Error checking category permission: {e}")
    return False


def log_access(db, caretaker_id: str, participant_id: str, action: str,
               resource_type: str, category: str, event: dict, record_count: int = 0):
    """
    Write an access log entry. Fire-and-forget — errors are logged but not raised.
    """
    try:
        headers = event.get('headers', {}) or {}
        ip_address = (
            headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or headers.get('x-forwarded-for', '').split(',')[0].strip()
            or ''
        )
        user_agent = headers.get('User-Agent') or headers.get('user-agent') or ''

        entry = {
            "id": str(uuid.uuid4()),
            "caretaker_id": caretaker_id,
            "participant_id": participant_id,
            "action": action,
            "resource_type": resource_type,
            "category": category,
            "record_count": record_count,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.write('app_access_log', [entry])
    except Exception as e:
        logger.error(f"Failed to write access log: {e}")


def generate_invitation_code() -> str:
    """Generate 8-char alphanumeric code without ambiguous characters (0/O/1/l/I)."""
    return ''.join(random.choices(SAFE_CHARS, k=8))

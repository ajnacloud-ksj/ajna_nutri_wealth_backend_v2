"""
Rate limiter for free-tier users.
Counts today's AI analyses via app_api_costs table (single source of truth).
Pro/subscribed users bypass the limit.
"""

import os
from datetime import datetime, timezone
from lib.logger import logger


FREE_DAILY_LIMIT = int(os.environ.get('FREE_DAILY_LIMIT', '10'))


def check_analysis_quota(db, user_id: str) -> tuple:
    """
    Check if user can submit another analysis today.
    Returns (allowed: bool, remaining: int, message: str)
    """
    try:
        # Check subscription status and admin role using db.query()
        # (execute_sql via Iceberg may not see all columns)
        sub_result = db.query(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            limit=1,
            include_deleted=False
        )
        sub_records = sub_result.get('data', {}).get('records', [])

        if sub_records:
            user = sub_records[0]
            if user.get('is_subscribed') or user.get('role') == 'admin' or user.get('subscription_tier') == 'pro':
                return True, 999, "Unlimited access"

        # Count today's analyses from app_api_costs
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        count_result = db.query(
            "app_api_costs",
            filters=[
                {"field": "user_id", "operator": "eq", "value": user_id},
                {"field": "created_at", "operator": "gte", "value": today + "T00:00:00"},
                {"field": "created_at", "operator": "lt", "value": today + "T23:59:59"}
            ],
            limit=1000,
            include_deleted=False
        )
        count_records = count_result.get('data', {}).get('records', [])
        used_today = len(count_records)

        remaining = max(0, FREE_DAILY_LIMIT - used_today)

        if used_today >= FREE_DAILY_LIMIT:
            return False, 0, f"Daily limit of {FREE_DAILY_LIMIT} free analyses reached. Upgrade to Pro for unlimited."

        return True, remaining, f"{used_today}/{FREE_DAILY_LIMIT} used today"

    except Exception as e:
        # Fail open - don't block users on system errors
        logger.warning(f"Rate limiter error: {e}")
        return True, FREE_DAILY_LIMIT, "Quota check bypassed"

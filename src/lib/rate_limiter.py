"""
Rate limiter for free-tier users.
Counts today's AI analyses via app_api_costs table (single source of truth).
Pro/subscribed users bypass the limit.
"""

from datetime import datetime, timezone
from lib.logger import logger


FREE_DAILY_LIMIT = 5


def check_analysis_quota(db, user_id: str) -> tuple:
    """
    Check if user can submit another analysis today.
    Returns (allowed: bool, remaining: int, message: str)
    """
    try:
        # Check subscription status and admin role
        sub_result = db.execute_sql(
            "SELECT is_subscribed, role FROM app_users_v4 "
            "WHERE id = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            params=[user_id]
        )
        sub_records = sub_result.get('data', {}).get('records', [])

        if sub_records:
            user = sub_records[0]
            if user.get('is_subscribed') or user.get('role') == 'admin':
                return True, 999, "Unlimited access"

        # Count today's analyses from app_api_costs
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        count_result = db.execute_sql(
            "SELECT COUNT(*) AS cnt FROM app_api_costs "
            "WHERE user_id = ? "
            "AND CAST(created_at AS DATE) = ?",
            params=[user_id, today]
        )
        count_records = count_result.get('data', {}).get('records', [])
        used_today = int(count_records[0].get('cnt', 0)) if count_records else 0

        remaining = max(0, FREE_DAILY_LIMIT - used_today)

        if used_today >= FREE_DAILY_LIMIT:
            return False, 0, f"Daily limit of {FREE_DAILY_LIMIT} free analyses reached. Upgrade to Pro for unlimited."

        return True, remaining, f"{used_today}/{FREE_DAILY_LIMIT} used today"

    except Exception as e:
        # Fail open - don't block users on system errors
        logger.warning(f"Rate limiter error: {e}")
        return True, FREE_DAILY_LIMIT, "Quota check bypassed"

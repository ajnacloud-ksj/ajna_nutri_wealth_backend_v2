"""
Rate limiter for free-tier users.
Counts today's AI analyses via app_api_costs table (single source of truth).
Pro/subscribed users bypass the limit.
"""

from datetime import datetime, timezone


FREE_DAILY_LIMIT = 5


def check_analysis_quota(db, user_id: str) -> tuple:
    """
    Check if user can submit another analysis today.
    Returns (allowed: bool, remaining: int, message: str)
    """
    try:
        # Check subscription status
        sub_sql = (
            f"SELECT is_subscribed FROM app_users "
            f"WHERE id = '{user_id}' "
            f"ORDER BY updated_at DESC LIMIT 1"
        )
        sub_result = db.execute_sql(sub_sql)
        sub_records = sub_result.get('data', {}).get('records', [])

        if sub_records and sub_records[0].get('is_subscribed'):
            return True, 999, "Pro subscription - unlimited"

        # Count today's analyses from app_api_costs
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        count_sql = (
            f"SELECT COUNT(*) AS cnt FROM app_api_costs "
            f"WHERE user_id = '{user_id}' "
            f"AND CAST(created_at AS DATE) = '{today}'"
        )
        count_result = db.execute_sql(count_sql)
        count_records = count_result.get('data', {}).get('records', [])
        used_today = int(count_records[0].get('cnt', 0)) if count_records else 0

        remaining = max(0, FREE_DAILY_LIMIT - used_today)

        if used_today >= FREE_DAILY_LIMIT:
            return False, 0, f"Daily limit of {FREE_DAILY_LIMIT} free analyses reached. Upgrade to Pro for unlimited."

        return True, remaining, f"{used_today}/{FREE_DAILY_LIMIT} used today"

    except Exception as e:
        # Fail open - don't block users on system errors
        print(f"Rate limiter error: {e}")
        return True, FREE_DAILY_LIMIT, "Quota check bypassed"

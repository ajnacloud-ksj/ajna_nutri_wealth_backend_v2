from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from src.lib.ibex_client import IbexClient
import os

class RateLimiter:
    def __init__(self, ibex_client: IbexClient):
        self.ibex = ibex_client
        self.daily_limit = 10  # Limit for free users

    def check_limit(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if user has reached their daily limit.
        Returns (allowed, reason).
        If allowed, increments the counter.
        """
        try:
            # 1. Fetch user data
            user = self.ibex.get_item("users", user_id)
            if not user:
                return False, "User not found"

            # 2. Check subscription (Pro users have no limits)
            if user.get("is_subscribed", False):
                return True, "Pro subscription"

            # 3. Check daily reset
            today = datetime.now().strftime("%Y-%m-%d")
            last_usage = user.get("last_usage_date")
            current_usage = user.get("trial_used_today", 0)

            needs_reset = last_usage != today

            if needs_reset:
                current_usage = 0

            # 4. Check limit
            if current_usage >= self.daily_limit:
                return False, f"Daily limit of {self.daily_limit} reached. Please upgrade to Pro."

            # 5. Increment usage
            new_usage = current_usage + 1
            
            # 6. Update user record
            update_data = {
                "trial_used_today": new_usage,
                "last_usage_date": today
            }
            
            self.ibex.update_item("users", user_id, update_data)
            
            return True, "Allowed"

        except Exception as e:
            print(f"Rate limiter error: {e}")
            # Fail open (allow) or closed (deny) depending on policy
            # Currently failing open to avoid blocking users on system errors
            return True, "Error check bypassed"

"""
User Synchronization Module
Handles automatic sync between Cognito and database
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def ensure_user_exists(user_id: str, user_claims: Dict[str, Any], db) -> bool:
    """
    Ensure user exists in database, create if not

    Args:
        user_id: Cognito user ID (sub claim)
        user_claims: JWT claims from Cognito
        db: IbexClient instance

    Returns:
        bool: True if user exists or was created successfully
    """
    try:
        # Check if user already exists
        result = db.query(
            "users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            limit=1,
            use_cache=False  # Always check fresh data
        )

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])

            if records:
                # User exists, update last seen
                logger.info(f"User {user_id} exists, updating last seen")

                db.update(
                    "users_v4",
                    filters=[{"field": "id", "operator": "eq", "value": user_id}],
                    updates={
                        "last_usage_date": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                )
                return True

        # User doesn't exist, create new user
        email = user_claims.get('email', '')
        full_name = user_claims.get('name', '') or user_claims.get('given_name', '') or email.split('@')[0]

        # Check for custom attributes (Cognito custom attributes are prefixed with 'custom:')
        role = user_claims.get('custom:role', 'participant')
        user_type = user_claims.get('custom:user_type', 'regular')

        # For first user in system, make them admin
        # Check if this is the first user
        all_users_result = db.query("users_v4", limit=1)
        if all_users_result and all_users_result.get('success'):
            existing_users = all_users_result.get('data', {}).get('records', [])
            if len(existing_users) == 0:
                logger.info(f"First user in system, granting admin role to {email}")
                role = 'admin'

        user_data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "user_type": user_type,
            "is_subscribed": False,
            "trial_used_today": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_usage_date": datetime.utcnow().isoformat()
        }

        logger.info(f"Creating new user: {email} with role: {role}")

        write_result = db.write("users_v4", [user_data])

        if write_result and write_result.get('success'):
            logger.info(f"Successfully created user {user_id} ({email})")
            return True
        else:
            logger.error(f"Failed to create user {user_id}: {write_result}")
            return False

    except Exception as e:
        logger.error(f"Error in ensure_user_exists for {user_id}: {e}")
        # Don't fail the request if sync fails
        return False

def sync_user_from_token(token: str, db) -> Optional[str]:
    """
    Sync user from Cognito token to database

    Args:
        token: JWT token from Cognito
        db: IbexClient instance

    Returns:
        str: User ID if successful, None otherwise
    """
    try:
        import jwt
        from jwt import PyJWKClient

        # Get Cognito configuration
        region = os.environ.get('COGNITO_REGION', 'ap-south-1')
        user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
        client_id = os.environ.get('COGNITO_CLIENT_ID')

        if not user_pool_id or not client_id:
            logger.warning("Cognito not configured, skipping sync")
            return None

        # Verify and decode token
        jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        jwks_client = PyJWKClient(jwks_url)

        signing_key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            leeway=60,
            options={"verify_exp": True}
        )

        user_id = decoded.get('sub')
        if user_id:
            # Ensure user exists in database
            ensure_user_exists(user_id, decoded, db)
            return user_id

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired, skipping sync")
    except Exception as e:
        logger.error(f"Error syncing user from token: {e}")

    return None

def get_user_role(user_id: str, db) -> Optional[str]:
    """
    Get user role from database

    Args:
        user_id: User ID
        db: IbexClient instance

    Returns:
        str: User role or None if not found
    """
    try:
        result = db.query(
            "users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            limit=1,
            use_cache=False
        )

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])
            if records:
                return records[0].get('role', 'participant')

    except Exception as e:
        logger.error(f"Error getting user role: {e}")

    return None

def is_admin(user_id: str, db) -> bool:
    """
    Check if user has admin role

    Args:
        user_id: User ID
        db: IbexClient instance

    Returns:
        bool: True if user is admin
    """
    role = get_user_role(user_id, db)
    return role == 'admin'
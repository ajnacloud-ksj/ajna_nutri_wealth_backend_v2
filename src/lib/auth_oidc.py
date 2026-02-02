"""
OpenID Connect (OIDC) Authentication Provider
Supports Google, Auth0, Okta, Azure AD, and other OIDC providers
"""

import os
import json
import time
import jwt
import requests
from typing import Dict, Any, Optional, Tuple
from functools import lru_cache
from dataclasses import dataclass

from lib.logger import logger


@dataclass
class OIDCConfig:
    """OIDC Provider Configuration"""
    issuer: str
    client_id: str
    client_secret: Optional[str] = None
    jwks_uri: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    scopes: str = "openid profile email"


class OIDCProvider:
    """OpenID Connect Authentication Provider"""

    # Common OIDC provider configurations
    PROVIDERS = {
        "google": {
            "issuer": "https://accounts.google.com",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo"
        },
        "auth0": {
            "issuer": os.environ.get("AUTH0_DOMAIN", "https://your-tenant.auth0.com"),
            "jwks_uri": f"{os.environ.get('AUTH0_DOMAIN', 'https://your-tenant.auth0.com')}/.well-known/jwks.json",
            "authorization_endpoint": f"{os.environ.get('AUTH0_DOMAIN')}authorize",
            "token_endpoint": f"{os.environ.get('AUTH0_DOMAIN')}oauth/token",
            "userinfo_endpoint": f"{os.environ.get('AUTH0_DOMAIN')}userinfo"
        },
        "okta": {
            "issuer": os.environ.get("OKTA_DOMAIN", "https://your-org.okta.com"),
            "jwks_uri": f"{os.environ.get('OKTA_DOMAIN')}/.well-known/jwks.json"
        },
        "azure": {
            "issuer": f"https://login.microsoftonline.com/{os.environ.get('AZURE_TENANT_ID', 'common')}/v2.0",
            "jwks_uri": f"https://login.microsoftonline.com/{os.environ.get('AZURE_TENANT_ID', 'common')}/discovery/v2.0/keys"
        },
        "custom": {
            "issuer": os.environ.get("OIDC_ISSUER", ""),
            "jwks_uri": os.environ.get("OIDC_JWKS_URI", ""),
            "client_id": os.environ.get("OIDC_CLIENT_ID", ""),
            "authorization_endpoint": os.environ.get("OIDC_AUTH_ENDPOINT", ""),
            "token_endpoint": os.environ.get("OIDC_TOKEN_ENDPOINT", ""),
            "userinfo_endpoint": os.environ.get("OIDC_USERINFO_ENDPOINT", "")
        }
    }

    def __init__(self, provider: str = "custom"):
        """Initialize OIDC provider"""
        self.provider_name = provider
        self.config = self._load_config(provider)
        self._jwks_cache = {}
        self._jwks_cache_time = 0
        self._jwks_cache_ttl = 3600  # 1 hour

    def _load_config(self, provider: str) -> OIDCConfig:
        """Load provider configuration"""
        base_config = self.PROVIDERS.get(provider, self.PROVIDERS["custom"])

        # Allow environment variables to override
        config = OIDCConfig(
            issuer=os.environ.get("OIDC_ISSUER", base_config.get("issuer", "")),
            client_id=os.environ.get("OIDC_CLIENT_ID", ""),
            client_secret=os.environ.get("OIDC_CLIENT_SECRET"),
            jwks_uri=os.environ.get("OIDC_JWKS_URI", base_config.get("jwks_uri")),
            authorization_endpoint=os.environ.get("OIDC_AUTH_ENDPOINT", base_config.get("authorization_endpoint")),
            token_endpoint=os.environ.get("OIDC_TOKEN_ENDPOINT", base_config.get("token_endpoint")),
            userinfo_endpoint=os.environ.get("OIDC_USERINFO_ENDPOINT", base_config.get("userinfo_endpoint")),
            scopes=os.environ.get("OIDC_SCOPES", "openid profile email")
        )

        # Auto-discover endpoints if not provided
        if config.issuer and not config.jwks_uri:
            config = self._discover_endpoints(config)

        return config

    def _discover_endpoints(self, config: OIDCConfig) -> OIDCConfig:
        """Auto-discover OIDC endpoints from .well-known"""
        try:
            discovery_url = f"{config.issuer}/.well-known/openid-configuration"
            response = requests.get(discovery_url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                config.jwks_uri = data.get("jwks_uri", config.jwks_uri)
                config.authorization_endpoint = data.get("authorization_endpoint", config.authorization_endpoint)
                config.token_endpoint = data.get("token_endpoint", config.token_endpoint)
                config.userinfo_endpoint = data.get("userinfo_endpoint", config.userinfo_endpoint)
                logger.info(f"Discovered OIDC endpoints from {discovery_url}")
        except Exception as e:
            logger.warning(f"Failed to discover OIDC endpoints: {e}")

        return config

    @lru_cache(maxsize=100)
    def _get_jwks(self) -> Dict[str, Any]:
        """Get JWKS (JSON Web Key Set) from provider"""
        current_time = time.time()

        # Check cache
        if self._jwks_cache and (current_time - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks_cache

        try:
            response = requests.get(self.config.jwks_uri, timeout=5)
            if response.status_code == 200:
                self._jwks_cache = response.json()
                self._jwks_cache_time = current_time
                return self._jwks_cache
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")

        return {}

    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify OIDC ID token
        Returns: (is_valid, claims)
        """
        try:
            # Decode header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            # Get JWKS
            jwks = self._get_jwks()

            # Find the key
            rsa_key = {}
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    break

            if not rsa_key:
                logger.error(f"Unable to find a signing key that matches: {kid}")
                return False, None

            # Verify token
            claims = jwt.decode(
                token,
                key=jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(rsa_key)),
                algorithms=["RS256"],
                audience=self.config.client_id,
                issuer=self.config.issuer,
                options={"verify_exp": True}
            )

            return True, claims

        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            return False, {"error": "Token expired"}
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return False, {"error": str(e)}

    def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user information from OIDC provider"""
        if not self.config.userinfo_endpoint:
            return None

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(
                self.config.userinfo_endpoint,
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.error(f"Failed to get user info: {e}")

        return None

    def build_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """Build authorization URL for OIDC flow"""
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": self.config.scopes,
            "redirect_uri": redirect_uri
        }

        if state:
            params["state"] = state

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.config.authorization_endpoint}?{query_string}"

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for tokens"""
        if not self.config.token_endpoint:
            return None

        try:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.config.client_id
            }

            if self.config.client_secret:
                data["client_secret"] = self.config.client_secret

            response = requests.post(
                self.config.token_endpoint,
                data=data,
                timeout=10
            )

            if response.status_code == 200:
                return response.json()

        except Exception as e:
            logger.error(f"Failed to exchange code for token: {e}")

        return None


def verify_oidc_token(event: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Verify OIDC token from Lambda event
    Returns: (is_valid, user_id, claims)
    """
    # Get token from Authorization header
    token = None
    headers = event.get("headers", {})

    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]

    if not token:
        return False, None, {"error": "No token provided"}

    # Determine provider from environment or token
    provider = os.environ.get("OIDC_PROVIDER", "custom")

    # Initialize OIDC provider
    oidc = OIDCProvider(provider)

    # Verify token
    is_valid, claims = oidc.verify_token(token)

    if is_valid:
        # Extract user ID from claims
        user_id = claims.get("sub") or claims.get("email") or claims.get("preferred_username")
        return True, user_id, claims

    return False, None, claims


def get_oidc_user_info(access_token: str, provider: str = "custom") -> Optional[Dict[str, Any]]:
    """Get user information from OIDC provider using access token"""
    oidc = OIDCProvider(provider)
    return oidc.get_user_info(access_token)
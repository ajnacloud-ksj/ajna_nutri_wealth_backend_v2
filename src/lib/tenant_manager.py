"""
Tenant Management for Multi-tenant Architecture
"""

import os
import json
from typing import Optional, Dict, Any

class TenantManager:
    """
    Manages tenant configuration and isolation for the food tracking app.

    Architecture:
    - Each organization/company gets their own tenant_id
    - Individual users within a tenant are tracked by user_id
    - Data isolation at namespace level in Ibex
    """

    # Load tenant configuration from file
    _config_loaded = False
    _tenant_config = {}
    _default_tenant = "nutriwealth"
    _feature_definitions = {}

    @classmethod
    def _load_config(cls):
        """Load tenant configuration from JSON file"""
        if cls._config_loaded:
            return

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'tenants.json'
        )

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                cls._tenant_config = config.get('tenants', {})
                cls._default_tenant = config.get('default_tenant', 'nutriwealth')
                cls._feature_definitions = config.get('feature_definitions', {})
                cls._config_loaded = True
                print(f"Loaded {len(cls._tenant_config)} tenant configurations")
        except FileNotFoundError:
            print(f"Warning: tenants.json not found at {config_path}, using defaults")
            cls._tenant_config = {
                "test": {
                    "tenant_id": "nutriwealth",
                    "namespace": "default",
                    "display_name": "Test Environment",
                    "features": ["all"]
                }
            }
            cls._config_loaded = True
        except Exception as e:
            print(f"Error loading tenant config: {e}")
            cls._tenant_config = {
                "test": {
                    "tenant_id": "nutriwealth",
                    "namespace": "default",
                    "display_name": "Test Environment",
                    "features": ["all"]
                }
            }
            cls._config_loaded = True

    @classmethod
    def get_tenant_config(cls, tenant_key: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific tenant"""
        cls._load_config()
        return cls._tenant_config.get(tenant_key)

    @classmethod
    def get_tenant_from_request(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tenant information from request headers or auth token.

        Priority:
        1. X-Tenant-ID header (for testing)
        2. Tenant from JWT token
        3. Domain-based tenant detection
        4. Default to configured default tenant
        """
        cls._load_config()
        headers = event.get('headers', {}) or {}

        # 1. Check explicit tenant header (for testing/development)
        tenant_header = headers.get('X-Tenant-ID') or headers.get('x-tenant-id')
        if tenant_header and tenant_header in cls._tenant_config:
            return cls._tenant_config[tenant_header]

        # 2. Extract from authorization token
        auth_header = headers.get('Authorization') or headers.get('authorization')
        if auth_header:
            # In production, decode JWT and extract tenant claim
            # For now, we'll use a simple approach
            for key, config in cls._tenant_config.items():
                if key in auth_header.lower():
                    return config

        # 3. Domain-based tenant detection
        host = headers.get('Host') or headers.get('host') or ''
        for key, config in cls._tenant_config.items():
            domain_patterns = config.get('domain_patterns', [])
            for pattern in domain_patterns:
                if pattern in host:
                    return config

        # 4. Default to configured default tenant
        default_config = cls._tenant_config.get(cls._default_tenant)
        if default_config:
            return default_config

        # 5. Fallback to nutriwealth config
        nutriwealth_config = cls._tenant_config.get('nutriwealth')
        if nutriwealth_config:
            return nutriwealth_config

        # 6. Last resort - return a default config
        return {
            "tenant_id": "nutriwealth",
            "namespace": "default",
            "display_name": "NutriWealth Default",
            "features": ["all"]
        }

    @classmethod
    def has_feature(cls, tenant_config: Dict[str, Any], feature: str) -> bool:
        """Check if tenant has access to a specific feature"""
        features = tenant_config.get('features', [])
        return 'all' in features or feature in features

    @classmethod
    def get_table_name(cls, base_table: str, tenant_config: Dict[str, Any]) -> str:
        """
        Get the actual table name for a tenant.

        For Ibex, we use namespace separation, so table names stay consistent
        but are isolated by namespace.
        """
        # Remove any existing prefix
        if base_table.startswith('app_'):
            base_table = base_table[4:]

        # In Ibex, tables are prefixed with app_ by convention
        return f"app_{base_table}"

    @classmethod
    def create_ibex_client(cls, tenant_config: Dict[str, Any], client_class=None):
        """Create an Ibex client configured for the specific tenant"""
        if client_class is None:
            from lib.ibex_client import IbexClient
            client_class = IbexClient

        api_url = os.environ.get('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb')
        api_key = os.environ.get('IBEX_API_KEY')

        # Check if the client class accepts specific arguments
        # OptimizedIbexClient might accept different args in future, but for now signature is compatible
        return client_class(
            api_url=api_url,
            api_key=api_key,
            tenant_id=tenant_config['tenant_id'],
            namespace=tenant_config['namespace']
        )

    @classmethod
    def list_tenants(cls) -> Dict[str, str]:
        """List all configured tenants"""
        cls._load_config()
        return {
            key: config['display_name']
            for key, config in cls._tenant_config.items()
        }
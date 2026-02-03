"""
Centralized configuration management with environment-specific settings
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    """Database configuration"""
    api_url: str
    api_key: str
    tenant_id: str
    namespace: str = "default"
    connection_timeout: int = 20
    max_retries: int = 3
    lambda_name: Optional[str] = None


@dataclass
class AuthConfig:
    """Authentication configuration"""
    mode: str  # 'local', 'cognito', 'test'
    user_pool_id: Optional[str] = None
    client_id: Optional[str] = None
    region: str = "us-east-1"
    require_auth: bool = True
    jwt_secret: Optional[str] = None


@dataclass
class CorsConfig:
    """CORS configuration"""
    allowed_origins: list = field(default_factory=list)
    allow_credentials: bool = True
    max_age: int = 86400


@dataclass
class SecurityConfig:
    """Security configuration"""
    enable_rate_limiting: bool = True
    max_requests_per_minute: int = 60
    enable_input_validation: bool = True
    max_request_size: int = 10485760  # 10MB
    allowed_file_types: list = field(default_factory=lambda: [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'application/pdf', 'text/plain'
    ])


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "json"
    include_request_body: bool = False
    include_response_body: bool = False
    mask_sensitive_fields: bool = True


@dataclass
class AppConfig:
    """Main application configuration"""
    environment: str
    debug: bool
    database: DatabaseConfig
    auth: AuthConfig
    cors: CorsConfig
    security: SecurityConfig
    logging: LoggingConfig
    features: Dict[str, bool] = field(default_factory=dict)


class Settings:
    """Settings manager with environment-specific configuration"""

    _instance: Optional['Settings'] = None
    _config: Optional[AppConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._config = self._load_config()

    def _load_config(self) -> AppConfig:
        """Load configuration based on environment"""
        env = os.environ.get('ENVIRONMENT', 'development')

        # Base configuration - convert dicts to dataclasses
        database_config = DatabaseConfig(**self._get_database_config())
        auth_config = AuthConfig(**self._get_auth_config(env))
        cors_config = CorsConfig(**self._get_cors_config(env))
        security_config = SecurityConfig(**self._get_security_config(env))
        logging_config = LoggingConfig(**self._get_logging_config(env))
        features = self._get_feature_flags(env)

        # Create AppConfig with dataclass instances
        config = AppConfig(
            environment=env,
            debug=env != 'production',
            database=database_config,
            auth=auth_config,
            cors=cors_config,
            security=security_config,
            logging=logging_config,
            features=features
        )

        # Load environment-specific overrides if they exist
        config_file = f'config.{env}.json'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                overrides = json.load(f)
                # Apply overrides (would need more complex logic for nested dataclasses)
                # For now, just update features
                if 'features' in overrides:
                    config.features.update(overrides['features'])

        return config

    def _get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return {
            'api_url': os.environ.get('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb'),
            'api_key': os.environ.get('IBEX_API_KEY', ''),
            'tenant_id': os.environ.get('TENANT_ID', 'test-tenant'),
            'namespace': os.environ.get('DB_NAMESPACE', 'default'),
            'connection_timeout': int(os.environ.get('DB_TIMEOUT', '20')),
            'max_retries': int(os.environ.get('DB_MAX_RETRIES', '3')),
            'lambda_name': os.environ.get('IBEX_LAMBDA_NAME')
        }

    def _get_auth_config(self, env: str) -> Dict[str, Any]:
        """Get auth configuration based on environment"""
        if env == 'production':
            return {
                'mode': 'cognito',
                'user_pool_id': os.environ.get('COGNITO_USER_POOL_ID'),
                'client_id': os.environ.get('COGNITO_CLIENT_ID'),
                'region': os.environ.get('COGNITO_REGION', 'us-east-1'),
                'require_auth': True
            }
        elif env == 'staging':
            return {
                'mode': os.environ.get('AUTH_MODE', 'cognito'),
                'user_pool_id': os.environ.get('COGNITO_USER_POOL_ID'),
                'client_id': os.environ.get('COGNITO_CLIENT_ID'),
                'region': os.environ.get('COGNITO_REGION', 'us-east-1'),
                'require_auth': True
            }
        else:  # development
            return {
                'mode': os.environ.get('AUTH_MODE', 'local'),
                'require_auth': False,
                'jwt_secret': os.environ.get('JWT_SECRET', 'dev-secret-key')
            }

    def _get_cors_config(self, env: str) -> Dict[str, Any]:
        """Get CORS configuration based on environment"""
        if env == 'production':
            return {
                'allowed_origins': [
                    'https://app.nutriwealth.com',
                    'https://www.nutriwealth.com'
                ],
                'allow_credentials': True,
                'max_age': 86400
            }
        elif env == 'staging':
            return {
                'allowed_origins': [
                    'https://staging.nutriwealth.com',
                    'http://localhost:5173'
                ],
                'allow_credentials': True,
                'max_age': 3600
            }
        else:  # development
            return {
                'allowed_origins': [
                    'http://localhost:5173',
                    'http://localhost:5174',
                    'http://localhost:3000',
                    'http://127.0.0.1:5173'
                ],
                'allow_credentials': True,
                'max_age': 3600
            }

    def _get_security_config(self, env: str) -> Dict[str, Any]:
        """Get security configuration based on environment"""
        base_config = {
            'enable_rate_limiting': env != 'development',
            'max_requests_per_minute': 60 if env == 'production' else 120,
            'enable_input_validation': True,
            'max_request_size': 10485760,  # 10MB
            'allowed_file_types': [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp',
                'application/pdf', 'text/plain'
            ]
        }
        return base_config

    def _get_logging_config(self, env: str) -> Dict[str, Any]:
        """Get logging configuration based on environment"""
        if env == 'production':
            return {
                'level': 'WARNING',
                'format': 'json',
                'include_request_body': False,
                'include_response_body': False,
                'mask_sensitive_fields': True
            }
        elif env == 'staging':
            return {
                'level': 'INFO',
                'format': 'json',
                'include_request_body': True,
                'include_response_body': False,
                'mask_sensitive_fields': True
            }
        else:  # development
            return {
                'level': 'DEBUG',
                'format': 'text',
                'include_request_body': True,
                'include_response_body': True,
                'mask_sensitive_fields': False
            }

    def _get_feature_flags(self, env: str) -> Dict[str, bool]:
        """Get feature flags based on environment"""
        flags = {
            'enable_ai_analysis': True,
            'enable_receipt_scanning': True,
            'enable_workout_tracking': True,
            'enable_notifications': env != 'development',
            'enable_export': True,
            'enable_sharing': env == 'production',
            'enable_premium_features': env == 'production'
        }

        # Override with environment variables
        for key in flags:
            env_key = f'FEATURE_{key.upper()}'
            if env_key in os.environ:
                flags[key] = os.environ.get(env_key, '').lower() in ('true', '1', 'yes')

        return flags

    def _merge_config(self, base: dict, overrides: dict):
        """Recursively merge configuration dictionaries"""
        for key, value in overrides.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    @property
    def config(self) -> AppConfig:
        """Get the current configuration"""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if hasattr(value, k):
                value = getattr(value, k)
            elif isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.config.features.get(feature, False)

    def reload(self):
        """Reload configuration (useful for testing)"""
        self._config = None
        self._config = self._load_config()


# Singleton instance
settings = Settings()
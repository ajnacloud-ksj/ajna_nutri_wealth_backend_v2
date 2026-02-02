"""
Platform-level Model Configuration Manager for Ibex DB (DuckDB/Iceberg)
Simple, efficient model management without complex JSON types
"""

import os
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from lib.logger import logger


class AIProvider(Enum):
    OPENAI = "openai"
    GROQ = "groq"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    TOGETHER = "together"


@dataclass
class ModelConfig:
    """Simple model configuration"""
    use_case: str
    provider: str
    model_name: str
    base_url: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 500
    timeout_seconds: int = 30
    cost_per_1k_tokens: float = 0.001
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    api_key_env: Optional[str] = None


class ModelManager:
    """
    Platform-level model configuration manager
    Uses Ibex DB for storage with Lambda container caching
    """

    # Container-level cache (survives between Lambda invocations)
    _config_cache: Dict[str, ModelConfig] = {}
    _cache_time: float = 0
    _cache_ttl: int = 300  # 5 minutes

    # Default platform configuration (hardcoded fallback)
    DEFAULT_CONFIGS = {
        "classifier": ModelConfig(
            use_case="classifier",
            provider="openai",
            model_name="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            temperature=0.0,
            max_tokens=100,
            timeout_seconds=10,
            cost_per_1k_tokens=0.00015,
            api_key_env="OPENAI_API_KEY"
        ),
        "food": ModelConfig(
            use_case="food",
            provider="openai",
            model_name="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            temperature=0.0,
            max_tokens=500,
            timeout_seconds=20,
            cost_per_1k_tokens=0.00015,
            fallback_provider="groq",
            fallback_model="llama-3.3-70b-versatile",
            api_key_env="OPENAI_API_KEY"
        ),
        "receipt": ModelConfig(
            use_case="receipt",
            provider="openai",
            model_name="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            temperature=0.0,
            max_tokens=500,
            timeout_seconds=20,
            cost_per_1k_tokens=0.00015,
            fallback_provider="groq",
            fallback_model="llama-3.3-70b-versatile",
            api_key_env="OPENAI_API_KEY"
        ),
        "workout": ModelConfig(
            use_case="workout",
            provider="openai",
            model_name="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            temperature=0.0,
            max_tokens=500,
            timeout_seconds=20,
            cost_per_1k_tokens=0.00015,
            api_key_env="OPENAI_API_KEY"
        )
    }

    # Provider configurations
    PROVIDER_CONFIGS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "supports_images": True,
            "supports_json_mode": True
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "supports_images": True,  # Llama 3.2 Vision
            "supports_json_mode": True
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "api_key_env": "ANTHROPIC_API_KEY",
            "supports_images": True,
            "supports_json_mode": False  # Uses XML
        },
        "ollama": {
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "api_key_env": None,  # No API key needed
            "supports_images": False,
            "supports_json_mode": True
        },
        "together": {
            "base_url": "https://api.together.xyz/v1",
            "api_key_env": "TOGETHER_API_KEY",
            "supports_images": False,
            "supports_json_mode": True
        }
    }

    def __init__(self, db_client=None):
        """
        Initialize model manager

        Args:
            db_client: IbexClient instance (optional)
        """
        self.db = db_client
        self._initialized = False

    def _ensure_table_exists(self):
        """Ensure the model config table exists in Ibex"""
        if not self.db or self._initialized:
            return

        try:
            # Check if table exists by querying it
            result = self.db.query("ai_model_config", limit=1)

            if not result.get('success'):
                # Table doesn't exist, create default entries
                self._create_default_configs()

            self._initialized = True

        except Exception as e:
            logger.warning(f"Could not check/create model config table: {e}")
            self._initialized = True

    def _create_default_configs(self):
        """Create default model configurations in database"""
        if not self.db:
            return

        try:
            records = []
            for use_case, config in self.DEFAULT_CONFIGS.items():
                records.append({
                    "id": use_case,
                    "use_case": config.use_case,
                    "provider": config.provider,
                    "model_name": config.model_name,
                    "base_url": config.base_url,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "timeout_seconds": config.timeout_seconds,
                    "cost_per_1k_tokens": config.cost_per_1k_tokens,
                    "fallback_provider": config.fallback_provider,
                    "fallback_model": config.fallback_model,
                    "is_active": True
                })

            result = self.db.write("ai_model_config", records)
            if result.get('success'):
                logger.info(f"Created {len(records)} default model configs")

        except Exception as e:
            logger.error(f"Failed to create default configs: {e}")

    def get_model_config(self, use_case: str) -> ModelConfig:
        """
        Get model configuration for a use case

        Args:
            use_case: One of "classifier", "food", "receipt", "workout"

        Returns:
            ModelConfig object
        """
        # Check container cache first
        if self._is_cache_valid():
            if use_case in self._config_cache:
                return self._config_cache[use_case]

        # Try to fetch from database
        if self.db:
            self._ensure_table_exists()

            try:
                result = self.db.query(
                    "ai_model_config",
                    filters=[
                        {"field": "use_case", "operator": "eq", "value": use_case},
                        {"field": "is_active", "operator": "eq", "value": True}
                    ],
                    limit=1
                )

                if result.get('success') and result.get('data', {}).get('records'):
                    record = result['data']['records'][0]

                    # Create ModelConfig from record
                    config = ModelConfig(
                        use_case=record['use_case'],
                        provider=record['provider'],
                        model_name=record['model_name'],
                        base_url=record.get('base_url'),
                        temperature=float(record.get('temperature', 0.0)),
                        max_tokens=int(record.get('max_tokens', 500)),
                        timeout_seconds=int(record.get('timeout_seconds', 30)),
                        cost_per_1k_tokens=float(record.get('cost_per_1k_tokens', 0.001)),
                        fallback_provider=record.get('fallback_provider'),
                        fallback_model=record.get('fallback_model')
                    )

                    # Add API key env from provider config
                    provider_cfg = self.PROVIDER_CONFIGS.get(config.provider, {})
                    config.api_key_env = provider_cfg.get('api_key_env')

                    # Update cache
                    self._update_cache(use_case, config)

                    return config

            except Exception as e:
                logger.warning(f"Could not fetch model config from DB: {e}")

        # Fall back to hardcoded defaults
        config = self.DEFAULT_CONFIGS.get(use_case)
        if config:
            self._update_cache(use_case, config)
            return config

        # Ultimate fallback
        return self.DEFAULT_CONFIGS["food"]

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        return (time.time() - self._cache_time) < self._cache_ttl

    def _update_cache(self, use_case: str, config: ModelConfig):
        """Update the container cache"""
        self._config_cache[use_case] = config
        self._cache_time = time.time()

    def get_all_configs(self) -> Dict[str, ModelConfig]:
        """Get all model configurations"""
        configs = {}
        for use_case in ["classifier", "food", "receipt", "workout"]:
            configs[use_case] = self.get_model_config(use_case)
        return configs

    def update_model_config(self, use_case: str, updates: Dict) -> bool:
        """
        Update model configuration

        Args:
            use_case: Use case to update
            updates: Dictionary of fields to update

        Returns:
            True if successful
        """
        if not self.db:
            logger.error("Cannot update config without database connection")
            return False

        try:
            # Update in database
            result = self.db.update(
                "ai_model_config",
                filters=[{"field": "use_case", "operator": "eq", "value": use_case}],
                data=updates
            )

            if result.get('success'):
                # Clear cache to force refresh
                self._config_cache.clear()
                self._cache_time = 0
                logger.info(f"Updated model config for {use_case}")
                return True

        except Exception as e:
            logger.error(f"Failed to update model config: {e}")

        return False

    def get_provider_config(self, provider: str) -> Dict:
        """Get provider configuration"""
        return self.PROVIDER_CONFIGS.get(provider, {})

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider"""
        provider_cfg = self.PROVIDER_CONFIGS.get(provider, {})
        api_key_env = provider_cfg.get('api_key_env')

        if api_key_env:
            return os.environ.get(api_key_env)
        return None

    def list_available_models(self) -> Dict[str, List[str]]:
        """List available models per provider"""
        return {
            "openai": [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-3.5-turbo"
            ],
            "groq": [
                "llama-3.3-70b-versatile",
                "llama-3.2-90b-vision",
                "mixtral-8x7b-32768",
                "llama-3.2-11b-vision"
            ],
            "anthropic": [
                "claude-3-5-sonnet-20241022",
                "claude-3-haiku-20240307",
                "claude-3-opus-20240229"
            ],
            "ollama": [
                "llama3.2",
                "mixtral:8x7b",
                "phi3",
                "gemma2"
            ]
        }


# Singleton instance for Lambda container reuse
_model_manager = None


def get_model_manager(db_client=None) -> ModelManager:
    """Get or create model manager singleton"""
    global _model_manager

    if _model_manager is None:
        _model_manager = ModelManager(db_client)
    elif db_client and not _model_manager.db:
        # Update DB client if provided
        _model_manager.db = db_client

    return _model_manager
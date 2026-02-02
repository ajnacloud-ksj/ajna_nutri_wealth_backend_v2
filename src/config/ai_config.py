"""
Centralized AI Model Configuration
Supports multiple providers and easy model switching
"""

import os
import json
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass


class AIProvider(Enum):
    """Supported AI providers"""
    OPENAI = "openai"
    GROQ = "groq"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    REPLICATE = "replicate"
    TOGETHER = "together"
    PERPLEXITY = "perplexity"


@dataclass
class ModelConfig:
    """Configuration for a specific model"""
    name: str
    provider: AIProvider
    api_key_env: str
    base_url: Optional[str] = None
    max_tokens: int = 500
    temperature: float = 0.0
    timeout: int = 30
    cost_per_1k_input: float = 0.001
    cost_per_1k_output: float = 0.001
    supports_images: bool = True
    supports_json_mode: bool = True
    context_window: int = 4096


class AIConfig:
    """
    Centralized AI configuration manager

    Usage:
        config = AIConfig()
        model = config.get_model("food")
        provider_config = config.get_provider_config("openai")
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize AI configuration

        Args:
            config_file: Optional JSON config file path
        """
        # Load from file if provided
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                self.custom_config = json.load(f)
        else:
            self.custom_config = {}

        # Initialize provider configurations
        self._init_provider_configs()

        # Initialize model mappings
        self._init_model_mappings()

        # Override with environment variables
        self._load_env_overrides()

    def _init_provider_configs(self):
        """Initialize provider configurations"""
        self.providers = {
            AIProvider.OPENAI: {
                "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                "api_key_env": "OPENAI_API_KEY",
                "headers": {"OpenAI-Beta": "assistants=v2"},
                "models": {
                    "gpt-4o-mini": ModelConfig(
                        name="gpt-4o-mini",
                        provider=AIProvider.OPENAI,
                        api_key_env="OPENAI_API_KEY",
                        max_tokens=16000,
                        cost_per_1k_input=0.00015,
                        cost_per_1k_output=0.0006,
                        context_window=128000
                    ),
                    "gpt-4o": ModelConfig(
                        name="gpt-4o",
                        provider=AIProvider.OPENAI,
                        api_key_env="OPENAI_API_KEY",
                        max_tokens=4096,
                        cost_per_1k_input=0.0025,
                        cost_per_1k_output=0.01,
                        context_window=128000
                    ),
                    "gpt-4-turbo": ModelConfig(
                        name="gpt-4-turbo",
                        provider=AIProvider.OPENAI,
                        api_key_env="OPENAI_API_KEY",
                        max_tokens=4096,
                        cost_per_1k_input=0.01,
                        cost_per_1k_output=0.03,
                        context_window=128000
                    ),
                    "gpt-3.5-turbo": ModelConfig(
                        name="gpt-3.5-turbo",
                        provider=AIProvider.OPENAI,
                        api_key_env="OPENAI_API_KEY",
                        max_tokens=4096,
                        cost_per_1k_input=0.0005,
                        cost_per_1k_output=0.0015,
                        context_window=16384
                    ),
                    # Add GPT-5.2 if it exists in your setup
                    "gpt-5.2-2025-12-11": ModelConfig(
                        name="gpt-5.2-2025-12-11",
                        provider=AIProvider.OPENAI,
                        api_key_env="OPENAI_API_KEY",
                        max_tokens=8192,
                        cost_per_1k_input=0.005,  # Estimated
                        cost_per_1k_output=0.015,  # Estimated
                        context_window=200000
                    ),
                }
            },

            AIProvider.GROQ: {
                "base_url": os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                "api_key_env": "GROQ_API_KEY",
                "models": {
                    "llama-3.3-70b-versatile": ModelConfig(
                        name="llama-3.3-70b-versatile",
                        provider=AIProvider.GROQ,
                        api_key_env="GROQ_API_KEY",
                        base_url="https://api.groq.com/openai/v1",
                        max_tokens=8192,
                        cost_per_1k_input=0.00059,
                        cost_per_1k_output=0.00079,
                        context_window=128000,
                        timeout=30
                    ),
                    "llama-3.2-90b-vision": ModelConfig(
                        name="llama-3.2-90b-vision",
                        provider=AIProvider.GROQ,
                        api_key_env="GROQ_API_KEY",
                        base_url="https://api.groq.com/openai/v1",
                        max_tokens=8192,
                        cost_per_1k_input=0.0009,
                        cost_per_1k_output=0.0009,
                        supports_images=True,
                        context_window=128000
                    ),
                    "mixtral-8x7b": ModelConfig(
                        name="mixtral-8x7b-32768",
                        provider=AIProvider.GROQ,
                        api_key_env="GROQ_API_KEY",
                        base_url="https://api.groq.com/openai/v1",
                        max_tokens=32768,
                        cost_per_1k_input=0.00024,
                        cost_per_1k_output=0.00024,
                        context_window=32768
                    ),
                }
            },

            AIProvider.ANTHROPIC: {
                "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
                "api_key_env": "ANTHROPIC_API_KEY",
                "models": {
                    "claude-3-5-sonnet": ModelConfig(
                        name="claude-3-5-sonnet-20241022",
                        provider=AIProvider.ANTHROPIC,
                        api_key_env="ANTHROPIC_API_KEY",
                        max_tokens=8192,
                        cost_per_1k_input=0.003,
                        cost_per_1k_output=0.015,
                        context_window=200000,
                        supports_json_mode=False  # Uses XML instead
                    ),
                    "claude-3-haiku": ModelConfig(
                        name="claude-3-haiku-20240307",
                        provider=AIProvider.ANTHROPIC,
                        api_key_env="ANTHROPIC_API_KEY",
                        max_tokens=4096,
                        cost_per_1k_input=0.00025,
                        cost_per_1k_output=0.00125,
                        context_window=200000,
                        supports_json_mode=False
                    ),
                }
            },

            AIProvider.OLLAMA: {
                "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                "api_key_env": None,  # Ollama doesn't need API key
                "models": {
                    "llama3.2": ModelConfig(
                        name="llama3.2",
                        provider=AIProvider.OLLAMA,
                        api_key_env="",
                        base_url="http://localhost:11434/v1",
                        max_tokens=4096,
                        cost_per_1k_input=0,  # Free local
                        cost_per_1k_output=0,
                        timeout=60,  # Local models can be slower
                        context_window=128000
                    ),
                    "mixtral": ModelConfig(
                        name="mixtral:8x7b",
                        provider=AIProvider.OLLAMA,
                        api_key_env="",
                        base_url="http://localhost:11434/v1",
                        max_tokens=32768,
                        cost_per_1k_input=0,
                        cost_per_1k_output=0,
                        timeout=60,
                        context_window=32768
                    ),
                }
            },

            AIProvider.TOGETHER: {
                "base_url": os.environ.get("TOGETHER_BASE_URL", "https://api.together.xyz/v1"),
                "api_key_env": "TOGETHER_API_KEY",
                "models": {
                    "mixtral-8x7b": ModelConfig(
                        name="mistralai/Mixtral-8x7B-Instruct-v0.1",
                        provider=AIProvider.TOGETHER,
                        api_key_env="TOGETHER_API_KEY",
                        base_url="https://api.together.xyz/v1",
                        max_tokens=32768,
                        cost_per_1k_input=0.0003,
                        cost_per_1k_output=0.0003,
                        context_window=32768
                    ),
                }
            },
        }

    def _init_model_mappings(self):
        """Initialize model mappings for different use cases"""

        # Default model selections per use case
        self.default_models = {
            "classifier": {
                AIProvider.OPENAI: "gpt-4o-mini",
                AIProvider.GROQ: "llama-3.3-70b-versatile",
                AIProvider.ANTHROPIC: "claude-3-haiku",
                AIProvider.OLLAMA: "llama3.2",
            },
            "food": {
                AIProvider.OPENAI: os.environ.get("FOOD_MODEL_OPENAI", "gpt-4o-mini"),
                AIProvider.GROQ: os.environ.get("FOOD_MODEL_GROQ", "llama-3.3-70b-versatile"),
                AIProvider.ANTHROPIC: "claude-3-5-sonnet",
                AIProvider.OLLAMA: "mixtral:8x7b",
            },
            "receipt": {
                AIProvider.OPENAI: os.environ.get("RECEIPT_MODEL_OPENAI", "gpt-4o-mini"),
                AIProvider.GROQ: os.environ.get("RECEIPT_MODEL_GROQ", "llama-3.2-90b-vision"),
                AIProvider.ANTHROPIC: "claude-3-5-sonnet",
                AIProvider.OLLAMA: "llama3.2",
            },
            "workout": {
                AIProvider.OPENAI: os.environ.get("WORKOUT_MODEL_OPENAI", "gpt-4o-mini"),
                AIProvider.GROQ: os.environ.get("WORKOUT_MODEL_GROQ", "llama-3.3-70b-versatile"),
                AIProvider.ANTHROPIC: "claude-3-haiku",
                AIProvider.OLLAMA: "llama3.2",
            },
        }

    def _load_env_overrides(self):
        """Load environment variable overrides"""

        # Global provider override
        self.default_provider = AIProvider(
            os.environ.get("AI_PROVIDER", "openai").lower()
        )

        # Feature flags
        self.features = {
            "enable_fallback": os.environ.get("AI_ENABLE_FALLBACK", "true").lower() == "true",
            "enable_cache": os.environ.get("AI_ENABLE_CACHE", "true").lower() == "true",
            "enable_retry": os.environ.get("AI_ENABLE_RETRY", "true").lower() == "true",
            "max_retries": int(os.environ.get("AI_MAX_RETRIES", "3")),
            "enable_classification": os.environ.get("AI_ENABLE_CLASSIFICATION", "true").lower() == "true",
            "enable_async": os.environ.get("AI_ENABLE_ASYNC", "false").lower() == "true",
        }

    def get_model(self, use_case: str, provider: Optional[AIProvider] = None) -> ModelConfig:
        """
        Get model configuration for a specific use case

        Args:
            use_case: One of "classifier", "food", "receipt", "workout"
            provider: Optional provider override

        Returns:
            ModelConfig for the appropriate model
        """
        provider = provider or self.default_provider

        # Get model name for this use case and provider
        model_name = self.default_models.get(use_case, {}).get(
            provider,
            self.default_models.get("food", {}).get(provider)
        )

        # Get model config
        provider_models = self.providers.get(provider, {}).get("models", {})
        model_config = provider_models.get(model_name)

        if not model_config:
            # Fallback to first available model for provider
            if provider_models:
                model_config = list(provider_models.values())[0]
            else:
                # Ultimate fallback
                model_config = ModelConfig(
                    name="gpt-4o-mini",
                    provider=AIProvider.OPENAI,
                    api_key_env="OPENAI_API_KEY"
                )

        return model_config

    def get_provider_config(self, provider: AIProvider) -> Dict[str, Any]:
        """Get provider configuration"""
        return self.providers.get(provider, {})

    def get_api_key(self, provider: AIProvider) -> Optional[str]:
        """Get API key for provider"""
        config = self.providers.get(provider, {})
        api_key_env = config.get("api_key_env")

        if api_key_env:
            return os.environ.get(api_key_env)
        return None

    def get_base_url(self, provider: AIProvider) -> str:
        """Get base URL for provider"""
        config = self.providers.get(provider, {})
        return config.get("base_url", "")

    def list_available_models(self, provider: Optional[AIProvider] = None) -> Dict[str, Any]:
        """List all available models"""
        if provider:
            return self.providers.get(provider, {}).get("models", {})

        all_models = {}
        for prov, config in self.providers.items():
            all_models[prov.value] = list(config.get("models", {}).keys())

        return all_models

    def get_fallback_chain(self, use_case: str) -> list:
        """
        Get fallback chain of models for reliability

        Returns:
            List of (provider, model) tuples to try in order
        """
        chain = []

        # Primary provider
        primary_model = self.get_model(use_case, self.default_provider)
        chain.append((self.default_provider, primary_model))

        # Add fallbacks if enabled
        if self.features.get("enable_fallback"):
            # Fallback order
            fallback_providers = [
                AIProvider.GROQ,  # Fast and cheap
                AIProvider.OPENAI,  # Reliable
                AIProvider.OLLAMA,  # Local fallback
            ]

            for provider in fallback_providers:
                if provider != self.default_provider:
                    try:
                        model = self.get_model(use_case, provider)
                        if model and self.get_api_key(provider):
                            chain.append((provider, model))
                    except:
                        pass

        return chain

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary"""
        return {
            "default_provider": self.default_provider.value,
            "features": self.features,
            "models": self.default_models,
            "available_providers": [p.value for p in AIProvider],
        }


# Singleton instance
_config_instance = None


def get_ai_config(config_file: Optional[str] = None) -> AIConfig:
    """Get or create AI configuration singleton"""
    global _config_instance

    if _config_instance is None:
        config_file = config_file or os.environ.get("AI_CONFIG_FILE")
        _config_instance = AIConfig(config_file)

    return _config_instance


# Convenience exports
ai_config = get_ai_config()
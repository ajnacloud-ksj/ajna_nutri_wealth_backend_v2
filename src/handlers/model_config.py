"""
Model Configuration Management Handlers
Platform-level AI model configuration endpoints
"""

import json
from utils.http import respond
from lib.model_manager import get_model_manager
from lib.logger import logger


def list_model_configs(event, context):
    """
    GET /v1/models/config - List all model configurations
    """
    try:
        db = context.get('db')
        model_manager = get_model_manager(db)

        # Get all configurations
        configs = model_manager.get_all_configs()

        # Convert to serializable format
        response = {}
        for use_case, config in configs.items():
            response[use_case] = {
                "provider": config.provider,
                "model": config.model_name,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "timeout": config.timeout_seconds,
                "cost_per_1k": config.cost_per_1k_tokens,
                "fallback_provider": config.fallback_provider,
                "fallback_model": config.fallback_model
            }

        return respond(200, {
            "configs": response,
            "available_providers": list(model_manager.PROVIDER_CONFIGS.keys())
        })

    except Exception as e:
        logger.error(f"Error listing model configs: {e}")
        return respond(500, {"error": str(e)})


def get_model_config(event, context):
    """
    GET /v1/models/config/{use_case} - Get specific model configuration
    """
    try:
        use_case = event.get('pathParameters', {}).get('use_case')
        if not use_case:
            return respond(400, {"error": "Use case required"})

        db = context.get('db')
        model_manager = get_model_manager(db)

        config = model_manager.get_model_config(use_case)

        return respond(200, {
            "use_case": config.use_case,
            "provider": config.provider,
            "model": config.model_name,
            "base_url": config.base_url,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "timeout": config.timeout_seconds,
            "cost_per_1k": config.cost_per_1k_tokens,
            "fallback_provider": config.fallback_provider,
            "fallback_model": config.fallback_model
        })

    except Exception as e:
        logger.error(f"Error getting model config: {e}")
        return respond(500, {"error": str(e)})


def update_model_config(event, context):
    """
    PUT /v1/models/config/{use_case} - Update model configuration
    Admin endpoint to change models without redeploy
    """
    try:
        use_case = event.get('pathParameters', {}).get('use_case')
        if not use_case:
            return respond(400, {"error": "Use case required"})

        # Check admin authorization
        # TODO: Add proper admin auth check
        auth_header = event.get('headers', {}).get('Authorization', '')
        if not auth_header.startswith('Bearer admin-'):
            return respond(403, {"error": "Admin authorization required"})

        body = json.loads(event.get('body', '{}'))
        if not body:
            return respond(400, {"error": "Request body required"})

        db = context.get('db')
        model_manager = get_model_manager(db)

        # Prepare updates
        updates = {}
        allowed_fields = [
            'provider', 'model_name', 'temperature', 'max_tokens',
            'timeout_seconds', 'cost_per_1k_tokens',
            'fallback_provider', 'fallback_model'
        ]

        for field in allowed_fields:
            if field in body:
                updates[field] = body[field]

        if not updates:
            return respond(400, {"error": "No valid fields to update"})

        # Update the configuration
        success = model_manager.update_model_config(use_case, updates)

        if success:
            # Get updated config
            config = model_manager.get_model_config(use_case)

            logger.info(f"Model config updated for {use_case}", extra={
                "use_case": use_case,
                "provider": config.provider,
                "model": config.model_name
            })

            return respond(200, {
                "message": "Configuration updated successfully",
                "use_case": use_case,
                "provider": config.provider,
                "model": config.model_name
            })
        else:
            return respond(500, {"error": "Failed to update configuration"})

    except Exception as e:
        logger.error(f"Error updating model config: {e}")
        return respond(500, {"error": str(e)})


def list_available_models(event, context):
    """
    GET /v1/models/available - List all available models per provider
    """
    try:
        db = context.get('db')
        model_manager = get_model_manager(db)

        models = model_manager.list_available_models()

        # Add cost information
        model_costs = {
            "openai": {
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-4o": {"input": 0.0025, "output": 0.01},
                "gpt-4-turbo": {"input": 0.01, "output": 0.03},
                "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015}
            },
            "groq": {
                "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
                "llama-3.2-90b-vision": {"input": 0.0009, "output": 0.0009},
                "mixtral-8x7b-32768": {"input": 0.00024, "output": 0.00024}
            }
        }

        return respond(200, {
            "models": models,
            "costs_per_1k_tokens": model_costs
        })

    except Exception as e:
        logger.error(f"Error listing available models: {e}")
        return respond(500, {"error": str(e)})


def test_model(event, context):
    """
    POST /v1/models/test - Test a model configuration
    """
    try:
        body = json.loads(event.get('body', '{}'))
        provider = body.get('provider', 'openai')
        model = body.get('model', 'gpt-4o-mini')
        test_prompt = body.get('prompt', 'Say "Hello, this is a test!"')

        db = context.get('db')
        model_manager = get_model_manager(db)

        # Get API key
        api_key = model_manager.get_api_key(provider)
        if not api_key and provider != 'ollama':
            return respond(400, {"error": f"No API key configured for {provider}"})

        # Get provider config
        provider_config = model_manager.get_provider_config(provider)

        # Test the model
        from openai import OpenAI
        import time

        client = OpenAI(
            api_key=api_key or "dummy",
            base_url=provider_config.get('base_url')
        )

        start_time = time.time()

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": test_prompt}
                ],
                max_tokens=50,
                temperature=0
            )

            elapsed = time.time() - start_time
            tokens = response.usage.total_tokens if response.usage else 0
            content = response.choices[0].message.content

            return respond(200, {
                "success": True,
                "provider": provider,
                "model": model,
                "response": content,
                "latency_ms": int(elapsed * 1000),
                "tokens": tokens
            })

        except Exception as api_error:
            return respond(200, {
                "success": False,
                "provider": provider,
                "model": model,
                "error": str(api_error)
            })

    except Exception as e:
        logger.error(f"Error testing model: {e}")
        return respond(500, {"error": str(e)})
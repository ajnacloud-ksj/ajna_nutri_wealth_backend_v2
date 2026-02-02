"""
Async AI Service with Queue-Based Processing
Supports multiple AI providers (OpenAI, Groq, Local)
"""

import os
import json
import time
import boto3
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from enum import Enum
import pytz
from openai import OpenAI
from lib.logger import logger
from config.settings import settings


class AIProvider(Enum):
    OPENAI = "openai"
    GROQ = "groq"
    LOCAL = "local"
    OLLAMA = "ollama"


class AsyncAIService:
    """
    Async AI Service with queue-based processing and multi-provider support
    """

    def __init__(self, db_client):
        self.db = db_client

        # Get provider from environment
        self.provider = AIProvider(os.environ.get("AI_PROVIDER", "openai").lower())

        # Initialize clients based on provider
        self._initialize_provider()

        # SQS configuration
        self.sqs_enabled = os.environ.get("ENABLE_SQS", "false").lower() == "true"
        if self.sqs_enabled:
            self.sqs = boto3.client('sqs', region_name=os.environ.get("AWS_REGION", "us-east-1"))
            self.queue_url = os.environ.get("AI_PROCESSING_QUEUE_URL")

        # Model configuration per provider
        self.model_configs = {
            AIProvider.OPENAI: {
                "classifier": os.environ.get("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini"),
                "food": os.environ.get("OPENAI_FOOD_MODEL", "gpt-4o-mini"),
                "receipt": os.environ.get("OPENAI_RECEIPT_MODEL", "gpt-4o-mini"),
                "workout": os.environ.get("OPENAI_WORKOUT_MODEL", "gpt-4o-mini"),
            },
            AIProvider.GROQ: {
                "classifier": os.environ.get("GROQ_CLASSIFIER_MODEL", "llama-3.3-70b-versatile"),
                "food": os.environ.get("GROQ_FOOD_MODEL", "llama-3.3-70b-versatile"),
                "receipt": os.environ.get("GROQ_RECEIPT_MODEL", "llama-3.3-70b-versatile"),
                "workout": os.environ.get("GROQ_WORKOUT_MODEL", "llama-3.3-70b-versatile"),
            },
            AIProvider.LOCAL: {
                "classifier": os.environ.get("LOCAL_MODEL", "llama2"),
                "food": os.environ.get("LOCAL_MODEL", "llama2"),
                "receipt": os.environ.get("LOCAL_MODEL", "llama2"),
                "workout": os.environ.get("LOCAL_MODEL", "llama2"),
            }
        }

        logger.info(f"AsyncAIService initialized with provider: {self.provider.value}, SQS: {self.sqs_enabled}")

    def _initialize_provider(self):
        """Initialize the AI provider client"""
        if self.provider == AIProvider.OPENAI:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI provider")

            self.client = OpenAI(
                api_key=api_key,
                timeout=30.0,
                max_retries=1
            )

        elif self.provider == AIProvider.GROQ:
            # Groq uses OpenAI-compatible API
            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY required for Groq provider")

            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=30.0,
                max_retries=1
            )

        elif self.provider == AIProvider.LOCAL:
            # For local models (Ollama)
            self.client = OpenAI(
                api_key="ollama",  # Ollama doesn't need API key
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                timeout=60.0,  # Local models may be slower
                max_retries=1
            )

    def submit_async_analysis(
        self,
        user_id: str,
        entry_id: str,
        description: Optional[str] = None,
        image_url: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit analysis request to queue for async processing
        Returns immediately with a tracking ID
        """
        if not self.sqs_enabled:
            # If SQS not enabled, fall back to sync processing
            return self._process_sync(user_id, description, image_url)

        try:
            # Create message payload
            message = {
                "entry_id": entry_id,
                "user_id": user_id,
                "description": description,
                "image_url": image_url,
                "callback_url": callback_url,
                "timestamp": datetime.now(pytz.utc).isoformat(),
                "provider": self.provider.value
            }

            # Send to SQS
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'user_id': {'StringValue': user_id, 'DataType': 'String'},
                    'entry_id': {'StringValue': entry_id, 'DataType': 'String'}
                }
            )

            logger.info(f"Submitted async analysis to queue", entry_id=entry_id, message_id=response['MessageId'])

            # Return immediately with tracking info
            return {
                "success": True,
                "entry_id": entry_id,
                "status": "processing",
                "message_id": response['MessageId'],
                "message": "Analysis submitted for processing"
            }

        except Exception as e:
            logger.error(f"Failed to submit to queue: {e}")
            # Fallback to sync processing
            return self._process_sync(user_id, description, image_url)

    def _process_sync(self, user_id: str, description: Optional[str], image_url: Optional[str]) -> Dict[str, Any]:
        """Synchronous processing (fallback or when SQS disabled)"""
        try:
            # Stage 1: Classification
            category, confidence, class_tokens = self._classify_content(description, image_url)

            # Stage 2: Detailed analysis with appropriate prompt
            result = self._analyze_detailed(category, description, image_url)

            total_tokens = class_tokens + result.get("metadata", {}).get("tokens", 0)

            return {
                "success": True,
                "data": result.get("data"),
                "category": category,
                "metadata": {
                    "tokens": total_tokens,
                    "processing_mode": "sync",
                    "provider": self.provider.value
                }
            }

        except Exception as e:
            logger.error(f"Sync processing failed: {e}")
            return {"success": False, "error": str(e)}

    def _classify_content(
        self,
        description: Optional[str],
        image_url: Optional[str]
    ) -> Tuple[str, float, int]:
        """
        Stage 1: Fast classification using appropriate model
        """
        start_time = time.time()

        # Classification prompt
        classification_prompt = """Classify this content into one of these categories:
- food: Any food, meal, drink, or nutrition content
- receipt: Purchase receipts, bills, invoices
- workout: Exercise, fitness, gym activities
- unknown: Doesn't fit above categories

Return JSON: {"category": "...", "confidence": 0.0-1.0}"""

        messages = [
            {"role": "system", "content": classification_prompt},
            {"role": "user", "content": []}
        ]

        user_content = []
        if description:
            user_content.append({"type": "text", "text": f"Description: {description}"})

        # Only add image for providers that support it
        if image_url and self.provider in [AIProvider.OPENAI, AIProvider.GROQ]:
            if image_url.startswith(('http://', 'https://')):
                user_content.append({"type": "image_url", "image_url": {"url": image_url}})

        user_content.append({"type": "text", "text": "Classify this content."})
        messages[1]["content"] = user_content

        try:
            model = self.model_configs[self.provider]["classifier"]
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=50,
                response_format={"type": "json_object"} if self.provider == AIProvider.OPENAI else None
            )

            result = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens if response.usage else 50

            logger.info(
                f"Classification complete",
                category=result.get("category"),
                confidence=result.get("confidence"),
                duration_ms=(time.time() - start_time) * 1000,
                provider=self.provider.value
            )

            return (
                result.get("category", "unknown"),
                result.get("confidence", 0.5),
                tokens
            )

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Fallback classification
            if description:
                desc_lower = description.lower()
                if any(word in desc_lower for word in ["receipt", "invoice", "bill"]):
                    return ("receipt", 0.5, 0)
                elif any(word in desc_lower for word in ["food", "meal", "eat"]):
                    return ("food", 0.5, 0)
                elif any(word in desc_lower for word in ["workout", "exercise", "gym"]):
                    return ("workout", 0.5, 0)

            return ("unknown", 0.0, 0)

    def _analyze_detailed(
        self,
        category: str,
        description: Optional[str],
        image_url: Optional[str]
    ) -> Dict[str, Any]:
        """
        Stage 2: Detailed analysis with category-specific prompt
        """
        start_time = time.time()

        # Get category-specific prompt
        prompt = self._get_category_prompt(category)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": []}
        ]

        user_content = []
        if description:
            user_content.append({"type": "text", "text": f"Description: {description}"})

        if image_url and self.provider in [AIProvider.OPENAI, AIProvider.GROQ]:
            if image_url.startswith(('http://', 'https://')):
                user_content.append({"type": "image_url", "image_url": {"url": image_url}})

        user_content.append({"type": "text", "text": f"Extract {category} information as JSON."})
        messages[1]["content"] = user_content

        try:
            model = self.model_configs[self.provider].get(category, self.model_configs[self.provider]["food"])
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=500,
                response_format={"type": "json_object"} if self.provider == AIProvider.OPENAI else None
            )

            result = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens if response.usage else 500

            logger.info(
                f"Detailed analysis complete",
                category=category,
                duration_ms=(time.time() - start_time) * 1000,
                provider=self.provider.value,
                model=model
            )

            return {
                "data": result,
                "metadata": {
                    "tokens": tokens,
                    "model": model,
                    "provider": self.provider.value
                }
            }

        except Exception as e:
            logger.error(f"Detailed analysis failed: {e}")
            # Return basic structure
            return {
                "data": self._get_fallback_data(category, description),
                "metadata": {"error": str(e), "fallback": True}
            }

    def _get_category_prompt(self, category: str) -> str:
        """Get category-specific prompt"""
        prompts = {
            "food": """Extract nutritional information:
{
    "food_items": [{"name": "...", "calories": 0, "protein": 0, "carbs": 0, "fat": 0}],
    "meal_type": "breakfast|lunch|dinner|snack",
    "total_calories": 0
}""",
            "receipt": """Extract receipt information:
{
    "merchant_name": "...",
    "purchase_date": "YYYY-MM-DD",
    "total_amount": 0.00,
    "currency": "USD",
    "items": [{"name": "...", "price": 0.00, "quantity": 1}]
}""",
            "workout": """Extract workout information:
{
    "workout_type": "...",
    "duration_minutes": 0,
    "calories_burned_estimate": 0,
    "exercises": [{"name": "...", "sets": 0, "reps": 0}]
}"""
        }
        return prompts.get(category, "Extract relevant information as JSON.")

    def _get_fallback_data(self, category: str, description: Optional[str]) -> Dict[str, Any]:
        """Get fallback data structure"""
        if category == "food":
            return {"food_items": [{"name": description or "Food", "calories": 0}], "meal_type": "snack"}
        elif category == "receipt":
            return {"merchant_name": description or "Store", "total_amount": 0, "items": []}
        elif category == "workout":
            return {"workout_type": description or "Exercise", "duration_minutes": 0}
        return {"description": description or "Unknown"}

    # Lambda handler for processing queue messages
    def process_queue_message(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Lambda handler for processing SQS messages
        """
        for record in event.get('Records', []):
            try:
                message = json.loads(record['body'])
                user_id = message['user_id']
                entry_id = message['entry_id']
                description = message.get('description')
                image_url = message.get('image_url')

                # Process the analysis
                result = self._process_sync(user_id, description, image_url)

                # Store result in database
                self._store_result(entry_id, result)

                # Call webhook if provided
                if message.get('callback_url'):
                    self._send_callback(message['callback_url'], entry_id, result)

                logger.info(f"Processed queue message", entry_id=entry_id)

            except Exception as e:
                logger.error(f"Failed to process queue message: {e}")

        return {"statusCode": 200}

    def _store_result(self, entry_id: str, result: Dict[str, Any]):
        """Store analysis result in database"""
        try:
            self.db.update("app_analysis_results", entry_id, {
                "status": "completed" if result.get("success") else "failed",
                "result": json.dumps(result),
                "completed_at": datetime.now(pytz.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to store result: {e}")

    def _send_callback(self, callback_url: str, entry_id: str, result: Dict[str, Any]):
        """Send webhook callback with results"""
        import requests
        try:
            requests.post(callback_url, json={
                "entry_id": entry_id,
                "result": result
            }, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send callback: {e}")

    # Compatibility wrapper
    def process_request(self, user_id: str, description: Optional[str] = None, image_url: Optional[str] = None) -> Dict[str, Any]:
        """Compatibility wrapper for existing code"""
        if self.sqs_enabled:
            # For async mode, generate entry_id and submit to queue
            import uuid
            entry_id = str(uuid.uuid4())
            return self.submit_async_analysis(user_id, entry_id, description, image_url)
        else:
            # Sync mode
            return self._process_sync(user_id, description, image_url)
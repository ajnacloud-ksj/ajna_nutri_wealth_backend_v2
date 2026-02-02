"""
Fast AI Service with Single-Pass Processing
Optimized for speed with configurable models
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import pytz
from openai import OpenAI
from lib.logger import logger
from config.settings import settings


class FastAIService:
    """Optimized AI Service for faster processing"""

    def __init__(self, db_client):
        self.db = db_client

        # Initialize OpenAI client
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = OpenAI(
            api_key=api_key,
            timeout=30.0,  # Reduced timeout for faster failure
            max_retries=1   # Reduced retries for faster response
        )

        # Use environment variables for model selection with fallbacks
        self.default_model = os.environ.get("AI_MODEL", "gpt-4o-mini")

        # Single-pass mode for better performance
        self.single_pass = os.environ.get("AI_SINGLE_PASS", "true").lower() == "true"

        # Cost tracking (per 1K tokens)
        self.model_costs = {
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4o": {"input": 0.0025, "output": 0.01},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015}
        }

        logger.info(f"FastAIService initialized with model: {self.default_model}, single_pass: {self.single_pass}")

    def _get_combined_prompt(self, category: Optional[str] = None) -> str:
        """Get a combined prompt that does classification and analysis in one pass"""

        base_prompt = """You are an AI assistant that analyzes images and text for a health tracking app.
Your task is to analyze the content and extract structured data in a SINGLE response.

First, determine the category:
- food: Any food, meal, drink, or nutrition-related content
- receipt: Purchase receipts, bills, invoices
- workout: Exercise, fitness, gym activities

Then, based on the category, extract the relevant information."""

        if category == "receipt":
            return base_prompt + """

For RECEIPTS, extract:
{
    "category": "receipt",
    "merchant_name": "store/vendor name",
    "purchase_date": "YYYY-MM-DD",
    "total_amount": 0.00,
    "currency": "USD",
    "items": [
        {"name": "item", "price": 0.00, "quantity": 1}
    ]
}"""

        elif category == "food":
            return base_prompt + """

For FOOD, extract:
{
    "category": "food",
    "food_items": [
        {
            "name": "food name",
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0
        }
    ],
    "meal_type": "breakfast|lunch|dinner|snack",
    "total_calories": 0
}"""

        else:  # General prompt
            return base_prompt + """

Return a JSON object with the appropriate structure based on the category you identify.
Be concise and accurate. If you cannot determine exact values, make reasonable estimates."""

    def process_request_fast(
        self,
        user_id: str,
        description: Optional[str] = None,
        image_url: Optional[str] = None,
        category_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fast single-pass processing
        """
        start_time = time.time()

        try:
            # Build messages
            messages = [
                {"role": "system", "content": self._get_combined_prompt(category_hint)},
                {"role": "user", "content": []}
            ]

            user_content = []

            # Add description
            if description:
                user_content.append({
                    "type": "text",
                    "text": f"Description: {description}"
                })

            # Add image if it's a direct URL
            if image_url and image_url.startswith(('http://', 'https://', 'data:')):
                # For base64 images, we should skip them to avoid timeout
                if image_url.startswith('data:') and len(image_url) > 100000:
                    # Large base64 image - skip it
                    user_content.append({
                        "type": "text",
                        "text": "Note: Large image provided but skipped for performance."
                    })
                else:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    })

            # Add instruction
            user_content.append({
                "type": "text",
                "text": "Analyze this content and return the structured JSON data."
            })

            messages[1]["content"] = user_content

            # Make the API call
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=0,
                max_tokens=500,  # Reduced for faster response
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens if response.usage else 0

            processing_time = time.time() - start_time

            logger.info(
                f"Fast AI processing complete",
                user_id=user_id,
                category=result.get("category"),
                tokens=tokens,
                duration_seconds=processing_time,
                model=self.default_model
            )

            # Calculate cost
            cost = self._calculate_cost(tokens)

            # Log the cost
            self._log_cost(user_id, "fast_process", result.get("category", "unknown"), tokens, cost)

            return {
                "success": True,
                "data": result,
                "category": result.get("category", "unknown"),
                "metadata": {
                    "tokens": tokens,
                    "cost_usd": cost,
                    "processing_time": processing_time,
                    "model": self.default_model
                }
            }

        except Exception as e:
            logger.error(f"Fast AI processing failed: {e}")

            # Fallback to simple extraction if AI fails
            return self._fallback_extraction(description, image_url)

    def _fallback_extraction(self, description: Optional[str], image_url: Optional[str]) -> Dict[str, Any]:
        """Fallback extraction when AI fails"""

        # Simple keyword-based classification
        category = "unknown"
        if description:
            desc_lower = description.lower()
            if any(word in desc_lower for word in ["receipt", "invoice", "bill", "purchase", "walmart", "target"]):
                category = "receipt"
            elif any(word in desc_lower for word in ["food", "meal", "eat", "drink", "calories"]):
                category = "food"
            elif any(word in desc_lower for word in ["workout", "exercise", "gym", "fitness"]):
                category = "workout"

        # Create basic response
        if category == "receipt":
            return {
                "success": True,
                "data": {
                    "merchant_name": description or "Unknown",
                    "total_amount": 0,
                    "items": [{"name": description or "Item", "price": 0, "quantity": 1}]
                },
                "category": "receipt",
                "metadata": {"fallback": True}
            }
        elif category == "food":
            return {
                "success": True,
                "data": {
                    "food_items": [{"name": description or "Food", "calories": 0}],
                    "meal_type": "snack",
                    "total_calories": 0
                },
                "category": "food",
                "metadata": {"fallback": True}
            }
        else:
            return {
                "success": True,
                "data": {"description": description},
                "category": "unknown",
                "metadata": {"fallback": True}
            }

    def _calculate_cost(self, tokens: int) -> float:
        """Calculate cost based on tokens"""
        costs = self.model_costs.get(self.default_model, {"input": 0.001, "output": 0.001})
        # Approximate 70/30 split for input/output
        input_tokens = int(tokens * 0.7)
        output_tokens = int(tokens * 0.3)

        cost = (input_tokens * costs["input"] / 1000) + (output_tokens * costs["output"] / 1000)
        return round(cost, 6)

    def _log_cost(self, user_id: str, function_name: str, category: str, tokens: int, cost: float):
        """Log the cost to database"""
        try:
            cost_record = {
                "id": None,  # Let DB generate
                "user_id": user_id,
                "function_name": function_name,
                "category": category,
                "model_used": self.default_model,
                "total_tokens": tokens,
                "cost_usd": cost,
                "created_at": datetime.now(pytz.utc).isoformat()
            }

            self.db.write("app_api_costs", [cost_record])

        except Exception as e:
            logger.error(f"Failed to log cost: {e}")

    # Compatibility method for existing code
    def process_request(self, user_id: str, description: Optional[str] = None, image_url: Optional[str] = None) -> Dict[str, Any]:
        """Compatibility wrapper for existing code"""
        return self.process_request_fast(user_id, description, image_url)
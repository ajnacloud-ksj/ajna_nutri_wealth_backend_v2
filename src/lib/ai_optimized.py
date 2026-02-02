"""
Optimized AI Service with Two-Stage Processing
- Stage 1: Fast classification using small model
- Stage 2: Detailed analysis using appropriate model
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import pytz
from openai import OpenAI
from lib.logger import logger
from config.settings import settings


class OptimizedAIService:
    """AI Service with intelligent two-stage processing for better performance"""

    def __init__(self, db_client):
        self.db = db_client

        # Initialize OpenAI client
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = OpenAI(
            api_key=api_key,
            timeout=60.0,
            max_retries=2
        )

        # Model configuration
        self.classifier_model = "gpt-4o-mini"  # Fast, cheap model for classification
        self.analysis_models = {
            'food': "gpt-5.2-2025-12-11",  # GPT-5.2 for superior nutritional analysis!
            'receipt': "gpt-4o-mini",  # Good enough for text extraction
            'workout': "gpt-4o-mini",  # Good enough for workout parsing
            'default': "gpt-5.2-2025-12-11"  # Use GPT-5.2 for unknown categories
        }

        # Option to skip classification for better performance
        self.skip_classification = os.environ.get("SKIP_AI_CLASSIFICATION", "false").lower() == "true"

        # Cost tracking (per 1K tokens)
        self.model_costs = {
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4o": {"input": 0.0025, "output": 0.01},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-5.2-chat-latest": {"input": 0.005, "output": 0.015},  # Estimated pricing
            "gpt-5.2": {"input": 0.005, "output": 0.015}  # Estimated pricing
        }

        logger.info("OptimizedAIService initialized with two-stage processing")

    def _get_classification_prompt(self) -> str:
        """Get the prompt for content classification"""
        return """You are a classification AI. Analyze the content and determine its category.

Categories:
- food: Any food, meal, drink, or nutrition-related content
- receipt: Purchase receipts, bills, invoices, or transaction records
- workout: Exercise, fitness, gym activities, or physical training
- unknown: Content that doesn't fit the above categories

Consider:
1. Image content (if provided)
2. Text description
3. Context clues

Return ONLY a JSON object with:
{
    "category": "food|receipt|workout|unknown",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""

    def _classify_content(
        self,
        description: Optional[str],
        image_url: Optional[str]
    ) -> Tuple[str, float, int]:
        """
        Intelligently classify content using a small, fast model

        Returns:
            Tuple of (category, confidence, tokens_used)
        """
        start_time = time.time()

        # Build classification prompt
        messages = [
            {"role": "system", "content": self._get_classification_prompt()},
            {"role": "user", "content": []}
        ]

        user_content = []

        # Add description if provided
        if description:
            user_content.append({
                "type": "text",
                "text": f"Description: {description}"
            })

        # Add image if provided
        if image_url and not image_url.startswith('uploads/'):
            # Only include if it's a direct URL (not a file key)
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        elif image_url:
            # If it's a file key, add text description
            user_content.append({
                "type": "text",
                "text": "Note: An image was uploaded but not directly accessible for classification."
            })

        # Add instruction
        user_content.append({
            "type": "text",
            "text": "Classify this content into the appropriate category."
        })

        messages[1]["content"] = user_content

        try:
            # Use small model for classification
            response = self.client.chat.completions.create(
                model=self.classifier_model,
                messages=messages,
                temperature=0,
                max_tokens=100,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens

            logger.debug(
                "Content classified",
                category=result.get("category"),
                confidence=result.get("confidence"),
                tokens=tokens,
                duration_ms=(time.time() - start_time) * 1000
            )

            return (
                result.get("category", "unknown"),
                result.get("confidence", 0.5),
                tokens
            )

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Fallback to keyword-based classification
            return self._fallback_classification(description), 0.3, 0

    def _fallback_classification(self, description: Optional[str]) -> str:
        """Simple keyword-based classification as fallback"""
        if not description:
            return "food"

        lower_desc = description.lower()

        if any(w in lower_desc for w in ["receipt", "bill", "invoice", "purchase", "bought"]):
            return "receipt"
        if any(w in lower_desc for w in ["workout", "gym", "exercise", "training", "fitness", "ran", "lifted"]):
            return "workout"

        return "food"

    def _load_prompt(self, category: str) -> Dict[str, str]:
        """Load prompt for specific category"""
        # Try database first
        try:
            res = self.db.query("app_prompts", filters=[
                {"field": "category", "operator": "eq", "value": category},
                {"field": "is_active", "operator": "eq", "value": True}
            ], limit=1)

            if res and res.get('success'):
                data = res.get('data', {})
                prompts = data.get('records', [])
                if prompts:
                    prompt = prompts[0]
                    return {
                        "system_prompt": prompt.get("system_prompt"),
                        "user_prompt_template": prompt.get("user_prompt_template")
                    }
        except Exception as e:
            logger.warning(f"Failed to load prompt from DB: {e}")

        # Load from files
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(current_dir)
            prompts_dir = os.path.join(src_dir, 'prompts')

            system_file = os.path.join(prompts_dir, f'{category}_system.md')
            user_file = os.path.join(prompts_dir, f'{category}_user.md')

            system_prompt = ""
            user_template = ""

            if os.path.exists(system_file):
                with open(system_file, 'r') as f:
                    system_prompt = f.read().strip()

            if os.path.exists(user_file):
                with open(user_file, 'r') as f:
                    user_template = f.read().strip()

            if system_prompt and user_template:
                return {
                    "system_prompt": system_prompt,
                    "user_prompt_template": user_template
                }
        except Exception as e:
            logger.warning(f"Failed to load prompt from files: {e}")

        # Fallback prompts
        if category == "food":
            return {
                "system_prompt": "You are an expert nutritionist. Analyze food and provide detailed nutritional information. Return valid JSON.",
                "user_prompt_template": "Analyze this food: {description}"
            }
        elif category == "receipt":
            return {
                "system_prompt": "You are a receipt parser. Extract merchant, date, total, and items. Return valid JSON.",
                "user_prompt_template": "Parse this receipt: {description}"
            }
        elif category == "workout":
            return {
                "system_prompt": "You are a fitness tracker. Extract workout type, duration, and exercises. Return valid JSON.",
                "user_prompt_template": "Analyze this workout: {description}"
            }

        return {
            "system_prompt": "You are a helpful AI assistant. Return valid JSON.",
            "user_prompt_template": "Analyze this: {description}"
        }

    def _get_time_context(self) -> str:
        """Get current time context for meal type hints"""
        now = datetime.now(pytz.utc)
        hour = now.hour

        meal_hint = 'snack'
        if 5 <= hour < 11:
            meal_hint = 'breakfast'
        elif 11 <= hour < 15:
            meal_hint = 'lunch'
        elif 17 <= hour < 22:
            meal_hint = 'dinner'

        return f"Current UTC time: {now.strftime('%H:%M')}. Time-based meal hint: {meal_hint}. But prioritize food content over time."

    def _resolve_image_url(self, image_url: str) -> str:
        """Resolve S3 key to presigned URL if needed"""
        if not image_url or not isinstance(image_url, str):
            return image_url

        if image_url.startswith('uploads/'):
            try:
                logger.debug(f"Resolving S3 key: {image_url}")
                res = self.db.get_download_url(image_url)
                if res.get('success'):
                    resolved_url = res['data']['download_url']
                    logger.debug("Successfully resolved to presigned URL")
                    return resolved_url
            except Exception as e:
                logger.error(f"Failed to resolve S3 key: {e}")

        return image_url

    def process_request(
        self,
        user_id: str,
        description: Optional[str],
        image_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process analysis request with two-stage approach

        Stage 1: Fast classification
        Stage 2: Detailed analysis with appropriate model
        """
        start_time = time.time()
        total_tokens = 0
        total_cost = 0.0

        try:
            # Resolve image URL if needed
            resolved_image_url = self._resolve_image_url(image_url)

            # Stage 1: Classification
            logger.info(f"Starting two-stage analysis for user {user_id}")

            category, confidence, classifier_tokens = self._classify_content(
                description, resolved_image_url
            )

            total_tokens += classifier_tokens

            # Calculate classifier cost
            classifier_cost = (
                (classifier_tokens * self.model_costs[self.classifier_model]["input"]) / 1000
            )
            total_cost += classifier_cost

            logger.info(
                "Classification complete",
                category=category,
                confidence=confidence,
                tokens=classifier_tokens,
                cost=classifier_cost
            )

            # Stage 2: Detailed Analysis
            # Select model based on category and confidence
            if confidence < 0.5:
                # Low confidence, use better model
                analysis_model = "gpt-4o"
            else:
                analysis_model = self.analysis_models.get(category, self.analysis_models['default'])

            # Load appropriate prompt
            prompt_config = self._load_prompt(category)
            system_prompt = prompt_config['system_prompt']
            user_template = prompt_config['user_prompt_template']

            # Build analysis prompt
            full_user_prompt = user_template.replace('{description}', description or '')

            # Add context based on category
            if category == 'food':
                full_user_prompt += f"\n\n{self._get_time_context()}"
                full_user_prompt += "\nProvide detailed nutritional analysis."
            elif category == 'receipt':
                full_user_prompt += "\n\nExtract all visible items with prices."
            elif category == 'workout':
                full_user_prompt += "\n\nInclude all exercises with sets, reps, and weights if visible."

            full_user_prompt += "\n\nReturn ONLY valid JSON matching the expected structure."

            # Build messages for analysis
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": []}
            ]

            content_parts = [{"type": "text", "text": full_user_prompt}]

            if resolved_image_url and not resolved_image_url.startswith('uploads/'):
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": resolved_image_url}
                })

            messages[1]["content"] = content_parts

            # Call OpenAI for detailed analysis
            analysis_params = {
                "model": analysis_model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"}
            }

            # Set appropriate token limit based on model
            if "gpt-5" in analysis_model.lower():
                # GPT-5.2 requires max_completion_tokens - use direct API call
                import requests

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY')}"
                }

                data = {
                    "model": analysis_model,
                    "messages": messages,
                    "temperature": 0,
                    "max_completion_tokens": 2000,
                    "response_format": {"type": "json_object"}
                }

                logger.debug(f"Starting detailed analysis with model: {analysis_model}")

                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=60
                )
                response.raise_for_status()
                completion_data = response.json()

                # Create a mock completion object to match the expected format
                class MockCompletion:
                    def __init__(self, data):
                        self.choices = [type('obj', (object,), {
                            'message': type('obj', (object,), {
                                'content': data['choices'][0]['message']['content']
                            })()
                        })()]
                        self.usage = type('obj', (object,), {
                            'total_tokens': data['usage']['total_tokens'],
                            'prompt_tokens': data['usage']['prompt_tokens'],
                            'completion_tokens': data['usage']['completion_tokens']
                        })()

                completion = MockCompletion(completion_data)
            else:
                analysis_params["max_tokens"] = 2000
                logger.debug(f"Starting detailed analysis with model: {analysis_model}")
                completion = self.client.chat.completions.create(**analysis_params)

            analysis_text = completion.choices[0].message.content
            analysis_tokens = completion.usage.total_tokens
            total_tokens += analysis_tokens

            # Parse result
            analysis_result = json.loads(analysis_text)

            # Calculate analysis cost
            model_rates = self.model_costs.get(analysis_model, self.model_costs['gpt-4o-mini'])
            analysis_cost = (
                (completion.usage.prompt_tokens / 1000 * model_rates["input"]) +
                (completion.usage.completion_tokens / 1000 * model_rates["output"])
            )
            total_cost += analysis_cost

            # Log cost tracking
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Analysis complete",
                category=category,
                total_tokens=total_tokens,
                total_cost=total_cost,
                duration_ms=duration_ms,
                classifier_model=self.classifier_model,
                analysis_model=analysis_model
            )

            # Store cost in database
            self._log_cost(
                user_id=user_id,
                category=category,
                models_used={
                    "classifier": self.classifier_model,
                    "analyzer": analysis_model
                },
                total_tokens=total_tokens,
                cost_usd=total_cost
            )

            return {
                "success": True,
                "category": category,
                "confidence": confidence,
                "data": analysis_result,
                "metadata": {
                    "total_tokens": total_tokens,
                    "total_cost": total_cost,
                    "duration_ms": duration_ms,
                    "models": {
                        "classifier": self.classifier_model,
                        "analyzer": analysis_model
                    },
                    "classification_confidence": confidence
                }
            }

        except Exception as e:
            logger.exception(f"AI Processing Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "category": "unknown"
            }

    def _log_cost(
        self,
        user_id: str,
        category: str,
        models_used: Dict[str, str],
        total_tokens: int,
        cost_usd: float
    ):
        """Log API usage and cost to database"""
        try:
            log_entry = {
                "user_id": user_id,
                "function_name": "process_request_optimized",
                "category": category,
                "model_used": json.dumps(models_used),  # Store both models
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "created_at": datetime.now(pytz.utc).isoformat()
            }

            self.db.write("app_api_costs", [log_entry])

        except Exception as e:
            logger.error(f"Failed to log cost: {e}")

    def get_usage_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get usage statistics for a user"""
        try:
            # Calculate date range
            end_date = datetime.now(pytz.utc)
            start_date = end_date - timedelta(days=days)

            # Query usage logs
            result = self.db.query(
                "app_api_costs",
                filters=[
                    {"field": "user_id", "operator": "eq", "value": user_id},
                    {"field": "created_at", "operator": "gte", "value": start_date.isoformat()}
                ],
                sort=[{"field": "created_at", "order": "desc"}],
                limit=1000
            )

            if not result.get('success'):
                return {"error": "Failed to fetch usage stats"}

            records = result.get('data', {}).get('records', [])

            # Calculate statistics
            total_cost = sum(r.get('cost_usd', 0) for r in records)
            total_tokens = sum(r.get('total_tokens', 0) for r in records)
            total_requests = len(records)

            # Group by category
            by_category = {}
            for record in records:
                cat = record.get('category', 'unknown')
                if cat not in by_category:
                    by_category[cat] = {
                        'count': 0,
                        'tokens': 0,
                        'cost': 0
                    }
                by_category[cat]['count'] += 1
                by_category[cat]['tokens'] += record.get('total_tokens', 0)
                by_category[cat]['cost'] += record.get('cost_usd', 0)

            return {
                "period_days": days,
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 4),
                "average_cost_per_request": round(total_cost / total_requests, 4) if total_requests > 0 else 0,
                "by_category": by_category,
                "optimization_savings": self._calculate_savings(records)
            }

        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {"error": str(e)}

    def _calculate_savings(self, records: list) -> Dict[str, float]:
        """Calculate cost savings from optimization"""
        optimized_cost = sum(r.get('cost_usd', 0) for r in records)

        # Calculate what it would cost with only gpt-4o
        hypothetical_cost = 0
        for record in records:
            tokens = record.get('total_tokens', 0)
            # Assume gpt-4o for everything
            hypothetical_cost += (tokens / 1000) * 0.0125  # Average of input/output

        savings = hypothetical_cost - optimized_cost
        savings_percent = (savings / hypothetical_cost * 100) if hypothetical_cost > 0 else 0

        return {
            "optimized_cost": round(optimized_cost, 4),
            "without_optimization": round(hypothetical_cost, 4),
            "saved": round(savings, 4),
            "saved_percent": round(savings_percent, 2)
        }
"""
Optimized AI Service with Two-Stage Processing
- Stage 1: Fast classification using small model
- Stage 2: Detailed analysis using appropriate model
"""

import os
import json
import time
from datetime import datetime, timedelta
from utils.timestamps import utc_now
from typing import Dict, Any, Optional, Tuple
import pytz
from openai import OpenAI
from lib.logger import logger
from lib.model_manager import get_model_manager


class OptimizedAIService:
    """AI Service with intelligent two-stage processing using ModelManager"""

    def __init__(self, db_client):
        self.db = db_client
        self.model_manager = get_model_manager(db_client)
        self._clients = {}  # Cache clients by provider

        self.default_model_config = self.model_manager.get_model_config("food")
        
        # Option to skip classification for better performance
        self.skip_classification = os.environ.get("SKIP_AI_CLASSIFICATION", "false").lower() == "true"

        logger.info("OptimizedAIService initialized with ModelManager")

    def _get_client(self, provider: str) -> OpenAI:
        """Get or create OpenAI-compatible client for provider"""
        if provider in self._clients:
            return self._clients[provider]
            
        api_key = self.model_manager.get_api_key(provider)
        provider_config = self.model_manager.get_provider_config(provider)
        base_url = provider_config.get("base_url")
        
        if not api_key:
             raise ValueError(f"API key required for provider {provider}")

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
            max_retries=2
        )
        self._clients[provider] = client
        return client

    def _get_classification_prompt(self) -> str:
        """Get the prompt for content classification"""
        return """You are an expert content classifier. Analyze the content and determine its category.

CATEGORIES (choose exactly one):

1. receipt: Purchase receipts, bills, invoices, or transaction records
   - Key indicators: Store/merchant name, date/time, itemized list with prices, subtotal/tax/total
   - Look for: Multiple items with prices, payment info, transaction ID, store address
   - Even if receipt shows food items, it's still a RECEIPT if it's a purchase record

2. food: Actual food, meals, drinks, or dishes (NOT receipts for food purchases)
   - Key indicators: Visible food/drinks, plates, cooking, restaurants meals
   - This is for food photos, NOT purchase receipts of food

3. workout: Exercise, fitness, gym activities, or physical training
   - Key indicators: Exercise equipment, people exercising, fitness tracking, sports

4. unknown: Content that doesn't clearly fit the above categories

IMPORTANT: A grocery receipt or restaurant bill is a RECEIPT, not food.
A photo of a meal or dish is FOOD, not a receipt.

Analyze:
1. Visual content if image provided
2. Text description if provided
3. Layout and structure (receipts have specific formatting)

Return ONLY a JSON object with:
{
    "category": "receipt|food|workout|unknown",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of your decision"
}"""

    def _classify_content(
        self,
        description: Optional[str],
        image_url: Optional[str]
    ) -> Tuple[str, float, int]:
        """
        Intelligently classify content
        """
        start_time = time.time()
        
        # Get config for classifier
        config = self.model_manager.get_model_config("classifier")
        client = self._get_client(config.provider)

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

        # Add image if provided (should already be resolved to presigned URL by caller)
        if image_url:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })

        # Add instruction
        user_content.append({
            "type": "text",
            "text": "Classify this content into the appropriate category."
        })

        messages[1]["content"] = user_content

        try:
            # Use configured model for classification
            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                **config.temperature_kwargs(),
                **config.token_kwargs(),
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0

            # Handle None/empty content (model refusal or content filtering)
            if not content or not content.strip():
                logger.warning("Classification returned empty content, falling back to keyword classification")
                return self._keyword_classify(description)

            result = json.loads(content)

            logger.debug(
                "Content classified",
                category=result.get("category"),
                confidence=result.get("confidence"),
                tokens=tokens,
                duration_ms=(time.time() - start_time) * 1000,
                provider=config.provider
            )

            return (
                result.get("category", "unknown"),
                result.get("confidence", 0.5),
                tokens
            )

        except json.JSONDecodeError as e:
            logger.error(f"Classification JSON parse failed: {e}")
            return self._keyword_classify(description)

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return self._keyword_classify(description)

    def _keyword_classify(self, description: Optional[str]) -> Tuple[str, float, int]:
        """Fallback keyword-based classification when AI classification fails"""
        if description:
            desc_lower = description.lower()
            if any(w in desc_lower for w in ["receipt", "invoice", "bill", "purchase", "store", "walmart", "target"]):
                return ("receipt", 0.6, 0)
            elif any(w in desc_lower for w in ["workout", "exercise", "gym", "fitness", "run", "jog"]):
                return ("workout", 0.6, 0)
            elif any(w in desc_lower for w in ["food", "meal", "eat", "drink", "calories", "breakfast", "lunch", "dinner"]):
                return ("food", 0.6, 0)
        # Default to food for image-based submissions
        return ("food", 0.4, 0)

    def _load_prompt(self, category: str) -> Dict[str, str]:
        """Load prompt for specific category"""
        # (Same implementation as before)
        # Try database first
        try:
            res = self.db.query("app_prompts", filters=[
                {"field": "category", "operator": "eq", "value": category},
                {"field": "is_active", "operator": "eq", "value": True}
            ], limit=1, include_deleted=False)

            if res and res.get('success'):
                data = res.get('data', {})
                records = data.get('records', [])
                if records:
                    prompt = records[0]
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

        # Fallback prompts (Same as before)
        if category == "food":
            return {
                "system_prompt": "You are an expert nutritionist. Analyze food and provide detailed nutritional information. Return valid JSON.",
                "user_prompt_template": "Analyze this food: {description}"
            }
        elif category == "receipt":
            return {
                "system_prompt": (
                    "You are a receipt/purchase parser. Extract purchase details and return valid JSON with these fields:\n"
                    "- merchant_name: the STORE or BRAND name (e.g. 'OLD Navy', 'Walmart', 'Starbucks'). NEVER use a country, city, or address as merchant_name.\n"
                    "- purchase_date: date in YYYY-MM-DD format, use today's date if not specified\n"
                    "- financial_summary: {total_amount, subtotal, tax_amount, discount_amount, currency}\n"
                    "- items: array of {name, quantity, unit_price, total_price, category}\n"
                    "- payment_method: cash/card/etc if mentioned\n"
                    "Fill in reasonable values from context. Never use placeholder text like 'string' or 'YYYY-MM-DD'."
                ),
                "user_prompt_template": "Parse this purchase/receipt: {description}"
            }
        elif category == "workout":
            return {
                "system_prompt": (
                    "You are a fitness tracker. Extract workout details and return valid JSON with these fields:\n"
                    "- workout_type: type of workout (e.g. 'Running', 'Weight Training', 'Yoga', 'HIIT', 'General')\n"
                    "- duration_minutes: total duration in minutes as a number (estimate if not stated)\n"
                    "- calories_burned: estimated calories burned as a number\n"
                    "- intensity_level: 'low', 'moderate', or 'high'\n"
                    "- muscle_groups: comma-separated list of muscle groups worked\n"
                    "- notes: brief summary of the workout\n"
                    "- exercises: array of objects with {name, sets, reps, weight_lbs, distance_miles, duration_seconds, calories_burned}\n"
                    "Fill in reasonable estimates. Never use placeholder text."
                ),
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
        """Resolve S3 key to presigned download URL via IbexDB SDK."""
        if not image_url or not isinstance(image_url, str):
            return image_url

        # If it's already an HTTP(S) URL or base64, return as-is
        if image_url.startswith('http://') or image_url.startswith('https://') or image_url.startswith('data:'):
            return image_url

        # S3 key — resolve via IbexDB
        logger.info(f"Resolving S3 key to presigned URL via IbexDB: {image_url}")
        try:
            # Legacy keys (uploads/{user_id}/...) are in the old bucket
            bucket = None
            if image_url.startswith('uploads/') and not image_url.startswith('tenants/'):
                bucket = 'nutriwealth-uploads'

            res = self.db.get_download_url(image_url, expires_in=3600, bucket=bucket)
            if res.get('success'):
                url = res.get('data', {}).get('download_url', '')
                if url:
                    logger.info("Successfully resolved S3 key to presigned download URL")
                    return url
            logger.error(f"IbexDB get_download_url failed for key={image_url}: {res.get('error', 'unknown')}")
        except Exception as e:
            logger.error(f"Error resolving image URL via IbexDB: {e}")

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
            
            # Get classifier config for cost
            classifier_config = self.model_manager.get_model_config("classifier")
            
            # Calculate classifier cost
            classifier_cost = (classifier_tokens / 1000) * classifier_config.cost_per_1k_tokens
            total_cost += classifier_cost

            logger.info(
                "Classification complete",
                category=category,
                confidence=confidence,
                tokens=classifier_tokens,
                cost=classifier_cost
            )

            # Stage 2: Detailed Analysis
            # Get model config for category
            config = self.model_manager.get_model_config(category)
            
            # Create client for analysis
            client = self._get_client(config.provider)

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

            if resolved_image_url:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": resolved_image_url}
                })

            messages[1]["content"] = content_parts

            # Call API for detailed analysis
            logger.debug(f"Starting detailed analysis with model: {config.model_name} (Provider: {config.provider})")

            # Use structured outputs for receipts with OpenAI models that support it
            response_format = {"type": "json_object"}  # Default
            if category == "receipt" and config.provider == "openai" and any(p in config.model_name for p in ("gpt-4o", "gpt-5")):
                try:
                    from schemas.receipt_schema import RECEIPT_RESPONSE_SCHEMA
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "receipt_extraction",
                            "strict": True,
                            "schema": RECEIPT_RESPONSE_SCHEMA
                        }
                    }
                    logger.info(f"Using structured outputs with schema for receipt analysis")
                except ImportError:
                    logger.warning("Could not import receipt schema, falling back to simple JSON mode")

            completion = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                **config.temperature_kwargs(),
                **config.token_kwargs(),
                response_format=response_format
            )

            analysis_text = completion.choices[0].message.content
            analysis_tokens = completion.usage.total_tokens if completion.usage else 0
            total_tokens += analysis_tokens

            # Handle None/empty analysis response
            if not analysis_text or not analysis_text.strip():
                logger.error(f"Analysis returned empty content for category={category}")
                return {
                    "success": False,
                    "error": f"AI returned empty response for {category} analysis",
                    "category": category
                }

            # Parse result with retry logic for receipts
            try:
                analysis_result = json.loads(analysis_text)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for {category}: {str(e)}")
                logger.error(f"Raw response (first 500 chars): {analysis_text[:500]}")

                # Retry once for receipts with a more explicit prompt
                if category == "receipt":
                    logger.info("Retrying receipt analysis with explicit JSON instructions")
                    retry_messages = messages + [
                        {"role": "assistant", "content": analysis_text},
                        {"role": "user", "content": "The response was not valid JSON. Please provide a valid JSON response matching the exact structure requested. Ensure all JSON syntax is correct."}
                    ]

                    retry_completion = client.chat.completions.create(
                        model=config.model_name,
                        messages=retry_messages,
                        **config.temperature_kwargs(0),  # Use zero temperature for retry
                        **config.token_kwargs(),
                        response_format=response_format
                    )

                    retry_text = retry_completion.choices[0].message.content
                    total_tokens += retry_completion.usage.total_tokens

                    try:
                        analysis_result = json.loads(retry_text)
                        logger.info("Retry successful - valid JSON received")
                    except json.JSONDecodeError as retry_error:
                        logger.error(f"Retry also failed: {str(retry_error)}")
                        # Return a minimal valid structure
                        analysis_result = {
                            "error": "Failed to parse receipt",
                            "raw_response_sample": analysis_text[:1000]
                        }
                else:
                    raise

            # Calculate analysis cost
            analysis_cost = (analysis_tokens / 1000) * config.cost_per_1k_tokens
            total_cost += analysis_cost

            # Log cost tracking
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Analysis complete",
                category=category,
                total_tokens=total_tokens,
                total_cost=total_cost,
                duration_ms=duration_ms,
                classifier_model=classifier_config.model_name,
                analysis_model=config.model_name
            )

            # Store cost in database
            self._log_cost(
                user_id=user_id,
                category=category,
                models_used={
                    "classifier": classifier_config.model_name,
                    "analyzer": config.model_name
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
                        "classifier": classifier_config.model_name,
                        "analyzer": config.model_name,
                        "provider": config.provider
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
            import uuid
            log_entry = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "function_name": "process_request_optimized",
                "category": category,
                "model_used": json.dumps(models_used),
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "created_at": utc_now()
            }

            self.db.write("app_api_costs", [log_entry])

        except Exception as e:
            logger.error(f"Failed to log cost: {e}")

    # get_usage_stats method removed for brevity as it's not changed in logic, 
    # but I must include it if I replace the whole file. 
    # Wait, the tool replaces CONTIGUOUS blocks.
    # The file content above replaces virtually the whole class.
    # I should include get_usage_stats so I don't delete it.
    
    def get_usage_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
         # (Keeping original implementation essentially)
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
                limit=1000,
                include_deleted=False
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
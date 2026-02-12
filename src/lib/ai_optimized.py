"""
Optimized AI Service with Two-Stage Processing
- Stage 1: Fast classification using small model
- Stage 2: Detailed analysis using appropriate model
"""

import os
import json
import time
from datetime import datetime, timedelta
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

        # Default fallback
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
            logger.warning(f"No API key found for provider {provider}, falling back to OpenAI defaults if possible")
            # Try getting OPENAI_API_KEY explicitly as last resort
            api_key = os.environ.get("OPENAI_API_KEY")
            
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
            # Use configured model for classification
            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens

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
        # (Same implementation as before)
        # Try database first
        try:
            res = self.db.query("app_prompts", filters=[
                {"field": "category", "operator": "eq", "value": category},
                {"field": "is_active", "operator": "eq", "value": True}
            ], limit=1)

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
            
            # If low confidence, maybe override? 
            # Current logic: rely on Manager's config. Manager can have fallbacks.
            # If needed, logic can check config.fallback_provider if primary fails (implemented in Manager?)
            
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

            if resolved_image_url and not resolved_image_url.startswith('uploads/'):
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": resolved_image_url}
                })

            messages[1]["content"] = content_parts

            # Call API for detailed analysis
            logger.debug(f"Starting detailed analysis with model: {config.model_name} (Provider: {config.provider})")
            
            completion = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                response_format={"type": "json_object"}
            )

            analysis_text = completion.choices[0].message.content
            analysis_tokens = completion.usage.total_tokens
            total_tokens += analysis_tokens

            # Parse result
            analysis_result = json.loads(analysis_text)

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
            log_entry = {
                "user_id": user_id,
                "function_name": "process_request_optimized",
                "category": category,
                "model_used": json.dumps(models_used),
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "created_at": datetime.now(pytz.utc).isoformat()
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
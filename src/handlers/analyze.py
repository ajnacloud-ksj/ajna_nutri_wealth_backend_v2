"""
Improved Analysis Handler - Example of all security and quality improvements
This demonstrates how to apply all the new patterns to existing handlers
"""

import json
import uuid
import base64
from datetime import datetime
from typing import Dict, Any, Optional

# Import new utilities
from lib.auth_provider import require_auth, get_user_id
from lib.validators import validate_request, ValidationError
from lib.logger import logger, log_handler
from config.settings import settings
from utils.http import respond


# Define validation schema for analyze endpoint
ANALYZE_SCHEMA = {
    'description': {
        'type': 'string',
        'required': False,
        'max_length': 1000
    },
    'imageUrl': {
        'type': 'string',
        'required': False
    },
    'image_url': {
        'type': 'string',
        'required': False
    },
    'category': {
        'type': 'string',
        'required': False,
        'choices': ['food', 'receipt', 'workout']
    }
}


@log_handler  # Automatic request/response logging
@require_auth  # Requires authentication based on AUTH_MODE
@validate_request(schema=ANALYZE_SCHEMA)  # Automatic input validation
def analyze_food(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/analyze - Improved food analysis with all security features

    Features:
    - Automatic authentication (local/Cognito based on environment)
    - Input validation and sanitization
    - Structured logging with request tracking
    - Configuration-based feature flags
    - Proper error handling
    """
    # Get authenticated user ID (guaranteed to exist due to @require_auth)
    user_id = get_user_id(event)
    request_id = context.get('request_id', str(uuid.uuid4()))

    # Log the analysis request
    logger.info(
        "Starting analysis",
        user_id=user_id,
        request_id=request_id,
        action="analyze_food"
    )

    # Check if AI analysis is enabled
    if not settings.is_feature_enabled('enable_ai_analysis'):
        logger.warning(
            "AI analysis disabled",
            user_id=user_id,
            request_id=request_id
        )
        return respond(503, {
            'error': 'AI analysis is currently disabled',
            'request_id': request_id
        }, event=event)

    # Get services from context
    db = context.get('db')
    ai_service = context.get('ai_service')

    # Validate service availability
    if not db or not ai_service:
        logger.error(
            "Required services not available",
            db_available=bool(db),
            ai_available=bool(ai_service),
            request_id=request_id
        )
        return respond(503, {
            'error': 'Required services not available',
            'request_id': request_id
        }, event=event)

    # Parse validated body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError as e:
        # This shouldn't happen due to @validate_request, but being defensive
        logger.error(
            "JSON decode error after validation",
            error=str(e),
            request_id=request_id
        )
        return respond(400, {
            'error': 'Invalid request body',
            'request_id': request_id
        }, event=event)

    # Extract parameters (already validated and sanitized)
    description = body.get('description', '')
    image_url = body.get('imageUrl') or body.get('image_url', '')

    # Ensure we have something to analyze
    if not description and not image_url:
        logger.warning(
            "Empty analysis request",
            user_id=user_id,
            request_id=request_id
        )
        return respond(400, {
            'error': 'Please provide a description or image',
            'request_id': request_id
        }, event=event)

    # Generate entry ID upfront
    entry_id = str(uuid.uuid4())

    try:
        # Log AI processing start
        logger.debug(
            "Processing with AI",
            user_id=user_id,
            entry_id=entry_id,
            has_description=bool(description),
            has_image=bool(image_url)
        )

        # Process with AI service
        analysis_result = ai_service.process_request(
            user_id,
            description,
            image_url
        )

        if not analysis_result.get('success'):
            raise Exception(analysis_result.get('error', 'AI analysis failed'))

        # Extract results
        ai_data = analysis_result.get('data', {})
        category = analysis_result.get('category', 'food')

        logger.info(
            "AI analysis completed",
            user_id=user_id,
            entry_id=entry_id,
            category=category,
            tokens_used=analysis_result.get('metadata', {}).get('tokens', 0)
        )

        # Store based on category
        if category == 'food':
            result = _store_food_entry(
                db, user_id, entry_id, ai_data, description, image_url, logger
            )
        elif category == 'receipt':
            result = _store_receipt(
                db, user_id, entry_id, ai_data, image_url, logger
            )
        elif category == 'workout':
            result = _store_workout(
                db, user_id, entry_id, ai_data, image_url, logger
            )
        else:
            # Unknown category
            logger.warning(
                "Unknown category from AI",
                category=category,
                user_id=user_id,
                entry_id=entry_id
            )
            result = {
                'success': True,
                'entry_id': entry_id,
                'category': category,
                'data': ai_data
            }

        # Add request ID to response
        result['request_id'] = request_id

        # Log successful completion
        logger.info(
            "Analysis completed successfully",
            user_id=user_id,
            entry_id=entry_id,
            category=category,
            request_id=request_id
        )

        return respond(200, result, event=event)

    except Exception as e:
        # Log the error with full context
        logger.exception(
            "Analysis failed",
            user_id=user_id,
            entry_id=entry_id,
            error=str(e),
            request_id=request_id
        )

        # Return user-friendly error
        return respond(500, {
            'success': False,
            'error': 'Analysis failed. Please try again.',
            'entry_id': entry_id,
            'request_id': request_id
        }, event=event)


def _upload_base64_to_s3(db, base64_image: str, user_id: str, entry_id: str) -> Optional[str]:
    """
    Upload a base64 image to S3 and return the S3 URL

    Args:
        db: Database/storage service instance
        base64_image: Base64 encoded image string (with or without data URL prefix)
        user_id: User ID for tracking
        entry_id: Entry ID for unique filename

    Returns:
        S3 URL of the uploaded image or None if upload fails
    """
    try:
        # Remove data URL prefix if present
        if base64_image.startswith('data:'):
            # Extract the base64 part from data URL
            # Format: data:image/png;base64,<base64_data>
            header, base64_data = base64_image.split(',', 1)
            # Extract mime type from header
            mime_type = header.split(':')[1].split(';')[0]
        else:
            base64_data = base64_image
            mime_type = 'image/jpeg'  # Default mime type

        # Generate unique filename using entry_id for consistency
        file_extension = mime_type.split('/')[-1]
        filename = f"receipts/{user_id}/{entry_id}.{file_extension}"

        # Upload to S3 using the existing upload functionality
        result = db.upload_file(base64_data, filename, mime_type)

        if result.get('success'):
            # Return the S3 URL
            s3_url = result.get('url')
            logger.info(
                "Image uploaded to S3",
                user_id=user_id,
                entry_id=entry_id,
                filename=filename,
                s3_url=s3_url
            )
            return s3_url
        else:
            logger.error(
                "Failed to upload image to S3",
                user_id=user_id,
                entry_id=entry_id,
                error=result.get('error')
            )
            return None

    except Exception as e:
        logger.error(
            "Error uploading image to S3",
            user_id=user_id,
            entry_id=entry_id,
            error=str(e)
        )
        return None


def _store_food_entry(
    db, user_id: str, entry_id: str, ai_data: Dict,
    description: str, image_url: str, logger
) -> Dict[str, Any]:
    """Store food entry in database with proper error handling"""
    try:
        # Handle image upload to S3 if it's base64 data
        s3_image_url = None
        if image_url and image_url.startswith('data:'):
            # This is base64 data - upload to S3
            logger.info("Uploading food image to S3", user_id=user_id)
            s3_image_url = _upload_base64_to_s3(db, image_url, user_id, entry_id)

            if not s3_image_url:
                logger.warning(
                    "Failed to upload image to S3, proceeding without image",
                    user_id=user_id,
                    entry_id=entry_id
                )
        elif image_url and (image_url.startswith('http://') or image_url.startswith('https://') or image_url.startswith('s3://')):
            # This is already a URL, use as is
            s3_image_url = image_url

        # Parse AI results
        food_items = ai_data.get('food_items', [])
        total_calories = ai_data.get('total_calories', 0)
        meal_type = ai_data.get('meal_type', 'snack')

        # Calculate nutrition totals
        total_protein = sum(item.get('protein', 0) for item in food_items)
        total_carbs = sum(item.get('carbs', 0) for item in food_items)
        total_fat = sum(item.get('fat', 0) for item in food_items)
        total_fiber = sum(item.get('fiber', 0) for item in food_items)
        total_sodium = sum(item.get('sodium', 0) for item in food_items)

        # Get food name
        food_name = food_items[0].get('name') if food_items else description

        # Create entry record with S3 URL instead of base64
        food_entry = {
            'id': entry_id,
            'user_id': user_id,
            'description': food_name,
            'meal_type': meal_type,
            'meal_date': datetime.utcnow().strftime('%Y-%m-%d'),
            'meal_time': datetime.utcnow().strftime('%H:%M'),
            'calories': total_calories,
            'total_protein': total_protein,
            'total_carbohydrates': total_carbs,
            'total_fats': total_fat,
            'total_fiber': total_fiber,
            'total_sodium': total_sodium,
            'extracted_nutrients': json.dumps(ai_data),
            'image_url': s3_image_url or '',  # Store S3 URL, not base64
            'image_storage_type': 's3' if s3_image_url else 'none',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        # Store in database
        write_result = db.write('app_food_entries_v2', [food_entry])

        if write_result.get('success'):
            logger.info(
                "Food entry stored",
                entry_id=entry_id,
                user_id=user_id,
                calories=total_calories
            )

            return {
                'success': True,
                'entry_id': entry_id,
                'status': 'completed',
                'category': 'food',
                'summary': {
                    'description': food_name,
                    'calories': total_calories,
                    'meal_type': meal_type
                }
            }
        else:
            raise Exception(f"Database write failed: {write_result.get('error')}")

    except Exception as e:
        logger.error(
            "Failed to store food entry",
            entry_id=entry_id,
            error=str(e)
        )
        raise


def _store_receipt(
    db, user_id: str, entry_id: str, ai_data: Dict,
    image_url: str, logger
) -> Dict[str, Any]:
    """Store receipt in database with proper error handling"""
    try:
        # Handle image upload to S3 if it's base64 data
        s3_image_url = None
        if image_url and image_url.startswith('data:'):
            # This is base64 data - upload to S3
            logger.info("Uploading receipt image to S3", user_id=user_id)
            s3_image_url = _upload_base64_to_s3(db, image_url, user_id, entry_id)

            if not s3_image_url:
                logger.warning(
                    "Failed to upload image to S3, proceeding without image",
                    user_id=user_id,
                    entry_id=entry_id
                )
        elif image_url and (image_url.startswith('http://') or image_url.startswith('https://') or image_url.startswith('s3://')):
            # This is already a URL, use as is
            s3_image_url = image_url

        # Extract receipt data
        merchant = ai_data.get('merchant_name', 'Unknown Vendor')
        date_str = ai_data.get('purchase_date') or datetime.utcnow().strftime('%Y-%m-%d')
        total = ai_data.get('total_amount', 0.0)

        # Create receipt record with S3 URL instead of base64
        receipt_record = {
            'id': entry_id,
            'user_id': user_id,
            'vendor': merchant,
            'receipt_date': date_str,
            'total_amount': total,
            'currency': ai_data.get('currency', 'USD'),
            'category': ai_data.get('category', 'General'),
            'image_url': s3_image_url or '',  # Store S3 URL, not base64
            'image_storage_type': 's3' if s3_image_url else 'none',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        # Store receipt
        db.write('app_receipts', [receipt_record])

        # Store receipt items if available
        items = ai_data.get('items', [])
        if items:
            item_records = []
            for item in items:
                item_records.append({
                    'id': str(uuid.uuid4()),
                    'receipt_id': entry_id,
                    'name': item.get('name', 'Unknown Item'),
                    'price': item.get('price', 0.0),
                    'quantity': item.get('quantity', 1.0),
                    'category': item.get('category'),
                    'created_at': datetime.utcnow().isoformat()
                })
            db.write('app_receipt_items', item_records)

        logger.info(
            "Receipt stored",
            entry_id=entry_id,
            user_id=user_id,
            merchant=merchant,
            total=total,
            item_count=len(items)
        )

        return {
            'success': True,
            'entry_id': entry_id,
            'status': 'completed',
            'category': 'receipt',
            'summary': {
                'merchant': merchant,
                'total': total,
                'items': len(items)
            }
        }

    except Exception as e:
        logger.error(
            "Failed to store receipt",
            entry_id=entry_id,
            error=str(e)
        )
        raise


def _store_workout(
    db, user_id: str, entry_id: str, ai_data: Dict,
    image_url: str, logger
) -> Dict[str, Any]:
    """Store workout in database with proper error handling"""
    try:
        # Handle image upload to S3 if it's base64 data
        s3_image_url = None
        if image_url and image_url.startswith('data:'):
            # This is base64 data - upload to S3
            logger.info("Uploading workout image to S3", user_id=user_id)
            s3_image_url = _upload_base64_to_s3(db, image_url, user_id, entry_id)

            if not s3_image_url:
                logger.warning(
                    "Failed to upload image to S3, proceeding without image",
                    user_id=user_id,
                    entry_id=entry_id
                )
        elif image_url and (image_url.startswith('http://') or image_url.startswith('https://') or image_url.startswith('s3://')):
            # This is already a URL, use as is
            s3_image_url = image_url

        # Extract workout data
        workout_type = ai_data.get('workout_type', 'General')
        duration = ai_data.get('duration_minutes', 0)
        calories = ai_data.get('calories_burned_estimate', 0)

        # Create workout record with S3 URL instead of base64
        workout_record = {
            'id': entry_id,
            'user_id': user_id,
            'workout_type': workout_type,
            'duration_minutes': duration,
            'calories_burned': calories,
            'workout_date': ai_data.get('workout_date') or datetime.utcnow().strftime('%Y-%m-%d'),
            'notes': ai_data.get('notes'),
            'image_url': s3_image_url or '',  # Store S3 URL, not base64
            'image_storage_type': 's3' if s3_image_url else 'none',
            'created_at': datetime.utcnow().isoformat()
        }

        # Store workout
        db.write('app_workouts', [workout_record])

        # Store exercises if available
        exercises = ai_data.get('exercises', [])
        if exercises:
            ex_records = []
            for ex in exercises:
                ex_records.append({
                    'id': str(uuid.uuid4()),
                    'workout_id': entry_id,
                    'exercise_name': ex.get('name', 'Exercise'),
                    'sets': ex.get('sets'),
                    'reps': ex.get('reps'),
                    'weight': ex.get('weight_lbs'),
                    'distance': ex.get('distance_miles'),
                    'created_at': datetime.utcnow().isoformat()
                })
            db.write('app_workout_exercises', ex_records)

        logger.info(
            "Workout stored",
            entry_id=entry_id,
            user_id=user_id,
            workout_type=workout_type,
            duration=duration,
            calories=calories,
            exercise_count=len(exercises)
        )

        return {
            'success': True,
            'entry_id': entry_id,
            'status': 'completed',
            'category': 'workout',
            'summary': {
                'type': workout_type,
                'duration': duration,
                'calories': calories,
                'exercises': len(exercises)
            }
        }

    except Exception as e:
        logger.error(
            "Failed to store workout",
            entry_id=entry_id,
            error=str(e)
        )
        raise
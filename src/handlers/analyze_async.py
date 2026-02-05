"""
Async Analysis Handler with Queue Support
Returns immediately, processes in background
"""

import json
import uuid
import boto3
from datetime import datetime
from typing import Dict, Any, Optional

from lib.auth_provider import get_user_id
from lib.logger import logger
from utils.http import respond


# Lambda async configuration - check environment variables
import os
LAMBDA_ASYNC_ENABLED = os.environ.get('ENABLE_LAMBDA_ASYNC', 'false').lower() == 'true'
LAMBDA_FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', '')

# Initialize Lambda client if async enabled
if LAMBDA_ASYNC_ENABLED:
    aws_region = os.environ.get('AWS_REGION', 'ap-south-1')
    lambda_client = boto3.client('lambda', region_name=aws_region)
else:
    lambda_client = None


def submit_analysis(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/analyze/async - Submit analysis for async processing
    Returns immediately with tracking ID
    """
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
    except:
        return respond(400, {"error": "Invalid JSON"})

    description = body.get('description', '')
    image_url = body.get('imageUrl') or body.get('image_url', '')
    callback_url = body.get('callback_url')  # Optional webhook

    if not description and not image_url:
        return respond(400, {"error": "Please provide a description or image"})

    # Generate unique entry ID
    entry_id = str(uuid.uuid4())

    if LAMBDA_ASYNC_ENABLED and lambda_client:
        # Submit via Lambda Event invocation
        try:
            payload = {
                "source": "async-processing",
                "entry_id": entry_id,
                "user_id": user_id,
                "description": description,
                "image_url": image_url,
                "callback_url": callback_url,
                "timestamp": datetime.utcnow().isoformat()
            }

            response = lambda_client.invoke(
                FunctionName=LAMBDA_FUNCTION_NAME,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps(payload)
            )

            logger.info(f"Submitted async analysis via Lambda Event",
                       entry_id=entry_id,
                       status_code=response['StatusCode'])

            # Store pending status in DB
            db = context.get('db')
            if db:
                db.write("pending_analyses", [{
                    "id": entry_id,
                    "user_id": user_id,
                    "status": "processing",
                    "description": description[:100],  # First 100 chars
                    "created_at": datetime.utcnow().isoformat()
                }])

            return respond(200, {
                "success": True,
                "entry_id": entry_id,
                "status": "processing",
                "message": "Analysis submitted for processing",
                "poll_url": f"/v1/analyze/status/{entry_id}"
            })

        except Exception as e:
            logger.error(f"Failed to invoke Lambda async: {e}")
            # Fall through to sync processing

    # Fallback to synchronous processing
    logger.info("Lambda async not enabled, falling back to sync processing")

    # Import sync handler
    from handlers.analyze import analyze_food

    # Process synchronously but return async-like response
    sync_result = analyze_food(event, context)

    if sync_result.get('statusCode') == 200:
        result_body = json.loads(sync_result.get('body', '{}'))
        return respond(200, {
            "success": True,
            "entry_id": result_body.get('entry_id', entry_id),
            "status": "completed",
            "result": result_body
        })

    return sync_result



def get_analysis_status(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/analyze/status/{entry_id} - Check analysis status
    """
    entry_id = event.get('pathParameters', {}).get('entry_id')
    if not entry_id:
        return respond(400, {"error": "Entry ID required"})

    db = context.get('db')
    if not db:
        return respond(503, {"error": "Database not available"})

    try:
        # Check pending_analyses table
        result = db.query("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         limit=1)

        if result.get('success') and result.get('data', {}).get('records'):
            record = result['data']['records'][0]

            response = {
                "entry_id": entry_id,
                "status": record.get('status', 'unknown'),
                "created_at": record.get('created_at')
            }

            # If completed, get the result
            if record.get('status') == 'completed':
                # Get from appropriate table based on category
                category = record.get('category', 'food')

                if category == 'food':
                    food_result = db.query("app_food_entries_v2",
                                          filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                                          limit=1)
                    if food_result.get('success') and food_result.get('data', {}).get('records'):
                        response['result'] = food_result['data']['records'][0]

                elif category == 'receipt':
                    receipt_result = db.query("app_receipts",
                                             filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                                             limit=1)
                    if receipt_result.get('success') and receipt_result.get('data', {}).get('records'):
                        response['result'] = receipt_result['data']['records'][0]

            return respond(200, response)

        return respond(404, {"error": "Analysis not found"})

    except Exception as e:
        logger.error(f"Error getting analysis status: {e}")
        return respond(500, {"error": str(e)})


def process_async_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process async Lambda Event invocation
    This is called when Lambda invokes itself with InvocationType='Event'
    """
    entry_id = event.get('entry_id')
    user_id = event.get('user_id')
    description = event.get('description')
    image_url = event.get('image_url')
    
    logger.info(f"Processing async request", entry_id=entry_id, user_id=user_id)
    
    try:
        # Import and call the sync analyze handler
        from handlers.analyze import analyze_food
        
        # Create a mock HTTP event for the analyze handler
        http_event = {
            'body': json.dumps({
                'description': description,
                'image_url': image_url,
                'user_id': user_id
            }),
            'headers': {
                'x-user-id': user_id,
                'x-tenant-id': 'default'
            }
        }
        
        # Process the analysis
        result = analyze_food(http_event, context)
        
        # Update status in pending_analyses
        db = context.get('db')
        if db and result.get('statusCode') == 200:
            result_body = json.loads(result.get('body', '{}'))
            db.update("pending_analyses",
                     filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                     data={
                         "status": "completed",
                         "result": json.dumps(result_body),
                         "completed_at": datetime.utcnow().isoformat()
                     })
            logger.info(f"Async analysis completed", entry_id=entry_id)
        else:
            # Mark as failed
            if db:
                db.update("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         data={
                             "status": "failed",
                             "error": "Analysis failed",
                             "failed_at": datetime.utcnow().isoformat()
                         })
            logger.error(f"Async analysis failed", entry_id=entry_id)
        
        return {"statusCode": 200, "body": json.dumps({"success": True})}
        
    except Exception as e:
        logger.error(f"Error processing async request: {e}", entry_id=entry_id)
        # Try to update status to failed
        try:
            db = context.get('db')
            if db:
                db.update("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         data={
                             "status": "failed",
                             "error": str(e),
                             "failed_at": datetime.utcnow().isoformat()
                         })
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def process_queue_message(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for processing SQS messages
    This runs in a separate Lambda triggered by SQS
    """
    from lib.ai_async_service import AsyncAIService
    from lib.model_manager import get_model_manager

    db = context.get('db')
    model_manager = get_model_manager(db)
    ai_service = AsyncAIService(db)

    for record in event.get('Records', []):
        try:
            message = json.loads(record['body'])
            user_id = message['user_id']
            entry_id = message['entry_id']
            description = message.get('description')
            image_url = message.get('image_url')

            logger.info(f"Processing async analysis", entry_id=entry_id)

            # Process with AI
            result = ai_service._process_sync(user_id, description, image_url)

            if result.get('success'):
                category = result.get('category', 'unknown')

                # Store based on category
                if category == 'food':
                    _store_food_result(db, user_id, entry_id, result.get('data', {}))
                elif category == 'receipt':
                    _store_receipt_result(db, user_id, entry_id, result.get('data', {}), image_url)
                elif category == 'workout':
                    _store_workout_result(db, user_id, entry_id, result.get('data', {}))

                # Update status
                db.update("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         data={
                             "status": "completed",
                             "category": category,
                             "completed_at": datetime.utcnow().isoformat()
                         })

                # Send webhook if provided
                if message.get('callback_url'):
                    _send_webhook(message['callback_url'], entry_id, result)

            else:
                # Mark as failed
                db.update("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         data={
                             "status": "failed",
                             "error": result.get('error', 'Processing failed'),
                             "failed_at": datetime.utcnow().isoformat()
                         })

            logger.info(f"Completed async analysis", entry_id=entry_id, success=result.get('success'))

        except Exception as e:
            logger.error(f"Failed to process queue message: {e}")

    return {"statusCode": 200}


def _store_food_result(db, user_id: str, entry_id: str, data: Dict):
    """Store food analysis result"""
    food_items = data.get('food_items', [])
    total_calories = sum(item.get('calories', 0) for item in food_items)

    db.write("app_food_entries_v2", [{
        "id": entry_id,
        "user_id": user_id,
        "description": food_items[0].get('name', 'Food') if food_items else 'Food',
        "meal_type": data.get('meal_type', 'snack'),
        "calories": total_calories,
        "extracted_nutrients": json.dumps(data),
        "created_at": datetime.utcnow().isoformat()
    }])


def _store_receipt_result(db, user_id: str, entry_id: str, data: Dict, image_url: str):
    """Store receipt analysis result"""
    db.write("app_receipts", [{
        "id": entry_id,
        "user_id": user_id,
        "vendor": data.get('merchant_name', 'Unknown'),
        "receipt_date": data.get('purchase_date', datetime.utcnow().strftime('%Y-%m-%d')),
        "total_amount": data.get('total_amount', 0),
        "image_url": image_url or '',
        "created_at": datetime.utcnow().isoformat()
    }])

    # Store items
    items = data.get('items', [])
    if items:
        item_records = []
        for item in items:
            item_records.append({
                "id": str(uuid.uuid4()),
                "receipt_id": entry_id,
                "name": item.get('name', 'Item'),
                "price": item.get('price', 0),
                "quantity": item.get('quantity', 1),
                "created_at": datetime.utcnow().isoformat()
            })
        db.write("app_receipt_items", item_records)


def _store_workout_result(db, user_id: str, entry_id: str, data: Dict):
    """Store workout analysis result"""
    db.write("app_workouts", [{
        "id": entry_id,
        "user_id": user_id,
        "workout_type": data.get('workout_type', 'General'),
        "duration_minutes": data.get('duration_minutes', 0),
        "calories_burned": data.get('calories_burned_estimate', 0),
        "created_at": datetime.utcnow().isoformat()
    }])


def _send_webhook(callback_url: str, entry_id: str, result: Dict):
    """Send webhook notification"""
    import requests
    try:
        requests.post(callback_url, json={
            "entry_id": entry_id,
            "status": "completed",
            "result": result
        }, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")
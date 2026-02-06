import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.lib.auth_provider import get_user_id
from src.lib.logger import logger
from src.utils.http import respond
from src.config.settings import settings
from src.lib.ai_optimized import OptimizedAIService
import boto3

# Use OptimizedIbexClient if available
try:
    from src.lib.ibex_client_optimized import OptimizedIbexClient as IbexClient
except ImportError:
    from src.lib.ibex_client import IbexClient

def submit_analysis(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    POST /v1/analyze/async
    Submit analysis request (starts async Lambda execution)
    """
    try:
        user_id = get_user_id(event)
        if not user_id:
            return respond(401, {"error": "Unauthorized"})
            
        body = json.loads(event.get('body', '{}'))
        description = body.get('description')
        image_url = body.get('image_url')
        
        if not description and not image_url:
            return respond(400, {"error": "Description or image_url required"})
            
        entry_id = str(uuid.uuid4())
        
        # 1. Create pending record
        db = context.get('db')
        db.write("pending_analyses", [{
            "id": entry_id,
            "user_id": user_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }])
        
        # 2. Invoke Lambda asynchronously
        payload = {
            "source": "async-processing",
            "entry_id": entry_id,
            "user_id": user_id,
            "description": description,
            "image_url": image_url
        }
        
        lambda_client = boto3.client('lambda')
        # Use current function name or from env
        function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event', # Async
            Payload=json.dumps(payload)
        )
        
        return respond(202, {
            "entry_id": entry_id,
            "status": "pending",
            "message": "Analysis started"
        })

    except Exception as e:
        logger.error(f"Error submitting analysis: {e}")
        return respond(500, {"error": str(e)})


def get_analysis_status(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /v1/analyze/async/{id}
    Get status of async analysis
    """
    try:
        path_params = event.get('pathParameters', {})
        entry_id = path_params.get('id')
        
        if not entry_id:
            return respond(400, {"error": "Missing entry ID"})

        # Get user ID for security check
        user_id = get_user_id(event)
        if not user_id:
            return respond(401, {"error": "Unauthorized"})

        db = context.get('db')
        
        # Query pending_analyses table
        result = db.query("pending_analyses", 
                         filters=[
                             {"field": "id", "operator": "eq", "value": entry_id},
                             {"field": "user_id", "operator": "eq", "value": user_id}
                         ],
                         limit=1)
        
        if result.get('success') and result.get('data', {}).get('records'):
            record = result['data']['records'][0]
            status = record.get('status', 'pending')
            
            response = {
                "id": entry_id,
                "status": status,
                "created_at": record.get('created_at'),
                "updated_at": record.get('updated_at', record.get('created_at'))
            }
            
            # If completed or failed, add result/error
            if status == 'completed':
                # Fetch actual result based on category if not in analysis record
                category = record.get('category', 'food')
                response['category'] = category
                
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

            elif status == 'failed':
                response['error'] = record.get('error')

            return respond(200, response)
            
        return respond(404, {"error": "Analysis not found"})

    except Exception as e:
        logger.error(f"Error getting analysis status: {e}")
        return respond(500, {"error": str(e)})


def process_async_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle async processing via Lambda Event invocation
    Payload comes directly in event body (already parsed by Lambda if invocation type is Event)
    """
    try:
        # For Event invocation, the event IS the payload
        payload = event
        
        user_id = payload.get('user_id')
        entry_id = payload.get('entry_id')
        description = payload.get('description')
        image_url = payload.get('image_url')
        
        if not user_id or not entry_id:
            logger.error("Missing required fields in async event")
            return {"statusCode": 400, "body": "Missing user_id or entry_id"}

        logger.info("Starting async analysis", extra={'entry_id': entry_id, 'user_id': user_id})

        # Initialize services
        # Note: We create new instances because context might not be fully populated in async event
        from src.config.settings import settings
        db_config = settings.config.database
        db = IbexClient(
            api_url=db_config.api_url,
            api_key=db_config.api_key,
            tenant_id=db_config.tenant_id,
            namespace=db_config.namespace
        )
        
        # Enable Direct Lambda invocation to avoid 403 errors
        lambda_name = os.environ.get('IBEX_LAMBDA_NAME') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME')
        if hasattr(db, 'enable_direct_lambda') and lambda_name:
            db.enable_direct_lambda(lambda_name)
            logger.info(f"Direct Lambda invocation enabled for async processing: {lambda_name}")
        ai_service = OptimizedAIService(db)

        # Process with AI
        result = ai_service.process_request(
            user_id=user_id,
            description=description,
            image_url=image_url
        )

        if result.get('success'):
            category = result.get('category', 'food')
            data = result.get('data', {})
            
            # Store result based on category
            if category == 'food':
                _store_food_result(db, user_id, entry_id, data)
            elif category == 'receipt':
                _store_receipt_result(db, user_id, entry_id, data, image_url)
            
            # Update pending_analyses status
            db.update("pending_analyses",
                     filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                     updates={
                         "status": "completed",
                         "category": category,
                         "completed_at": datetime.utcnow().isoformat()
                     })
            
            logger.info("Async analysis completed successfully", extra={'entry_id': entry_id})
        else:
            error_msg = result.get('error', 'Unknown error')
            db.update("pending_analyses",
                     filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                     updates={
                         "status": "failed",
                         "error": error_msg,
                         "failed_at": datetime.utcnow().isoformat()
                     })
            logger.error("Async analysis failed", extra={'entry_id': entry_id, 'error': error_msg})

        return {"statusCode": 200, "body": json.dumps({"success": True})}

    except Exception as e:
        logger.error(f"Critical error in process_async_request: {e}", exc_info=True)
        # Try to mark as failed if DB available
        try:
             if 'db' in locals():
                db.update("pending_analyses",
                         filters=[{"field": "id", "operator": "eq", "value": entry_id}],
                         updates={
                             "status": "failed",
                             "error": str(e),
                             "failed_at": datetime.utcnow().isoformat()
                         })
        except:
            pass
        return {"statusCode": 500, "body": str(e)}


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
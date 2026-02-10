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

        # Log tenant info for debugging
        tenant_info = context.get('tenant', {})
        current_tenant_id = tenant_info.get('tenant_id', 'nutriwealth')
        current_namespace = tenant_info.get('namespace', 'default')
        logger.info(f"Creating pending record with tenant_id={current_tenant_id}, namespace={current_namespace}")

        db.write("app_pending_analyses", [{
            "id": entry_id,
            "user_id": user_id,
            "status": "pending",
            "description": description,
            "image_url": image_url,
            "category": "food",  # Default to food category
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }])
        
        # 2. Send to SQS queue (instead of Lambda.invoke)
        sqs = boto3.client('sqs')
        # Use full URL for SQS (not just queue name)
        queue_url = os.environ.get('ANALYSIS_QUEUE_URL',
                                   'https://sqs.ap-south-1.amazonaws.com/808527335982/nutriwealth-analysis-queue')

        message = {
            "source": "sqs-processing",
            "entry_id": entry_id,
            "user_id": user_id,
            "description": description,
            "image_url": image_url,
            # Add IBEX credentials to ensure async processor can access DB
            # CRITICAL: Must use EXACT same tenant_id as the db.write above!
            "ibex_config": {
                "api_url": os.environ.get('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb'),
                "api_key": os.environ.get('IBEX_API_KEY'),
                "tenant_id": current_tenant_id,  # Use same tenant_id as the WRITE
                "namespace": current_namespace     # Use same namespace as the WRITE
            }
        }

        # Add tenant context if available
        tenant = context.get('tenant')
        if tenant:
            message['tenant_id'] = tenant.get('tenant_id')
            message['namespace'] = tenant.get('namespace')

        # Send message to SQS
        sqs_response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
            MessageAttributes={
                'user_id': {'StringValue': user_id, 'DataType': 'String'},
                'entry_id': {'StringValue': entry_id, 'DataType': 'String'}
            }
        )

        logger.info(f"Message sent to SQS: {sqs_response['MessageId']} for entry {entry_id}")

        return respond(202, {
            "entry_id": entry_id,
            "status": "pending",
            "message": "Analysis queued",
            "sqs_message_id": sqs_response['MessageId']
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
        entry_id = path_params.get('entry_id') or path_params.get('id')
        
        if not entry_id:
            return respond(400, {"error": "Missing entry ID"})

        # Get user ID for security check
        user_id = get_user_id(event)
        if not user_id:
            return respond(401, {"error": "Unauthorized"})

        db = context.get('db')
        
        # Query pending_analyses table with retry logic for cache consistency
        # IMPORTANT: use_cache=False to get latest data after UPDATE operations
        logger.info(f"Checking status for entry_id: {entry_id}, user_id: {user_id}")

        # Try up to 3 times with small delay to handle cache lag
        record = None
        for attempt in range(3):
            result = db.query("app_pending_analyses",
                             filters=[
                                 {"field": "id", "operator": "eq", "value": entry_id},
                                 {"field": "user_id", "operator": "eq", "value": user_id}
                             ],
                             limit=1,
                             use_cache=False,  # Critical: Bypass cache to get latest version
                             include_deleted=False)

            if result.get('success') and result.get('data', {}).get('records'):
                temp_record = result['data']['records'][0]
                # If we get a newer version or completed status, use it
                if not record or temp_record.get('_version', 0) > record.get('_version', 0) or temp_record.get('status') == 'completed':
                    record = temp_record
                    if record.get('status') == 'completed':
                        break

            # Small delay between attempts to allow cache to refresh
            if attempt < 2:
                import time
                time.sleep(0.5)

        logger.info(f"Query result - found: {bool(record)}, status: {record.get('status') if record else 'N/A'}")

        if record:
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


def process_sqs_messages(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process messages from SQS queue
    This is triggered by SQS event source mapping
    """
    try:
        # SQS sends batch of messages in Records
        for record in event.get('Records', []):
            # Each record contains the message body
            message_body = record.get('body')
            if not message_body:
                logger.error("Empty SQS message")
                continue

            # Parse the message
            try:
                payload = json.loads(message_body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in SQS message: {e}")
                continue

            # Process the message
            result = process_async_request(payload, context)

            # If processing fails, raise exception to trigger retry
            if not result or result.get('statusCode') != 200:
                raise Exception(f"Processing failed for entry {payload.get('entry_id')}")

        return {"statusCode": 200, "body": json.dumps({"success": True})}

    except Exception as e:
        logger.error(f"Error processing SQS messages: {e}")
        # Raise to trigger SQS retry
        raise


def process_async_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle async processing (from SQS or direct invocation)
    Processes the analysis request asynchronously
    """
    try:
        # The event is now the parsed message payload
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

        # Get IBEX config from payload (passed from submit_analysis)
        ibex_config = payload.get('ibex_config', {})

        # Use credentials from payload, fallback to environment/settings
        api_url = ibex_config.get('api_url') or os.environ.get('IBEX_API_URL') or db_config.api_url
        api_key = ibex_config.get('api_key') or os.environ.get('IBEX_API_KEY') or db_config.api_key
        final_tenant_id = ibex_config.get('tenant_id') or payload.get('tenant_id') or db_config.tenant_id
        final_namespace = ibex_config.get('namespace') or payload.get('namespace') or db_config.namespace

        db = IbexClient(
            api_url=api_url,
            api_key=api_key,
            tenant_id=final_tenant_id,
            namespace=final_namespace
        )

        logger.info(f"Async processor using IBEX at {api_url} with tenant={final_tenant_id}, namespace={final_namespace}")
        logger.info(f"Processing entry_id={entry_id} for user_id={user_id}")
        
        # Enable Direct Lambda invocation to avoid 403 errors
        lambda_name = os.environ.get('IBEX_LAMBDA_NAME') or 'ibex-db-lambda'
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
                _store_food_result(db, user_id, entry_id, data, image_url)
            elif category == 'receipt':
                _store_receipt_result(db, user_id, entry_id, data, image_url)
            
            # Update pending_analyses status
            logger.info(f"Updating status for entry_id={entry_id}, user_id={user_id}")
            logger.info(f"Using tenant={final_tenant_id}, namespace={final_namespace}")

            # First, verify the record exists before updating
            check_result = db.query("app_pending_analyses",
                                   filters=[
                                       {"field": "id", "operator": "eq", "value": entry_id},
                                       {"field": "user_id", "operator": "eq", "value": user_id}
                                   ],
                                   limit=1)

            if check_result.get('success') and check_result.get('data', {}).get('records'):
                existing_record = check_result['data']['records'][0]
                logger.info(f"Found pending record to update: {existing_record}")

                # Use UPDATE - now fixed in IBEX and working properly!
                # UPDATE creates proper version records and maintains data integrity
                logger.info(f"Updating status using UPDATE for entry {entry_id}")

                update_result = db.update("app_pending_analyses",
                                        filters=[
                                            {"field": "id", "operator": "eq", "value": entry_id},
                                            {"field": "user_id", "operator": "eq", "value": user_id}
                                        ],
                                        updates={
                                            "status": "completed",
                                            "category": category,
                                            "completed_at": datetime.utcnow().isoformat(),
                                            "updated_at": datetime.utcnow().isoformat()
                                        })

                if update_result.get('success'):
                    logger.info(f"Status updated to completed for entry {entry_id}")
                else:
                    logger.error(f"Failed to update status for {entry_id}: {update_result.get('error')}")

            else:
                logger.error(f"Could not find pending record for entry_id={entry_id}, user_id={user_id}")
                logger.error(f"Query result: {json.dumps(check_result)}")
            
            logger.info("Async analysis completed successfully", extra={'entry_id': entry_id})
        else:
            error_msg = result.get('error', 'Unknown error')
            # Update status to failed
            db.update("app_pending_analyses",
                     filters=[
                         {"field": "id", "operator": "eq", "value": entry_id},
                         {"field": "user_id", "operator": "eq", "value": user_id}
                     ],
                     updates={
                         "status": "failed",
                         "error": error_msg,
                         "failed_at": datetime.utcnow().isoformat(),
                         "updated_at": datetime.utcnow().isoformat()
                     })
            logger.error("Async analysis failed", extra={'entry_id': entry_id, 'error': error_msg})

        return {"statusCode": 200, "body": json.dumps({"success": True})}

    except Exception as e:
        logger.error(f"Critical error in process_async_request: {e}", exc_info=True)
        # Try to mark as failed if DB available
        try:
            if 'db' in locals() and 'entry_id' in locals():
                # Use single filter for UPDATE (IBEX limitation)
                db.update("app_pending_analyses",
                         filters=[
                             {"field": "id", "operator": "eq", "value": entry_id}
                         ],
                         updates={
                             "status": "failed",
                             "error": str(e),
                             "failed_at": datetime.utcnow().isoformat()
                         })
        except:
            pass
        return {"statusCode": 500, "body": str(e)}


def _store_food_result(db, user_id: str, entry_id: str, data: Dict, image_url: str):
    """Store food analysis result"""
    food_items = data.get('food_items', [])
    total_calories = sum(item.get('calories', 0) for item in food_items)

    db.write("app_food_entries_v2", [{
        "id": entry_id,
        "user_id": user_id,
        "description": food_items[0].get('name', 'Food') if food_items else 'Food',
        "meal_type": data.get('meal_type', 'snack'),
        "calories": total_calories,
        "image_url": image_url or '',
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
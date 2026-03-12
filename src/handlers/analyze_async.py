import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.lib.auth_provider import get_user_id, require_auth
from ajna_cloud import logger, respond
from src.lib.ai_optimized import OptimizedAIService
import boto3

@require_auth
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
            "category": "unknown",  # Will be determined by AI classification
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }])
        
        # 2. Send to SQS queue - DO NOT send image data, only references
        sqs = boto3.client('sqs')
        # Use full URL for SQS (not just queue name)
        queue_url = os.environ.get('ANALYSIS_QUEUE_URL',
                                   'https://sqs.ap-south-1.amazonaws.com/808527335982/nutriwealth-analysis-queue')

        # SQS message: only identifiers needed.
        # Image URL and description are in app_pending_analyses record.
        # Tenant context is resolved by app_optimized.py when processing SQS messages.
        message = {
            "source": "sqs-processing",
            "entry_id": entry_id,
            "user_id": user_id,
            "tenant_id": current_tenant_id,
            "namespace": current_namespace
        }

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


@require_auth
def get_analysis_status(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /v1/analyze/status/{entry_id}
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

        # Validate UUIDs to prevent SQL injection in execute_sql
        try:
            uuid.UUID(entry_id)
            uuid.UUID(user_id)
        except ValueError:
            return respond(400, {"error": "Invalid ID format"})

        logger.info(f"Checking status for entry_id: {entry_id}, user_id: {user_id}")

        # Use execute_sql for consistent reads — db.query() uses cached Parquet metadata
        # which misses recently written data. execute_sql goes through DuckDB's Iceberg
        # extension which reads all data files including new ones.
        # IbexDB updates create new version rows (append-only), so ORDER BY updated_at DESC
        # and LIMIT 1 gets the latest version.
        sql = (
            "SELECT id, user_id, status, category, error, created_at, updated_at "
            "FROM app_pending_analyses "
            f"WHERE id = '{entry_id}' AND user_id = '{user_id}' "
            "ORDER BY updated_at DESC LIMIT 1"
        )
        result = db.execute_sql(sql)

        if not result.get('success') or not result.get('data', {}).get('records'):
            return respond(404, {"error": "Analysis not found"})

        record = result['data']['records'][0]
        status = record.get('status', 'pending')

        response = {
            "id": entry_id,
            "status": status,
            "created_at": record.get('created_at'),
            "updated_at": record.get('updated_at', record.get('created_at'))
        }

        if status == 'completed':
            category = record.get('category', 'food')
            response['category'] = category

            # Fetch result data using execute_sql for consistency
            if category == 'food':
                food_sql = f"SELECT * FROM app_food_entries_v2 WHERE id = '{entry_id}' LIMIT 1"
                food_result = db.execute_sql(food_sql)
                if food_result.get('success') and food_result.get('data', {}).get('records'):
                    response['result'] = food_result['data']['records'][0]
            elif category == 'receipt':
                receipt_sql = f"SELECT * FROM app_receipts WHERE id = '{entry_id}' LIMIT 1"
                receipt_result = db.execute_sql(receipt_sql)
                if receipt_result.get('success') and receipt_result.get('data', {}).get('records'):
                    response['result'] = receipt_result['data']['records'][0]
            elif category == 'workout':
                workout_sql = f"SELECT * FROM app_workouts WHERE id = '{entry_id}' LIMIT 1"
                workout_result = db.execute_sql(workout_sql)
                if workout_result.get('success') and workout_result.get('data', {}).get('records'):
                    response['result'] = workout_result['data']['records'][0]

        elif status == 'failed':
            response['error'] = record.get('error')

        logger.info(f"Query result - status: {status}")
        return respond(200, response)

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

        if not user_id or not entry_id:
            logger.error("Missing required fields in async event")
            return {"statusCode": 400, "body": "Missing user_id or entry_id"}

        logger.info("Starting async analysis", extra={'entry_id': entry_id, 'user_id': user_id})

        # Get db from context — app_optimized.py sets this up with correct tenant for SQS path
        ctx = context if isinstance(context, dict) else {}
        db = ctx.get('db')
        if not db:
            raise RuntimeError("No database client in context. SQS handler must provide context['db'].")

        tenant_info = ctx.get('tenant', {})
        logger.info(f"Async processor using tenant={tenant_info.get('tenant_id')}, namespace={tenant_info.get('namespace')}")

        # Retrieve the full record from pending_analyses to get image_url and description
        logger.info(f"Retrieving pending analysis record for entry_id={entry_id}")

        result = db.query("app_pending_analyses",
                         filters=[
                             {"field": "id", "operator": "eq", "value": entry_id},
                             {"field": "user_id", "operator": "eq", "value": user_id}
                         ],
                         limit=1,
                         use_cache=False)  # Don't use cache to get latest data

        if not result.get('success') or not result.get('data', {}).get('records'):
            logger.error(f"Pending analysis record not found for entry_id={entry_id}")
            return {"statusCode": 404, "body": "Analysis record not found"}

        pending_record = result['data']['records'][0]
        description = pending_record.get('description')
        image_url = pending_record.get('image_url')

        logger.info(f"Processing entry_id={entry_id} for user_id={user_id}")
        logger.info(f"Description: {description[:50] if description else 'None'}...")
        logger.info(f"Has image: {bool(image_url)}")

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
            
            # Store result based on category with error handling
            storage_success = False
            try:
                if category == 'food':
                    storage_success = _store_food_result(db, user_id, entry_id, data, image_url, description)
                elif category == 'receipt':
                    storage_success = _store_receipt_result(db, user_id, entry_id, data, image_url)
                elif category == 'workout':
                    storage_success = _store_workout_result(db, user_id, entry_id, data, image_url)

                if not storage_success:
                    raise Exception(f"Failed to store {category} result for entry {entry_id}")

            except Exception as storage_error:
                logger.error(f"Failed to store analysis result for {entry_id}: {str(storage_error)}")
                # Update status to error
                db.update("app_pending_analyses",
                         filters=[
                             {"field": "id", "operator": "eq", "value": entry_id},
                             {"field": "user_id", "operator": "eq", "value": user_id}
                         ],
                         updates={
                             "status": "storage_failed",
                             "error": f"Storage failed: {str(storage_error)}",
                             "category": category,
                             "failed_at": datetime.utcnow().isoformat(),
                             "updated_at": datetime.utcnow().isoformat()
                         })
                # Don't continue to mark as completed if storage failed
                return {"statusCode": 500, "body": json.dumps({"success": False, "error": f"Storage failed: {str(storage_error)}"})}

            # Update pending_analyses status to completed
            logger.info(f"Updating status to completed for entry_id={entry_id}")
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


def _store_food_result(db, user_id: str, entry_id: str, data: Dict, image_url: str, description: Optional[str] = None):
    """Store food analysis result with proper error handling"""
    try:
        food_items = data.get('food_items', [])

        logger.info(f"Storing food result for entry {entry_id}, user {user_id}")
        logger.info(f"Food items to store: {json.dumps(food_items)}")

        # Calculate totals from food_items
        total_calories = 0
        total_protein = 0
        total_carbohydrates = 0
        total_fats = 0
        total_fiber = 0
        total_sodium = 0

        for item in food_items:
            quantity = item.get('quantity', 1)
            total_calories += (item.get('calories', 0) * quantity)
            # Check both singular and plural field names
            total_protein += (item.get('protein', item.get('proteins', 0)) * quantity)
            total_carbohydrates += (item.get('carbs', item.get('carbohydrates', 0)) * quantity)
            total_fats += (item.get('fat', item.get('fats', 0)) * quantity)
            total_fiber += (item.get('fiber', 0) * quantity)
            total_sodium += (item.get('sodium', 0) * quantity)

        # Use the original description if available, otherwise construct from food items
        if description:
            final_description = description
        else:
            # Fallback: create description from food items
            if food_items:
                food_names = [item.get('name', 'Food') for item in food_items[:3]]  # First 3 items
                final_description = ', '.join(food_names)
            else:
                final_description = 'Food'

        # Prepare the food entry record
        food_entry = {
            "id": entry_id,
            "user_id": user_id,
            "description": final_description,
            "meal_type": data.get('meal_type', 'snack'),
            "calories": total_calories,
            "total_protein": total_protein,
            "total_carbohydrates": total_carbohydrates,
            "total_fats": total_fats,
            "total_fiber": total_fiber,
            "total_sodium": total_sodium,
            "image_url": image_url or '',
            "extracted_nutrients": json.dumps(data),
            "analysis_status": "completed",  # Mark as completed
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Attempting to write food entry: {json.dumps(food_entry)}")

        # Write to database with error handling
        result = db.write("app_food_entries_v2", [food_entry])

        if result.get('success'):
            logger.info(f"✅ Successfully stored food entry {entry_id} for user {user_id}")

            # Store individual food items in app_food_items table
            if food_items:
                item_records = []
                for item in food_items:
                    item_records.append({
                        'id': str(uuid.uuid4()),
                        'food_entry_id': entry_id,
                        'name': item.get('name', 'Unknown'),
                        'serving_size': item.get('serving_size', ''),
                        'calories': item.get('calories', 0),
                        'proteins': item.get('protein', item.get('proteins', 0)),
                        'carbohydrates': item.get('carbs', item.get('carbohydrates', 0)),
                        'fats': item.get('fat', item.get('fats', 0)),
                        'fiber': item.get('fiber', 0),
                        'sodium': item.get('sodium', 0),
                        'created_at': datetime.utcnow().isoformat()
                    })
                items_write = db.write('app_food_items', item_records)
                if items_write.get('success'):
                    logger.info(f"✅ Stored {len(item_records)} food items for entry {entry_id}")
                else:
                    logger.error(f"Failed to store food items for {entry_id}: {items_write.get('error')}")

            return True
        else:
            error_msg = result.get('error', 'Unknown error during write')
            logger.error(f"Failed to store food entry {entry_id}: {error_msg}")
            raise Exception(f"Failed to store food entry: {error_msg}")

    except Exception as e:
        logger.error(f"❌ Critical error in _store_food_result for entry {entry_id}: {str(e)}", exc_info=True)

        # Log full details for debugging
        logger.error(f"Failed entry details - user_id: {user_id}, data: {json.dumps(data)}")

        # Don't let this fail silently - raise the error
        raise


def _store_receipt_result(db, user_id: str, entry_id: str, data: Dict, image_url: str) -> bool:
    """Store comprehensive receipt analysis result. Returns True on success."""
    try:
        # Extract financial summary
        financial = data.get('financial_summary', {})

        # Extract location info
        location = data.get('store_location', {})

        # Extract payment info
        payment = data.get('payment', {})

        # Store main receipt record with all available fields
        receipt_record = {
            "id": entry_id,
            "user_id": user_id,
            "vendor": data.get('merchant_name', 'Unknown'),
            "store_address": data.get('store_address', ''),
            "city": location.get('city', ''),
            "state": location.get('state', ''),
            "postal_code": location.get('postal_code', ''),
            "country": location.get('country', 'USA'),
            "receipt_date": data.get('purchase_date', datetime.utcnow().strftime('%Y-%m-%d')),
            "receipt_time": data.get('purchase_time', ''),
            "purchase_channel": data.get('receipt_category', 'Retail'),
            "total_amount": financial.get('total_amount', data.get('total_amount', 0)),
            "subtotal": financial.get('subtotal', 0),
            "tax_amount": financial.get('tax_amount', data.get('tax_amount', 0)),
            "discount_amount": financial.get('discount_amount', 0),
            "currency": financial.get('currency', 'USD'),
            "payment_method": payment.get('method', ''),
            "card_last_digits": payment.get('card_last_digits', ''),
            "transaction_id": payment.get('transaction_id', ''),
            "receipt_id": data.get('receipt_number', ''),
            "image_url": image_url or '',
            "notes": data.get('notes', ''),
            "tags": data.get('receipt_category', ''),
            # Store full items data as JSON for reference
            "items": json.dumps(data.get('items', [])),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        result = db.write("app_receipts", [receipt_record])
        if not result.get('success'):
            raise Exception(f"Failed to write receipt: {result.get('error')}")

        # Store detailed items in separate table
        items = data.get('items', [])
        if items:
            item_records = []
            for idx, item in enumerate(items):
                item_record = {
                    "id": str(uuid.uuid4()),
                    "receipt_id": entry_id,
                    "name": item.get('name', f'Item {idx+1}'),
                    "sku": item.get('sku', ''),
                    "quantity": item.get('quantity', 1),
                    "unit_price": item.get('unit_price', item.get('price', 0)),
                    "total_price": item.get('total_price',
                                  item.get('quantity', 1) * item.get('unit_price', item.get('price', 0))),
                    "discount": item.get('discount', 0),
                    "category": item.get('category', 'Other'),
                    "department": item.get('department', ''),
                    "is_taxable": item.get('is_taxable', True),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                item_records.append(item_record)

            if item_records:
                items_result = db.write("app_receipt_items", item_records)
                if not items_result.get('success'):
                    logger.error(f"Failed to write receipt items for {entry_id}: {items_result.get('error')}")

                # Generate embeddings for receipt items (for semantic shopping search)
                try:
                    from lib.embeddings import get_embeddings_batch, zvec_insert_items
                    item_texts = [f"{item.get('name', '')} {item.get('category', '')}".strip() for item in items]
                    embeddings = get_embeddings_batch(item_texts)

                    embedding_records = []
                    zvec_items = []
                    for item_rec, emb in zip(item_records, embeddings):
                        embedding_records.append({
                            'id': str(uuid.uuid4()),
                            'receipt_item_id': item_rec['id'],
                            'item_name': item_rec['name'],
                            'category': item_rec.get('category', ''),
                            'unit_price': item_rec.get('unit_price', item_rec.get('total_price', 0)),
                            'store_name': data.get('merchant_name', 'Unknown'),
                            'embedding': json.dumps(emb),
                            'embedding_model': 'text-embedding-3-small',
                            'created_at': datetime.utcnow().isoformat()
                        })
                        zvec_items.append({
                            'receipt_item_id': item_rec['id'],
                            'item_name': item_rec['name'],
                            'category': item_rec.get('category', ''),
                            'unit_price': item_rec.get('unit_price', item_rec.get('total_price', 0)),
                            'store_name': data.get('merchant_name', 'Unknown'),
                            'embedding': emb,
                        })
                    if embedding_records:
                        db.write('app_receipt_item_embeddings', embedding_records)
                        zvec_insert_items(zvec_items)
                        logger.info(f"Receipt item embeddings stored for {entry_id}: {len(embedding_records)} items")
                except Exception as e:
                    logger.error(f"Failed to generate receipt item embeddings: {e}")

        logger.info(f"Stored receipt {entry_id} with {len(items)} items for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store receipt {entry_id}: {str(e)}", exc_info=True)
        raise


def _store_workout_result(db, user_id: str, entry_id: str, data: Dict, image_url: str) -> bool:
    """Store workout analysis result. Returns True on success."""
    try:
        workout_type = data.get('workout_type', 'General')
        duration = float(data.get('duration_minutes') or data.get('duration') or 0)
        calories = float(data.get('calories_burned') or data.get('calories_burned_estimate') or data.get('estimated_calories') or 0)

        workout_record = {
            'id': entry_id,
            'user_id': user_id,
            'workout_type': workout_type,
            'duration': duration,
            'calories_burned': calories,
            'workout_date': data.get('workout_date') or datetime.utcnow().strftime('%Y-%m-%d'),
            'intensity_level': data.get('intensity_level', ''),
            'muscle_groups': data.get('muscle_groups', ''),
            'description': data.get('notes') or data.get('description') or '',
            'notes': data.get('notes', ''),
            'image_url': image_url or '',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        result = db.write('app_workouts', [workout_record])
        if not result.get('success'):
            raise Exception(f"Failed to write workout: {result.get('error')}")

        # Store individual exercises
        exercises = data.get('exercises', [])
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
                    'duration_minutes': float(ex.get('duration_seconds', 0) or 0) / 60.0 if ex.get('duration_seconds') else float(ex.get('duration_minutes', 0) or 0),
                    'calories_burned': ex.get('calories_burned', 0),
                    'created_at': datetime.utcnow().isoformat()
                })
            ex_result = db.write('app_workout_exercises', ex_records)
            if ex_result.get('success'):
                logger.info(f"Stored {len(ex_records)} exercises for workout {entry_id}")
            else:
                logger.error(f"Failed to store exercises for {entry_id}: {ex_result.get('error')}")

        logger.info(f"Stored workout {entry_id}: {workout_type}, {duration}min, {calories}cal for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store workout {entry_id}: {str(e)}", exc_info=True)
        raise
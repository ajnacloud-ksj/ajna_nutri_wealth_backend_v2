import json
import uuid
import os
import base64
import boto3
from datetime import datetime
from utils.http import respond, get_user_id
from lib.logger import logger

# Import table name resolution from data handler
from .data import resolve_table_name

def get_upload_url_endpoint(event, context):
    """POST /storage/upload-url - Get a presigned upload URL for direct binary upload"""
    try:
        # Get user ID from the request
        user_id = get_user_id(event)
        if not user_id:
            return respond(401, {"error": "Unauthorized"})

        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except:
            return respond(400, {"error": "Invalid JSON"})

        filename = body.get('filename') or f"{uuid.uuid4()}.jpg"
        content_type = body.get('content_type', 'image/jpeg')

        # Generate unique S3 key
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        key = f"uploads/{user_id}/{timestamp}_{unique_id}_{filename}"

        # Configure S3 client
        s3 = boto3.client('s3', region_name=os.environ.get('AWS_REGION', 'ap-south-1'))
        bucket = os.environ.get('S3_BUCKET', 'nutriwealth-uploads')

        # Generate presigned URL for PUT operation
        url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket,
                'Key': key,
                'ContentType': content_type
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )

        logger.info(f"Generated upload URL for user {user_id}, key: {key}")

        return respond(200, {
            "success": True,
            "upload_url": url,
            "key": key,
            "bucket": bucket,
            "expires_in": 3600,
            "instructions": "Send a PUT request to 'upload_url' with the binary file data and Content-Type header."
        })

    except Exception as e:
        logger.error(f"Error generating upload URL: {e}")
        return respond(500, {"error": str(e)})


def upload_file(event, context):
    """POST /storage/upload - Upload a file to storage"""
    db = context['db']

    try:
        body = json.loads(event.get('body', '{}'))
    except:
        return respond(400, {"error": "Invalid JSON"})

    bucket = body.get('bucket', 'uploads')
    path = body.get('path') or f"{uuid.uuid4()}.jpg"
    file_data = body.get('file')  # base64 encoded data
    mime_type = body.get('mime_type', 'image/jpeg')
    size_bytes = body.get('size_bytes', 0)

    if not file_data:
        return respond(400, {"error": "Missing file data"})

    try:
        # Always use real S3 via IbexClient - no mocking
        result = db.upload_file(file_data, path, mime_type)

        if not result['success']:
            return respond(500, {"error": f"Upload failed: {result.get('error')}"}, event=event)

        s3_key = result['key']
        s3_url = result['url']

        # Get user_id from event headers (helpers)
        from utils.http import get_user_id
        user_id = get_user_id(event) or "anonymous"

        # Store in database
        record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "bucket": result['bucket'],
            "file_path": path,     # Original path/filename intent
            "s3_key": s3_key,      # Actual object key
            "s3_url": s3_url,      # s3:// url
            "data": "",            # Legacy field (required by schema currently?)
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "storage_type": "ibex_s3",
            "created_at": datetime.utcnow().isoformat()
        }

        # write to 'images' table with proper table name resolution
        db_table_name = resolve_table_name("images")  # Use the resolver for consistency
        db_result = db.write(db_table_name, [record])

        if db_result.get('success'):
            return respond(200, {
                "success": True,
                "path": path,
                "url": s3_url,
                "s3_key": s3_key
            })
        else:
            return respond(500, {"error": "Failed to store file metadata"})

    except Exception as e:
        print(f"Upload handler error: {e}")
        return respond(500, {"error": str(e)})

def get_file(event, context):
    """GET /v1/storage/{path+}"""
    db = context['db']
    # 'path' parameter contains the file path
    path_param = event['pathParameters'].get('path')
    
    if not path_param:
        return respond(400, {"error": "Missing path"})
        
    try:
        filters = [{"field": "file_path", "operator": "eq", "value": path_param}]
        # Also check s3_key if passed? logic might need adjustment if path_param is s3 key. 
        # For now assume path_param matches what we stored in 'file_path'.
        
        # Use correct table name with resolution
        db_table_name = resolve_table_name("images")
        result = db.query(db_table_name, filters=filters, limit=1)
        
        items = result.get('data', [])
        if not items:
            return respond(404, {"error": "File not found"})
            
        record = items[0]
        
        # Check if stored in S3 (or ibex_s3)
        if record.get('storage_type') in ['s3', 'ibex_s3']:
             s3_key = record.get('s3_key')
             if not s3_key:
                 return respond(500, {"error": "S3 key missing"})
                 
             # Use IbexClient to get download URL
             res = db.get_download_url(s3_key)
             url = res.get('data', {}).get('download_url')
             
             if url:
                 return {
                    "statusCode": 302,
                    "headers": {
                        "Location": url
                    },
                    "body": ""
                 }
             else:
                 return respond(500, {"error": "Failed to generate URL"})
        
        # Fallback to old base64 behavior
        data = record.get('data')
        
        if not data:
            return respond(404, {"error": "Content empty"})
            
        return respond(200, data, is_base64=True)
    except Exception as e:
        return respond(500, {"error": str(e)}, event=event)

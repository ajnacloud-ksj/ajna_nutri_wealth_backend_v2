"""
Receipt handlers - Fetch receipts with joined items
"""

import json
from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger


@require_auth
def get_receipt_with_items(event, context):
    """
    GET /v1/receipts/:id - Get receipt with all items
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    receipt_id = event.get('pathParameters', {}).get('id')

    if not receipt_id:
        return respond(400, {"error": "Receipt ID required"})

    try:
        # Fetch receipt
        receipt_result = db.query("app_receipts", filters=[
            {"field": "id", "operator": "eq", "value": receipt_id},
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], limit=1, include_deleted=False)

        if not receipt_result.get('success'):
            return respond(500, {"error": "Failed to fetch receipt"})

        receipts = receipt_result.get('data', {}).get('records', [])
        if not receipts:
            return respond(404, {"error": "Receipt not found"})

        receipt = receipts[0]

        # Transform image URL
        receipt = _transform_receipt_image(db, receipt)

        # Fetch items
        items_result = db.query("app_receipt_items", filters=[
            {"field": "receipt_id", "operator": "eq", "value": receipt_id}
        ], limit=100, include_deleted=False)

        items = []
        if items_result.get('success'):
            items = items_result.get('data', {}).get('records', [])

        # Attach items to receipt
        receipt['items'] = items

        return respond(200, receipt)
        
    except Exception as e:
        logger.error(f"Error fetching receipt: {e}")
        return respond(500, {"error": str(e)})


def _transform_receipt_image(db, receipt):
    """
    Transform receipt image URL - convert S3 keys to presigned URLs,
    and skip base64 data to reduce payload size.
    Handles: uploads/ keys, s3:// URLs, http(s) URLs, base64 data.
    """
    image_url = receipt.get('image_url', '')

    if image_url:
        if image_url.startswith('data:'):
            # Base64 data - don't send to reduce payload
            receipt['image_url'] = ''
            receipt['image_format'] = 'base64_omitted'
            receipt['has_image'] = True
        elif image_url.startswith('uploads/'):
            # IbexDB-managed S3 key - resolve via db.get_download_url()
            try:
                res = db.get_download_url(image_url, expiry_seconds=3600)
                if res.get('success'):
                    presigned_url = res.get('data', {}).get('download_url')
                    if presigned_url:
                        receipt['image_url'] = presigned_url
                        receipt['image_format'] = 's3_presigned'
                        receipt['has_image'] = True
                        return receipt
                receipt['image_url'] = ''
                receipt['has_image'] = True
            except Exception as e:
                logger.error(f"Error generating presigned URL: {e}")
                receipt['image_url'] = ''
                receipt['has_image'] = True
        elif image_url.startswith('s3://'):
            # Legacy s3:// URL format
            try:
                s3_key = image_url.replace('s3://', '').split('/', 1)[1] if '/' in image_url else image_url.replace('s3://', '')
                res = db.get_download_url(s3_key, expiry_seconds=3600)
                if res.get('success'):
                    presigned_url = res.get('data', {}).get('download_url')
                    if presigned_url:
                        receipt['image_url'] = presigned_url
                        receipt['image_format'] = 's3_presigned'
                        receipt['has_image'] = True
                        return receipt
                receipt['image_url'] = ''
                receipt['has_image'] = True
            except Exception as e:
                logger.error(f"Error generating presigned URL: {e}")
                receipt['image_url'] = ''
                receipt['has_image'] = True
        elif image_url.startswith('http://') or image_url.startswith('https://'):
            receipt['image_format'] = 'public_url'
            receipt['has_image'] = True
    else:
        receipt['has_image'] = False

    return receipt


@require_auth
def list_receipts(event, context):
    """
    GET /v1/receipts - List all receipts for user
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        result = db.query("app_receipts", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], sort=[{"field": "created_at", "order": "desc"}], limit=50, include_deleted=False)

        if result.get('success'):
            receipts = result.get('data', {}).get('records', [])

            # Transform each receipt to use presigned URLs and skip base64
            transformed_receipts = []
            for receipt in receipts:
                receipt = _transform_receipt_image(db, receipt)
                transformed_receipts.append(receipt)

            return respond(200, {"receipts": transformed_receipts, "total": len(transformed_receipts)})
        else:
            return respond(500, {"error": "Failed to fetch receipts"})

    except Exception as e:
        logger.error(f"Error listing receipts: {e}")
        return respond(500, {"error": str(e)})

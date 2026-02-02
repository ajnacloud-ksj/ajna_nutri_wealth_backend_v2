"""
Receipt handlers - Fetch receipts with joined items
"""

import json
from utils.http import respond, get_user_id

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
        ], limit=1)

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
        ], limit=100)

        items = []
        if items_result.get('success'):
            items = items_result.get('data', {}).get('records', [])

        # Attach items to receipt
        receipt['items'] = items

        return respond(200, receipt)
        
    except Exception as e:
        print(f"Error fetching receipt: {e}")
        return respond(500, {"error": str(e)})


def _transform_receipt_image(db, receipt):
    """
    Transform receipt image URL - convert S3 URLs to presigned URLs,
    and skip base64 data to reduce payload size
    """
    image_url = receipt.get('image_url', '')

    if image_url:
        if image_url.startswith('data:'):
            # This is base64 data - don't send it to reduce payload
            # Mark it so client knows image exists but wasn't sent
            receipt['image_url'] = ''
            receipt['image_format'] = 'base64_omitted'
            receipt['has_image'] = True
        elif image_url.startswith('s3://'):
            # This is an S3 URL - generate a presigned URL
            try:
                s3_key = image_url.replace('s3://', '').split('/', 1)[1] if '/' in image_url else image_url.replace('s3://', '')
                # Get presigned URL with 1 hour expiry
                res = db.get_download_url(s3_key, expiry_seconds=3600)
                if res.get('success'):
                    presigned_url = res.get('data', {}).get('download_url')
                    if presigned_url:
                        receipt['image_url'] = presigned_url
                        receipt['image_format'] = 's3_presigned'
                        receipt['has_image'] = True
                    else:
                        print(f"Failed to generate presigned URL for {s3_key}")
                        receipt['image_url'] = ''
                        receipt['has_image'] = True
            except Exception as e:
                print(f"Error generating presigned URL: {e}")
                receipt['image_url'] = ''
                receipt['has_image'] = True
        elif image_url.startswith('http://') or image_url.startswith('https://'):
            # This is already a public URL - use as is
            receipt['image_format'] = 'public_url'
            receipt['has_image'] = True
    else:
        receipt['has_image'] = False

    return receipt


def list_receipts(event, context):
    """
    GET /v1/receipts - List all receipts for user
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        result = db.query("app_receipts", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], sort=[{"field": "created_at", "order": "desc"}], limit=50)

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
        print(f"Error listing receipts: {e}")
        return respond(500, {"error": str(e)})

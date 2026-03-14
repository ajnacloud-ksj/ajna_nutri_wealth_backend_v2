"""
NutriWealth IbexDB Client

Extends ajna-cloud-sdk's OptimizedIbexClient with app-specific methods:
- upload_file: Convenience method for base64 -> S3 upload via presigned URL
- create_database: Database initialization
- App-specific NEVER_CACHE_TABLES configuration
"""

import json
import logging
import requests
from typing import Any, Dict

from ajna_cloud.ibex import (
    OptimizedIbexClient as _SDKClient,
    NEVER_CACHE_TABLES,
)

logger = logging.getLogger(__name__)

# Configure app-specific tables that should never be cached
NEVER_CACHE_TABLES.update({
    'app_pending_analyses', 'food_entries',
    'app_shopping_lists', 'app_shopping_list_items',
})


class OptimizedIbexClient(_SDKClient):
    """
    Extended IbexDB client for NutriWealth.

    Inherits all SDK capabilities (caching, Lambda invocation, retries, etc.)
    and adds upload_file and create_database for this app's needs.
    """

    def create_database(self) -> Dict[str, Any]:
        """Create the database/namespace if it doesn't exist."""
        return self._execute({
            "operation": "CREATE_DATABASE",
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
        }, is_write=True)

    def execute_sql(self, sql: str, params: list = None, namespace: str = None, timeout_ms: int = 30000) -> Dict[str, Any]:
        """Execute raw SQL via IbexDB EXECUTE_SQL operation."""
        payload = {
            "operation": "EXECUTE_SQL",
            "tenant_id": self.tenant_id,
            "namespace": namespace or self.namespace,
            "sql": sql,
            "timeout_ms": timeout_ms,
        }
        if params:
            payload["params"] = params
        return self._execute(payload, is_write=False)

    def upload_file(self, file_data: Any, filename: str, content_type: str) -> Dict[str, Any]:
        """
        Upload a file to S3 via IbexDB presigned URL.

        Args:
            file_data: Raw bytes, string, or base64-encoded string (with data URL prefix)
            filename: Target filename / S3 key
            content_type: MIME type (e.g. 'image/jpeg')

        Returns:
            Dict with success, key, url, bucket
        """
        # 1. Get presigned upload URL from IbexDB
        res = self.get_upload_url(filename, content_type)
        if not res.get('success'):
            return {"success": False, "error": f"Failed to get upload URL: {res.get('error')}"}

        data = res.get('data')
        if not data:
            return {"success": False, "error": "No data in upload response"}

        upload_url = data['upload_url']
        file_key = data['file_key']

        # 2. Upload content via PUT to presigned URL
        try:
            # Handle base64 data URL prefix
            if isinstance(file_data, str) and 'base64,' in file_data:
                import base64
                _header, b64_data = file_data.split('base64,', 1)
                file_data = base64.b64decode(b64_data)
            elif isinstance(file_data, str):
                file_data = file_data.encode('utf-8')

            put_res = requests.put(
                upload_url,
                data=file_data,
                headers={'Content-Type': content_type},
                timeout=60,
            )
            put_res.raise_for_status()

            return {
                "success": True,
                "key": file_key,
                "url": file_key,
                "bucket": "managed-by-ibex",
            }
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {str(e)}"}

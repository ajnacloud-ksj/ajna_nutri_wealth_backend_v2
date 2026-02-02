import requests
import json
import os
import re
from typing import Dict, List, Any, Optional

class IbexClient:
    """Production-grade Ibex database client with proper error handling and data sanitization."""

    def __init__(self, api_url: str, api_key: str, tenant_id: str, namespace: str = "default"):
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        self.base_payload = {
            "tenant_id": tenant_id,
            "namespace": namespace
        }

    def _sanitize_response(self, response_text: str) -> str:
        """Replace NaN and other non-JSON values with null."""
        # Replace NaN with null (Ibex returns NaN for null numeric values)
        response_text = re.sub(r'\bNaN\b', 'null', response_text)
        # Replace NaT (Not a Time) with null
        response_text = re.sub(r'"NaT"', 'null', response_text)
        return response_text

    def _call(self, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
        """Make API call to Ibex with proper error handling."""
        full_payload = {**self.base_payload, **payload}
        
        # DEBUG: Log the FULL payload including tenant_id and namespace
        if payload.get("operation") == "CREATE_TABLE":
            print(f"FULL IBEX PAYLOAD (with tenant): {json.dumps(full_payload, indent=2)}")

        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=full_payload,
                timeout=timeout
            )
            response.raise_for_status()

            # Sanitize and parse response
            response_text = self._sanitize_response(response.text)
            return json.loads(response_text)

        except requests.exceptions.Timeout:
            raise Exception(f"Ibex API timeout after {timeout} seconds")
        except requests.exceptions.ConnectionError:
            raise Exception("Unable to connect to Ibex API")
        except requests.exceptions.RequestException as e:
            # Extract error details if available
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = error_detail.get('error', {}).get('message', str(e))
                except:
                    error_msg = e.response.text or str(e)
            raise Exception(f"Ibex API error: {error_msg}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response from Ibex: {e}")

    def create_database(self) -> Dict[str, Any]:
        """Create the database if it doesn't exist."""
        return self._call({"operation": "CREATE_DATABASE"})

    def list_tables(self) -> Dict[str, Any]:
        """List all tables in the namespace."""
        return self._call({"operation": "LIST_TABLES"})

    def create_table(self, table_name: str, schema: Dict[str, Any], if_not_exists: bool = True) -> Dict[str, Any]:
        """Create a new table with the given schema.
        
        Args:
            table_name: Name of the table to create
            schema: Table schema definition
            if_not_exists: If True, creates database and table if they don't exist (default: True)
        """
        payload = {
            "operation": "CREATE_TABLE",
            "table": table_name,
            "schema": schema,
            "if_not_exists": if_not_exists
        }
        # DEBUG: Log the exact payload being sent
        print(f"IBEX CREATE_TABLE PAYLOAD: {json.dumps(payload, indent=2)}")
        result = self._call(payload, timeout=29)
        # DEBUG: Log the Ibex response
        print(f"IBEX CREATE_TABLE RESPONSE for {table_name}: {json.dumps(result, indent=2)}")
        return result

    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Get the schema of a table."""
        return self._call({
            "operation": "DESCRIBE_TABLE",
            "table": table_name
        })

    def drop_table(self, table_name: str) -> Dict[str, Any]:
        """Drop a table."""
        return self._call({
            "operation": "DROP_TABLE",
            "table": table_name
        })

    def query(self, table: str, filters: Optional[List[Dict]] = None,
              limit: int = 50, sort: Optional[List[Dict]] = None,
              offset: int = 0, skip_versioning: bool = True) -> Dict[str, Any]:
        """
        Query records from a table.

        Args:
            table: Table name
            filters: List of filter conditions [{"field": "name", "operator": "eq", "value": "John"}]
            limit: Maximum number of records to return
            sort: List of sort conditions [{"field": "created_at", "order": "desc"}]
            offset: Number of records to skip
            skip_versioning: True for read-only operations (bypasses expensive window functions)

        Returns:
            Query result with records
        """
        payload = {
            "operation": "QUERY",
            "table": table,
            "limit": min(limit, 1000),  # Cap at 1000 for safety
            "skip_versioning": skip_versioning  # Optimization for read-only queries
        }

        if filters:
            payload["filters"] = filters
        if sort:
            payload["sort"] = sort
        if offset > 0:
            payload["offset"] = offset

        return self._call(payload)

    def write(self, table: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Write records to a table.

        Args:
            table: Table name
            records: List of records to write

        Returns:
            Write result
        """
        # Ensure records is a list
        if not isinstance(records, list):
            records = [records]

        print(f"IbexClient.write called with table: {table}")
        print(f"Records to write: {json.dumps(records, indent=2)}")
        return self._call({
            "operation": "WRITE",
            "table": table,
            "records": records
        }, timeout=29)

    def update(self, table: str, filters: List[Dict], updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update records in a table.

        Args:
            table: Table name
            filters: Filter conditions to identify records
            updates: Field updates to apply

        Returns:
            Update result
        """
        return self._call({
            "operation": "UPDATE",
            "table": table,
            "filters": filters,
            "updates": updates
        }, timeout=29)

    def delete(self, table: str, filters: List[Dict]) -> Dict[str, Any]:
        """
        Delete records from a table.

        Args:
            table: Table name
            filters: Filter conditions to identify records

        Returns:
            Delete result
        """
        return self._call({
            "operation": "DELETE",
            "table": table,
            "filters": filters
        }, timeout=29)

    def get_upload_url(self, filename: str, content_type: str, expires_in: int = 300) -> Dict[str, Any]:
        """Get a presigned S3 upload URL from Ibex."""
        return self._call({
            "operation": "GET_UPLOAD_URL",
            "filename": filename,
            "content_type": content_type,
            "expires_in": expires_in
        })

    def get_download_url(self, file_key: str, expires_in: int = 3600) -> Dict[str, Any]:
        """Get a presigned S3 download URL from Ibex."""
        return self._call({
            "operation": "GET_DOWNLOAD_URL",
            "file_key": file_key,
            "expires_in": expires_in
        })

    def upload_file(self, file_data: Any, filename: str, content_type: str) -> Dict[str, Any]:
        """
        Upload a file via Ibex presigned URL.
        
        Args:
            file_data: Raw bytes or string content (or base64 string)
            filename: Name of the file
            content_type: MIME type
            
        Returns:
            Dict with success, key, and url
        """
        # 1. Get presigned URL
        res = self.get_upload_url(filename, content_type)
        if not res.get('success'):
            return {"success": False, "error": f"Failed to get upload URL: {res.get('error')}"}
            
        data = res.get('data')
        if not data:
            return {"success": False, "error": "No data in upload response"}

        upload_url = data['upload_url']
        file_key = data['file_key']
        bucket = "managed-by-ibex"

        # 2. Upload content via standard requests
        try:
            # Handle base64 string if passed directly
            if isinstance(file_data, str) and 'base64,' in file_data:
                import base64
                header, file_data = file_data.split('base64,')
                file_data = base64.b64decode(file_data)
            elif isinstance(file_data, str):
                file_data = file_data.encode('utf-8')

            put_res = requests.put(
                upload_url, 
                data=file_data, 
                headers={'Content-Type': content_type},
                timeout=60
            )
            put_res.raise_for_status()
            
            return {
                "success": True,
                "key": file_key,
                "url": file_key,  # Just return the key as the identifier
                "bucket": bucket
            }
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {str(e)}"}
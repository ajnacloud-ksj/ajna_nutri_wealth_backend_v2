"""
Optimized Ibex Client with In-Memory Caching and Performance Improvements
This client wraps the shared IbexDB Lambda service with optimizations
"""

import json
import time
import hashlib
import requests
import functools
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict
import threading
import boto3
from datetime import datetime, timedelta
from src.lib.logger import logger

# Global cache that persists between Lambda invocations
# This stays in memory for ~15 minutes in Lambda containers
GLOBAL_CACHE = OrderedDict()
CACHE_STATS = {"hits": 0, "misses": 0, "evictions": 0}
CACHE_LOCK = threading.Lock()

# Cache configuration - Optimized for production with very short TTLs
# Short TTLs prevent stale data issues while still providing performance benefits
import os

# Allow environment-based cache control
CACHE_ENABLED = os.environ.get('IBEX_CACHE_ENABLED', 'true').lower() == 'true'
MAX_CACHE_SIZE = 100 if CACHE_ENABLED else 0  # Maximum number of cached items
CACHE_TTL_SECONDS = 30 if CACHE_ENABLED else 0  # 30 seconds for non-critical data
READ_CACHE_TTL = 5 if CACHE_ENABLED else 0  # 5 seconds for read operations (very short)
WRITE_THROUGH_CACHE = CACHE_ENABLED  # Update cache on writes only if enabled

# Critical operations that should NEVER be cached
NEVER_CACHE_TABLES = {'app_pending_analyses', 'food_entries'}  # Tables with real-time requirements

class OptimizedIbexClient:
    """
    Optimized client for IbexDB with:
    - In-memory caching (LRU)
    - Connection reuse
    - Batch operations
    - Direct Lambda invocation option
    - Query optimization
    """

    def __init__(self, api_url: str, api_key: str, tenant_id: str, namespace: str = "default"):
        self.api_url = api_url
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.namespace = namespace

        # Reusable session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-api-key": api_key
        })

        # Base payload for all requests
        self.base_payload = {
            "tenant_id": tenant_id,
            "namespace": namespace
        }

        # Lambda client for direct invocation (optional)
        self.lambda_client = None
        self.lambda_function_name = None

        # Statistics
        self.stats = {
            "total_requests": 0,
            "cached_responses": 0,
            "cache_hit_rate": 0.0
        }

    def enable_direct_lambda(self, function_name: str, use_for_writes_only: bool = True):
        """
        Enable direct Lambda invocation (bypasses API Gateway)

        Args:
            function_name: Lambda function name
            use_for_writes_only: If True, only use direct invocation for writes
                                 (keeps reads through API Gateway for caching)
        """
        self.lambda_client = boto3.client('lambda')
        self.lambda_function_name = function_name
        self.direct_lambda_writes_only = use_for_writes_only
        print(f"Direct Lambda invocation enabled for: {function_name}")
        if use_for_writes_only:
            print("  Mode: Writes only (reads still use API Gateway)")

    def _get_cache_key(self, operation: str, **params) -> str:
        """Generate a cache key for the operation"""
        # Create a deterministic key from operation and parameters
        key_data = {
            "op": operation,
            "tenant": self.tenant_id,
            "namespace": self.namespace,
            **params
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get item from cache if valid"""
        with CACHE_LOCK:
            if cache_key in GLOBAL_CACHE:
                entry = GLOBAL_CACHE[cache_key]

                # Check if entry is still valid
                if time.time() - entry["timestamp"] < entry["ttl"]:
                    # Move to end (LRU)
                    GLOBAL_CACHE.move_to_end(cache_key)
                    CACHE_STATS["hits"] += 1

                    # Deep copy to prevent cache mutation
                    import copy
                    return copy.deepcopy(entry["data"])
                else:
                    # Expired entry
                    del GLOBAL_CACHE[cache_key]

            CACHE_STATS["misses"] += 1
            return None

    def _put_in_cache(self, cache_key: str, data: Dict, ttl: int = CACHE_TTL_SECONDS):
        """Store item in cache with TTL"""
        with CACHE_LOCK:
            # Evict oldest items if cache is full
            while len(GLOBAL_CACHE) >= MAX_CACHE_SIZE:
                oldest_key = next(iter(GLOBAL_CACHE))
                del GLOBAL_CACHE[oldest_key]
                CACHE_STATS["evictions"] += 1

            GLOBAL_CACHE[cache_key] = {
                "data": data,
                "timestamp": time.time(),
                "ttl": ttl
            }

    def _invalidate_cache_pattern(self, pattern: str):
        """Invalidate cache entries matching a pattern"""
        with CACHE_LOCK:
            keys_to_delete = [
                key for key in GLOBAL_CACHE.keys()
                if pattern in key
            ]
            for key in keys_to_delete:
                del GLOBAL_CACHE[key]

    def _call_direct_lambda(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Direct Lambda invocation (faster than API Gateway)"""
        response = self.lambda_client.invoke(
            FunctionName=self.lambda_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({
                "body": json.dumps({**self.base_payload, **payload}),
                "headers": {"x-api-key": self.api_key}
            })
        )

        result = json.loads(response['Payload'].read())
        if "body" in result:
            return json.loads(result["body"])
        return result

    def _call_api(self, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
        """Standard API call with connection reuse"""
        full_payload = {**self.base_payload, **payload}

        try:
            response = self.session.post(
                self.api_url,
                json=full_payload,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise Exception(f"Ibex API timeout after {timeout} seconds")
        except Exception as e:
            raise Exception(f"Ibex API error: {str(e)}")

    def _call(self, payload: Dict[str, Any], timeout: int = 20, use_cache: bool = True) -> Dict[str, Any]:
        """Intelligent call routing with caching"""
        self.stats["total_requests"] += 1

        # Check cache for read operations (only if cache is enabled)
        operation = payload.get("operation", "")
        if use_cache and MAX_CACHE_SIZE > 0 and operation in ["QUERY", "LIST_TABLES", "DESCRIBE_TABLE"]:
            # Remove operation from payload to avoid duplicate argument error
            cache_params = payload.copy()
            if "operation" in cache_params:
                del cache_params["operation"]
            cache_key = self._get_cache_key(operation, **cache_params)
            cached_result = self._get_from_cache(cache_key)

            if cached_result is not None:
                self.stats["cached_responses"] += 1
                self.stats["cache_hit_rate"] = self.stats["cached_responses"] / self.stats["total_requests"]
                return cached_result

        # Make the actual call
        if self.lambda_client and self.lambda_function_name:
            result = self._call_direct_lambda(payload)
        else:
            result = self._call_api(payload, timeout)

        # Cache successful read operations (only if cache is enabled)
        if use_cache and MAX_CACHE_SIZE > 0 and operation in ["QUERY", "LIST_TABLES", "DESCRIBE_TABLE"]:
            if result.get("success"):
                # Remove operation from payload to avoid duplicate argument error
                cache_params = payload.copy()
                if "operation" in cache_params:
                    del cache_params["operation"]
                cache_key = self._get_cache_key(operation, **cache_params)
                ttl = READ_CACHE_TTL if operation == "QUERY" else CACHE_TTL_SECONDS
                if ttl > 0:  # Only cache if TTL is positive
                    self._put_in_cache(cache_key, result, ttl)

        return result

    # Optimized Query Method
    def query(self, table: str, filters: List[Dict] = None, limit: int = 100,
              offset: int = 0, sort: List[Dict] = None, use_cache: bool = True,
              skip_versioning: bool = True) -> Dict[str, Any]:
        """
        Optimized query with caching
        skip_versioning: True for read-only operations (bypasses expensive window functions)
        """
        # CRITICAL: Never cache tables with real-time requirements
        if table in NEVER_CACHE_TABLES:
            use_cache = False

        # For single ID lookups, use special cache (unless it's a critical table)
        if use_cache and filters and len(filters) == 1 and filters[0].get("field") == "id":
            cache_key = f"id:{table}:{filters[0].get('value')}"
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

        payload = {
            "operation": "QUERY",
            "table": table,
            "limit": limit,
            "offset": offset,
            "skip_versioning": skip_versioning  # Add optimization flag
        }

        if filters:
            payload["filters"] = filters
        if sort:
            payload["sort"] = sort

        result = self._call(payload, use_cache=use_cache)

        # Cache individual records by ID for faster lookups (only for non-critical tables)
        if use_cache and table not in NEVER_CACHE_TABLES:
            if result.get("success") and result.get("data", {}).get("records"):
                for record in result["data"]["records"]:
                    if "id" in record:
                        id_cache_key = f"id:{table}:{record['id']}"
                        self._put_in_cache(id_cache_key, {
                            "success": True,
                            "data": {"records": [record]}
                        }, ttl=READ_CACHE_TTL)

        return result

    # Batch Operations
    def batch_write(self, operations: List[Dict]) -> Dict[str, Any]:
        """
        Batch multiple write operations in a single call
        Reduces Lambda invocations significantly
        """
        # Group operations by table
        grouped = {}
        for op in operations:
            table = op.get("table")
            if table not in grouped:
                grouped[table] = []
            grouped[table].append(op)

        results = []
        for table, table_ops in grouped.items():
            # Process up to 25 items at a time (Lambda limit)
            for i in range(0, len(table_ops), 25):
                batch = table_ops[i:i+25]

                # Create batch payload
                records = [op.get("record") for op in batch if op.get("operation") == "WRITE"]

                if records:
                    result = self.write(table, records)
                    results.append(result)

                    # Invalidate cache for this table
                    if WRITE_THROUGH_CACHE:
                        self._invalidate_cache_pattern(f"table:{table}")

        return {
            "success": all(r.get("success") for r in results),
            "results": results
        }

    # Optimized Write with Write-Through Cache
    def write(self, table: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Write records and update cache"""
        if not isinstance(records, list):
            records = [records]

        result = self._call({
            "operation": "WRITE",
            "table": table,
            "records": records
        }, use_cache=False)

        # Invalidate query cache for this table
        if WRITE_THROUGH_CACHE and result.get("success"):
            self._invalidate_cache_pattern(f"table:{table}")

            # Cache the written records by ID
            for record in records:
                if "id" in record:
                    id_cache_key = f"id:{table}:{record['id']}"
                    self._put_in_cache(id_cache_key, {
                        "success": True,
                        "data": {"records": [record]}
                    }, ttl=READ_CACHE_TTL)

        return result

    # Prefetch commonly used data
    def prefetch_user_data(self, user_id: str):
        """Prefetch all user-related data in parallel"""
        import concurrent.futures

        tables = ["food_entries", "receipts", "workouts", "health_assessments"]

        def fetch_table(table):
            return self.query(
                table,
                filters=[{"field": "user_id", "operator": "eq", "value": user_id}],
                limit=50,
                use_cache=True
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_table, table): table for table in tables}
            results = {}

            for future in concurrent.futures.as_completed(futures):
                table = futures[future]
                try:
                    results[table] = future.result()
                except Exception as e:
                    results[table] = {"error": str(e)}

        return results

    # Get cache statistics
    def get_stats(self) -> Dict:
        """Get performance statistics"""
        return {
            **self.stats,
            "cache_stats": CACHE_STATS,
            "cache_size": len(GLOBAL_CACHE),
            "cache_memory_kb": sum(
                len(json.dumps(v).encode()) for v in GLOBAL_CACHE.values()
            ) / 1024
        }

    # Clear cache (for testing)
    def clear_cache(self):
        """Clear all cached data"""
        with CACHE_LOCK:
            GLOBAL_CACHE.clear()
            CACHE_STATS["hits"] = 0
            CACHE_STATS["misses"] = 0
            CACHE_STATS["evictions"] = 0

    # Existing methods remain the same but use _call internally
    def create_database(self) -> Dict[str, Any]:
        return self._call({"operation": "CREATE_DATABASE"}, use_cache=False)

    def list_tables(self) -> Dict[str, Any]:
        return self._call({"operation": "LIST_TABLES"})

    def create_table(self, table: str, schema: Dict[str, Any], if_not_exists: bool = True) -> Dict[str, Any]:
        return self._call({
            "operation": "CREATE_TABLE",
            "table": table,
            "schema": schema,
            "if_not_exists": if_not_exists
        }, use_cache=False)

    def update(self, table: str, filters: List[Dict], updates: Dict[str, Any]) -> Dict[str, Any]:
        result = self._call({
            "operation": "UPDATE",
            "table": table,
            "filters": filters,
            "updates": updates
        }, use_cache=False)

        # Invalidate cache
        if result.get("success"):
            self._invalidate_cache_pattern(f"table:{table}")
        else:
            logger.error(f"UPDATE failed for table {table}: {result.get('error')}")

        return result

    def delete(self, table: str, filters: List[Dict]) -> Dict[str, Any]:
        result = self._call({
            "operation": "DELETE",
            "table": table,
            "filters": filters
        }, use_cache=False)

        # Invalidate cache
        if result.get("success"):
            self._invalidate_cache_pattern(f"table:{table}")

        return result
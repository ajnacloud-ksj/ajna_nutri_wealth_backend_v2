"""
IbexClient optimized for Lambda Function URLs
Simpler and faster than API Gateway
"""

import json
import requests
import hashlib
import time
from typing import Dict, Any, Optional, List
from collections import OrderedDict
import threading
from datetime import datetime
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Import base optimized client
from .ibex_client_optimized import OptimizedIbexClient, GLOBAL_CACHE, CACHE_STATS

class FunctionURLIbexClient(OptimizedIbexClient):
    """
    IbexClient optimized for Lambda Function URLs
    - Lower latency than API Gateway
    - Native AWS SigV4 authentication support
    - Direct HTTPS endpoint
    """

    def __init__(self, function_url: str = None, use_iam_auth: bool = False,
                 tenant_id: str = "default", namespace: str = "default", **kwargs):
        """
        Initialize client for Lambda Function URL

        Args:
            function_url: The Lambda Function URL (https://xxx.lambda-url.region.on.aws/)
            use_iam_auth: Whether to use IAM authentication (SigV4)
            tenant_id: Tenant identifier
            namespace: Namespace for data isolation
        """
        # Use function URL if provided, otherwise fall back to API Gateway
        if function_url:
            self.function_url = function_url.rstrip('/')
            self.use_function_url = True
        else:
            # Fall back to API Gateway
            self.function_url = kwargs.get('api_url', 'https://your-api-gateway-url')
            self.use_function_url = False

        self.use_iam_auth = use_iam_auth
        self.tenant_id = tenant_id
        self.namespace = namespace

        # Session for connection pooling
        self.session = requests.Session()

        # If using IAM auth, we need boto3 session for signing
        if use_iam_auth:
            self.boto_session = boto3.Session()
            self.credentials = self.boto_session.get_credentials()
            self.region = self.boto_session.region_name or 'us-east-1'

        # Base payload
        self.base_payload = {
            "tenant_id": tenant_id,
            "namespace": namespace
        }

        # Statistics
        self.stats = {
            "total_requests": 0,
            "cached_responses": 0,
            "function_url_requests": 0,
            "api_gateway_requests": 0
        }

    def _sign_request(self, request: requests.PreparedRequest) -> requests.PreparedRequest:
        """Sign request with AWS SigV4 for IAM authentication"""
        if not self.use_iam_auth:
            return request

        # Create AWS request for signing
        aws_request = AWSRequest(
            method=request.method,
            url=request.url,
            data=request.body,
            headers=dict(request.headers)
        )

        # Sign with SigV4
        SigV4Auth(self.credentials, "lambda", self.region).add_auth(aws_request)

        # Update original request with signed headers
        request.headers.update(dict(aws_request.headers))
        return request

    def _call_function_url(self, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
        """
        Call Lambda Function URL directly
        15-20% faster than API Gateway
        """
        full_payload = {**self.base_payload, **payload}

        # Prepare request
        request = requests.Request(
            method='POST',
            url=self.function_url,
            json=full_payload,
            headers={
                'Content-Type': 'application/json',
                'X-Tenant-Id': self.tenant_id  # Custom header for tenant
            }
        )

        prepared = self.session.prepare_request(request)

        # Sign if using IAM auth
        if self.use_iam_auth:
            prepared = self._sign_request(prepared)

        # Execute request
        try:
            response = self.session.send(prepared, timeout=timeout)
            response.raise_for_status()

            # Parse response
            result = response.json()

            # Function URLs return the Lambda response directly
            # No need to parse 'body' field like with API Gateway
            return result

        except requests.exceptions.Timeout:
            raise Exception(f"Function URL timeout after {timeout} seconds")
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    raise Exception(f"Function URL error: {error_detail.get('error', str(e))}")
                except:
                    raise Exception(f"Function URL error: {e.response.text or str(e)}")
            raise Exception(f"Function URL error: {str(e)}")

    def _call(self, payload: Dict[str, Any], timeout: int = 20, use_cache: bool = True) -> Dict[str, Any]:
        """
        Intelligent call routing with Function URL support
        """
        self.stats["total_requests"] += 1

        # Check cache for read operations
        operation = payload.get("operation", "")
        if use_cache and operation in ["QUERY", "LIST_TABLES", "DESCRIBE_TABLE"]:
            # Remove 'operation' from payload before passing to _get_cache_key
            payload_without_op = {k: v for k, v in payload.items() if k != "operation"}
            cache_key = self._get_cache_key(operation, **payload_without_op)
            cached_result = self._get_from_cache(cache_key)

            if cached_result is not None:
                self.stats["cached_responses"] += 1
                return cached_result

        # Make the actual call
        if self.use_function_url:
            self.stats["function_url_requests"] += 1
            result = self._call_function_url(payload, timeout)
        else:
            self.stats["api_gateway_requests"] += 1
            result = self._call_api(payload, timeout)  # Falls back to parent class method

        # Cache successful read operations
        if use_cache and operation in ["QUERY", "LIST_TABLES", "DESCRIBE_TABLE"]:
            if result.get("success"):
                # Remove 'operation' from payload before passing to _get_cache_key
                payload_without_op = {k: v for k, v in payload.items() if k != "operation"}
                cache_key = self._get_cache_key(operation, **payload_without_op)
                ttl = 60 if operation == "QUERY" else 300
                self._put_in_cache(cache_key, result, ttl)

        return result

    def get_stats(self) -> Dict:
        """Get performance statistics including Function URL metrics"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            "function_url_requests": self.stats["function_url_requests"],
            "api_gateway_requests": self.stats["api_gateway_requests"],
            "function_url_percentage": (
                self.stats["function_url_requests"] / max(self.stats["total_requests"], 1) * 100
            )
        }


# Factory function to create the best client based on environment
def create_ibex_client(prefer_function_url: bool = True, **kwargs) -> OptimizedIbexClient:
    """
    Factory function to create the optimal IbexClient

    Args:
        prefer_function_url: If True, use Function URL when available
        **kwargs: Additional arguments for client initialization

    Returns:
        Optimized IbexClient instance

    Environment Variables:
        IBEX_FUNCTION_URL: Lambda Function URL
        IBEX_USE_IAM_AUTH: Whether to use IAM authentication
        IBEX_API_URL: API Gateway URL (fallback)
    """
    import os

    function_url = os.environ.get('IBEX_FUNCTION_URL')
    api_url = os.environ.get('IBEX_API_URL')
    use_iam_auth = os.environ.get('IBEX_USE_IAM_AUTH', 'false').lower() == 'true'

    if prefer_function_url and function_url:
        print(f"Using Lambda Function URL: {function_url}")
        return FunctionURLIbexClient(
            function_url=function_url,
            use_iam_auth=use_iam_auth,
            **kwargs
        )
    elif api_url:
        print(f"Using API Gateway: {api_url}")
        return OptimizedIbexClient(
            api_url=api_url,
            **kwargs
        )
    else:
        raise ValueError("No IbexDB endpoint configured. Set IBEX_FUNCTION_URL or IBEX_API_URL")


# Performance comparison function
def compare_endpoints():
    """Compare performance between Function URL and API Gateway"""
    import time
    import statistics

    print("="*60)
    print("FUNCTION URL vs API GATEWAY PERFORMANCE COMPARISON")
    print("="*60)

    # Test payload
    test_payload = {
        "operation": "QUERY",
        "table": "food_entries",
        "limit": 10
    }

    # Test Function URL
    if os.environ.get('IBEX_FUNCTION_URL'):
        print("\n📊 Testing Function URL...")
        function_client = FunctionURLIbexClient(
            function_url=os.environ['IBEX_FUNCTION_URL'],
            tenant_id="test"
        )

        function_times = []
        for i in range(10):
            start = time.perf_counter()
            function_client._call(test_payload, use_cache=False)
            end = time.perf_counter()
            function_times.append((end - start) * 1000)
            print(f"  Run {i+1}: {function_times[-1]:.2f}ms")

        print(f"\n  Function URL Average: {statistics.mean(function_times):.2f}ms")
        print(f"  Function URL P95: {sorted(function_times)[int(len(function_times)*0.95)]:.2f}ms")

    # Test API Gateway
    if os.environ.get('IBEX_API_URL'):
        print("\n📊 Testing API Gateway...")
        api_client = OptimizedIbexClient(
            api_url=os.environ['IBEX_API_URL'],
            api_key=os.environ.get('IBEX_API_KEY', ''),
            tenant_id="test"
        )

        api_times = []
        for i in range(10):
            start = time.perf_counter()
            api_client._call(test_payload, use_cache=False)
            end = time.perf_counter()
            api_times.append((end - start) * 1000)
            print(f"  Run {i+1}: {api_times[-1]:.2f}ms")

        print(f"\n  API Gateway Average: {statistics.mean(api_times):.2f}ms")
        print(f"  API Gateway P95: {sorted(api_times)[int(len(api_times)*0.95)]:.2f}ms")

    # Compare
    if 'function_times' in locals() and 'api_times' in locals():
        improvement = ((statistics.mean(api_times) - statistics.mean(function_times)) /
                      statistics.mean(api_times)) * 100
        print(f"\n🎯 Function URL is {improvement:.1f}% faster than API Gateway")

    print("="*60)
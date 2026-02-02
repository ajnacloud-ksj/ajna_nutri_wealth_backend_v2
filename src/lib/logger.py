"""
Structured logging system for production environments
"""

import os
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps
import traceback


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add extra fields
        if hasattr(record, 'user_id'):
            log_obj['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_obj['request_id'] = record.request_id
        if hasattr(record, 'tenant_id'):
            log_obj['tenant_id'] = record.tenant_id
        if hasattr(record, 'correlation_id'):
            log_obj['correlation_id'] = record.correlation_id

        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }

        # Add extra data
        if hasattr(record, 'extra_data'):
            log_obj['data'] = record.extra_data

        return json.dumps(log_obj)


class Logger:
    """Enhanced logger with structured logging and context"""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is None:
            self._setup_logger()

    def _setup_logger(self):
        """Setup logger based on environment"""
        env = os.environ.get('ENVIRONMENT', 'development')
        log_level = os.environ.get('LOG_LEVEL', 'INFO' if env == 'production' else 'DEBUG')

        # Create logger
        self._logger = logging.getLogger('food-app')
        self._logger.setLevel(getattr(logging, log_level))

        # Remove existing handlers
        self._logger.handlers = []

        # Create handler
        handler = logging.StreamHandler(sys.stdout)

        # Set formatter based on environment
        if env == 'production':
            formatter = JSONFormatter()
        else:
            # Human-readable format for development
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

        # Prevent propagation to root logger
        self._logger.propagate = False

    def _mask_sensitive_data(self, data: Any) -> Any:
        """Mask sensitive data in logs"""
        if isinstance(data, dict):
            masked = {}
            sensitive_keys = [
                'password', 'token', 'api_key', 'secret', 'authorization',
                'x-api-key', 'credit_card', 'ssn', 'social_security'
            ]

            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in sensitive_keys):
                    if isinstance(value, str) and len(value) > 4:
                        masked[key] = value[:2] + '*' * (len(value) - 4) + value[-2:]
                    else:
                        masked[key] = '***'
                elif isinstance(value, (dict, list)):
                    masked[key] = self._mask_sensitive_data(value)
                else:
                    masked[key] = value
            return masked
        elif isinstance(data, list):
            return [self._mask_sensitive_data(item) for item in data]
        return data

    def log(self, level: str, message: str, **kwargs):
        """Log a message with context"""
        extra = {}

        # Add context data
        if 'user_id' in kwargs:
            extra['user_id'] = kwargs.pop('user_id')
        if 'request_id' in kwargs:
            extra['request_id'] = kwargs.pop('request_id')
        if 'tenant_id' in kwargs:
            extra['tenant_id'] = kwargs.pop('tenant_id')
        if 'correlation_id' in kwargs:
            extra['correlation_id'] = kwargs.pop('correlation_id')

        # Add any remaining kwargs as extra data
        if kwargs:
            # Mask sensitive data if enabled
            if os.environ.get('MASK_SENSITIVE_DATA', 'true').lower() == 'true':
                kwargs = self._mask_sensitive_data(kwargs)
            extra['extra_data'] = kwargs

        # Log the message
        log_method = getattr(self._logger, level.lower())
        log_method(message, extra=extra)

    def debug(self, message: str, **kwargs):
        self.log('debug', message, **kwargs)

    def info(self, message: str, **kwargs):
        self.log('info', message, **kwargs)

    def warning(self, message: str, **kwargs):
        self.log('warning', message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log('error', message, **kwargs)

    def critical(self, message: str, **kwargs):
        self.log('critical', message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log an exception with traceback"""
        self._logger.exception(message, extra=kwargs)


class RequestLogger:
    """Middleware for logging API requests and responses"""

    def __init__(self, logger: Logger):
        self.logger = logger

    def log_request(self, event: Dict[str, Any], context: Dict[str, Any]):
        """Log incoming request"""
        # Generate request ID
        import uuid
        request_id = str(uuid.uuid4())

        # Extract request details
        method = event.get('httpMethod', 'UNKNOWN')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters', {})
        headers = event.get('headers', {})

        # Get user and tenant info
        from lib.auth_provider import get_user_id
        user_id = get_user_id(event)
        tenant_id = headers.get('X-Tenant-Id', 'default')

        # Log request
        self.logger.info(
            f"Request: {method} {path}",
            request_id=request_id,
            user_id=user_id,
            tenant_id=tenant_id,
            method=method,
            path=path,
            query_params=query_params,
            headers=self._sanitize_headers(headers)
        )

        # Add request ID to context for use in handlers
        context['request_id'] = request_id

        return request_id

    def log_response(self, request_id: str, response: Dict[str, Any], duration_ms: float):
        """Log outgoing response"""
        status_code = response.get('statusCode', 0)

        log_data = {
            'request_id': request_id,
            'status_code': status_code,
            'duration_ms': duration_ms
        }

        # Log based on status code
        if status_code < 400:
            self.logger.info(f"Response: {status_code}", **log_data)
        elif status_code < 500:
            self.logger.warning(f"Client error: {status_code}", **log_data)
        else:
            self.logger.error(f"Server error: {status_code}", **log_data)

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive headers from logs"""
        sanitized = {}
        sensitive_headers = ['authorization', 'x-api-key', 'cookie', 'x-auth-token']

        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                sanitized[key] = '***'
            else:
                sanitized[key] = value

        return sanitized


def log_handler(func):
    """
    Decorator to log handler execution

    Usage:
        @log_handler
        def my_handler(event, context):
            # Handler code
    """
    @wraps(func)
    def wrapper(event, context):
        logger = Logger()
        request_logger = RequestLogger(logger)

        # Log request
        import time
        start_time = time.time()
        request_id = request_logger.log_request(event, context)

        try:
            # Execute handler
            response = func(event, context)

            # Log response
            duration_ms = (time.time() - start_time) * 1000
            request_logger.log_response(request_id, response, duration_ms)

            return response

        except Exception as e:
            # Log exception
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(
                f"Handler error: {str(e)}",
                request_id=request_id,
                handler=func.__name__,
                duration_ms=duration_ms
            )

            # Return error response
            from utils.http import respond
            return respond(500, {
                'error': 'Internal server error',
                'request_id': request_id
            })

    return wrapper


# Singleton logger instance
logger = Logger()
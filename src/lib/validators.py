"""
Input validation system with schema validation and sanitization
"""

import re
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from functools import wraps


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class Validator:
    """Base validator class"""

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_uuid(uuid_str: str) -> bool:
        """Validate UUID format"""
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(pattern, uuid_str.lower()))

    @staticmethod
    def validate_date(date_str: str, format: str = '%Y-%m-%d') -> bool:
        """Validate date format"""
        try:
            datetime.strptime(date_str, format)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format"""
        pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
        return bool(re.match(pattern, url))

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number (US format)"""
        pattern = r'^\+?1?\d{10,14}$'
        return bool(re.match(pattern, phone.replace('-', '').replace(' ', '')))

    @staticmethod
    def sanitize_string(value: str, max_length: int = None) -> str:
        """Sanitize string input"""
        if not isinstance(value, str):
            raise ValidationError(f"Expected string, got {type(value).__name__}")

        # Remove leading/trailing whitespace
        value = value.strip()

        # Remove null bytes
        value = value.replace('\x00', '')

        # Limit length if specified
        if max_length and len(value) > max_length:
            value = value[:max_length]

        return value

    @staticmethod
    def sanitize_html(html: str) -> str:
        """Remove potentially dangerous HTML tags"""
        # Remove script tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove style tags
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove onclick and other event handlers
        html = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
        # Remove javascript: protocol
        html = re.sub(r'javascript:', '', html, flags=re.IGNORECASE)

        return html


class SchemaValidator:
    """Schema-based validation for request bodies"""

    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data against schema"""
        validated = {}
        errors = []

        for field_name, field_config in self.schema.items():
            field_type = field_config.get('type', 'string')
            required = field_config.get('required', False)
            default = field_config.get('default', None)
            min_val = field_config.get('min', None)
            max_val = field_config.get('max', None)
            max_length = field_config.get('max_length', None)
            pattern = field_config.get('pattern', None)
            choices = field_config.get('choices', None)
            custom_validator = field_config.get('validator', None)

            # Check if field exists
            if field_name not in data:
                if required:
                    errors.append(f"Missing required field: {field_name}")
                elif default is not None:
                    validated[field_name] = default
                continue

            value = data[field_name]

            # Type validation
            try:
                if field_type == 'string':
                    if not isinstance(value, str):
                        raise ValidationError(f"Expected string for {field_name}")
                    value = Validator.sanitize_string(value, max_length)

                elif field_type == 'integer':
                    value = int(value)
                    if min_val is not None and value < min_val:
                        raise ValidationError(f"{field_name} must be >= {min_val}")
                    if max_val is not None and value > max_val:
                        raise ValidationError(f"{field_name} must be <= {max_val}")

                elif field_type == 'float' or field_type == 'double':
                    value = float(value)
                    if min_val is not None and value < min_val:
                        raise ValidationError(f"{field_name} must be >= {min_val}")
                    if max_val is not None and value > max_val:
                        raise ValidationError(f"{field_name} must be <= {max_val}")

                elif field_type == 'boolean':
                    if isinstance(value, str):
                        value = value.lower() in ('true', '1', 'yes')
                    else:
                        value = bool(value)

                elif field_type == 'email':
                    if not Validator.validate_email(value):
                        raise ValidationError(f"Invalid email format for {field_name}")

                elif field_type == 'uuid':
                    if not Validator.validate_uuid(value):
                        raise ValidationError(f"Invalid UUID format for {field_name}")

                elif field_type == 'date':
                    if not Validator.validate_date(value):
                        raise ValidationError(f"Invalid date format for {field_name}")

                elif field_type == 'url':
                    if not Validator.validate_url(value):
                        raise ValidationError(f"Invalid URL format for {field_name}")

                elif field_type == 'array':
                    if not isinstance(value, list):
                        raise ValidationError(f"Expected array for {field_name}")

                elif field_type == 'object':
                    if not isinstance(value, dict):
                        raise ValidationError(f"Expected object for {field_name}")

                # Pattern validation
                if pattern and isinstance(value, str):
                    if not re.match(pattern, value):
                        raise ValidationError(f"{field_name} does not match required pattern")

                # Choices validation
                if choices and value not in choices:
                    raise ValidationError(f"{field_name} must be one of: {choices}")

                # Custom validator
                if custom_validator and callable(custom_validator):
                    if not custom_validator(value):
                        raise ValidationError(f"Custom validation failed for {field_name}")

                validated[field_name] = value

            except ValidationError as e:
                errors.append(str(e))
            except (ValueError, TypeError) as e:
                errors.append(f"Invalid {field_type} for {field_name}: {str(e)}")

        if errors:
            raise ValidationError("; ".join(errors))

        return validated


# Pre-defined schemas for common endpoints
SCHEMAS = {
    'food_entry': {
        'description': {'type': 'string', 'required': False, 'max_length': 500},
        'image_url': {'type': 'url', 'required': False},
        'meal_type': {
            'type': 'string',
            'required': False,
            'choices': ['breakfast', 'lunch', 'dinner', 'snack']
        },
        'meal_date': {'type': 'date', 'required': False},
        'calories': {'type': 'float', 'min': 0, 'max': 10000},
        'total_protein': {'type': 'float', 'min': 0, 'max': 1000},
        'total_carbohydrates': {'type': 'float', 'min': 0, 'max': 1000},
        'total_fats': {'type': 'float', 'min': 0, 'max': 1000}
    },

    'user_registration': {
        'email': {'type': 'email', 'required': True},
        'password': {
            'type': 'string',
            'required': True,
            'min_length': 8,
            'pattern': r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{8,}$'
        },
        'name': {'type': 'string', 'required': True, 'max_length': 100},
        'role': {
            'type': 'string',
            'required': False,
            'choices': ['participant', 'caretaker', 'admin'],
            'default': 'participant'
        }
    },

    'analyze_request': {
        'description': {'type': 'string', 'required': False, 'max_length': 1000},
        'image_url': {'type': 'string', 'required': False},
        'category': {
            'type': 'string',
            'required': False,
            'choices': ['food', 'receipt', 'workout']
        }
    }
}


def validate_request(schema_name: str = None, schema: Dict = None):
    """
    Decorator to validate request body against a schema

    Usage:
        @validate_request('food_entry')
        def create_food_entry(event, context):
            # Body is already validated
            body = json.loads(event['body'])
    """
    def decorator(func):
        @wraps(func)
        def wrapper(event, context):
            # Get schema
            if schema:
                validation_schema = schema
            elif schema_name and schema_name in SCHEMAS:
                validation_schema = SCHEMAS[schema_name]
            else:
                # No validation
                return func(event, context)

            # Parse body
            try:
                body = json.loads(event.get('body', '{}'))
            except json.JSONDecodeError:
                from utils.http import respond
                return respond(400, {'error': 'Invalid JSON in request body'})

            # Validate
            try:
                validator = SchemaValidator(validation_schema)
                validated_body = validator.validate(body)
                # Replace body with validated version
                event['body'] = json.dumps(validated_body)
            except ValidationError as e:
                from utils.http import respond
                return respond(400, {'error': str(e)})

            return func(event, context)
        return wrapper
    return decorator


def validate_file_upload(allowed_types: List[str] = None, max_size: int = 10485760):
    """
    Decorator to validate file uploads

    Usage:
        @validate_file_upload(['image/jpeg', 'image/png'], max_size=5242880)
        def upload_image(event, context):
            # File is validated
    """
    def decorator(func):
        @wraps(func)
        def wrapper(event, context):
            try:
                body = json.loads(event.get('body', '{}'))
            except:
                from utils.http import respond
                return respond(400, {'error': 'Invalid request body'})

            # Check file data
            file_data = body.get('file') or body.get('file_data')
            if not file_data:
                from utils.http import respond
                return respond(400, {'error': 'No file data provided'})

            # Check size (if base64, calculate decoded size)
            if isinstance(file_data, str) and 'base64,' in file_data:
                # Rough estimate of decoded size
                estimated_size = len(file_data) * 3 / 4
                if estimated_size > max_size:
                    from utils.http import respond
                    return respond(400, {
                        'error': f'File too large. Maximum size: {max_size} bytes'
                    })

            # Check content type
            if allowed_types:
                content_type = body.get('content_type') or body.get('mime_type')
                if content_type not in allowed_types:
                    from utils.http import respond
                    return respond(400, {
                        'error': f'Invalid file type. Allowed: {", ".join(allowed_types)}'
                    })

            return func(event, context)
        return wrapper
    return decorator
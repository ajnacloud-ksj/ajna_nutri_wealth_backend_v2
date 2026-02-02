# Security & Code Quality Improvements Guide

## Overview

This document describes the comprehensive security and code quality improvements implemented for the NutriWealth Food App backend. These improvements address authentication, input validation, logging, and configuration management while maintaining easy local development.

## Table of Contents

1. [Authentication System](#authentication-system)
2. [Input Validation](#input-validation)
3. [Configuration Management](#configuration-management)
4. [Structured Logging](#structured-logging)
5. [CORS Security](#cors-security)
6. [Migration Guide](#migration-guide)
7. [Testing](#testing)

## Authentication System

### Overview

The new authentication system provides a flexible abstraction layer that supports multiple authentication providers:
- **Local Mode**: Mock authentication for development
- **Cognito Mode**: AWS Cognito for production
- **Test Mode**: Simplified authentication for unit tests

### Configuration

Set the authentication mode via environment variable:

```bash
# Development
AUTH_MODE=local

# Production
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxx
```

### Usage in Handlers

```python
from lib.auth_provider import require_auth, get_user_id
from lib.validators import validate_request
from lib.logger import log_handler

@log_handler
@require_auth
@validate_request('food_entry')
def create_food_entry(event, context):
    # User is authenticated
    user_id = get_user_id(event)

    # Body is validated
    body = json.loads(event['body'])

    # Your handler logic here
    return respond(200, {"success": True})
```

### Local Development Users

In local mode, the following mock users are available:

| User ID | Email | Role | Description |
|---------|-------|------|-------------|
| dev-user-1 | developer@local.test | admin | Default developer account |
| test-user-1 | testuser@local.test | participant | Test participant |
| caretaker-1 | caretaker@local.test | caretaker | Test caretaker |

To use a specific user in local mode, set the `X-User-Id` header:

```bash
curl -H "X-User-Id: test-user-1" http://localhost:8080/v1/food_entries
```

## Input Validation

### Schema-Based Validation

The new validation system provides automatic input validation using schemas:

```python
from lib.validators import validate_request, ValidationError

# Using predefined schema
@validate_request('food_entry')
def create_food_entry(event, context):
    # Body is automatically validated
    pass

# Using custom schema
custom_schema = {
    'name': {'type': 'string', 'required': True, 'max_length': 100},
    'age': {'type': 'integer', 'min': 0, 'max': 150},
    'email': {'type': 'email', 'required': True}
}

@validate_request(schema=custom_schema)
def custom_handler(event, context):
    pass
```

### File Upload Validation

```python
from lib.validators import validate_file_upload

@validate_file_upload(
    allowed_types=['image/jpeg', 'image/png'],
    max_size=5242880  # 5MB
)
def upload_image(event, context):
    # File is validated
    pass
```

### Available Validators

- **Email**: RFC-compliant email validation
- **UUID**: UUID format validation
- **Date**: Date format validation (customizable)
- **URL**: URL format validation
- **Phone**: Phone number validation (US format)
- **HTML Sanitization**: Remove dangerous HTML/JavaScript

## Configuration Management

### Environment-Based Configuration

The new configuration system automatically loads settings based on environment:

```python
from config.settings import settings

# Access configuration
db_url = settings.config.database.api_url
auth_mode = settings.config.auth.mode

# Check feature flags
if settings.is_feature_enabled('enable_ai_analysis'):
    # AI analysis code
    pass

# Get nested configuration
max_requests = settings.get('security.max_requests_per_minute', 60)
```

### Environment Files

1. **Development**: `.env` (local overrides)
2. **Staging**: `config.staging.json`
3. **Production**: `config.production.json`

### Configuration Priority

1. Environment variables (highest)
2. Environment-specific config file
3. Default values (lowest)

## Structured Logging

### Logger Usage

```python
from lib.logger import logger, log_handler

# Basic logging
logger.info("Processing request", user_id=user_id, action="create_food")
logger.error("Database error", error=str(e), table="food_entries")

# Automatic handler logging
@log_handler
def my_handler(event, context):
    # Automatically logs request/response/errors
    pass
```

### Log Output Formats

**Development** (Human-readable):
```
2024-01-29 10:30:45 - food-app - INFO - Processing request
```

**Production** (JSON):
```json
{
  "timestamp": "2024-01-29T10:30:45.123Z",
  "level": "INFO",
  "message": "Processing request",
  "user_id": "user-123",
  "request_id": "abc-123",
  "tenant_id": "tenant-1"
}
```

### Sensitive Data Masking

Sensitive fields are automatically masked in logs:
- Passwords: `pa****rd`
- API Keys: `sk****ey`
- Tokens: `to****en`

## CORS Security

### Environment-Specific CORS

CORS origins are now environment-specific:

```python
# Development
ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:5174'
]

# Production
ALLOWED_ORIGINS = [
    'https://app.nutriwealth.com',
    'https://www.nutriwealth.com'
]
```

### Dynamic CORS Headers

The system automatically sets appropriate CORS headers based on the request origin:

```python
from utils.http import respond

def handler(event, context):
    # CORS headers are automatically added based on request origin
    return respond(200, {"data": "value"}, event=event)
```

## Migration Guide

### Step 1: Update Environment Variables

```bash
# Copy new environment template
cp backend/.env.example backend/.env

# Edit .env with your values
vim backend/.env
```

### Step 2: Update Handler Imports

Replace old imports:
```python
# Old
from utils.http import respond, get_user_id

# New
from utils.http import respond
from lib.auth_provider import get_user_id, require_auth
from lib.validators import validate_request
from lib.logger import log_handler
```

### Step 3: Add Decorators to Handlers

```python
# Before
def create_food_entry(event, context):
    user_id = get_user_id(event) or 'local-dev-user'
    # Handler logic

# After
@log_handler
@require_auth
@validate_request('food_entry')
def create_food_entry(event, context):
    user_id = get_user_id(event)  # Never returns None in authenticated handlers
    # Handler logic
```

### Step 4: Update Docker Compose

```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - ENVIRONMENT=development
      - AUTH_MODE=local
      - LOG_LEVEL=DEBUG
```

### Step 5: Test Authentication Modes

```bash
# Test local mode
AUTH_MODE=local python local_server.py

# Test with Cognito (requires valid credentials)
AUTH_MODE=cognito COGNITO_USER_POOL_ID=xxx python local_server.py
```

## Testing

### Unit Testing with Test Auth

```python
import unittest
from lib.auth_provider import AuthFactory

class TestFoodHandler(unittest.TestCase):
    def setUp(self):
        # Use test auth provider
        os.environ['AUTH_MODE'] = 'test'
        AuthFactory.reset()

    def test_create_food_entry(self):
        event = {
            'httpMethod': 'POST',
            'path': '/v1/food_entries',
            'body': json.dumps({
                'description': 'Test food',
                'calories': 100
            })
        }

        response = create_food_entry(event, {})
        self.assertEqual(response['statusCode'], 201)
```

### Integration Testing

```bash
# Run with local auth
AUTH_MODE=local pytest tests/

# Run with Cognito simulation
AUTH_MODE=test pytest tests/
```

## Best Practices

### 1. Always Use Authentication Decorator

```python
@require_auth  # This ensures user is authenticated
def protected_handler(event, context):
    user_id = get_user_id(event)  # Guaranteed to return valid user_id
```

### 2. Validate All User Input

```python
@validate_request('schema_name')  # Automatic validation
def handler(event, context):
    # Body is pre-validated and sanitized
    pass
```

### 3. Use Structured Logging

```python
# Good - structured data
logger.info("User action", user_id=user_id, action="create", resource="food_entry")

# Bad - unstructured string
print(f"User {user_id} created food entry")
```

### 4. Environment-Specific Configuration

```python
from config.settings import settings

# Good - use configuration system
if settings.config.environment == 'production':
    # Production-specific code

# Bad - hardcoded environment checks
if os.environ.get('ENV') == 'prod':
    # This is harder to maintain
```

### 5. Handle Errors Gracefully

```python
@log_handler  # Automatically logs errors
def handler(event, context):
    try:
        # Handler logic
        pass
    except ValidationError as e:
        # Specific error handling
        return respond(400, {'error': str(e)}, event=event)
    # Framework handles unexpected errors
```

## Deployment Checklist

### Development
- [ ] Set `AUTH_MODE=local`
- [ ] Set `ENVIRONMENT=development`
- [ ] Configure mock users if needed
- [ ] Enable debug logging

### Staging
- [ ] Set `AUTH_MODE=cognito`
- [ ] Configure Cognito credentials
- [ ] Set appropriate CORS origins
- [ ] Enable info-level logging
- [ ] Test with real authentication

### Production
- [ ] Set `AUTH_MODE=cognito`
- [ ] Verify Cognito configuration
- [ ] Restrict CORS origins
- [ ] Enable warning-level logging
- [ ] Enable rate limiting
- [ ] Enable sensitive data masking
- [ ] Verify all feature flags

## Troubleshooting

### Issue: "Unauthorized" errors in local development

**Solution**: Ensure `AUTH_MODE=local` is set:
```bash
export AUTH_MODE=local
python local_server.py
```

### Issue: CORS errors in browser

**Solution**: Check allowed origins match your frontend URL:
```bash
# For local development
export ALLOWED_ORIGINS=http://localhost:5173

# Or update in docker-compose.yml
```

### Issue: Validation errors for valid data

**Solution**: Check schema definition and field types:
```python
# Ensure types match
schema = {
    'age': {'type': 'integer'},  # Not 'string'
    'price': {'type': 'float'}   # Not 'integer'
}
```

### Issue: Logs not appearing

**Solution**: Check log level:
```bash
# For detailed logs
export LOG_LEVEL=DEBUG
```

## Security Considerations

1. **Never commit `.env` files** with real credentials
2. **Rotate API keys** regularly
3. **Use least privilege** for IAM roles
4. **Enable CloudWatch** monitoring in production
5. **Implement rate limiting** for public endpoints
6. **Regularly update** dependencies
7. **Use AWS Secrets Manager** for production secrets
8. **Enable AWS WAF** for additional protection

## Support

For questions or issues:
1. Check this documentation
2. Review code examples in `/backend/examples/`
3. Check logs for detailed error messages
4. Create an issue in the repository
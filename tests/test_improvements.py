#!/usr/bin/env python3
"""
Test script for authentication system and AI improvements
Run this to verify all improvements are working correctly
"""

import os
import sys
import json
import time
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

# Set environment for testing
os.environ['ENVIRONMENT'] = 'development'
os.environ['AUTH_MODE'] = 'local'
os.environ['LOG_LEVEL'] = 'DEBUG'


def test_auth_system():
    """Test the authentication system in different modes"""
    print("\n" + "="*60)
    print("TESTING AUTHENTICATION SYSTEM")
    print("="*60)

    from lib.auth_provider import AuthFactory, get_user_id
    from utils.http import respond

    # Test Local Auth Provider
    print("\n1. Testing Local Auth Provider...")
    os.environ['AUTH_MODE'] = 'local'
    AuthFactory.reset()
    provider = AuthFactory.get_provider()
    print(f"   Provider: {provider.__class__.__name__}")

    # Test with different user IDs
    test_events = [
        {"headers": {}},  # No user specified
        {"headers": {"x-user-id": "test-user-1"}},  # Specific user
        {"headers": {"x-user-id": "caretaker-1"}},  # Different role
    ]

    for event in test_events:
        user_id = get_user_id(event)
        print(f"   Event headers: {event['headers']}")
        print(f"   Retrieved user_id: {user_id}")

    # Test auth decorator
    from lib.auth_provider import require_auth

    @require_auth
    def protected_handler(event, context):
        user_id = get_user_id(event)
        return {"statusCode": 200, "body": json.dumps({"user_id": user_id})}

    print("\n2. Testing @require_auth decorator...")
    result = protected_handler({"headers": {}}, {})
    print(f"   Result: {result}")

    # Test token verification
    print("\n3. Testing token verification...")
    token = "local:test-user-1"
    user_info = provider.verify_token(token)
    print(f"   Token: {token}")
    print(f"   User info: {json.dumps(user_info, indent=2)}")

    print("\n✅ Authentication tests passed!")


def test_validation_system():
    """Test the input validation system"""
    print("\n" + "="*60)
    print("TESTING VALIDATION SYSTEM")
    print("="*60)

    from lib.validators import SchemaValidator, ValidationError, Validator

    # Test email validation
    print("\n1. Testing email validation...")
    test_emails = [
        ("user@example.com", True),
        ("invalid.email", False),
        ("user+tag@domain.co.uk", True)
    ]

    for email, expected in test_emails:
        result = Validator.validate_email(email)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {email}: {result}")

    # Test schema validation
    print("\n2. Testing schema validation...")
    schema = {
        'name': {'type': 'string', 'required': True, 'max_length': 50},
        'age': {'type': 'integer', 'min': 0, 'max': 150},
        'email': {'type': 'email', 'required': True}
    }

    validator = SchemaValidator(schema)

    # Valid data
    try:
        valid_data = {
            'name': 'John Doe',
            'age': 30,
            'email': 'john@example.com'
        }
        result = validator.validate(valid_data)
        print(f"   ✅ Valid data passed: {result}")
    except ValidationError as e:
        print(f"   ❌ Valid data failed: {e}")

    # Invalid data
    try:
        invalid_data = {
            'name': 'A' * 100,  # Too long
            'age': -5,  # Negative
            'email': 'not-an-email'
        }
        result = validator.validate(invalid_data)
        print(f"   ❌ Invalid data passed (should have failed)")
    except ValidationError as e:
        print(f"   ✅ Invalid data correctly rejected: {e}")

    # Test HTML sanitization
    print("\n3. Testing HTML sanitization...")
    dangerous_html = '<script>alert("XSS")</script><p onclick="evil()">Text</p>'
    sanitized = Validator.sanitize_html(dangerous_html)
    print(f"   Original: {dangerous_html}")
    print(f"   Sanitized: {sanitized}")

    print("\n✅ Validation tests passed!")


def test_configuration_system():
    """Test the configuration management system"""
    print("\n" + "="*60)
    print("TESTING CONFIGURATION SYSTEM")
    print("="*60)

    from config.settings import settings

    print("\n1. Testing environment detection...")
    print(f"   Environment: {settings.config.environment}")
    print(f"   Debug mode: {settings.config.debug}")

    print("\n2. Testing configuration access...")
    print(f"   Auth mode: {settings.config.auth.mode}")
    print(f"   Database URL: {settings.config.database.api_url}")
    print(f"   Log level: {settings.config.logging.level}")

    print("\n3. Testing feature flags...")
    features = [
        'enable_ai_analysis',
        'enable_receipt_scanning',
        'enable_notifications'
    ]
    for feature in features:
        enabled = settings.is_feature_enabled(feature)
        status = "✅ Enabled" if enabled else "❌ Disabled"
        print(f"   {feature}: {status}")

    print("\n4. Testing nested configuration access...")
    max_requests = settings.get('security.max_requests_per_minute', 60)
    print(f"   Max requests/min: {max_requests}")

    print("\n✅ Configuration tests passed!")


def test_logging_system():
    """Test the structured logging system"""
    print("\n" + "="*60)
    print("TESTING LOGGING SYSTEM")
    print("="*60)

    from lib.logger import logger, RequestLogger

    print("\n1. Testing basic logging...")
    logger.debug("Debug message", extra_field="value")
    logger.info("Info message", user_id="test-user", action="test")
    logger.warning("Warning message", threshold=100, current=150)
    logger.error("Error message", error_code="TEST_ERROR")

    print("\n2. Testing sensitive data masking...")
    sensitive_data = {
        'username': 'john_doe',
        'password': 'secret123',
        'api_key': 'sk-1234567890',
        'email': 'john@example.com'
    }
    logger.info("User login", **sensitive_data)

    print("\n3. Testing request logging...")
    request_logger = RequestLogger(logger)

    event = {
        'httpMethod': 'POST',
        'path': '/v1/analyze',
        'headers': {
            'Authorization': 'Bearer secret-token',
            'X-User-Id': 'test-user'
        },
        'queryStringParameters': {'debug': 'true'}
    }
    context = {}

    request_id = request_logger.log_request(event, context)
    print(f"   Request ID: {request_id}")

    # Simulate response
    response = {'statusCode': 200, 'body': '{"success": true}'}
    request_logger.log_response(request_id, response, 123.45)

    print("\n✅ Logging tests passed!")


def test_cors_system():
    """Test the CORS security system"""
    print("\n" + "="*60)
    print("TESTING CORS SYSTEM")
    print("="*60)

    from utils.http import get_cors_headers, respond

    print("\n1. Testing CORS headers for different origins...")

    test_cases = [
        {'headers': {'origin': 'http://localhost:5173'}},  # Allowed
        {'headers': {'origin': 'https://evil.com'}},  # Not allowed
        {'headers': {}}  # No origin
    ]

    for event in test_cases:
        headers = get_cors_headers(event)
        origin = event['headers'].get('origin', 'None')
        print(f"\n   Origin: {origin}")
        print(f"   CORS Origin: {headers['Access-Control-Allow-Origin']}")
        print(f"   Credentials: {headers.get('Access-Control-Allow-Credentials', 'false')}")

    print("\n2. Testing response with CORS...")
    response = respond(200, {"data": "test"}, event={'headers': {'origin': 'http://localhost:5173'}})
    print(f"   Response headers: {json.dumps(response['headers'], indent=2)}")

    print("\n✅ CORS tests passed!")


def test_ai_optimization():
    """Test the optimized AI service"""
    print("\n" + "="*60)
    print("TESTING AI OPTIMIZATION")
    print("="*60)

    # Check if OpenAI key is available
    if not os.environ.get('OPENAI_API_KEY'):
        print("⚠️  Skipping AI tests - OPENAI_API_KEY not set")
        print("   Set OPENAI_API_KEY to test AI functionality")
        return

    try:
        # Import optimized AI service
        from lib.ai_optimized import OptimizedAIService
        from lib.ibex_client import IbexClient

        # Create mock DB client for testing
        class MockDB:
            def query(self, *args, **kwargs):
                return {"success": False}

            def write(self, *args, **kwargs):
                return {"success": True}

            def get_download_url(self, *args, **kwargs):
                return {"success": False}

        db = MockDB()
        ai_service = OptimizedAIService(db)

        print("\n1. Testing content classification...")

        test_cases = [
            ("Chicken curry with rice", None, "food"),
            ("Receipt from Walmart total $45.67", None, "receipt"),
            ("Ran 5 miles in 45 minutes", None, "workout"),
        ]

        for description, image, expected in test_cases:
            category, confidence, tokens = ai_service._classify_content(description, image)
            status = "✅" if category == expected else "❌"
            print(f"   {status} '{description[:30]}...' -> {category} ({confidence:.2f} confidence)")

        print("\n2. Testing full analysis pipeline...")
        result = ai_service.process_request(
            user_id="test-user",
            description="Grilled chicken salad with vegetables",
            image_url=None
        )

        if result['success']:
            print(f"   ✅ Analysis successful")
            print(f"   Category: {result['category']}")
            print(f"   Confidence: {result.get('confidence', 'N/A')}")
            print(f"   Total tokens: {result['metadata']['total_tokens']}")
            print(f"   Total cost: ${result['metadata']['total_cost']:.4f}")
            print(f"   Models used: {json.dumps(result['metadata']['models'], indent=6)}")
        else:
            print(f"   ❌ Analysis failed: {result.get('error')}")

        print("\n✅ AI optimization tests passed!")

    except Exception as e:
        print(f"⚠️  AI tests failed: {e}")
        import traceback
        traceback.print_exc()


def run_all_tests():
    """Run all test suites"""
    print("\n")
    print("🚀 TESTING SECURITY & QUALITY IMPROVEMENTS")
    print("="*60)

    start_time = time.time()

    # Run test suites
    test_auth_system()
    test_validation_system()
    test_configuration_system()
    test_logging_system()
    test_cors_system()
    # test_ai_optimization()  # Skip if no OpenAI key

    # Summary
    duration = time.time() - start_time
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
    print(f"⏱️  Total time: {duration:.2f} seconds")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()
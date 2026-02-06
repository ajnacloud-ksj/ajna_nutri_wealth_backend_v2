
import sys
import os
import json
import logging

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.handlers.analyze_async import process_async_request
from src.lib.logger import logger

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG)

def test_async_process():
    print("Testing async process with invalid image URL (UUID)...")
    
    event = {
        "source": "async-processing",
        "entry_id": "test-entry-uuid",
        "user_id": "test-user",
        "description": "Test food",
        "image_url": "some-random-uuid-key.jpg"  # Simulate the key from frontend
    }
    
    class MockContext:
        def __init__(self):
            self.aws_request_id = "test-req-id"
            
    try:
        response = process_async_request(event, MockContext())
        print("Response:", json.dumps(response, indent=2))
    except Exception as e:
        print("CRITICAL EXCEPTION CAUGHT IN TEST:", e)

if __name__ == "__main__":
    # Mock Environment variables needed for DB
    # We rely on existing .env or hardcoded fallbacks in settings if feasible
    # But settings loads from .env.
    # We need to make sure we can run this.
    
    # Ideally use user's credentials if available or skip DB if mocked.
    # The real code initializes DB.
    # We'll run this and see if it inits DB or fails.
    test_async_process()

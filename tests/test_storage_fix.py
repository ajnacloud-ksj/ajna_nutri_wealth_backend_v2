#!/usr/bin/env python3
"""Test storage upload after images table creation"""

import requests
import json

BASE_URL = "http://localhost:8080"
AUTH_TOKEN = "dev-user-1"

def test_storage_upload():
    """Test storage upload endpoint"""
    print("Testing storage upload with images table...")

    response = requests.post(
        f"{BASE_URL}/storage/upload",
        headers={
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "bucket": "test-uploads",
            "path": "test-image.png",
            "file": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==",
            "mime_type": "image/png",
            "size_bytes": 96
        }
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        print("✅ Storage upload fixed and working!")
    else:
        print("❌ Storage upload still has issues")

    return response.status_code == 200

if __name__ == "__main__":
    test_storage_upload()
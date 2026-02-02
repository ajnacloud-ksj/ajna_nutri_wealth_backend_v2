#!/usr/bin/env python3
"""
Test AI analysis with the Chicken Biryani image
Using real OpenAI API
"""

import requests
import json
import base64
import os
from pathlib import Path

# Configuration
BACKEND_URL = "http://localhost:8000/v1"
IMAGE_PATH = "/Users/pnalla/Downloads/Chicken-Biryani-Recipe.png"

# Read and encode the image
def encode_image(image_path):
    """Encode image to base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

print("="*60)
print("TESTING AI ANALYSIS WITH CHICKEN BIRYANI IMAGE")
print("="*60)

# Test 1: Text description only
print("\n1. Testing with text description only...")
text_request = {
    "description": "Chicken Biryani with basmati rice, marinated chicken pieces, fried onions, mint leaves, served with yogurt raita",
    "image_url": None
}

response = requests.post(
    f"{BACKEND_URL}/ai/analyze",
    json=text_request,
    headers={
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json"
    }
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print("✅ AI Analysis successful!")
    print(f"Category: {result.get('category')}")

    data = result.get('data', {})
    if 'food_items' in data:
        print("\n📊 Nutritional Analysis:")
        for item in data.get('food_items', []):
            print(f"  - {item['name']}:")
            print(f"    • Calories: {item.get('calories', 'N/A')}")
            print(f"    • Protein: {item.get('protein', 'N/A')}g")
            print(f"    • Carbs: {item.get('carbs', 'N/A')}g")
            print(f"    • Fat: {item.get('fat', 'N/A')}g")

        print(f"\n  Total Calories: {data.get('total_calories', 'N/A')}")
        print(f"  Meal Type: {data.get('meal_type', 'N/A')}")
        print(f"  Summary: {data.get('nutritional_summary', 'N/A')}")
        print(f"  Health Notes: {data.get('health_notes', 'N/A')}")
else:
    print(f"❌ Failed: {response.text[:500]}")

# Test 2: With image URL (base64)
print("\n2. Testing with image analysis...")
if os.path.exists(IMAGE_PATH):
    image_base64 = encode_image(IMAGE_PATH)
    image_url = f"data:image/png;base64,{image_base64}"

    image_request = {
        "description": "Analyze this Chicken Biryani dish",
        "image_url": image_url
    }

    print("Sending image for analysis (this may take a moment)...")
    response = requests.post(
        f"{BACKEND_URL}/ai/analyze",
        json=image_request,
        headers={
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json"
        },
        timeout=60  # Longer timeout for image analysis
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print("✅ Image Analysis successful!")
        print(f"Category: {result.get('category')}")

        data = result.get('data', {})
        if 'food_items' in data:
            print("\n📊 Nutritional Analysis from Image:")
            for item in data.get('food_items', []):
                print(f"  - {item['name']}:")
                print(f"    • Calories: {item.get('calories', 'N/A')}")
                print(f"    • Protein: {item.get('protein', 'N/A')}g")
                print(f"    • Carbs: {item.get('carbs', 'N/A')}g")
                print(f"    • Fat: {item.get('fat', 'N/A')}g")

            print(f"\n  Total Calories: {data.get('total_calories', 'N/A')}")
            print(f"  Meal Type: {data.get('meal_type', 'N/A')}")
            print(f"  Summary: {data.get('nutritional_summary', 'N/A')}")
            print(f"  Health Notes: {data.get('health_notes', 'N/A')}")

        # Now create a food entry with this data
        print("\n3. Creating food entry from analysis...")
        food_entry = {
            "description": "Chicken Biryani",
            "meal_type": data.get('meal_type', 'dinner'),
            "meal_date": "2026-01-26",
            "calories": data.get('total_calories', 0),
            "total_protein": sum(item.get('protein', 0) for item in data.get('food_items', [])),
            "total_carbohydrates": sum(item.get('carbs', 0) for item in data.get('food_items', [])),
            "total_fats": sum(item.get('fat', 0) for item in data.get('food_items', [])),
            "user_id": "local-dev-user",
            "ingredients": json.dumps(data.get('food_items', [])),
            "extracted_nutrients": json.dumps(data)
        }

        create_response = requests.post(
            f"{BACKEND_URL}/food_entries",
            json=food_entry,
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json"
            }
        )

        if create_response.status_code in [200, 201]:
            created = create_response.json()
            print(f"✅ Food entry created with ID: {created.get('id')}")
        else:
            print(f"❌ Failed to create entry: {create_response.text[:200]}")
    else:
        print(f"❌ Failed: {response.text[:500]}")
else:
    print(f"⚠️ Image not found at {IMAGE_PATH}")

print("\n" + "="*60)
print("✅ Test complete!")
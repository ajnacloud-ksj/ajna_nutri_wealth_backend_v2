#!/usr/bin/env python3
"""
Create fresh Ibex tables with app_ prefix
"""

import requests
import json
from datetime import datetime

# Configuration
API_URL = "https://smartlink.ajna.cloud/ibexdb"
API_KEY = "McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl"
TENANT_ID = "test-tenant"
NAMESPACE = "default"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY
}

def call_ibex(operation_payload):
    """Make a call to Ibex API"""
    payload = {
        "tenant_id": TENANT_ID,
        "namespace": NAMESPACE,
        **operation_payload
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ibex Error: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                print(f"Details: {e.response.json()}")
            except:
                print(f"Response: {e.response.text}")
        return None

# Tables with clean schemas - using app_ prefix
tables = {
    "app_users": {
        "fields": {
            "id": {"type": "string", "required": True},
            "email": {"type": "string", "required": False},
            "full_name": {"type": "string", "required": False},
            "role": {"type": "string", "required": False},
            "user_type": {"type": "string", "required": False},
            "is_subscribed": {"type": "boolean", "required": False},
            "trial_used_today": {"type": "boolean", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "app_food_entries": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "description": {"type": "string", "required": False},
            "meal_type": {"type": "string", "required": False},
            "meal_date": {"type": "string", "required": False},
            "meal_time": {"type": "string", "required": False},
            "calories": {"type": "double", "required": False},
            "total_protein": {"type": "double", "required": False},
            "total_carbohydrates": {"type": "double", "required": False},
            "total_fats": {"type": "double", "required": False},
            "total_fiber": {"type": "double", "required": False},
            "total_sodium": {"type": "double", "required": False},
            "ingredients": {"type": "string", "required": False},
            "extracted_nutrients": {"type": "string", "required": False},
            "confidence_score": {"type": "double", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "app_pending_analyses": {
        "fields": {
            "id": {"type": "string", "required": True},
            "user_id": {"type": "string", "required": True},
            "status": {"type": "string", "required": False},
            "category": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "created_at": {"type": "string", "required": False},
            "updated_at": {"type": "string", "required": False}
        }
    },
    "app_models": {
        "fields": {
            "id": {"type": "string", "required": True},
            "model_id": {"type": "string", "required": False},
            "provider": {"type": "string", "required": False},
            "name": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "is_active": {"type": "boolean", "required": False},
            "is_default": {"type": "boolean", "required": False},
            "created_at": {"type": "string", "required": False}
        }
    },
    "app_prompts": {
        "fields": {
            "id": {"type": "string", "required": True},
            "category": {"type": "string", "required": False},
            "name": {"type": "string", "required": False},
            "system_prompt": {"type": "string", "required": False},
            "user_prompt_template": {"type": "string", "required": False},
            "is_active": {"type": "boolean", "required": False},
            "created_at": {"type": "string", "required": False}
        }
    }
}

print("=== Creating Fresh Tables with app_ prefix ===\n")

for table_name, schema in tables.items():
    print(f"Creating {table_name}...")
    result = call_ibex({
        "operation": "CREATE_TABLE",
        "table": table_name,
        "schema": schema
    })

    if result and result.get('success'):
        print(f"  ✓ Created {table_name}")
    else:
        print(f"  ⚠️  {table_name} may already exist")

print("\n=== Setting up default data ===\n")

# Create default user
user_record = {
    "id": "local-dev-user",
    "email": "test@example.com",
    "full_name": "Test User",
    "role": "user",
    "user_type": "participant",
    "is_subscribed": False,
    "trial_used_today": False,
    "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
}

result = call_ibex({
    "operation": "WRITE",
    "table": "app_users",
    "records": [user_record]
})

if result and result.get('success'):
    print("✓ Created default user")
else:
    print("⚠️ Could not create default user")

# Create default model
model_record = {
    "id": "default-gpt4o-mini",
    "model_id": "gpt-4o-mini",
    "provider": "openai",
    "name": "GPT-4 Optimized Mini",
    "description": "Fast and cost-effective GPT-4 model",
    "is_active": True,
    "is_default": True,
    "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
}

result = call_ibex({
    "operation": "WRITE",
    "table": "app_models",
    "records": [model_record]
})

if result and result.get('success'):
    print("✓ Created default model")
else:
    print("⚠️ Could not create default model")

# Create food analysis prompt
prompt_record = {
    "id": "food-prompt-v1",
    "category": "food",
    "name": "Food Analysis Prompt",
    "system_prompt": """You are an expert nutritionist AI. Analyze food descriptions and images to provide detailed nutritional information.
Always return valid JSON with this structure:
{
  "food_items": [{"name": "string", "calories": number, "protein": number, "carbs": number, "fat": number, "fiber": number, "sodium": number}],
  "total_calories": number,
  "meal_type": "breakfast|lunch|dinner|snack",
  "nutritional_summary": "string",
  "health_notes": "string"
}""",
    "user_prompt_template": "Analyze this food: {description}",
    "is_active": True,
    "created_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
}

result = call_ibex({
    "operation": "WRITE",
    "table": "app_prompts",
    "records": [prompt_record]
})

if result and result.get('success'):
    print("✓ Created food analysis prompt")
else:
    print("⚠️ Could not create prompt")

print("\n✅ Fresh tables created successfully!")
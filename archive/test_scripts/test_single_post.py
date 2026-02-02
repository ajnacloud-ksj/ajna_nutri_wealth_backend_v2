import requests
import json

url = "http://localhost:8000/v1/food_entries"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer test-token"
}
data = {
    "description": "Test meal",
    "meal_type": "lunch",
    "calories": 500,
    "user_id": "test-user"
}

response = requests.post(url, headers=headers, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:500]}")

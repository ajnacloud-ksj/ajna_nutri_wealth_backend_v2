
import requests
import time
import datetime

API_URL = "http://localhost:8000"

def reset_and_seed():
    print("🔥 1. Resetting Database (Skipped - manually cleaned)...")
    # res = requests.post(f"{API_URL}/v1/system/reset-database")
    # if res.status_code == 200:
    #     print("✅ Database Reset Complete.")
    # else:
    #     print(f"❌ Reset Failed: {res.text}")
    #     return

    print("\n⚙️ 2. Initializing Schemas...")
    time.sleep(5) # Wait for Ibex to process drops
    res = requests.post(f"{API_URL}/v1/system/initialize-schemas")
    if res.status_code == 200:
        print("✅ Tables Created.")
    else:
        print(f"❌ Init Failed: {res.text}")
        return

    print("\n👤 3. Seeding 'local-dev-user'...")
    user_payload = {
        "id": "local-dev-user",
        "email": "dev@local.com",
        "full_name": "Local Developer",
        "role": "admin",
        "user_type": "standard",
        "subscription_id": None,
        "is_subscribed": False,
        "trial_used_today": 0,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }
    
    # Generic create endpoint for 'users' table
    res = requests.post(f"{API_URL}/v1/users", json=user_payload)
    if res.status_code == 200:
        print("✅ User Created: local-dev-user")
    else:
        print(f"❌ Seeding Failed: {res.text}")

if __name__ == "__main__":
    reset_and_seed()

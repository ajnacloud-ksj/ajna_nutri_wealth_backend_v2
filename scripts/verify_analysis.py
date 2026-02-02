
import requests
import json
import os
import time

# Configuration
API_URL = "http://localhost:8000"
TEST_IMAGE = "docs/test-assets/test-biryani.png"

def verify_analysis():
    print(f"🔍 Starting Analysis Verification against {API_URL}...\n")

    # 1. Upload Image
    print("👉 1. Uploading Image...")
    try:
        # Check if file exists
        if not os.path.exists(TEST_IMAGE):
            # Try absolute path from user prompt if relative fails
            TEST_IMAGE_ABS = "/Users/parameshnalla/ajna/ajna-expriements/food-sense-ai-tracker-3b84f458/docs/test-assets/test-biryani.png"
            if os.path.exists(TEST_IMAGE_ABS):
                image_path = TEST_IMAGE_ABS
            else:
                print(f"❌ Test image not found at {TEST_IMAGE} or {TEST_IMAGE_ABS}")
                # Create dummy image if needed? No, relying on user file.
                return
        else:
            image_path = TEST_IMAGE

        with open(image_path, 'rb') as f:
            file_content = f.read()
            import base64
            b64_content = base64.b64encode(file_content).decode('utf-8')
            # Prepend header for IbexClient detection
            b64_payload = f"data:image/png;base64,{b64_content}"

        payload = {
            "path": f"tests/analysis/{int(time.time())}_biryani.png",
            "file": b64_payload,
            "mime_type": "image/png",
            "size_bytes": len(file_content)
        }

        res = requests.post(f"{API_URL}/storage/upload", json=payload)
        
        if res.status_code != 200:
            print(f"❌ Upload Failed: {res.text}")
            return

        upload_data = res.json()
        s3_key = upload_data.get('s3_key')
        print(f"✅ Upload Successful. Key: {s3_key}")

        # 2. Analyze Image
        print("\n👉 2. Calling AI Analysis...")
        # Payload for analysis: url (as S3 key)
        # Endpoint: POST /v1/ai/analyze
        
        analyze_payload = {
            "imageUrl": s3_key, # New logic supports raw key
            "description": "Plate of Biryani"
        }
        
        # Note: Analysis might take time (OpenAI)
        print("   Sending request to OpenAI (via backend)...")
        res_ai = requests.post(f"{API_URL}/v1/ai/analyze", json=analyze_payload, timeout=60)
        
        if res_ai.status_code == 200:
            data = res_ai.json()
            print("✅ Analysis Successful!")
            # print(f"   Response: {json.dumps(data, indent=2)}")
            
            # Check structure
            category = data.get('category')
            print(f"   Category Detected: {category}")
            
            stored = data.get('stored_entry')
            if stored:
                print(f"   ✅ Result Stored in DB. Entry ID: {stored.get('id')}")
                print(f"   Stored Meal: {stored.get('meal_type')}")
                print(f"   Calories: {stored.get('calories')}")
                
                # 3. Verify Storage by Re-fetching? (Optional)
                # GET /v1/food_entries/{id}
                entry_id = stored.get('id')
                print(f"\n👉 3. Verifying Stored Entry (GET /v1/food_entries/{entry_id})...")
                res_get = requests.get(f"{API_URL}/v1/food_entries/{entry_id}")
                if res_get.status_code == 200:
                    print("✅ Fetched Stored Entry Successfully.")
                else:
                    print(f"⚠️ Could not fetch stored entry: {res_get.status_code}")
            else:
                print("⚠️ Result NOT stored (missing 'stored_entry' in response). check logs.")
                if 'warning' in data:
                    print(f"   Warning: {data['warning']}")

        else:
            print(f"❌ Analysis Failed. Status: {res_ai.status_code}")
            print(f"   Error: {res_ai.text}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_analysis()

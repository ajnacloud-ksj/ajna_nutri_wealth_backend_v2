import requests

API_URL = "http://localhost:8000"

def create_database():
    """Create the database instance if it doesn't exist"""
    print("🏗️  Creating database instance...")
    
    # Try to call a custom endpoint or use Ibex directly
    # First, let's try to create via a new endpoint
    res = requests.post(f"{API_URL}/v1/system/create-database")
    
    if res.status_code == 200:
        print("✅ Database Created")
        return True
    else:
        print(f"❌ Create Failed: {res.text}")
        return False

if __name__ == "__main__":
    if create_database():
        print("\n✅ Database ready. You can now run reset_and_seed.py")
    else:
        print("\n❌ Database creation failed. Manual intervention needed.")


import os
import sys
import json
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from lib.ibex_client import IbexClient
except ImportError:
    print("Could not import IbexClient")
    sys.exit(1)

def test_ibex_storage():
    print("Testing Ibex Proxy Storage...")
    
    # Load env from root
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    
    api_url = os.environ.get('IBEX_API_URL')
    api_key = os.environ.get('IBEX_API_KEY')
    
    if not api_url:
        print("❌ IBEX_API_URL not set")
        return

    client = IbexClient(api_url, api_key, "test-tenant")
    
    try:
        # Test Upload
        print("\nTesting upload...")
        # Simulating base64 image or raw text
        content = "Hello Ibex Storage Proxy!"
        
        # We need to manually call upload_file if I added it
        if hasattr(client, 'upload_file'):
            res = client.upload_file(content, "test_proxy.txt", "text/plain")
            if res['success']:
                print(f"✅ Upload successful!")
                print(f"   Key: {res['key']}")
                # URL acts as identifier now (same as key)
                
                # Test Download URL
                print("\nTesting download URL generation...")
                dl_res = client.get_download_url(res['key'])
                if dl_res.get('success'):
                    print(f"✅ Download URL: {dl_res['data']['download_url']}")
                else:
                    print(f"❌ Failed to get download URL: {dl_res.get('error')}")
                    
            else:
                print(f"❌ Upload failed: {res.get('error')}")
        else:
            print("❌ IbexClient does not have upload_file method yet (update failed?)")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ibex_storage()

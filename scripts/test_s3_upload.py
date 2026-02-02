
import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Add parent dir to sys.path to import utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_s3_access():
    print("Testing S3 Access...")
    
    # Load env
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    
    bucket = os.environ.get('S3_BUCKET_NAME')
    print(f"Bucket: {bucket}")
    
    if not bucket:
        print("❌ S3_BUCKET_NAME not set in .env")
        return

    try:
        from utils.aws_s3 import S3Client
        s3 = S3Client()
        
        # Test 1: List objects (check read access)
        print("\nChecking list objects access...")
        s3.s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        print("✅ List objects successful")
        
        # Test 2: Upload file
        print("\nTesting upload...")
        test_content = b"Hello S3 from Food Sense AI"
        res = s3.upload_file(test_content, file_name="test_s3_verify.txt", content_type="text/plain")
        
        if res['success']:
            print(f"✅ Upload successful: {res['url']}")
            print(f"   Key: {res['key']}")
            
            # Test 3: Generate Presigned URL
            print("\nTesting presigned URL...")
            url = s3.generate_presigned_url(res['key'])
            print(f"✅ Presigned URL: {url}")
            
        else:
             print(f"❌ Upload failed: {res.get('error')}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_s3_access()

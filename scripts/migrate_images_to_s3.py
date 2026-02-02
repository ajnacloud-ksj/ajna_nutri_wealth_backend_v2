#!/usr/bin/env python3
"""
Migration script to move base64 images to S3
This script will migrate existing base64-encoded images in the database to S3 storage
"""

import sys
import os
import json
import base64
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lib.ibex_client_optimized import IbexClient
from src.config.settings import settings


def upload_base64_to_s3(db, base64_image: str, user_id: str, record_id: str, record_type: str = 'receipt'):
    """
    Upload a base64 image to S3 and return the S3 URL
    """
    try:
        # Remove data URL prefix if present
        if base64_image.startswith('data:'):
            # Extract the base64 part from data URL
            header, base64_data = base64_image.split(',', 1)
            # Extract mime type from header
            mime_type = header.split(':')[1].split(';')[0]
            file_extension = mime_type.split('/')[-1]
        else:
            base64_data = base64_image
            mime_type = 'image/jpeg'  # Default mime type
            file_extension = 'jpg'

        # Generate unique filename
        filename = f"{record_type}s/{user_id}/{record_id}.{file_extension}"

        # Upload to S3
        result = db.upload_file(base64_data, filename, mime_type)

        if result.get('success'):
            s3_url = result.get('url')
            print(f"✅ Uploaded {record_type} {record_id} image to S3: {s3_url}")
            return s3_url
        else:
            print(f"❌ Failed to upload {record_type} {record_id}: {result.get('error')}")
            return None

    except Exception as e:
        print(f"❌ Error uploading {record_type} {record_id}: {e}")
        return None


def migrate_table(db, table_name: str, record_type: str = 'receipt'):
    """
    Migrate all base64 images in a table to S3
    """
    print(f"\n{'='*60}")
    print(f"📊 Migrating {table_name}...")
    print(f"{'='*60}")

    try:
        # Query all records
        result = db.query(table_name, limit=1000)

        if not result.get('success'):
            print(f"❌ Failed to query {table_name}: {result.get('error')}")
            return 0

        records = result.get('data', {}).get('records', [])
        print(f"📋 Found {len(records)} total records in {table_name}")

        migrated_count = 0
        skipped_count = 0
        failed_count = 0

        for record in records:
            record_id = record.get('id')
            user_id = record.get('user_id', 'unknown')
            image_url = record.get('image_url', '')

            # Check if image needs migration
            if not image_url:
                skipped_count += 1
                continue

            if image_url.startswith('data:'):
                # This is base64 data - needs migration
                print(f"\n🔄 Migrating {record_type} {record_id}...")

                # Calculate size of base64 data
                base64_size = len(image_url) / 1024  # KB
                print(f"   📦 Base64 size: {base64_size:.2f} KB")

                # Upload to S3
                s3_url = upload_base64_to_s3(db, image_url, user_id, record_id, record_type)

                if s3_url:
                    # Update record with S3 URL
                    update_data = {
                        'image_url': s3_url,
                        'image_storage_type': 's3',
                        'updated_at': datetime.utcnow().isoformat()
                    }

                    # Update the record
                    update_result = db.update(table_name, record_id, update_data)

                    if update_result.get('success'):
                        migrated_count += 1
                        print(f"   ✅ Successfully migrated to S3")
                    else:
                        failed_count += 1
                        print(f"   ❌ Failed to update database: {update_result.get('error')}")
                else:
                    failed_count += 1
                    print(f"   ❌ Failed to upload to S3")

            elif image_url.startswith('s3://') or image_url.startswith('http'):
                # Already using S3 or external URL - skip
                print(f"⏭️  Skipping {record_type} {record_id} - already using S3/URL")
                skipped_count += 1
            else:
                # Unknown format
                print(f"⚠️  Unknown image format for {record_type} {record_id}: {image_url[:50]}...")
                skipped_count += 1

        print(f"\n{'='*60}")
        print(f"📊 Migration Summary for {table_name}:")
        print(f"   ✅ Migrated: {migrated_count}")
        print(f"   ⏭️  Skipped: {skipped_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📋 Total: {len(records)}")
        print(f"{'='*60}")

        return migrated_count

    except Exception as e:
        print(f"❌ Error migrating {table_name}: {e}")
        return 0


def main():
    """
    Main migration function
    """
    print("\n🚀 Starting Base64 to S3 Migration")
    print("="*60)

    # Initialize IbexClient
    db = IbexClient(
        ibex_url=settings.IBEX_URL,
        tenant_id=settings.TENANT_ID,
        table_prefix=settings.TABLE_PREFIX
    )

    total_migrated = 0

    # Migrate receipts
    total_migrated += migrate_table(db, 'app_receipts', 'receipt')

    # Migrate food entries
    total_migrated += migrate_table(db, 'app_food_entries_v2', 'food')

    # Migrate workouts
    total_migrated += migrate_table(db, 'app_workouts', 'workout')

    print("\n" + "="*60)
    print("✨ Migration Complete!")
    print(f"📊 Total images migrated to S3: {total_migrated}")
    print("="*60)

    # Test the results
    if total_migrated > 0:
        print("\n🧪 Testing migrated data...")
        test_migration(db)


def test_migration(db):
    """
    Test that migration worked by checking a few records
    """
    try:
        # Test receipts
        result = db.query('app_receipts', limit=5)
        if result.get('success'):
            receipts = result.get('data', {}).get('records', [])
            for receipt in receipts:
                image_url = receipt.get('image_url', '')
                if image_url:
                    if image_url.startswith('data:'):
                        print(f"⚠️  Receipt {receipt['id']} still has base64 data!")
                    elif image_url.startswith('s3://'):
                        # Try to get presigned URL
                        s3_key = image_url.replace('s3://', '').split('/', 1)[1]
                        url_result = db.get_download_url(s3_key)
                        if url_result.get('success'):
                            print(f"✅ Receipt {receipt['id']} has valid S3 URL")
                        else:
                            print(f"❌ Receipt {receipt['id']} S3 URL invalid")

    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    # Add confirmation prompt
    print("\n⚠️  WARNING: This will migrate all base64 images to S3")
    print("This may take several minutes and incur S3 storage costs.")
    response = input("\nDo you want to continue? (yes/no): ")

    if response.lower() == 'yes':
        main()
    else:
        print("Migration cancelled.")
        sys.exit(0)
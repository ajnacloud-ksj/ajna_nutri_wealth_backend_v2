import boto3
import argparse
import sys

def cleanup_cognito():
    parser = argparse.ArgumentParser(description='Delete AWS Cognito User Pool')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pool-id', help='ID of the User Pool to delete')
    group.add_argument('--pool-name', help='Name of the User Pool to find and delete')
    parser.add_argument('--force', action='store_true', help='Force deletion without confirmation')
    
    args = parser.parse_args()
    
    try:
        client = boto3.client('cognito-idp')
    except Exception as e:
        print(f"Error initializing boto3 client: {e}")
        sys.exit(1)

    pool_id = args.pool_id

    # If pool name is provided, find the ID
    if args.pool_name:
        print(f"Searching for pool with name: {args.pool_name}...")
        try:
            paginator = client.get_paginator('list_user_pools')
            found = False
            for page in paginator.paginate(MaxResults=50):
                for pool in page['UserPools']:
                    if pool['Name'] == args.pool_name:
                        pool_id = pool['Id']
                        found = True
                        break
                if found:
                    break
            
            if not found:
                print(f"Error: Could not find User Pool with name '{args.pool_name}'")
                sys.exit(1)
                
            print(f"Found User Pool ID: {pool_id}")
            
        except Exception as e:
            print(f"Error searching for pool: {e}")
            sys.exit(1)

    # Confirm deletion
    if not args.force:
        confirm = input(f"WARNING: This will PERMANENTLY DELETE User Pool {pool_id}. Type 'DELETE' to confirm: ")
        if confirm != 'DELETE':
            print("Deletion cancelled.")
            sys.exit(0)

    # Delete
    try:
        print(f"Deleting User Pool {pool_id}...")
        client.delete_user_pool(UserPoolId=pool_id)
        print(f"Successfully deleted User Pool: {pool_id}")
    except client.exceptions.ResourceNotFoundException:
        print(f"Error: User Pool {pool_id} not found.")
    except Exception as e:
        print(f"Error deleting User Pool: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cleanup_cognito()

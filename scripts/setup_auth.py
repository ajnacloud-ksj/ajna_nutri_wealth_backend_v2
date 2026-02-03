import boto3
import json
import os
import argparse
import sys

def setup_cognito():
    # Parse Arguments
    parser = argparse.ArgumentParser(description='Setup AWS Cognito User Pool and Client')
    parser.add_argument('--pool-name', required=True, help='Name of the User Pool')
    parser.add_argument('--client-name', required=True, help='Name of the App Client')
    args = parser.parse_args()

    print(f"Setting up Cognito User Pool: {args.pool_name}")
    print(f"App Client Name: {args.client_name}")
    
    try:
        client = boto3.client('cognito-idp')
    except Exception as e:
        print(f"Error initializing boto3 client: {e}")
        print("Have you set up your AWS credentials?")
        sys.exit(1)
    
    pool_name = args.pool_name
    
    # 1. Create User Pool
    try:
        response = client.create_user_pool(
            PoolName=pool_name,
            Policies={
                'PasswordPolicy': {
                    'MinimumLength': 8,
                    'RequireUppercase': False,
                    'RequireLowercase': False,
                    'RequireNumbers': False,
                    'RequireSymbols': False
                }
            },
            AutoVerifiedAttributes=['email'],
            UsernameAttributes=['email'],
            MfaConfiguration='OFF'
        )
        user_pool_id = response['UserPool']['Id']
        print(f"Created User Pool: {user_pool_id}")
    except client.exceptions.InvalidParameterException as e:
        print(f"Error creating pool (might exist?): {e}")
        # Identify existing pool?? For now, just exit or continue if we could find it
        return

    # 2. Create App Client
    try:
        client_response = client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName=args.client_name,
            GenerateSecret=False, # Web apps usually don't verify secrets
            ExplicitAuthFlows=[
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_REFRESH_TOKEN_AUTH',
                'ALLOW_USER_SRP_AUTH'
            ]
        )
        client_id = client_response['UserPoolClient']['ClientId']
        print(f"Created App Client: {client_id}")
    except Exception as e:
        print(f"Error creating client: {e}")
        return

    # 3. Output for Config
    config = {
        "user_pool_id": user_pool_id,
        "user_pool_client_id": client_id,
        "region": client.meta.region_name
    }
    
    print("\nSUCCESS! Add these to your config:")
    print(json.dumps(config, indent=2))
    
    # Optional: Save to file
    with open('aws-auth-export.json', 'w') as f:
        json.dump(config, f, indent=2)

if __name__ == "__main__":
    setup_cognito()

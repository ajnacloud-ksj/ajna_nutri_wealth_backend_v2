import boto3
import json
import os

def setup_cognito():
    print("Setting up Cognito User Pool...")
    client = boto3.client('cognito-idp')
    
    pool_name = "food-sense-ai-users"
    
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
        return

    # 2. Create App Client
    try:
        client_response = client.create_user_pool_client(
            UserPoolId=user_pool_id,
            ClientName="food-sense-web",
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


import boto3
import json
import os
import sys

# Setup environment variables (simulate Lambda environment if needed)
env_vars = {
    'IBEX_API_URL': 'https://smartlink.ajna.cloud/ibexdb',
    'TENANT_ID': 'test-tenant',
    'DB_NAMESPACE': 'default',
    'IBEX_LAMBDA_NAME': 'ibex-db-lambda'
}

def check_user_data(user_id):
    # Credentials
    session = boto3.Session()
    credentials = session.get_credentials()
    current_credentials = credentials.get_frozen_credentials()
    
    print(f"   Fetching credentials from AWS Lambda config...")
    
    tenant_id = env_vars.get('TENANT_ID', 'test-tenant')
    namespace = env_vars.get('DB_NAMESPACE', 'default')
    ibex_lambda = env_vars.get('IBEX_LAMBDA_NAME', 'ibex-db-lambda')
    
    print(f"   Context: Default Tenant={tenant_id}, Namespace={namespace}, DB Lambda={ibex_lambda}")
    
    lambda_client = boto3.client('lambda')

    # Helper for Direct Invocation
    def invoke_ibex(payload):
        # Enforce tenant context
        full_payload = {**payload, "tenant_id": tenant_id, "namespace": namespace}
        
        # Wrap in API Gateway Proxy structure
        event = {
            "body": json.dumps(full_payload),
            "headers": {"x-api-key": "internal-call", "Content-Type": "application/json"},
            "httpMethod": "POST",
            "isBase64Encoded": False
        }
        
        res = lambda_client.invoke(
            FunctionName=ibex_lambda,
            InvocationType='RequestResponse',
            Payload=json.dumps(event)
        )
        response_payload = json.loads(res['Payload'].read())
        
        # Handle API Gateway style response
        if 'body' in response_payload:
            try:
                return json.loads(response_payload['body'])
            except:
                return response_payload['body']
        return response_payload

    # Check food entries for user
    print(f"\n👉 Checking ALL food entries for User {user_id}...")
    
    food_payload = {
        "operation": "QUERY",
        "table": "app_food_entries_v2",
        "filters": [{"field": "user_id", "operator": "eq", "value": user_id}],
        "limit": 100
    }
    res = invoke_ibex(food_payload)
    if res.get('success'):
        records = res.get('data', {}).get('records', [])
        print(f"   ✅ Found {len(records)} records in app_food_entries_v2")
        for r in records:
            print(f"      - {r.get('id')} | {r.get('description')} | {r.get('created_at')}")
    else:
        print(f"   ❌ Query failed: {res}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    else:
        user_id = "6153bd2a-e0f1-709e-a6d4-1039f8182d1e"
        
    check_user_data(user_id)

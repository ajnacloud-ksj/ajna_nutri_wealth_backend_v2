
import boto3
import json
import os
import sys

# Configuration
# (Simulating environment variables locally)
env_vars = {
    'IBEX_API_URL': 'https://smartlink.ajna.cloud/ibexdb',
    'TENANT_ID': 'test-tenant',
    'DB_NAMESPACE': 'default',
    'IBEX_LAMBDA_NAME': 'ibex-db-lambda'
}

def check_status(entry_id):
    # Credentials (uses local AWS config or env)
    session = boto3.Session()
    credentials = session.get_credentials()
    
    print(f"👉 Checking status for Entry ID: {entry_id}")
    
    tenant_id = env_vars.get('TENANT_ID', 'test-tenant')
    namespace = env_vars.get('DB_NAMESPACE', 'default')
    ibex_lambda = env_vars.get('IBEX_LAMBDA_NAME', 'ibex-db-lambda')
    
    lambda_client = boto3.client('lambda')

    def invoke_ibex(payload):
        full_payload = {**payload, "tenant_id": tenant_id, "namespace": namespace}
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
        if 'body' in response_payload:
            try:
                return json.loads(response_payload['body'])
            except:
                return response_payload['body']
        return response_payload

    # Check pending_analyses
    print("   Checking app_pending_analyses...")
    res = invoke_ibex({
        "operation": "QUERY",
        "table": "app_pending_analyses",
        "filters": [
            {"field": "id", "operator": "eq", "value": entry_id},
            {"field": "status", "operator": "ne", "value": "bust_timestamp"} 
        ],
        "limit": 1
    })
    
    status = "unknown"
    if res.get('success'):
        records = res.get('data', {}).get('records', [])
        if records:
            print(f"   ✅ FOUND in Pending Analyses! Status: {records[0].get('status')}")
            status = records[0].get('status')
        else:
            print("   ❌ NOT FOUND in Pending Analyses")
    else:
        print(f"   ❌ Query Failed: {res}")

    # Check food entries
    print("   Checking app_food_entries_v2...")
    res = invoke_ibex({
        "operation": "QUERY",
        "table": "app_food_entries_v2",
        "filters": [{"field": "id", "operator": "eq", "value": entry_id}],
        "limit": 1
    })
    if res.get('success'):
        records = res.get('data', {}).get('records', [])
        if records:
            print(f"   ✅ FOUND in Food Entries! ID: {records[0].get('id')}")
        else:
            print("   ❌ NOT FOUND in Food Entries")
    else:
        print(f"   ❌ Query Failed: {res}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        entry_id = sys.argv[1]
    else:
        entry_id = "62cda859-a39d-44a0-abd7-4c21ea9df50c"
    check_status(entry_id)

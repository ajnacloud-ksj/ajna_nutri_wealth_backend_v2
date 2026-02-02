#!/bin/bash

# Create app_users_v4 table with all fields
curl --request POST \
  --url https://smartlink.ajna.cloud/ibexdb \
  --header 'Content-Type: application/json' \
  --header 'x-api-key: McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl' \
  --data '{
  "operation": "CREATE_TABLE",
  "tenant_id": "test-tenant",
  "namespace": "default",
  "table": "app_users_v4",
  "if_not_exists": true,
  "schema": {
    "fields": {
      "id": {"type": "string", "required": true},
      "email": {"type": "string", "required": true},
      "full_name": {"type": "string", "required": false},
      "role": {"type": "string", "required": false},
      "user_type": {"type": "string", "required": false},
      "subscription_id": {"type": "string", "required": false},
      "is_subscribed": {"type": "boolean", "required": false},
      "trial_used_today": {"type": "integer", "required": false},
      "created_at": {"type": "string", "required": false},
      "updated_at": {"type": "string", "required": false}
    }
  }
}' --max-time 30

echo ""
echo "Table creation complete. Now seeding user..."

# Seed the local-dev-user
curl --request POST \
  --url https://smartlink.ajna.cloud/ibexdb \
  --header 'Content-Type: application/json' \
  --header 'x-api-key: McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl' \
  --data '{
  "operation": "WRITE",
  "tenant_id": "test-tenant",
  "namespace": "default",
  "table": "app_users_v4",
  "records": [{
    "id": "local-dev-user",
    "email": "dev@local.com",
    "full_name": "Local Developer",
    "role": "admin",
    "user_type": "standard",
    "subscription_id": null,
    "is_subscribed": false,
    "trial_used_today": 0,
    "created_at": "2026-01-27T00:00:00Z",
    "updated_at": "2026-01-27T00:00:00Z"
  }]
}' --max-time 10

echo ""
echo "Done!"

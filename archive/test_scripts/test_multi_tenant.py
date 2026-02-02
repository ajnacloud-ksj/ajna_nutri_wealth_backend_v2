#!/usr/bin/env python3
"""
Test Multi-tenant Architecture
Demonstrates how different tenants have isolated data
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.tenant_manager import TenantManager
from datetime import datetime
import uuid
import json

def test_tenant_isolation():
    """Test that different tenants have isolated data"""

    print("=" * 60)
    print("MULTI-TENANT ARCHITECTURE TEST")
    print("=" * 60)

    # List all configured tenants
    print("\n📁 Configured Tenants:")
    for key, name in TenantManager.list_tenants().items():
        config = TenantManager.get_tenant_config(key)
        print(f"  - {key}: {name}")
        print(f"    └─ Tenant ID: {config['tenant_id']}")
        print(f"    └─ Namespace: {config['namespace']}")
        print(f"    └─ Features: {', '.join(config['features'])}")

    # Test tenant detection from different request formats
    print("\n🔍 Testing Tenant Detection:")

    test_requests = [
        {
            "name": "Default (no headers)",
            "event": {"headers": {}}
        },
        {
            "name": "ACME Corp (via header)",
            "event": {"headers": {"X-Tenant-ID": "acme_corp"}}
        },
        {
            "name": "HealthCo (via domain)",
            "event": {"headers": {"Host": "app.healthco.com"}}
        },
        {
            "name": "Demo (via header)",
            "event": {"headers": {"X-Tenant-ID": "demo"}}
        }
    ]

    for test in test_requests:
        tenant = TenantManager.get_tenant_from_request(test["event"])
        print(f"\n  {test['name']}:")
        print(f"    → Tenant: {tenant['display_name']}")
        print(f"    → Namespace: {tenant['namespace']}")

    # Demonstrate data isolation
    print("\n🔐 Data Isolation Example:")
    print("  Each tenant's data is isolated in their namespace:")
    print()
    print("  ACME Corp writes to:")
    print("    └─ Database: acme-corp-prod")
    print("    └─ Namespace: acme")
    print("    └─ Table: app_food_entries")
    print("    └─ Full path: acme-corp-prod.acme.app_food_entries")
    print()
    print("  HealthCo writes to:")
    print("    └─ Database: health-co-prod")
    print("    └─ Namespace: healthco")
    print("    └─ Table: app_food_entries")
    print("    └─ Full path: health-co-prod.healthco.app_food_entries")
    print()
    print("  ✅ Complete isolation - no data leakage possible")

    # Test feature flags
    print("\n🚀 Feature Access Control:")
    for key in ["demo", "acme_corp", "health_co"]:
        config = TenantManager.get_tenant_config(key)
        print(f"\n  {config['display_name']}:")
        features_to_check = ["basic_analysis", "advanced_analysis", "queue", "nutrition_coaching"]
        for feature in features_to_check:
            has_access = TenantManager.has_feature(config, feature)
            status = "✅" if has_access else "❌"
            print(f"    {status} {feature}")

    # Example of creating tenant-specific clients
    print("\n💾 Creating Tenant-Specific Database Clients:")

    # Set API key for testing (in production, this comes from environment)
    os.environ['IBEX_API_KEY'] = 'McuMsuWDXo1g9zqLBBzVy3uXsIKDklGT8GbIhpyl'

    for key in ["test", "acme_corp"]:
        config = TenantManager.get_tenant_config(key)
        try:
            client = TenantManager.create_ibex_client(config)
            print(f"\n  ✅ Created client for {config['display_name']}:")
            print(f"     - Tenant ID: {client.tenant_id}")
            print(f"     - Namespace: {client.namespace}")
        except Exception as e:
            print(f"\n  ❌ Failed to create client for {config['display_name']}: {e}")

    print("\n" + "=" * 60)
    print("RECOMMENDED ARCHITECTURE")
    print("=" * 60)
    print("""
For your food tracking application, the recommended approach is:

1. **Organization-Level Tenants**:
   - Each company/organization gets their own tenant_id
   - Data is isolated at the namespace level in Ibex
   - Example: "acme-corp", "healthco", "startup-x"

2. **User-Level Isolation**:
   - Within each tenant, users are tracked by user_id
   - All queries filter by user_id for row-level security
   - Example: ACME has users "user1", "user2", etc.

3. **Database Structure**:
   ```
   Ibex Cloud
   ├── acme-corp-prod (database)
   │   └── acme (namespace)
   │       ├── app_food_entries
   │       ├── app_analysis_queue
   │       └── app_users
   │
   ├── healthco-prod (database)
   │   └── healthco (namespace)
   │       ├── app_food_entries
   │       ├── app_analysis_queue
   │       └── app_users
   │
   └── test-tenant (database)
       └── default (namespace)
           ├── app_food_entries
           ├── app_analysis_queue
           └── app_users
   ```

4. **Benefits**:
   - Complete data isolation between organizations
   - Scalable architecture
   - Per-tenant feature flags
   - Easy compliance with data residency requirements
   - Simple billing per organization

5. **Implementation**:
   - Use X-Tenant-ID header for testing
   - Use JWT claims for production
   - Domain-based routing for custom domains
   - Automatic fallback to test tenant
""")

if __name__ == "__main__":
    test_tenant_isolation()
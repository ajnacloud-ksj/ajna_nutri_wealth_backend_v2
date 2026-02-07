"""
Database setup and cleanup admin endpoints
"""

import json
import os
from datetime import datetime
from typing import Dict, Any

from src.lib.auth_provider_enhanced import require_admin_role
from src.lib.logger import logger, log_handler
from src.utils.http import respond

@log_handler
@require_admin_role
def setup_database(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/admin/database/setup - Set up all database tables
    """
    try:
        db = context['db']
        tenant = context.get('tenant', {})
        tenant_id = tenant.get('tenant_id', 'nutriwealth')
        namespace = tenant.get('namespace', 'default')

        logger.info(f"Setting up database for tenant: {tenant_id}, namespace: {namespace}")

        # Load schemas from the schemas directory
        schemas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')

        created_tables = []
        failed_tables = []

        # List of essential tables to create
        essential_tables = [
            'users_v4',
            'pending_analyses',
            'food_entries_v2',
            'food_items',
            'receipts',
            'receipt_items',
            'workouts',
            'workout_exercises',
            'images',
            'user_goals',
            'meal_summaries',
            'health_assessments'
        ]

        for table_name in essential_tables:
            schema_file = f"{table_name}.json"
            schema_path = os.path.join(schemas_dir, schema_file)

            if not os.path.exists(schema_path):
                logger.warning(f"Schema file not found: {schema_file}")
                # Use a default schema
                schema = {
                    "fields": {
                        "id": {"type": "string", "required": True},
                        "created_at": {"type": "string", "required": True},
                        "updated_at": {"type": "string", "required": False}
                    }
                }
            else:
                with open(schema_path, 'r') as f:
                    schema = json.load(f)

            # Add app_ prefix to table name
            full_table_name = f"app_{table_name}"

            # Try to create the table
            result = db.create_table(
                table=full_table_name,
                schema=schema,
                if_not_exists=True
            )

            if result.get('success'):
                created_tables.append(full_table_name)
                logger.info(f"Created table: {full_table_name}")
            else:
                error = result.get('error', 'Unknown error')
                if 'already exists' in str(error).lower():
                    created_tables.append(full_table_name + " (already exists)")
                else:
                    failed_tables.append(f"{full_table_name}: {error}")
                    logger.error(f"Failed to create table {full_table_name}: {error}")

        # Create a default admin user if requested
        body = json.loads(event.get('body', '{}'))
        if body.get('create_admin_user'):
            admin_email = body.get('admin_email', 'admin@nutriwealth.com')
            admin_id = body.get('admin_id', 'admin-' + datetime.utcnow().strftime('%Y%m%d%H%M%S'))

            # Check if admin user exists
            admin_result = db.query("app_users_v4",
                                  filters=[
                                      {"field": "email", "operator": "eq", "value": admin_email}
                                  ],
                                  limit=1)

            if not (admin_result.get('success') and admin_result.get('data', {}).get('records')):
                # Create admin user
                admin_user = {
                    "id": admin_id,
                    "email": admin_email,
                    "name": "System Admin",
                    "role": "admin",
                    "created_at": datetime.utcnow().isoformat(),
                    "profile": json.dumps({
                        "preferences": {},
                        "settings": {"is_admin": True}
                    })
                }

                write_result = db.write("app_users_v4", [admin_user])

                if write_result.get('success'):
                    logger.info(f"Created admin user: {admin_email}")
                else:
                    logger.error(f"Failed to create admin user: {write_result.get('error')}")

        return respond(200, {
            "message": "Database setup completed",
            "tenant_id": tenant_id,
            "namespace": namespace,
            "created_tables": created_tables,
            "failed_tables": failed_tables,
            "total_tables": len(created_tables),
            "failures": len(failed_tables)
        }, event=event)

    except Exception as e:
        logger.error(f"Error setting up database: {e}", exc_info=True)
        return respond(500, {"error": f"Failed to setup database: {str(e)}"}, event=event)

@log_handler
@require_admin_role
def cleanup_database(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/admin/database/cleanup - Clean up database (remove all data)
    """
    try:
        db = context['db']
        tenant = context.get('tenant', {})
        tenant_id = tenant.get('tenant_id', 'nutriwealth')
        namespace = tenant.get('namespace', 'default')

        # Safety check - require confirmation
        body = json.loads(event.get('body', '{}'))
        confirm = body.get('confirm')

        if confirm != f"DELETE_{tenant_id}_{namespace}":
            return respond(400, {
                "error": "Confirmation required",
                "message": f"Send 'confirm': 'DELETE_{tenant_id}_{namespace}' in request body to confirm deletion"
            }, event=event)

        logger.warning(f"Starting database cleanup for tenant: {tenant_id}, namespace: {namespace}")

        # List all tables
        list_result = db.list_tables()
        if not list_result.get('success'):
            return respond(500, {"error": "Failed to list tables"}, event=event)

        tables = list_result.get('data', {}).get('tables', [])

        deleted_tables = []
        failed_deletions = []

        # Delete each table
        for table_name in tables:
            if not table_name.startswith('app_'):
                continue  # Skip non-app tables

            # Option 1: Drop the table completely
            drop_result = db.drop_table(table_name, purge=True)

            if drop_result.get('success'):
                deleted_tables.append(table_name)
                logger.info(f"Dropped table: {table_name}")
            else:
                # Option 2: If drop fails, try to delete all records
                try:
                    # Query all records
                    query_result = db.query(table_name, limit=10000)
                    if query_result.get('success'):
                        records = query_result.get('data', {}).get('records', [])

                        # Delete each record
                        for record in records:
                            if 'id' in record:
                                db.delete(table_name,
                                        filters=[{"field": "id", "operator": "eq", "value": record['id']}])

                        deleted_tables.append(f"{table_name} (data cleared)")
                        logger.info(f"Cleared data from table: {table_name}")
                    else:
                        failed_deletions.append(f"{table_name}: {drop_result.get('error')}")
                except Exception as e:
                    failed_deletions.append(f"{table_name}: {str(e)}")
                    logger.error(f"Failed to clean table {table_name}: {e}")

        return respond(200, {
            "message": "Database cleanup completed",
            "tenant_id": tenant_id,
            "namespace": namespace,
            "deleted_tables": deleted_tables,
            "failed_deletions": failed_deletions,
            "total_deleted": len(deleted_tables),
            "failures": len(failed_deletions)
        }, event=event)

    except Exception as e:
        logger.error(f"Error cleaning up database: {e}", exc_info=True)
        return respond(500, {"error": f"Failed to cleanup database: {str(e)}"}, event=event)

@log_handler
@require_admin_role
def reset_database(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/admin/database/reset - Reset database (cleanup + setup)
    """
    try:
        # First cleanup
        cleanup_result = cleanup_database(event, context)
        cleanup_body = json.loads(cleanup_result.get('body', '{}'))

        if cleanup_result.get('statusCode') != 200:
            return cleanup_result

        # Then setup
        setup_result = setup_database(event, context)
        setup_body = json.loads(setup_result.get('body', '{}'))

        if setup_result.get('statusCode') != 200:
            return setup_result

        return respond(200, {
            "message": "Database reset completed",
            "cleanup": cleanup_body,
            "setup": setup_body
        }, event=event)

    except Exception as e:
        logger.error(f"Error resetting database: {e}", exc_info=True)
        return respond(500, {"error": f"Failed to reset database: {str(e)}"}, event=event)

@log_handler
def database_health_check(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/admin/database/health - Check database health (no auth required for health checks)
    """
    try:
        db = context['db']

        # Try to list tables
        list_result = db.list_tables()

        if list_result.get('success'):
            tables = list_result.get('data', {}).get('tables', [])

            # Check essential tables
            essential_tables = ['app_users_v4', 'app_pending_analyses', 'app_food_entries_v2']
            missing_tables = []

            for table in essential_tables:
                if table not in tables:
                    missing_tables.append(table)

            if missing_tables:
                return respond(503, {
                    "status": "unhealthy",
                    "message": "Missing essential tables",
                    "missing_tables": missing_tables
                }, event=event)

            return respond(200, {
                "status": "healthy",
                "message": "Database is operational",
                "table_count": len(tables),
                "essential_tables": "present"
            }, event=event)
        else:
            return respond(503, {
                "status": "unhealthy",
                "message": "Cannot connect to database",
                "error": list_result.get('error')
            }, event=event)

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return respond(503, {
            "status": "unhealthy",
            "message": "Database health check failed",
            "error": str(e)
        }, event=event)
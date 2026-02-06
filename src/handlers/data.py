"""
Modern Data Handler with Authentication and Validation
Provides generic CRUD operations for all database tables
"""

import json
import os
from datetime import datetime
import uuid
from typing import Dict, Any, Optional, List

from lib.auth_provider import require_auth, get_user_id
from lib.validators import validate_request, ValidationError
from lib.logger import logger, log_handler
from utils.http import respond


# Table configuration
TABLE_PREFIX = 'app_'
SPECIAL_TABLES = {
    'users': 'users_v4',
    'food_entries': 'food_entries_v2'
}


def resolve_table_name(table_name: str) -> Optional[str]:
    """Resolves the database table name with correct prefix and version handling"""
    if not table_name:
        return None

    if table_name in SPECIAL_TABLES:
        return f"{TABLE_PREFIX}{SPECIAL_TABLES[table_name]}"

    if table_name.startswith(TABLE_PREFIX):
        return table_name

    return f"{TABLE_PREFIX}{table_name}"


def sanitize_json_response(data: Any) -> Any:
    """Replace NaN and other non-JSON values in response data"""
    if isinstance(data, dict):
        return {k: sanitize_json_response(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json_response(item) for item in data]
    elif isinstance(data, float):
        if data != data:  # NaN check
            return None
        return data
    elif isinstance(data, str) and data == "NaT":
        return None
    return data


@log_handler
@require_auth
def list_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/{table} - List records from a table

    Supports:
    - Filtering via query parameters
    - Sorting via order_by and order_dir
    - Pagination via limit and offset
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']
    table_name = event['pathParameters'].get('table')

    logger.info(f"Listing data from {table_name}", user_id=user_id, table=table_name)

    db_table_name = resolve_table_name(table_name)

    # Return empty array for non-existent tables
    if table_name not in schemas:
        logger.warning(f"Table {table_name} not found in schemas", user_id=user_id)
        return respond(200, [], event=event)

    # Get query parameters
    query_params = event.get('queryStringParameters') or {}
    schema_fields = schemas[table_name].get('fields', {})

    # Build filters from query parameters
    filters = []
    for key, value in query_params.items():
        if key in ['limit', 'order_by', 'order_dir', 'sort', 'offset']:
            continue
        if key in schema_fields:
            filters.append({"field": key, "operator": "eq", "value": value})

    # Handle sorting
    sort = None
    if 'order_by' in query_params:
        order_field = query_params['order_by']
        order_dir = query_params.get('order_dir', 'asc')
        if order_field in schema_fields:
            sort = [{"field": order_field, "order": order_dir}]

    # Handle pagination
    limit = min(int(query_params.get('limit', 50)), 1000)
    offset = int(query_params.get('offset', 0))

    try:
        # Execute query
        kwargs = {"limit": limit}
        if filters:
            kwargs["filters"] = filters
        if sort:
            kwargs["sort"] = sort
        if offset > 0:
            kwargs["offset"] = offset

        result = db.query(db_table_name, use_cache=False, **kwargs)

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])

            # Clean internal fields and sanitize
            cleaned_records = []
            for record in records:
                cleaned = {k: v for k, v in record.items() if not k.startswith('_')}
                cleaned = sanitize_json_response(cleaned)
                cleaned_records.append(cleaned)

            logger.info(
                f"Retrieved {len(cleaned_records)} records from {table_name}",
                user_id=user_id,
                count=len(cleaned_records)
            )

            return respond(200, cleaned_records, event=event)
        else:
            return respond(200, [], event=event)

    except Exception as e:
        logger.error(f"Query error for {table_name}: {str(e)}", user_id=user_id, error=str(e))
        # Return empty array for non-critical tables to allow app to function
        if table_name in ['care_relationships', 'users', 'food_entries']:
            logger.info(f"Returning empty array for {table_name} after error")
            return respond(200, [], event=event)
        return respond(500, {"error": "Failed to retrieve data"}, event=event)


@log_handler
@require_auth
def create_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/{table} - Create new record(s) in a table

    Automatically adds:
    - ID if not provided
    - Timestamps (created_at, updated_at)
    - User ID for user-scoped tables
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']
    table_name = event['pathParameters'].get('table')

    logger.info(f"Creating data in {table_name}", user_id=user_id, table=table_name)

    db_table_name = resolve_table_name(table_name)

    # Parse body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"}, event=event)

    # Handle batch or single
    records = body if isinstance(body, list) else [body]

    # Get schema
    schema = schemas.get(table_name, {})
    schema_fields = schema.get('fields', {})

    # Process records
    current_time = datetime.utcnow().isoformat()
    processed_records = []

    for record in records:
        if not record:
            continue

        # Auto-fill fields if schema exists
        if schema_fields:
            # Generate ID if needed
            if 'id' in schema_fields and 'id' not in record:
                record['id'] = str(uuid.uuid4())

            # Add timestamps
            if 'created_at' in schema_fields and 'created_at' not in record:
                record['created_at'] = current_time
            if 'updated_at' in schema_fields:
                record['updated_at'] = current_time

            # Add user_id for user-scoped tables (not users table itself)
            if 'user_id' in schema_fields and 'user_id' not in record and table_name != 'users':
                record['user_id'] = user_id

        processed_records.append(record)

    if not processed_records:
        return respond(400, {"error": "No valid records"}, event=event)

    try:
        result = db.write(db_table_name, processed_records)

        if result and result.get('success'):
            written_records = result.get('data', {}).get('records', processed_records)

            # Clean and sanitize
            cleaned_records = []
            for record in written_records:
                cleaned = {k: v for k, v in record.items() if not k.startswith('_')}
                cleaned = sanitize_json_response(cleaned)
                cleaned_records.append(cleaned)

            logger.info(
                f"Created {len(cleaned_records)} records in {table_name}",
                user_id=user_id,
                count=len(cleaned_records)
            )

            # Return single if input was single
            if not isinstance(body, list) and cleaned_records:
                return respond(201, cleaned_records[0], event=event)
            return respond(201, cleaned_records, event=event)
        else:
            error_msg = result.get('error') if result else "Unknown DB error"
            logger.error(f"Write failed for {table_name}: {error_msg}", user_id=user_id)
            return respond(500, {"error": f"Failed to create records: {error_msg}"}, event=event)

    except Exception as e:
        logger.error(f"Write error for {table_name}: {str(e)}", user_id=user_id, error=str(e))
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def get_data_by_id(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/{table}/{id} - Get a specific record by ID

    Automatically filters by user_id for user-scoped tables
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']
    table_name = event['pathParameters'].get('table')
    item_id = event['pathParameters'].get('id')

    logger.info(f"Getting {table_name}/{item_id}", user_id=user_id, table=table_name, id=item_id)

    db_table_name = resolve_table_name(table_name)

    if table_name not in schemas:
        return respond(404, {"error": f"Resource {table_name} not found"}, event=event)

    schema_fields = schemas[table_name].get('fields', {})

    # Build filters
    filters = [{"field": "id", "operator": "eq", "value": item_id}]

    # Add user_id filter for user-scoped tables (not users table itself)
    if 'user_id' in schema_fields and table_name != 'users' and user_id:
        filters.append({"field": "user_id", "operator": "eq", "value": user_id})

    try:
        result = db.query(db_table_name, filters=filters, limit=1)

        if result and result.get('success'):
            data = result.get('data', {})
            records = data.get('records', [])

            if not records:
                return respond(404, {"error": "Not found"}, event=event)

            # Clean and sanitize
            record = records[0]
            cleaned = {k: v for k, v in record.items() if not k.startswith('_')}
            cleaned = sanitize_json_response(cleaned)

            return respond(200, cleaned, event=event)
        else:
            return respond(404, {"error": "Not found"}, event=event)

    except Exception as e:
        logger.error(f"Get by ID error for {table_name}/{item_id}: {str(e)}", user_id=user_id)
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def update_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    PUT /v1/{table}/{id} - Update a record

    Automatically:
    - Updates the updated_at timestamp
    - Validates user ownership for user-scoped tables
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']
    table_name = event['pathParameters'].get('table')
    item_id = event['pathParameters'].get('id')

    logger.info(f"Updating {table_name}/{item_id}", user_id=user_id, table=table_name, id=item_id)

    db_table_name = resolve_table_name(table_name)

    if table_name not in schemas:
        return respond(404, {"error": f"Resource {table_name} not found"}, event=event)

    # Parse body
    try:
        updates = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"}, event=event)

    if not updates:
        return respond(400, {"error": "No updates provided"}, event=event)

    schema_fields = schemas[table_name].get('fields', {})

    # Add updated_at timestamp
    if 'updated_at' in schema_fields:
        updates['updated_at'] = datetime.utcnow().isoformat()

    # Build filters
    filters = [{"field": "id", "operator": "eq", "value": item_id}]

    # Add user_id filter for user-scoped tables
    if 'user_id' in schema_fields and table_name != 'users' and user_id:
        filters.append({"field": "user_id", "operator": "eq", "value": user_id})

    try:
        result = db.update(db_table_name, filters=filters, updates=updates)

        if result and result.get('success'):
            # Get updated record
            get_result = db.query(db_table_name, filters=[{"field": "id", "operator": "eq", "value": item_id}], limit=1)

            if get_result and get_result.get('success'):
                records = get_result.get('data', {}).get('records', [])
                if records:
                    record = records[0]
                    cleaned = {k: v for k, v in record.items() if not k.startswith('_')}
                    cleaned = sanitize_json_response(cleaned)

                    logger.info(f"Updated {table_name}/{item_id}", user_id=user_id)
                    return respond(200, cleaned, event=event)

            return respond(200, {"id": item_id, "updated": True}, event=event)
        else:
            return respond(404, {"error": "Record not found or not authorized"}, event=event)

    except Exception as e:
        logger.error(f"Update error for {table_name}/{item_id}: {str(e)}", user_id=user_id)
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def delete_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/{table}/{id} - Delete a record

    Validates user ownership for user-scoped tables
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']
    table_name = event['pathParameters'].get('table')
    item_id = event['pathParameters'].get('id')

    logger.info(f"Deleting {table_name}/{item_id}", user_id=user_id, table=table_name, id=item_id)

    db_table_name = resolve_table_name(table_name)

    if table_name not in schemas:
        return respond(404, {"error": f"Resource {table_name} not found"}, event=event)

    schema_fields = schemas[table_name].get('fields', {})

    # Build filters
    filters = [{"field": "id", "operator": "eq", "value": item_id}]

    # Add user_id filter for user-scoped tables
    if 'user_id' in schema_fields and table_name != 'users' and user_id:
        filters.append({"field": "user_id", "operator": "eq", "value": user_id})

    try:
        result = db.delete(db_table_name, filters=filters)

        if result and result.get('success'):
            logger.info(f"Deleted {table_name}/{item_id}", user_id=user_id)
            return respond(204, None, event=event)
        else:
            return respond(404, {"error": "Record not found or not authorized"}, event=event)

    except Exception as e:
        logger.error(f"Delete error for {table_name}/{item_id}: {str(e)}", user_id=user_id)
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def initialize_schemas(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/system/initialize-schemas - Initialize database tables

    Admin only endpoint to create all tables
    """
    user_id = get_user_id(event)
    db = context['db']
    schemas = context['schemas']

    logger.info("Initializing database schemas", user_id=user_id)

    # TODO: Add admin role check here
    # if not is_admin(user_id):
    #     return respond(403, {"error": "Admin access required"}, event=event)

    results = {}
    try:
        existing_response = db.list_tables()
        existing = existing_response.get('data', {}).get('tables', [])

        for table, schema in schemas.items():
            db_table_name = resolve_table_name(table)

            if db_table_name in existing:
                results[table] = f"Exists ({db_table_name})"
            else:
                try:
                    # Convert schema to Ibex format
                    ibex_schema = {"fields": {}}

                    type_mapping = {
                        "string": "string",
                        "integer": "integer",
                        "boolean": "boolean",
                        "timestamp": "string",
                        "text": "string",
                        "double": "double",
                        "long": "long",
                        "float": "double"
                    }

                    for field_name, field_config in schema.get("fields", {}).items():
                        field_type = field_config.get("type", "string")
                        ibex_type = type_mapping.get(field_type, "string")
                        ibex_schema["fields"][field_name] = {
                            "type": ibex_type,
                            "required": field_config.get("required", False)
                        }

                    logger.debug(f"Creating table {db_table_name}")
                    db.create_table(db_table_name, ibex_schema, if_not_exists=True)
                    results[table] = f"Created ({db_table_name})"

                except Exception as e:
                    logger.error(f"Failed to create table {table}: {e}")
                    results[table] = f"Error: {str(e)}"

        logger.info("Schema initialization complete", results=results)
        return respond(200, results, event=event)

    except Exception as e:
        logger.error(f"Schema initialization error: {e}")
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def create_database(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/system/create-database - Create database if it doesn't exist

    Admin only endpoint to create the database
    """
    user_id = get_user_id(event)
    db = context['db']

    logger.info("Creating database", user_id=user_id)

    # TODO: Add admin role check here

    try:
        result = db.create_database()
        if result and result.get('success'):
            logger.info("Database created successfully", user_id=user_id)
            return respond(200, {"message": "Database created successfully"}, event=event)
        else:
            return respond(500, {"error": "Failed to create database"}, event=event)
    except Exception as e:
        # If database already exists, that's fine
        if "already exists" in str(e).lower():
            logger.info("Database already exists", user_id=user_id)
            return respond(200, {"message": "Database already exists"}, event=event)
        logger.error(f"Create database error: {e}", user_id=user_id)
        return respond(500, {"error": str(e)}, event=event)


@log_handler
@require_auth
def reset_database(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/system/reset-database - WIPE ALL DATA

    WARNING: This deletes ALL tables. Use with caution.
    Admin only endpoint
    """
    user_id = get_user_id(event)
    db = context['db']

    logger.warning("DATABASE RESET REQUESTED", user_id=user_id)

    # TODO: Add admin role check here - CRITICAL!

    results = {}
    try:
        existing_response = db.list_tables()
        existing = existing_response.get('data', {}).get('tables', [])

        for table in existing:
            try:
                db.drop_table(table)
                results[table] = "Dropped"
                logger.info(f"Dropped table: {table}", user_id=user_id)
            except Exception as e:
                logger.error(f"Failed to drop table {table}: {e}", user_id=user_id)
                results[table] = f"Error: {str(e)}"

        logger.warning("DATABASE RESET COMPLETE", user_id=user_id, results=results)
        return respond(200, results, event=event)

    except Exception as e:
        logger.error(f"Reset database error: {e}", user_id=user_id)
        return respond(500, {"error": str(e)}, event=event)

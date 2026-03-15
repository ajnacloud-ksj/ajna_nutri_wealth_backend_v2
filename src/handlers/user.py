"""
User Profile Handler
Provides endpoints for user profile management, data export, and account deletion
"""

import json
from typing import Dict, Any
from lib.auth_provider import require_auth, get_user_id
from lib.auth_sync import sync_user_from_token
from ajna_cloud import logger, log_handler, respond
from utils.timestamps import utc_now


@log_handler
@require_auth
def get_current_user(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/user/profile - Get current user's profile with role information
    """
    user_id = get_user_id(event)
    db = context['db']

    logger.info(f"Getting user profile for {user_id}")

    # Try to sync user from token first (in case role was updated externally)
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization') or headers.get('authorization') or ''
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        sync_user_from_token(token, db)

    try:
        result = db.query(
            "app_users_v4",
            filters=[{"field": "id", "operator": "eq", "value": user_id}],
            limit=1,
            use_cache=False,
            include_deleted=False
        )

        if result and result.get('success'):
            records = result.get('data', {}).get('records', [])
            if records:
                user_data = records[0]
                cleaned_user = {k: v for k, v in user_data.items() if not k.startswith('_')}
                return respond(200, cleaned_user, event=event)
            else:
                return respond(404, {"error": "User not found"}, event=event)
        else:
            return respond(500, {"error": "Failed to retrieve user profile"}, event=event)

    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return respond(500, {"error": "Internal server error"}, event=event)


@log_handler
@require_auth
def export_user_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/user/export - Export all user data as JSON
    Returns all food entries, receipts, workouts, shopping lists, and profile data.
    """
    user_id = get_user_id(event)
    db = context['db']

    logger.info(f"Exporting all data for user {user_id}")

    try:
        export = {"exported_at": utc_now(), "user_id": user_id}

        # Tables to export with their user_id field name
        tables = [
            ("app_users_v4", "id", "profile"),
            ("app_food_entries_v2", "user_id", "food_entries"),
            ("app_food_items", None, None),  # joined via food_entry_id
            ("app_receipts", "user_id", "receipts"),
            ("app_receipt_items", None, None),  # joined via receipt_id
            ("app_workouts", "user_id", "workouts"),
            ("app_workout_exercises", None, None),  # joined via workout_id
            ("app_shopping_lists", "user_id", "shopping_lists"),
            ("app_shopping_list_items", "user_id", "shopping_list_items"),
            ("app_user_goals", "user_id", "goals"),
            ("app_health_assessments", "user_id", "health_assessments"),
        ]

        # Export direct user tables
        for table, user_field, export_key in tables:
            if user_field is None:
                continue
            try:
                result = db.query(
                    table,
                    filters=[{"field": user_field, "operator": "eq", "value": user_id}],
                    limit=10000,
                    include_deleted=False
                )
                if result and result.get('success'):
                    records = result.get('data', {}).get('records', [])
                    # Clean internal fields
                    cleaned = [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]
                    export[export_key] = cleaned
                else:
                    export[export_key] = []
            except Exception as e:
                logger.warning(f"Could not export {table}: {e}")
                export[export_key] = []

        # Export food items (joined via food_entry_id from food entries)
        food_entry_ids = [e.get('id') for e in export.get('food_entries', []) if e.get('id')]
        if food_entry_ids:
            all_food_items = []
            for entry_id in food_entry_ids:
                try:
                    result = db.query(
                        "app_food_items",
                        filters=[{"field": "food_entry_id", "operator": "eq", "value": entry_id}],
                        limit=100,
                        include_deleted=False
                    )
                    if result and result.get('success'):
                        items = result.get('data', {}).get('records', [])
                        all_food_items.extend([{k: v for k, v in r.items() if not k.startswith('_')} for r in items])
                except Exception:
                    pass
            export["food_items"] = all_food_items

        # Export receipt items (joined via receipt_id from receipts)
        receipt_ids = [r.get('id') for r in export.get('receipts', []) if r.get('id')]
        if receipt_ids:
            all_receipt_items = []
            for receipt_id in receipt_ids:
                try:
                    result = db.query(
                        "app_receipt_items",
                        filters=[{"field": "receipt_id", "operator": "eq", "value": receipt_id}],
                        limit=500,
                        include_deleted=False
                    )
                    if result and result.get('success'):
                        items = result.get('data', {}).get('records', [])
                        all_receipt_items.extend([{k: v for k, v in r.items() if not k.startswith('_')} for r in items])
                except Exception:
                    pass
            export["receipt_items"] = all_receipt_items

        # Export workout exercises (joined via workout_id)
        workout_ids = [w.get('id') for w in export.get('workouts', []) if w.get('id')]
        if workout_ids:
            all_exercises = []
            for workout_id in workout_ids:
                try:
                    result = db.query(
                        "app_workout_exercises",
                        filters=[{"field": "workout_id", "operator": "eq", "value": workout_id}],
                        limit=500,
                        include_deleted=False
                    )
                    if result and result.get('success'):
                        items = result.get('data', {}).get('records', [])
                        all_exercises.extend([{k: v for k, v in r.items() if not k.startswith('_')} for r in items])
                except Exception:
                    pass
            export["workout_exercises"] = all_exercises

        # Summary
        summary = {}
        for key in ["food_entries", "food_items", "receipts", "receipt_items",
                     "workouts", "workout_exercises", "shopping_lists", "shopping_list_items",
                     "goals", "health_assessments"]:
            summary[key] = len(export.get(key, []))
        export["summary"] = summary

        logger.info(f"Data export complete for user {user_id}: {json.dumps(summary)}")
        return respond(200, export, event=event)

    except Exception as e:
        logger.error(f"Error exporting user data: {str(e)}", exc_info=True)
        return respond(500, {"error": "Failed to export data"}, event=event)


@log_handler
@require_auth
def delete_account(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/user/account - Permanently delete all user data
    Requires confirmation string in request body.
    """
    user_id = get_user_id(event)
    db = context['db']

    body = json.loads(event.get('body', '{}'))
    confirm = body.get('confirm')

    if confirm != "DELETE_MY_ACCOUNT":
        return respond(400, {
            "error": "Confirmation required",
            "message": "Send {'confirm': 'DELETE_MY_ACCOUNT'} in request body"
        }, event=event)

    logger.warning(f"Account deletion requested for user {user_id}")

    try:
        deleted = {}

        # First collect parent IDs for cascade deletes
        food_entry_ids = []
        receipt_ids = []
        workout_ids = []

        for table, id_list, query_table in [
            ("app_food_entries_v2", food_entry_ids, "app_food_entries_v2"),
            ("app_receipts", receipt_ids, "app_receipts"),
            ("app_workouts", workout_ids, "app_workouts"),
        ]:
            try:
                result = db.query(
                    query_table,
                    filters=[{"field": "user_id", "operator": "eq", "value": user_id}],
                    projection=["id"],
                    limit=10000,
                    include_deleted=False
                )
                if result and result.get('success'):
                    for r in result.get('data', {}).get('records', []):
                        if r.get('id'):
                            id_list.append(r['id'])
            except Exception:
                pass

        # Delete child records first
        for entry_id in food_entry_ids:
            try:
                db.delete("app_food_items", filters=[{"field": "food_entry_id", "operator": "eq", "value": entry_id}])
            except Exception:
                pass

        for receipt_id in receipt_ids:
            try:
                # Get receipt item IDs for embeddings cascade
                items_result = db.query("app_receipt_items", filters=[{"field": "receipt_id", "operator": "eq", "value": receipt_id}], projection=["id"], limit=1000, include_deleted=False)
                if items_result and items_result.get('success'):
                    for item in items_result.get('data', {}).get('records', []):
                        try:
                            db.delete("app_receipt_item_embeddings", filters=[{"field": "receipt_item_id", "operator": "eq", "value": item['id']}])
                        except Exception:
                            pass
                db.delete("app_receipt_items", filters=[{"field": "receipt_id", "operator": "eq", "value": receipt_id}])
            except Exception:
                pass

        for workout_id in workout_ids:
            try:
                db.delete("app_workout_exercises", filters=[{"field": "workout_id", "operator": "eq", "value": workout_id}])
            except Exception:
                pass

        # Delete direct user tables
        direct_tables = [
            "app_food_entries_v2", "app_receipts", "app_workouts",
            "app_shopping_list_items", "app_shopping_lists",
            "app_pending_analyses", "app_user_goals", "app_health_assessments",
            "app_meal_summaries", "app_user_notifications",
            "app_care_relationships", "app_participant_permissions", "app_caretaker_notes",
        ]

        for table in direct_tables:
            try:
                result = db.delete(table, filters=[{"field": "user_id", "operator": "eq", "value": user_id}])
                if result and result.get('success'):
                    deleted[table] = "deleted"
                else:
                    deleted[table] = "skipped"
            except Exception as e:
                deleted[table] = f"error: {str(e)[:100]}"

        # Delete user record last
        try:
            result = db.delete("app_users_v4", filters=[{"field": "id", "operator": "eq", "value": user_id}])
            deleted["app_users_v4"] = "deleted" if result and result.get('success') else "skipped"
        except Exception as e:
            deleted["app_users_v4"] = f"error: {str(e)[:100]}"

        logger.warning(f"Account deletion complete for user {user_id}: {json.dumps(deleted)}")

        return respond(200, {
            "message": "Account and all associated data have been permanently deleted",
            "user_id": user_id,
            "tables_processed": deleted
        }, event=event)

    except Exception as e:
        logger.error(f"Error deleting account for {user_id}: {str(e)}", exc_info=True)
        return respond(500, {"error": "Failed to delete account"}, event=event)

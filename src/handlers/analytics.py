"""
Analytics handlers - Cross-table insights powered by EXECUTE_SQL
Leverages DuckDB's analytical engine for complex queries across Iceberg tables.
"""

from datetime import datetime, timedelta

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger


@require_auth
def dashboard_summary(event, context):
    """
    GET /v1/analytics/dashboard - Dashboard summary with cross-table stats
    Returns spending trends, nutrition summary, and recent activity in one call.
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    days = int(event.get('queryStringParameters', {}).get('days', '30') or '30')
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    result = {}

    # Spending summary from receipts
    try:
        spending = db.execute_sql(
            "SELECT "
            "COUNT(*) as total_receipts, "
            "COALESCE(SUM(total_amount), 0) as total_spent, "
            "COALESCE(AVG(total_amount), 0) as avg_per_receipt, "
            "COALESCE(MAX(total_amount), 0) as largest_receipt "
            "FROM app_receipts "
            "WHERE _deleted = false AND created_at >= ?",
            params=[since]
        )
        if spending.get('success'):
            records = spending.get('data', {}).get('records', [])
            result['spending'] = records[0] if records else {}
    except Exception as e:
        logger.warning(f"Spending query failed: {e}")
        result['spending'] = {}

    # Top categories from receipt items
    try:
        categories = db.execute_sql(
            "SELECT category, COUNT(*) as item_count, "
            "COALESCE(SUM(total_price), 0) as total_spent "
            "FROM app_receipt_items "
            "WHERE _deleted = false AND created_at >= ? "
            "GROUP BY category ORDER BY total_spent DESC LIMIT 10",
            params=[since]
        )
        if categories.get('success'):
            result['top_categories'] = categories.get('data', {}).get('records', [])
    except Exception as e:
        logger.warning(f"Categories query failed: {e}")
        result['top_categories'] = []

    # Nutrition summary from food entries
    try:
        nutrition = db.execute_sql(
            "SELECT "
            "COUNT(*) as total_entries, "
            "COALESCE(AVG(CAST(json_extract_string(extracted_nutrients, '$.total_calories') AS DOUBLE)), 0) as avg_calories, "
            "COALESCE(AVG(CAST(json_extract_string(extracted_nutrients, '$.total_protein') AS DOUBLE)), 0) as avg_protein "
            "FROM app_food_entries_v2 "
            "WHERE _deleted = false AND created_at >= ?",
            params=[since]
        )
        if nutrition.get('success'):
            records = nutrition.get('data', {}).get('records', [])
            result['nutrition'] = records[0] if records else {}
    except Exception as e:
        logger.warning(f"Nutrition query failed: {e}")
        result['nutrition'] = {}

    result['period_days'] = days

    return respond(200, result)


@require_auth
def spending_by_vendor(event, context):
    """
    GET /v1/analytics/spending/vendors - Spending breakdown by vendor
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    days = int(event.get('queryStringParameters', {}).get('days', '90') or '90')
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    try:
        result = db.execute_sql(
            "SELECT vendor, COUNT(*) as receipt_count, "
            "SUM(total_amount) as total_spent, "
            "AVG(total_amount) as avg_amount, "
            "MAX(receipt_date) as last_visit "
            "FROM app_receipts "
            "WHERE _deleted = false AND created_at >= ? "
            "GROUP BY vendor ORDER BY total_spent DESC LIMIT 20",
            params=[since]
        )
        if result.get('success'):
            return respond(200, {
                "vendors": result.get('data', {}).get('records', []),
                "period_days": days
            })
        return respond(500, {"error": "Query failed"})
    except Exception as e:
        logger.error(f"Vendor spending query failed: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def spending_trend(event, context):
    """
    GET /v1/analytics/spending/trend - Weekly spending trend
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    days = int(event.get('queryStringParameters', {}).get('days', '90') or '90')
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    try:
        result = db.execute_sql(
            "SELECT date_trunc('week', CAST(receipt_date AS DATE)) as week, "
            "COUNT(*) as receipt_count, "
            "SUM(total_amount) as total_spent "
            "FROM app_receipts "
            "WHERE _deleted = false AND created_at >= ? "
            "GROUP BY week ORDER BY week",
            params=[since]
        )
        if result.get('success'):
            return respond(200, {
                "trend": result.get('data', {}).get('records', []),
                "period_days": days
            })
        return respond(500, {"error": "Query failed"})
    except Exception as e:
        logger.error(f"Spending trend query failed: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def nutrition_trend(event, context):
    """
    GET /v1/analytics/nutrition/trend - Daily nutrition trend
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    days = int(event.get('queryStringParameters', {}).get('days', '30') or '30')
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    try:
        result = db.execute_sql(
            "SELECT CAST(created_at AS DATE) as date, "
            "COUNT(*) as entries, "
            "SUM(CAST(json_extract_string(extracted_nutrients, '$.total_calories') AS DOUBLE)) as total_calories, "
            "SUM(CAST(json_extract_string(extracted_nutrients, '$.total_protein') AS DOUBLE)) as total_protein "
            "FROM app_food_entries_v2 "
            "WHERE _deleted = false AND created_at >= ? "
            "GROUP BY date ORDER BY date",
            params=[since]
        )
        if result.get('success'):
            return respond(200, {
                "trend": result.get('data', {}).get('records', []),
                "period_days": days
            })
        return respond(500, {"error": "Query failed"})
    except Exception as e:
        logger.error(f"Nutrition trend query failed: {e}")
        return respond(500, {"error": str(e)})

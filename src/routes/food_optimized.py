"""
Optimized food entries API with server-side pagination and filtering
"""

from flask import Blueprint, request, jsonify
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
from functools import wraps
import hashlib
import json

from ..lib.ibex_client_function_url import FunctionURLIbexClient
from ..lib.auth_provider import AuthProvider
from ..lib.storage_service import StorageService

# Create blueprint
food_optimized_bp = Blueprint('food_optimized', __name__)

# Initialize services
ibex_client = FunctionURLIbexClient()
auth_provider = AuthProvider()
storage_service = StorageService()

# Simple in-memory cache for demo (use Redis in production)
CACHE = {}
CACHE_TTL = 300  # 5 minutes

def cache_key(user_id: str, **params) -> str:
    """Generate cache key from parameters"""
    key_parts = [f"food_entries:{user_id}"]
    for k, v in sorted(params.items()):
        if v is not None:
            key_parts.append(f"{k}:{v}")
    return hashlib.md5(":".join(key_parts).encode()).hexdigest()

def with_cache(ttl: int = CACHE_TTL):
    """Decorator for caching API responses"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Get user from request
            user = getattr(request, 'user', None)
            if not user:
                return f(*args, **kwargs)

            # Generate cache key
            cache_params = {
                'page': request.args.get('page', 1),
                'limit': request.args.get('limit', 20),
                'sort_by': request.args.get('sort_by', 'created_at'),
                'sort_order': request.args.get('sort_order', 'desc'),
                'meal_type': request.args.get('meal_type'),
                'start_date': request.args.get('start_date'),
                'end_date': request.args.get('end_date'),
                'search': request.args.get('search')
            }
            key = cache_key(user['id'], **cache_params)

            # Check cache
            if key in CACHE:
                cached_data, cached_time = CACHE[key]
                if datetime.now().timestamp() - cached_time < ttl:
                    response = jsonify(cached_data)
                    response.headers['X-Cache'] = 'HIT'
                    return response

            # Execute function
            result = f(*args, **kwargs)

            # Cache successful responses
            if result.status_code == 200:
                CACHE[key] = (result.get_json(), datetime.now().timestamp())

            result.headers['X-Cache'] = 'MISS'
            return result

        return wrapper
    return decorator

@food_optimized_bp.route('/v1/food-entries/optimized', methods=['GET'])
@auth_provider.require_auth
@with_cache(ttl=60)  # Cache for 1 minute
def get_food_entries_optimized():
    """
    Optimized endpoint for fetching food entries with server-side pagination and filtering

    Query Parameters:
    - page: Page number (default: 1)
    - limit: Items per page (default: 20, max: 100)
    - sort_by: Field to sort by (created_at, calories, meal_type)
    - sort_order: asc or desc (default: desc)
    - meal_type: Filter by meal type
    - start_date: Filter by start date (ISO format)
    - end_date: Filter by end date (ISO format)
    - search: Search in description
    - fields: Comma-separated list of fields to return (for response optimization)
    """
    try:
        user = request.user
        user_id = user['id']

        # Parse pagination parameters
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 items
        offset = (page - 1) * limit

        # Parse sorting parameters
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')

        # Validate sort field
        allowed_sort_fields = ['created_at', 'calories', 'meal_type', 'description']
        if sort_by not in allowed_sort_fields:
            sort_by = 'created_at'

        # Build filters
        filters = [
            {"field": "user_id", "operator": "eq", "value": user_id}
        ]

        # Add optional filters
        meal_type = request.args.get('meal_type')
        if meal_type and meal_type != 'all':
            filters.append({"field": "meal_type", "operator": "eq", "value": meal_type})

        start_date = request.args.get('start_date')
        if start_date:
            filters.append({"field": "created_at", "operator": "gte", "value": start_date})

        end_date = request.args.get('end_date')
        if end_date:
            # Add one day to include the entire end date
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            end_dt = end_dt + timedelta(days=1)
            filters.append({"field": "created_at", "operator": "lt", "value": end_dt.isoformat()})

        # Search filter (if Ibex supports it)
        search = request.args.get('search')
        if search:
            filters.append({"field": "description", "operator": "like", "value": f"%{search}%"})

        # Execute query with pagination
        result = ibex_client.query(
            table="food_entries",
            filters=filters,
            limit=limit + 1,  # Fetch one extra to check if there are more
            offset=offset,
            sort=[{"field": sort_by, "order": sort_order}],
            use_cache=False  # We're using our own caching
        )

        if not result.get('success'):
            return jsonify({"error": "Failed to fetch entries"}), 500

        records = result.get('data', {}).get('records', [])

        # Check if there are more pages
        has_more = len(records) > limit
        if has_more:
            records = records[:limit]  # Remove the extra record

        # Optimize response - only return requested fields
        fields = request.args.get('fields')
        if fields:
            field_list = fields.split(',')
            records = [
                {k: v for k, v in record.items() if k in field_list}
                for record in records
            ]
        else:
            # Default optimization - remove large fields if not needed
            for record in records:
                # Parse extracted_nutrients if it's a string
                if 'extracted_nutrients' in record and isinstance(record['extracted_nutrients'], str):
                    try:
                        record['extracted_nutrients'] = json.loads(record['extracted_nutrients'])
                    except:
                        pass

                # Compute nutrition totals on the fly from food_items
                extracted = record.get('extracted_nutrients', {})
                if extracted and isinstance(extracted, dict):
                    food_items = extracted.get('food_items', [])
                    if food_items:
                        total_protein = 0
                        total_carbohydrates = 0
                        total_fats = 0
                        total_fiber = 0
                        total_sodium = 0

                        for item in food_items:
                            quantity = item.get('quantity', 1)
                            # Check both singular and plural field names
                            total_protein += (item.get('protein', item.get('proteins', 0)) * quantity)
                            total_carbohydrates += (item.get('carbs', item.get('carbohydrates', 0)) * quantity)
                            total_fats += (item.get('fat', item.get('fats', 0)) * quantity)
                            total_fiber += (item.get('fiber', 0) * quantity)
                            total_sodium += (item.get('sodium', 0) * quantity)

                        # Add computed totals to the record
                        record['total_protein'] = total_protein
                        record['total_carbohydrates'] = total_carbohydrates
                        record['total_fats'] = total_fats
                        record['total_fiber'] = total_fiber
                        record['total_sodium'] = total_sodium

                # Remove base64 images from response (use URLs instead)
                if 'image_data' in record:
                    del record['image_data']

        # Calculate total count (for pagination UI)
        # Note: This is expensive, consider caching or estimating
        count_result = ibex_client.query(
            table="food_entries",
            filters=[{"field": "user_id", "operator": "eq", "value": user_id}],
            limit=1
        )
        total_count = len(count_result.get('data', {}).get('records', []))

        # Build response with pagination metadata
        response = {
            "success": True,
            "data": records,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "total_pages": (total_count + limit - 1) // limit,
                "has_more": has_more,
                "has_previous": page > 1
            },
            "meta": {
                "cached": False,
                "query_time": result.get('query_time', 0),
                "sort_by": sort_by,
                "sort_order": sort_order,
                "filters_applied": len(filters) - 1  # Excluding user_id filter
            }
        }

        return jsonify(response)

    except Exception as e:
        print(f"Error in optimized food entries endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@food_optimized_bp.route('/v1/food-entries/stats', methods=['GET'])
@auth_provider.require_auth
@with_cache(ttl=300)  # Cache for 5 minutes
def get_food_stats():
    """
    Get aggregated statistics for food entries
    Cached separately from main entries for performance
    """
    try:
        user = request.user
        user_id = user['id']

        # Get date range for stats (default: last 30 days)
        days = int(request.args.get('days', 30))
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # Fetch entries for stats calculation
        result = ibex_client.query(
            table="food_entries",
            filters=[
                {"field": "user_id", "operator": "eq", "value": user_id},
                {"field": "created_at", "operator": "gte", "value": start_date}
            ],
            limit=1000  # Reasonable limit for stats
        )

        if not result.get('success'):
            return jsonify({"error": "Failed to fetch stats"}), 500

        records = result.get('data', {}).get('records', [])

        # Calculate statistics
        total_entries = len(records)
        total_calories = sum(r.get('calories', 0) for r in records)
        avg_calories = total_calories / total_entries if total_entries > 0 else 0

        # Meal type distribution
        meal_types = {}
        for record in records:
            meal_type = record.get('meal_type', 'unknown')
            meal_types[meal_type] = meal_types.get(meal_type, 0) + 1

        # Daily averages
        daily_totals = {}
        for record in records:
            date = record.get('created_at', '')[:10]  # Get date part
            if date:
                if date not in daily_totals:
                    daily_totals[date] = {
                        'calories': 0,
                        'protein': 0,
                        'carbs': 0,
                        'fats': 0,
                        'count': 0
                    }
                daily_totals[date]['calories'] += record.get('calories', 0)
                daily_totals[date]['protein'] += record.get('total_protein', 0)
                daily_totals[date]['carbs'] += record.get('total_carbohydrates', 0)
                daily_totals[date]['fats'] += record.get('total_fats', 0)
                daily_totals[date]['count'] += 1

        # Calculate daily averages
        if daily_totals:
            avg_daily_calories = sum(d['calories'] for d in daily_totals.values()) / len(daily_totals)
            avg_daily_protein = sum(d['protein'] for d in daily_totals.values()) / len(daily_totals)
            avg_daily_carbs = sum(d['carbs'] for d in daily_totals.values()) / len(daily_totals)
            avg_daily_fats = sum(d['fats'] for d in daily_totals.values()) / len(daily_totals)
        else:
            avg_daily_calories = avg_daily_protein = avg_daily_carbs = avg_daily_fats = 0

        stats = {
            "success": True,
            "data": {
                "period_days": days,
                "total_entries": total_entries,
                "total_calories": round(total_calories, 1),
                "average_calories_per_entry": round(avg_calories, 1),
                "average_daily_calories": round(avg_daily_calories, 1),
                "average_daily_protein": round(avg_daily_protein, 1),
                "average_daily_carbs": round(avg_daily_carbs, 1),
                "average_daily_fats": round(avg_daily_fats, 1),
                "meal_type_distribution": meal_types,
                "daily_entry_count": len(daily_totals)
            }
        }

        return jsonify(stats)

    except Exception as e:
        print(f"Error calculating food stats: {e}")
        return jsonify({"error": str(e)}), 500

@food_optimized_bp.route('/v1/food-entries/batch', methods=['POST'])
@auth_provider.require_auth
def batch_operations():
    """
    Batch operations for multiple food entries
    Reduces round trips for bulk updates/deletes
    """
    try:
        user = request.user
        user_id = user['id']
        data = request.get_json()

        operations = data.get('operations', [])
        if not operations:
            return jsonify({"error": "No operations provided"}), 400

        results = []
        for op in operations:
            op_type = op.get('type')
            entry_id = op.get('id')

            if op_type == 'delete':
                # Delete entry
                result = ibex_client.delete(
                    table="food_entries",
                    filters=[
                        {"field": "id", "operator": "eq", "value": entry_id},
                        {"field": "user_id", "operator": "eq", "value": user_id}
                    ]
                )
                results.append({
                    "id": entry_id,
                    "operation": "delete",
                    "success": result.get('success', False)
                })

            elif op_type == 'update':
                # Update entry
                updates = op.get('data', {})
                result = ibex_client.update(
                    table="food_entries",
                    record_id=entry_id,
                    data=updates,
                    filters=[{"field": "user_id", "operator": "eq", "value": user_id}]
                )
                results.append({
                    "id": entry_id,
                    "operation": "update",
                    "success": result.get('success', False)
                })

        # Clear cache after batch operations
        global CACHE
        CACHE = {}

        return jsonify({
            "success": True,
            "results": results,
            "total_operations": len(operations),
            "successful": sum(1 for r in results if r['success'])
        })

    except Exception as e:
        print(f"Error in batch operations: {e}")
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@food_optimized_bp.route('/v1/food-entries/health', methods=['GET'])
def health_check():
    """Simple health check for monitoring"""
    return jsonify({
        "status": "healthy",
        "cache_size": len(CACHE),
        "timestamp": datetime.now().isoformat()
    })
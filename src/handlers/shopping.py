"""
Shopping List handlers - CRUD + AI-powered item parsing and smart purchase plan

The "prepare" endpoint builds a store-grouped purchase plan from the user's
actual receipt history, using vector similarity + SQL aggregation.
"""

import json
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from utils.http import respond, get_user_id
from utils.timestamps import utc_now
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.model_manager import get_model_manager
from openai import OpenAI

# Try to import embeddings (may not be available in all environments)
try:
    from lib.embeddings import get_embeddings_batch, find_similar_multi, zvec_load_from_ibexdb, ZVEC_AVAILABLE
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    ZVEC_AVAILABLE = False


# ---------- Structured output schemas ----------

PARSE_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "produce", "dairy", "meat", "seafood", "bakery",
                            "frozen", "canned", "snacks", "beverages",
                            "condiments", "grains", "household", "other"
                        ]
                    },
                    "estimated_price": {"type": "number"}
                },
                "required": ["name", "quantity", "unit", "category", "estimated_price"],
                "additionalProperties": False
            }
        }
    },
    "required": ["items"],
    "additionalProperties": False
}

# New: store-grouped purchase plan schema
PURCHASE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "store_stops": {
            "type": "array",
            "description": "Shopping stops ordered by priority (most items first)",
            "items": {
                "type": "object",
                "properties": {
                    "store_name": {"type": "string"},
                    "store_type": {
                        "type": "string",
                        "enum": ["grocery", "wholesale", "pharmacy", "specialty", "convenience", "online", "other"]
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit": {"type": "string"},
                                "category": {"type": "string"},
                                "estimated_price": {"type": "number"},
                                "price_source": {
                                    "type": "string",
                                    "description": "How price was determined: 'receipt_history', 'estimated', 'similar_item'"
                                },
                                "last_purchased": {
                                    "type": "string",
                                    "description": "When last bought at this store, e.g. '2 weeks ago', 'never'"
                                },
                                "alternative": {
                                    "type": "string",
                                    "description": "Cheaper or healthier alternative if any, empty string if none"
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Price trend, nutrition note, or tip"
                                }
                            },
                            "required": ["name", "quantity", "unit", "category", "estimated_price",
                                         "price_source", "last_purchased", "alternative", "notes"],
                            "additionalProperties": False
                        }
                    },
                    "store_subtotal": {"type": "number"},
                    "item_count": {"type": "number"},
                    "why_this_store": {
                        "type": "string",
                        "description": "Why shop here for these items (e.g. 'Best prices on produce based on your history')"
                    }
                },
                "required": ["store_name", "store_type", "items", "store_subtotal", "item_count", "why_this_store"],
                "additionalProperties": False
            }
        },
        "estimated_total": {"type": "number"},
        "potential_savings": {"type": "number", "description": "How much saved vs buying everything at one store"},
        "budget_tips": {
            "type": "array",
            "items": {"type": "string"}
        },
        "nutrition_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Health-related tips based on the items and user's food history"
        },
        "summary": {
            "type": "string",
            "description": "One-paragraph shopping plan summary"
        }
    },
    "required": ["store_stops", "estimated_total", "potential_savings", "budget_tips", "nutrition_notes", "summary"],
    "additionalProperties": False
}


def _get_ai_client():
    """Get OpenAI client using model manager config"""
    manager = get_model_manager()
    config = manager.get_model_config("shopping")
    api_key = manager.get_api_key(config.provider)
    provider_config = manager.get_provider_config(config.provider)
    return OpenAI(
        api_key=api_key,
        base_url=provider_config.get("base_url"),
        timeout=60.0,
        max_retries=2
    ), config


# ---------- CRUD endpoints ----------

@require_auth
def create_list(event, context):
    """POST /v1/shopping-lists - Create a new shopping list"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
        name = body.get('name', '').strip()
        if not name:
            return respond(400, {"error": "List name is required"})

        list_id = str(uuid.uuid4())
        now = utc_now()

        record = {
            "id": list_id,
            "user_id": user_id,
            "name": name,
            "status": "active",
            "item_count": 0,
            "estimated_total": 0.0,
            "notes": body.get('notes', ''),
            "created_at": now,
            "updated_at": now
        }

        result = db.write("app_shopping_lists", [record])
        if not result.get('success'):
            return respond(500, {"error": f"Failed to create list: {result.get('error')}"})

        return respond(201, record)

    except Exception as e:
        logger.error(f"Error creating shopping list: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def list_lists(event, context):
    """GET /v1/shopping-lists - List all shopping lists for user"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        result = db.query("app_shopping_lists", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], sort=[{"field": "updated_at", "order": "desc"}], limit=50)

        if result.get('success'):
            lists = result.get('data', {}).get('records', [])
            return respond(200, {"lists": lists, "total": len(lists)})
        else:
            return respond(500, {"error": "Failed to fetch lists"})

    except Exception as e:
        logger.error(f"Error listing shopping lists: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def get_list(event, context):
    """GET /v1/shopping-lists/{id} - Get a shopping list with its items"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        list_result = db.query("app_shopping_lists", filters=[
            {"field": "id", "operator": "eq", "value": list_id},
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], limit=1, use_cache=False)

        if not list_result.get('success'):
            return respond(500, {"error": "Failed to fetch list"})

        lists = list_result.get('data', {}).get('records', [])
        if not lists:
            return respond(404, {"error": "List not found"})

        shopping_list = lists[0]

        items_result = db.query("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ], sort=[{"field": "category", "order": "asc"}], limit=200)

        items = []
        if items_result.get('success'):
            items = items_result.get('data', {}).get('records', [])

        shopping_list['items'] = items
        return respond(200, shopping_list)

    except Exception as e:
        logger.error(f"Error fetching shopping list: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def update_list(event, context):
    """PUT /v1/shopping-lists/{id} - Update a shopping list"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        body = json.loads(event.get('body', '{}'))
        updates = {}
        for field in ['name', 'status', 'notes']:
            if field in body:
                updates[field] = body[field]

        if not updates:
            return respond(400, {"error": "No valid fields to update"})

        updates['updated_at'] = utc_now()

        result = db.update("app_shopping_lists",
                          filters=[
                              {"field": "id", "operator": "eq", "value": list_id},
                              {"field": "user_id", "operator": "eq", "value": user_id}
                          ],
                          updates=updates)

        if result.get('success'):
            return respond(200, {"message": "List updated", "id": list_id})
        else:
            return respond(500, {"error": f"Failed to update: {result.get('error')}"})

    except Exception as e:
        logger.error(f"Error updating shopping list: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def delete_list(event, context):
    """DELETE /v1/shopping-lists/{id} - Delete a shopping list and its items"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        db.delete("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ])

        result = db.delete("app_shopping_lists", filters=[
            {"field": "id", "operator": "eq", "value": list_id},
            {"field": "user_id", "operator": "eq", "value": user_id}
        ])

        if result.get('success'):
            return respond(200, {"message": "List deleted", "id": list_id})
        else:
            return respond(500, {"error": f"Failed to delete: {result.get('error')}"})

    except Exception as e:
        logger.error(f"Error deleting shopping list: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def add_items(event, context):
    """
    POST /v1/shopping-lists/{id}/items - Add items to a shopping list
    Accepts natural language text which is parsed by AI using structured outputs.
    Body: {"text": "2 gallons of milk, dozen eggs, bananas"} or {"items": [...]}
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        body = json.loads(event.get('body', '{}'))
        text = body.get('text', '').strip()
        manual_items = body.get('items', [])

        if not text and not manual_items:
            return respond(400, {"error": "Provide 'text' or 'items'"})

        parsed_items = []

        if text:
            client, config = _get_ai_client()

            response = client.chat.completions.create(
                model=config.model_name,
                messages=[
                    {"role": "system", "content": (
                        "You are a shopping list parser. Parse the user's natural language "
                        "shopping list into structured items. Estimate reasonable prices in USD. "
                        "Use standard units (each, lb, oz, gal, dozen, pack, etc)."
                    )},
                    {"role": "user", "content": f"Parse these shopping items: {text}"}
                ],
                temperature=0.1,
                max_tokens=config.max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "shopping_items",
                        "strict": True,
                        "schema": PARSE_ITEMS_SCHEMA
                    }
                }
            )

            result_data = json.loads(response.choices[0].message.content)
            parsed_items = result_data.get('items', [])
            logger.info(f"AI parsed {len(parsed_items)} items from text")
            _log_shopping_cost(db, user_id, "parse_items", response.usage.total_tokens, config)

        for item in manual_items:
            parsed_items.append({
                "name": item.get('name', 'Unknown'),
                "quantity": item.get('quantity', 1),
                "unit": item.get('unit', 'each'),
                "category": item.get('category', 'other'),
                "estimated_price": item.get('estimated_price', 0)
            })

        now = utc_now()
        item_records = []
        for item in parsed_items:
            item_records.append({
                "id": str(uuid.uuid4()),
                "list_id": list_id,
                "user_id": user_id,
                "name": item.get('name', 'Unknown'),
                "quantity": item.get('quantity', 1),
                "unit": item.get('unit', 'each'),
                "category": item.get('category', 'other'),
                "estimated_price": item.get('estimated_price', 0),
                "actual_price": 0,
                "store_recommendation": "",
                "is_purchased": "false",
                "priority": "normal",
                "notes": "",
                "added_via": "text" if text else "manual",
                "created_at": now,
                "updated_at": now
            })

        if item_records:
            write_result = db.write("app_shopping_list_items", item_records)
            if not write_result.get('success'):
                return respond(500, {"error": f"Failed to add items: {write_result.get('error')}"})
            _update_list_totals(db, user_id, list_id)

        return respond(201, {
            "message": f"Added {len(item_records)} items",
            "items": item_records
        })

    except Exception as e:
        logger.error(f"Error adding shopping items: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def update_item(event, context):
    """PUT /v1/shopping-lists/{id}/items/{item_id} - Update a shopping list item"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')
    item_id = event.get('pathParameters', {}).get('item_id')

    if not list_id or not item_id:
        return respond(400, {"error": "List ID and Item ID required"})

    try:
        body = json.loads(event.get('body', '{}'))
        updates = {}
        for field in ['name', 'quantity', 'unit', 'category', 'estimated_price',
                       'actual_price', 'store_recommendation', 'is_purchased',
                       'priority', 'notes']:
            if field in body:
                updates[field] = body[field]

        if not updates:
            return respond(400, {"error": "No valid fields to update"})

        # IbexDB stores is_purchased as string — convert bool to string
        if 'is_purchased' in updates:
            updates['is_purchased'] = str(updates['is_purchased']).lower()

        updates['updated_at'] = utc_now()

        result = db.update("app_shopping_list_items",
                          filters=[
                              {"field": "id", "operator": "eq", "value": item_id},
                              {"field": "list_id", "operator": "eq", "value": list_id}
                          ],
                          updates=updates)

        if result.get('success'):
            _update_list_totals(db, user_id, list_id)
            return respond(200, {"message": "Item updated", "id": item_id})
        else:
            return respond(500, {"error": f"Failed to update: {result.get('error')}"})

    except Exception as e:
        logger.error(f"Error updating shopping item: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def delete_item(event, context):
    """DELETE /v1/shopping-lists/{id}/items/{item_id} - Delete a shopping list item"""
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')
    item_id = event.get('pathParameters', {}).get('item_id')

    if not list_id or not item_id:
        return respond(400, {"error": "List ID and Item ID required"})

    try:
        result = db.delete("app_shopping_list_items", filters=[
            {"field": "id", "operator": "eq", "value": item_id},
            {"field": "list_id", "operator": "eq", "value": list_id}
        ])

        if result.get('success'):
            _update_list_totals(db, user_id, list_id)
            return respond(200, {"message": "Item deleted", "id": item_id})
        else:
            return respond(500, {"error": f"Failed to delete: {result.get('error')}"})

    except Exception as e:
        logger.error(f"Error deleting shopping item: {e}")
        return respond(500, {"error": str(e)})


# ---------- Smart purchase plan ----------

def _build_store_price_index(db, user_id: str, days: int = 180) -> Dict:
    """
    Build a comprehensive price index from receipt history.
    Returns: {
        "stores": {"Trader Joe's": {"city": "...", "state": "...", "visit_count": 5, "last_visit": "..."}},
        "item_prices": {"milk": [{"store": "Trader Joe's", "price": 3.49, "date": "...", "qty": 1}]},
        "user_location": {"city": "...", "state": "...", "postal_code": "..."}
    }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')

    stores = {}       # store_name -> {city, state, visit_count, last_visit, total_spent}
    item_prices = {}   # item_name_lower -> [{store, price, date, qty, category}]
    user_location = {}

    # 1. Fetch receipts (store-level info)
    try:
        receipts_result = db.query("app_receipts", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id},
            {"field": "created_at", "operator": "gte", "value": cutoff}
        ], sort=[{"field": "created_at", "order": "desc"}], limit=200)

        if receipts_result.get('success'):
            for r in receipts_result.get('data', {}).get('records', []):
                vendor = r.get('vendor', '') or ''
                if not vendor or vendor == 'Unknown Vendor':
                    continue

                # Track store info
                if vendor not in stores:
                    stores[vendor] = {
                        "city": r.get('city', ''),
                        "state": r.get('state', ''),
                        "postal_code": r.get('postal_code', ''),
                        "visit_count": 0,
                        "last_visit": '',
                        "total_spent": 0.0
                    }
                stores[vendor]["visit_count"] += 1
                stores[vendor]["total_spent"] += float(r.get('total_amount', 0) or 0)
                visit_date = r.get('receipt_date') or r.get('created_at', '')
                if visit_date > stores[vendor]["last_visit"]:
                    stores[vendor]["last_visit"] = visit_date

                # Infer user location from most recent receipt with location data
                if not user_location and (r.get('city') or r.get('state') or r.get('postal_code')):
                    user_location = {
                        "city": r.get('city', ''),
                        "state": r.get('state', ''),
                        "postal_code": r.get('postal_code', '')
                    }
    except Exception as e:
        logger.warning(f"Failed to fetch receipts for price index: {e}")

    # 2. Fetch receipt items with store mapping
    try:
        # Use execute_sql to join receipt_items with receipts for store info
        sql = (
            "SELECT ri.name, ri.unit_price, ri.total_price, ri.quantity, ri.category, "
            "r.vendor, r.receipt_date, r.created_at "
            "FROM app_receipt_items ri "
            "JOIN app_receipts r ON ri.receipt_id = r.id "
            "WHERE r.user_id = ? AND r.created_at >= ? AND r._deleted = false AND ri._deleted = false "
            "ORDER BY r.created_at DESC LIMIT 1000"
        )
        sql_result = db.execute_sql(sql, params=[user_id, cutoff])

        if sql_result.get('success'):
            for row in sql_result.get('data', {}).get('records', []):
                name = (row.get('name', '') or '').strip()
                if not name:
                    continue
                store = row.get('vendor', '') or 'Unknown'
                price = float(row.get('unit_price', 0) or row.get('total_price', 0) or 0)
                date = row.get('receipt_date') or row.get('created_at', '')
                qty = float(row.get('quantity', 1) or 1)
                cat = row.get('category', '')

                key = name.lower()
                if key not in item_prices:
                    item_prices[key] = []
                item_prices[key].append({
                    "store": store,
                    "price": round(price, 2),
                    "date": date,
                    "qty": qty,
                    "category": cat,
                    "name_original": name
                })
    except Exception as e:
        logger.warning(f"execute_sql join failed, falling back to basic query: {e}")
        # Fallback: query receipt_items without store info
        try:
            items_result = db.query("app_receipt_items", filters=[
                {"field": "created_at", "operator": "gte", "value": cutoff}
            ], sort=[{"field": "created_at", "order": "desc"}], limit=500)

            if items_result.get('success'):
                for row in items_result.get('data', {}).get('records', []):
                    name = (row.get('name', '') or '').strip()
                    if not name:
                        continue
                    price = float(row.get('unit_price', 0) or row.get('total_price', 0) or 0)
                    key = name.lower()
                    if key not in item_prices:
                        item_prices[key] = []
                    item_prices[key].append({
                        "store": "Unknown",
                        "price": round(price, 2),
                        "date": row.get('created_at', ''),
                        "qty": float(row.get('quantity', 1) or 1),
                        "category": row.get('category', ''),
                        "name_original": name
                    })
        except Exception as e2:
            logger.warning(f"Basic receipt items query also failed: {e2}")

    logger.info(f"Price index built: {len(stores)} stores, {len(item_prices)} unique items, "
                f"location: {user_location}")

    return {
        "stores": stores,
        "item_prices": item_prices,
        "user_location": user_location
    }


def _find_vector_matches(db, items: List[Dict], days: int = 90) -> Dict:
    """Use vector similarity to match shopping items against receipt item embeddings."""
    if not EMBEDDINGS_AVAILABLE:
        return {}

    try:
        zvec_load_from_ibexdb(db, days=days)
        item_names = [i.get("name", "") for i in items]
        item_embeddings = get_embeddings_batch(item_names)

        if ZVEC_AVAILABLE:
            return find_similar_multi(item_embeddings, item_names, candidates=[], top_k=5, threshold=0.65)
        else:
            # Fallback Python cosine search
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
            emb_result = db.query("app_receipt_item_embeddings", filters=[
                {"field": "created_at", "operator": "gte", "value": cutoff}
            ], sort=[{"field": "created_at", "order": "desc"}], limit=500)

            candidates = []
            if emb_result.get('success'):
                for rc in emb_result.get('data', {}).get('records', []):
                    try:
                        emb = json.loads(rc.get("embedding", "[]"))
                        if emb:
                            candidates.append({
                                "embedding": emb,
                                "item_name": rc.get("item_name", ""),
                                "category": rc.get("category", ""),
                                "unit_price": rc.get("unit_price", 0),
                                "store_name": rc.get("store_name", ""),
                            })
                    except (json.JSONDecodeError, TypeError):
                        continue

            return find_similar_multi(item_embeddings, item_names, candidates, top_k=5, threshold=0.65)

    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
        return {}


@require_auth
def prepare_list(event, context):
    """
    POST /v1/shopping-lists/{id}/prepare - Smart Purchase Plan

    Builds a store-grouped purchase plan from the user's actual receipt history:
    1. Builds price index from receipt history (which stores, what prices, when)
    2. Uses vector similarity to match shopping items to past purchases
    3. AI generates optimized store-by-store purchase plan

    Body (optional): {"location": {"lat": 33.7, "lng": -84.4}} for future location features
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        # Parse optional body
        try:
            body = json.loads(event.get('body', '{}') or '{}')
        except json.JSONDecodeError:
            body = {}

        # 1. Fetch current shopping list items
        items_result = db.query("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ], limit=200)

        if not items_result.get('success'):
            return respond(500, {"error": "Failed to fetch list items"})

        items = items_result.get('data', {}).get('records', [])
        if not items:
            return respond(400, {"error": "List has no items to optimize"})

        # 2. Build store-level price index from receipt history
        price_index = _build_store_price_index(db, user_id, days=180)

        # 3. Vector similarity matching
        vector_matches = _find_vector_matches(db, items, days=90)

        # 4. Fetch food nutrition history
        food_history = []
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
            food_result = db.query("app_food_entries_v2", filters=[
                {"field": "user_id", "operator": "eq", "value": user_id},
                {"field": "created_at", "operator": "gte", "value": cutoff}
            ], sort=[{"field": "created_at", "order": "desc"}], limit=50)

            if food_result.get('success'):
                food_history = food_result.get('data', {}).get('records', [])
        except Exception as e:
            logger.warning(f"Could not fetch food history: {e}")

        # 5. Build rich context for AI
        items_text = json.dumps([{
            "name": i.get("name"), "quantity": i.get("quantity"),
            "unit": i.get("unit"), "category": i.get("category"),
            "current_estimate": i.get("estimated_price", 0)
        } for i in items], indent=2)

        # Store profile
        store_profiles = []
        for store, info in price_index["stores"].items():
            last = info.get("last_visit", "")
            days_ago = ""
            if last:
                try:
                    last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
                    delta = (datetime.now(timezone.utc) - last_dt).days
                    days_ago = f"{delta} days ago"
                except Exception:
                    days_ago = last
            store_profiles.append(
                f"- {store}: {info['visit_count']} visits, ${info['total_spent']:.0f} total spent, "
                f"last visit: {days_ago}"
                + (f", location: {info.get('city', '')}, {info.get('state', '')}" if info.get('city') else "")
            )
        stores_text = "\n".join(store_profiles) if store_profiles else "No store history available."

        # Item-level price history
        price_lines = []
        for item in items:
            name = item.get("name", "")
            name_lower = name.lower()

            # Check exact/fuzzy match in price index
            matches_found = []
            for key, prices in price_index["item_prices"].items():
                if name_lower in key or key in name_lower:
                    for p in prices[:3]:  # top 3 price records
                        matches_found.append(p)

            # Also check vector matches
            if name in vector_matches:
                for vm in vector_matches[name]:
                    matches_found.append({
                        "store": vm.get("store_name", "unknown"),
                        "price": vm.get("unit_price", 0),
                        "date": "",
                        "name_original": vm.get("item_name", ""),
                    })

            if matches_found:
                # Group by store, show best price per store
                store_prices = {}
                for m in matches_found:
                    store = m.get("store", "Unknown")
                    price = m.get("price", 0)
                    if store not in store_prices or price < store_prices[store]["price"]:
                        store_prices[store] = {"price": price, "date": m.get("date", ""), "matched": m.get("name_original", "")}

                price_parts = []
                for store, info in store_prices.items():
                    part = f"${info['price']:.2f} at {store}"
                    if info.get("date"):
                        part += f" ({info['date'][:10]})"
                    if info.get("matched") and info["matched"].lower() != name_lower:
                        part += f" [matched: {info['matched']}]"
                    price_parts.append(part)
                price_lines.append(f"- {name}: {', '.join(price_parts)}")
            else:
                price_lines.append(f"- {name}: no purchase history found")

        price_history_text = "\n".join(price_lines)

        # Nutrition context
        nutrition_text = ""
        if food_history:
            food_names = list(set(f.get('food_name', '') or f.get('name', '') for f in food_history[:30] if f.get('food_name') or f.get('name')))
            nutrition_text = f"User's recently consumed foods: {', '.join(food_names[:20])}"

        # Location context
        loc = price_index.get("user_location", {})
        location_text = ""
        if loc.get("city") or loc.get("state"):
            location_text = f"User's area: {loc.get('city', '')}, {loc.get('state', '')} {loc.get('postal_code', '')}"

        # 6. Call AI with structured outputs
        client, config = _get_ai_client()

        system_prompt = (
            "You are a smart shopping assistant that creates store-grouped purchase plans "
            "optimized for BOTH cost AND health quality.\n\n"
            "Given a shopping list, the user's actual store visit history, item price history "
            "from their receipts, and their recent food/nutrition history, create an optimized plan:\n\n"
            "COST OPTIMIZATION:\n"
            "1. Group items by the BEST STORE based on the user's actual purchase history and prices\n"
            "2. Use REAL PRICES from receipt history (adjusted slightly for inflation if old)\n"
            "3. Order store stops by most items first (minimize trips)\n"
            "4. For items with no history, estimate prices and suggest a likely store\n\n"
            "HEALTH & QUALITY:\n"
            "5. Flag unhealthy items in the 'notes' field (e.g. high sodium, processed, high sugar)\n"
            "6. For unhealthy items, ALWAYS suggest a healthier alternative in the 'alternative' field "
            "(e.g. 'white bread' → 'whole wheat bread', 'soda' → 'sparkling water')\n"
            "7. In 'nutrition_notes', give practical health tips based on the overall list balance "
            "(e.g. 'Your list is heavy on carbs — consider adding leafy greens')\n"
            "8. Consider the user's recent food history — if they're eating too much of something, note it\n\n"
            "Be practical and specific. Use the actual store names from the user's history. "
            "If the user mainly shops at 2-3 stores, keep the plan to those stores."
        )

        user_prompt = f"""SHOPPING LIST:
{items_text}

USER'S STORES (from receipt history, last 6 months):
{stores_text}

PRICE HISTORY (from user's receipts):
{price_history_text}

{nutrition_text}
{location_text}

Create a store-grouped purchase plan. Group items by the best store based on this user's actual shopping patterns and prices."""

        response = client.chat.completions.create(
            model=config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=4096,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "purchase_plan",
                    "strict": True,
                    "schema": PURCHASE_PLAN_SCHEMA
                }
            }
        )

        prepare_result = json.loads(response.choices[0].message.content)
        tokens_used = response.usage.total_tokens

        _log_shopping_cost(db, user_id, "prepare_list", tokens_used, config)

        logger.info(f"Purchase plan for list {list_id}: {len(prepare_result.get('store_stops', []))} stores, "
                     f"${prepare_result.get('estimated_total', 0):.2f} total, {tokens_used} tokens")

        # Update list estimated_total
        estimated_total = prepare_result.get('estimated_total', 0)
        db.update("app_shopping_lists",
                  filters=[{"field": "id", "operator": "eq", "value": list_id}],
                  updates={"estimated_total": estimated_total, "updated_at": utc_now()})

        return respond(200, {
            "list_id": list_id,
            "preparation": prepare_result,
            "metadata": {
                "tokens_used": tokens_used,
                "stores_in_history": len(price_index["stores"]),
                "items_in_price_index": len(price_index["item_prices"]),
                "vector_matches": len(vector_matches),
                "food_history_items": len(food_history),
                "user_location": price_index.get("user_location", {})
            }
        })

    except Exception as e:
        logger.error(f"Error preparing shopping list: {e}", exc_info=True)
        return respond(500, {"error": str(e)})


# ---------- Helpers ----------

def _update_list_totals(db, user_id: str, list_id: str):
    """Update item_count and estimated_total on the parent list"""
    try:
        items_result = db.query("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ], limit=500)

        if items_result.get('success'):
            items = items_result.get('data', {}).get('records', [])
            total = sum(
                (i.get('estimated_price', 0) or 0) * (i.get('quantity', 1) or 1)
                for i in items
            )
            db.update("app_shopping_lists",
                      filters=[
                          {"field": "id", "operator": "eq", "value": list_id},
                          {"field": "user_id", "operator": "eq", "value": user_id}
                      ],
                      updates={
                          "item_count": len(items),
                          "estimated_total": round(total, 2),
                          "updated_at": utc_now()
                      })
    except Exception as e:
        logger.error(f"Error updating list totals: {e}")


def _log_shopping_cost(db, user_id: str, function_name: str, tokens: int, config):
    """Log AI API cost for shopping operations"""
    try:
        cost = (tokens / 1000) * config.cost_per_1k_tokens
        db.write("app_api_costs", [{
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "function_name": f"shopping_{function_name}",
            "category": "shopping",
            "model_used": json.dumps({"analyzer": config.model_name}),
            "total_tokens": tokens,
            "cost_usd": cost,
            "created_at": utc_now()
        }])
    except Exception as e:
        logger.error(f"Failed to log shopping cost: {e}")


# ---------- Receipt Reconciliation ----------

def reconcile_receipt_with_shopping_lists(db, user_id: str, receipt_items: List[Dict], vendor: str = ""):
    """
    Auto-reconcile receipt items against active shopping lists.
    Called after a receipt is processed to mark matching shopping list items as purchased.

    Uses fuzzy name matching: if a receipt item name contains (or is contained by)
    a shopping list item name, it's a match.

    Returns: {"matched": int, "lists_updated": [list_id, ...]}
    """
    try:
        # 1. Fetch active shopping lists for this user
        lists_result = db.query("app_shopping_lists", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id},
            {"field": "status", "operator": "eq", "value": "active"}
        ], limit=20)

        if not lists_result.get('success'):
            return {"matched": 0, "lists_updated": []}

        active_lists = lists_result.get('data', {}).get('records', [])
        if not active_lists:
            return {"matched": 0, "lists_updated": []}

        # 2. Fetch all items from active lists that are NOT yet purchased
        list_ids = [l['id'] for l in active_lists]
        all_shopping_items = []
        for list_id in list_ids:
            items_result = db.query("app_shopping_list_items", filters=[
                {"field": "list_id", "operator": "eq", "value": list_id},
            ], limit=200)
            if items_result.get('success'):
                for item in items_result.get('data', {}).get('records', []):
                    # Normalize is_purchased (IbexDB may return string)
                    purchased = item.get('is_purchased', False)
                    if isinstance(purchased, str):
                        purchased = purchased.lower() == 'true'
                    if not purchased:
                        all_shopping_items.append(item)

        if not all_shopping_items:
            return {"matched": 0, "lists_updated": []}

        # 3. Build receipt item name lookup (lowercased, cleaned)
        receipt_names = []
        for ri in receipt_items:
            name = (ri.get('name', '') or '').strip().lower()
            if name and name != 'unknown item':
                receipt_names.append(name)

        if not receipt_names:
            return {"matched": 0, "lists_updated": []}

        # 4. Match shopping items against receipt items (fuzzy containment)
        matched_count = 0
        updated_lists = set()
        now = utc_now()

        for si in all_shopping_items:
            si_name = (si.get('name', '') or '').strip().lower()
            if not si_name:
                continue

            # Check if any receipt item matches this shopping item
            is_match = False
            for rn in receipt_names:
                # Fuzzy containment: "milk" matches "whole milk 2%", "chicken breast" matches "chicken breast boneless"
                if si_name in rn or rn in si_name:
                    is_match = True
                    break
                # Also check word-level overlap for multi-word items
                si_words = set(si_name.split())
                rn_words = set(rn.split())
                if len(si_words) > 1 and len(si_words & rn_words) >= len(si_words) * 0.6:
                    is_match = True
                    break

            if is_match:
                # Mark as purchased
                db.update("app_shopping_list_items",
                          filters=[{"field": "id", "operator": "eq", "value": si['id']}],
                          updates={
                              "is_purchased": "true",
                              "actual_price": si.get('estimated_price', 0),
                              "store_recommendation": vendor,
                              "updated_at": now
                          })
                matched_count += 1
                updated_lists.add(si['list_id'])

        # 5. Update totals for affected lists
        for list_id in updated_lists:
            _update_list_totals(db, user_id, list_id)

        if matched_count > 0:
            logger.info(f"Receipt reconciliation: matched {matched_count} items across "
                       f"{len(updated_lists)} shopping lists for user {user_id}")

        return {"matched": matched_count, "lists_updated": list(updated_lists)}

    except Exception as e:
        logger.error(f"Receipt reconciliation failed: {e}")
        return {"matched": 0, "lists_updated": []}

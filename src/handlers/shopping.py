"""
Shopping List handlers - CRUD + AI-powered item parsing and list preparation
"""

import json
import uuid
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from utils.http import respond, get_user_id
from utils.timestamps import utc_now, utc_date
from lib.auth_provider import require_auth
from lib.logger import logger
from lib.model_manager import get_model_manager
from lib.embeddings import get_embeddings_batch, find_similar, find_similar_multi, zvec_load_from_ibexdb, ZVEC_AVAILABLE
from openai import OpenAI


# Structured output schema for parsing natural language items
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

# Structured output schema for the prepare/optimize endpoint
PREPARE_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "optimized_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "category": {"type": "string"},
                    "estimated_price": {"type": "number"},
                    "store_recommendation": {"type": "string"},
                    "price_note": {"type": "string"},
                    "alternative": {"type": "string"},
                    "nutrition_note": {"type": "string"}
                },
                "required": [
                    "name", "quantity", "unit", "category",
                    "estimated_price", "store_recommendation",
                    "price_note", "alternative", "nutrition_note"
                ],
                "additionalProperties": False
            }
        },
        "estimated_total": {"type": "number"},
        "budget_tips": {
            "type": "array",
            "items": {"type": "string"}
        },
        "nutrition_summary": {"type": "string"}
    },
    "required": ["optimized_items", "estimated_total", "budget_tips", "nutrition_summary"],
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
        # Fetch list
        list_result = db.query("app_shopping_lists", filters=[
            {"field": "id", "operator": "eq", "value": list_id},
            {"field": "user_id", "operator": "eq", "value": user_id}
        ], limit=1)

        if not list_result.get('success'):
            return respond(500, {"error": "Failed to fetch list"})

        lists = list_result.get('data', {}).get('records', [])
        if not lists:
            return respond(404, {"error": "List not found"})

        shopping_list = lists[0]

        # Fetch items
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

        # Only allow updating specific fields
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
        # Delete items first
        db.delete("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ])

        # Delete the list
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

        # If natural language text, use AI to parse with structured outputs
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

            # Log API cost
            _log_shopping_cost(db, user_id, "parse_items", response.usage.total_tokens, config)

        # Add manual items directly
        for item in manual_items:
            parsed_items.append({
                "name": item.get('name', 'Unknown'),
                "quantity": item.get('quantity', 1),
                "unit": item.get('unit', 'each'),
                "category": item.get('category', 'other'),
                "estimated_price": item.get('estimated_price', 0)
            })

        # Write to database
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
                "is_purchased": False,
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

            # Update list item_count and estimated_total
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

        updates['updated_at'] = utc_now()

        result = db.update("app_shopping_list_items",
                          filters=[
                              {"field": "id", "operator": "eq", "value": item_id},
                              {"field": "list_id", "operator": "eq", "value": list_id}
                          ],
                          updates=updates)

        if result.get('success'):
            # Update list totals
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


@require_auth
def prepare_list(event, context):
    """
    POST /v1/shopping-lists/{id}/prepare - AI-powered list optimization
    Queries receipt history + food nutrition history, returns optimized list
    with store recommendations, price estimates, and alternatives.
    Uses structured outputs for reliable JSON responses.
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    list_id = event.get('pathParameters', {}).get('id')

    if not list_id:
        return respond(400, {"error": "List ID required"})

    try:
        # 1. Fetch current shopping list items
        items_result = db.query("app_shopping_list_items", filters=[
            {"field": "list_id", "operator": "eq", "value": list_id}
        ], limit=200)

        if not items_result.get('success'):
            return respond(500, {"error": "Failed to fetch list items"})

        items = items_result.get('data', {}).get('records', [])
        if not items:
            return respond(400, {"error": "List has no items to optimize"})

        # 2. Vector similarity search against receipt item embeddings (last 90 days)
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')

        receipt_history = []
        vector_matches = {}  # keyed by shopping item name
        candidates = []
        try:
            # Ensure zvec is loaded from IbexDB (no-op if already warm)
            zvec_load_from_ibexdb(db, days=90)

            # Embed each shopping item name
            item_names = [i.get("name", "") for i in items]
            item_embeddings = get_embeddings_batch(item_names)

            if ZVEC_AVAILABLE:
                # zvec HNSW search — fast, no need to load candidates into memory
                vector_matches = find_similar_multi(
                    item_embeddings, item_names, candidates=[], top_k=5, threshold=0.7
                )
                for matches in vector_matches.values():
                    receipt_history.extend(matches)
                logger.info(f"zvec search: {len(vector_matches)} items matched")
            else:
                # Fallback: load candidates from IbexDB and use Python cosine
                emb_result = db.query("app_receipt_item_embeddings", filters=[
                    {"field": "created_at", "operator": "gte", "value": ninety_days_ago}
                ], sort=[{"field": "created_at", "order": "desc"}], limit=500)

                if emb_result.get('success'):
                    raw_candidates = emb_result.get('data', {}).get('records', [])
                    for rc in raw_candidates:
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

                    vector_matches = find_similar_multi(
                        item_embeddings, item_names, candidates, top_k=5, threshold=0.7
                    )
                    for matches in vector_matches.values():
                        receipt_history.extend(matches)

                logger.info(f"Python vector search: {len(vector_matches)} items matched from {len(candidates)} candidates")

        except Exception as e:
            logger.warning(f"Vector search failed, falling back to basic query: {e}")

        # Fallback: if vector search found nothing, use EXECUTE_SQL for aggregated receipt data
        if not receipt_history:
            try:
                sql_result = db.execute_sql(
                    "SELECT name, category, "
                    "AVG(unit_price) as avg_price, COUNT(*) as purchase_count, "
                    "MAX(created_at) as last_purchased "
                    "FROM app_receipt_items "
                    "WHERE created_at >= ? AND _deleted = false "
                    "GROUP BY name, category "
                    "ORDER BY purchase_count DESC LIMIT 200",
                    params=[ninety_days_ago]
                )
                if sql_result.get('success'):
                    receipt_history = sql_result.get('data', {}).get('records', [])
            except Exception as e:
                logger.warning(f"EXECUTE_SQL failed for receipt history, falling back to basic query: {e}")
                try:
                    receipt_result = db.query("app_receipt_items", filters=[
                        {"field": "created_at", "operator": "gte", "value": ninety_days_ago}
                    ], sort=[{"field": "created_at", "order": "desc"}], limit=200)

                    if receipt_result.get('success'):
                        receipt_history = receipt_result.get('data', {}).get('records', [])
                except Exception as e2:
                    logger.warning(f"Could not fetch receipt history: {e2}")

        # 3. Query food nutrition history for patterns
        food_history = []
        try:
            food_result = db.query("app_food_items", filters=[
                {"field": "created_at", "operator": "gte", "value": ninety_days_ago}
            ], sort=[{"field": "created_at", "order": "desc"}], limit=100)

            if food_result.get('success'):
                food_history = food_result.get('data', {}).get('records', [])
        except Exception as e:
            logger.warning(f"Could not fetch food history: {e}")

        # 4. Build context for AI
        items_text = json.dumps([{
            "name": i.get("name"), "quantity": i.get("quantity"),
            "unit": i.get("unit"), "category": i.get("category"),
            "estimated_price": i.get("estimated_price", 0)
        } for i in items], indent=2)

        receipt_text = ""
        if vector_matches:
            # Use vector search results grouped by shopping item
            price_summary = []
            for shopping_item, matches in vector_matches.items():
                for match in matches:
                    receipt_item = match.get("item_name", "")
                    price = match.get("unit_price", 0)
                    store = match.get("store_name", "unknown")
                    score = match.get("similarity", 0)
                    price_summary.append(
                        f"- {shopping_item} matched '{receipt_item}': avg ${price:.2f} at {store} (similarity: {score:.2f})"
                    )
            receipt_text = "\n".join(price_summary) if price_summary else "No recent purchase history."
        elif receipt_history:
            # Fallback: summarize basic receipt history
            recent_items = {}
            for ri in receipt_history[:100]:
                name = ri.get('name', '')
                if name:
                    if name not in recent_items:
                        recent_items[name] = {
                            "prices": [],
                            "count": 0
                        }
                    price = ri.get('unit_price') or ri.get('total_price', 0)
                    if price:
                        recent_items[name]["prices"].append(price)
                    recent_items[name]["count"] += 1

            price_summary = []
            for name, info in list(recent_items.items())[:30]:
                avg_price = sum(info["prices"]) / len(info["prices"]) if info["prices"] else 0
                price_summary.append(f"- {name}: avg ${avg_price:.2f} (bought {info['count']}x)")

            receipt_text = "\n".join(price_summary) if price_summary else "No recent purchase history."

        nutrition_text = ""
        if food_history:
            food_names = list(set(f.get('name', '') for f in food_history[:50] if f.get('name')))
            nutrition_text = f"Recently consumed foods: {', '.join(food_names[:20])}"

        # 5. Call AI with structured outputs
        client, config = _get_ai_client()

        system_prompt = (
            "You are a smart shopping assistant. Given a shopping list, recent purchase "
            "history (with prices), and nutrition patterns, optimize the list with: "
            "price estimates based on history, store recommendations, healthier alternatives "
            "where appropriate, and budget tips. Be practical and specific."
        )

        user_prompt = f"""Shopping list items:
{items_text}

Recent purchase history (last 90 days):
{receipt_text or "No history available."}

{nutrition_text or "No nutrition data available."}

Optimize this shopping list with price estimates, store recommendations, and suggestions."""

        response = client.chat.completions.create(
            model=config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "shopping_preparation",
                    "strict": True,
                    "schema": PREPARE_LIST_SCHEMA
                }
            }
        )

        prepare_result = json.loads(response.choices[0].message.content)
        tokens_used = response.usage.total_tokens

        # Log cost
        _log_shopping_cost(db, user_id, "prepare_list", tokens_used, config)

        logger.info(f"Prepared shopping list {list_id}: {len(prepare_result.get('optimized_items', []))} items, "
                     f"{tokens_used} tokens")

        # Update the list's estimated_total
        estimated_total = prepare_result.get('estimated_total', 0)
        db.update("app_shopping_lists",
                  filters=[{"field": "id", "operator": "eq", "value": list_id}],
                  updates={
                      "estimated_total": estimated_total,
                      "updated_at": utc_now()
                  })

        return respond(200, {
            "list_id": list_id,
            "preparation": prepare_result,
            "metadata": {
                "tokens_used": tokens_used,
                "receipt_history_items": len(receipt_history),
                "food_history_items": len(food_history)
            }
        })

    except Exception as e:
        logger.error(f"Error preparing shopping list: {e}")
        return respond(500, {"error": str(e)})


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

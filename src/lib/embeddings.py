"""
Embedding utilities for vector similarity search.
Uses OpenAI text-embedding-3-small for embeddings and zvec for HNSW vector search.

Architecture in Lambda:
- zvec collection persisted to /tmp/zvec_receipts/ (survives warm invocations)
- On cold start: rebuild from IbexDB (source of truth)
- On warm invocations: reuse cached zvec collection for sub-ms search
- New items inserted into zvec live (no rebuild needed)
"""

import json
import os
from typing import List, Optional

from openai import OpenAI
from lib.logger import logger
from lib.model_manager import get_model_manager

try:
    import zvec
    ZVEC_AVAILABLE = True
except ImportError:
    ZVEC_AVAILABLE = False
    logger.warning("zvec not installed, falling back to Python cosine similarity")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

ZVEC_PATH = os.environ.get("ZVEC_PATH", "/tmp/zvec_receipts")

# Module-level singletons
_client = None
_zvec_collection = None
_zvec_doc_count = 0


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = get_model_manager().get_api_key("openai")
        _client = OpenAI(api_key=api_key, timeout=30.0, max_retries=2)
    return _client


def get_embedding(text: str) -> List[float]:
    """Get embedding vector for a single text string."""
    client = _get_client()
    response = client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Get embedding vectors for a batch of texts."""
    if not texts:
        return []
    client = _get_client()
    response = client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


# ---------------------------------------------------------------------------
# zvec-powered vector search (with Python fallback)
# ---------------------------------------------------------------------------

def _get_zvec_schema():
    """Get the zvec collection schema for receipt item embeddings."""
    return zvec.CollectionSchema(
        name="receipt_items",
        fields=[
            zvec.FieldSchema("item_name", zvec.DataType.STRING),
            zvec.FieldSchema("category", zvec.DataType.STRING),
            zvec.FieldSchema("unit_price", zvec.DataType.DOUBLE, nullable=True),
            zvec.FieldSchema("store_name", zvec.DataType.STRING),
            zvec.FieldSchema("receipt_item_id", zvec.DataType.STRING),
        ],
        vectors=zvec.VectorSchema(
            "embedding",
            zvec.DataType.VECTOR_FP32,
            dimension=EMBEDDING_DIMENSIONS,
            index_param=zvec.HnswIndexParam(ef_construction=200, m=16),
        ),
    )


def _get_zvec_collection():
    """Get or create the zvec collection. Cached across warm Lambda invocations."""
    global _zvec_collection, _zvec_doc_count

    if _zvec_collection is not None:
        return _zvec_collection

    try:
        if os.path.exists(os.path.join(ZVEC_PATH, "manifest")):
            # Reopen existing collection (warm container, /tmp survived)
            _zvec_collection = zvec.open(ZVEC_PATH)
            _zvec_doc_count = _zvec_collection.stats.doc_count
            logger.info(f"Reopened zvec collection: {_zvec_doc_count} docs")
        else:
            # Cold start: create fresh collection
            _zvec_collection = zvec.create_and_open(
                path=ZVEC_PATH,
                schema=_get_zvec_schema(),
            )
            _zvec_doc_count = 0
            logger.info("Created new zvec collection")

        return _zvec_collection
    except Exception as e:
        logger.error(f"Failed to initialize zvec collection: {e}")
        _zvec_collection = None
        return None


def zvec_load_from_ibexdb(db, days: int = 90):
    """
    Load receipt item embeddings from IbexDB into zvec.
    Called on cold start or when collection is empty.
    """
    if not ZVEC_AVAILABLE:
        return 0

    collection = _get_zvec_collection()
    if collection is None:
        return 0

    global _zvec_doc_count

    # Skip if already populated
    if _zvec_doc_count > 0:
        logger.info(f"zvec already has {_zvec_doc_count} docs, skipping reload")
        return _zvec_doc_count

    try:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        result = db.query("app_receipt_item_embeddings", filters=[
            {"field": "created_at", "operator": "gte", "value": cutoff}
        ], limit=2000)

        if not result.get('success'):
            logger.warning(f"Failed to load embeddings from IbexDB: {result.get('error')}")
            return 0

        records = result.get('data', {}).get('records', [])
        if not records:
            return 0

        docs = []
        for rec in records:
            try:
                emb = json.loads(rec.get("embedding", "[]"))
                if not emb or len(emb) != EMBEDDING_DIMENSIONS:
                    continue

                docs.append(zvec.Doc(
                    id=rec.get("receipt_item_id", rec.get("id", "")),
                    vectors={"embedding": emb},
                    fields={
                        "item_name": rec.get("item_name", ""),
                        "category": rec.get("category", ""),
                        "unit_price": rec.get("unit_price", 0.0),
                        "store_name": rec.get("store_name", ""),
                        "receipt_item_id": rec.get("receipt_item_id", rec.get("id", "")),
                    },
                ))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        if docs:
            collection.insert(docs)
            collection.flush()
            _zvec_doc_count = len(docs)
            logger.info(f"Loaded {len(docs)} embeddings into zvec from IbexDB")

        return len(docs)

    except Exception as e:
        logger.error(f"Failed to load embeddings into zvec: {e}")
        return 0


def zvec_insert_items(items: List[dict]):
    """
    Insert new receipt item embeddings into zvec (live update, no rebuild).
    Called after storing receipt items + embeddings in IbexDB.

    Each item dict should have: receipt_item_id, item_name, category, unit_price, store_name, embedding (list)
    """
    if not ZVEC_AVAILABLE:
        return

    collection = _get_zvec_collection()
    if collection is None:
        return

    global _zvec_doc_count

    try:
        docs = []
        for item in items:
            emb = item.get("embedding")
            if not emb or len(emb) != EMBEDDING_DIMENSIONS:
                continue

            docs.append(zvec.Doc(
                id=item.get("receipt_item_id", ""),
                vectors={"embedding": emb},
                fields={
                    "item_name": item.get("item_name", ""),
                    "category": item.get("category", ""),
                    "unit_price": item.get("unit_price", 0.0),
                    "store_name": item.get("store_name", ""),
                    "receipt_item_id": item.get("receipt_item_id", ""),
                },
            ))

        if docs:
            collection.insert(docs)
            collection.flush()
            _zvec_doc_count += len(docs)
            logger.info(f"Inserted {len(docs)} items into zvec (total: {_zvec_doc_count})")

    except Exception as e:
        logger.error(f"Failed to insert into zvec: {e}")


def find_similar(query_embedding, candidates: List[dict], top_k: int = 5, threshold: float = 0.0) -> List[dict]:
    """
    Find top-k most similar items. Uses zvec HNSW if available, falls back to Python cosine.

    When zvec is active, 'candidates' param is ignored (search is against the zvec collection).
    When falling back, 'candidates' must have 'embedding' key in each dict.
    """
    if ZVEC_AVAILABLE and _zvec_collection is not None and _zvec_doc_count > 0:
        return _zvec_find_similar(query_embedding, top_k, threshold)

    # Fallback: Python cosine similarity
    return _python_find_similar(query_embedding, candidates, top_k, threshold)


def find_similar_multi(query_embeddings: List[List[float]], item_names: List[str],
                       candidates: List[dict], top_k: int = 5, threshold: float = 0.7) -> dict:
    """
    Find similar items for multiple queries at once.
    Returns dict keyed by item_name → list of matches.
    """
    results = {}
    for name, emb in zip(item_names, query_embeddings):
        matches = find_similar(emb, candidates, top_k, threshold)
        if matches:
            results[name] = matches
    return results


def _zvec_find_similar(query_embedding: List[float], top_k: int, threshold: float) -> List[dict]:
    """Use zvec HNSW index for fast similarity search."""
    try:
        results = _zvec_collection.query(
            vectors=zvec.VectorQuery("embedding", vector=query_embedding),
            topk=top_k,
            output_fields=["item_name", "category", "unit_price", "store_name", "receipt_item_id"],
            include_vector=False,
        )

        matches = []
        for doc in results:
            score = doc.score
            if score < threshold:
                continue
            matches.append({
                "item_name": doc.field("item_name"),
                "category": doc.field("category"),
                "unit_price": doc.field("unit_price"),
                "store_name": doc.field("store_name"),
                "receipt_item_id": doc.field("receipt_item_id"),
                "similarity": score,
            })

        return matches

    except Exception as e:
        logger.error(f"zvec query failed: {e}")
        return []


def _python_find_similar(query_embedding, candidates: List[dict], top_k: int, threshold: float) -> List[dict]:
    """Fallback: pure Python cosine similarity."""
    import math

    def _cosine_sim(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    scored = []
    for candidate in candidates:
        emb = candidate.get("embedding")
        if not emb:
            continue
        sim = _cosine_sim(query_embedding, emb)
        if sim >= threshold:
            result = {k: v for k, v in candidate.items() if k != "embedding"}
            result["similarity"] = sim
            scored.append(result)

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]

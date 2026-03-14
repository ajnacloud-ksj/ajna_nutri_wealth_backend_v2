"""
Financial Reconciliation Handlers

Provides three reconciliation capabilities:
1. Cross-account transfer matching (e.g., BofA payment → Apple Card receipt)
2. Double-count elimination (same spend as both credit charge + bank withdrawal)
3. Receipt-to-transaction matching (AI-analyzed receipts ↔ bank transactions)
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Tuple

from utils.http import respond, get_user_id
from lib.auth_provider import require_auth
from lib.logger import logger


# Transfer matching patterns
TRANSFER_PATTERNS = [
    # BofA → Apple Card
    {"from_keywords": ["APPLECARD GSBANK"], "to_account": "Apple Card", "to_keywords": ["PAYMENT"]},
    # BofA → Chase
    {"from_keywords": ["CHASE CREDIT CRD"], "to_account": "Chase Sapphire", "to_keywords": ["PAYMENT THANK YOU"]},
    # BofA → Discover
    {"from_keywords": ["DISCOVER"], "to_account": "Discover", "to_keywords": ["PAYMENT", "INTERNET PAYMENT"]},
    # BofA ↔ SoFi
    {"from_keywords": ["SOFI BANK", "BANK OF AMERICA"], "to_account": "BofA Checking", "to_keywords": ["SOFI BANK", "TRANSFER"]},
    {"from_keywords": ["BANK OF AMERICA"], "to_account": "SoFi Savings", "to_keywords": ["BANK OF AMERICA", "TRANSFER"]},
]


def _validate_user_id(user_id: str) -> None:
    """Validate user_id is a valid UUID to prevent SQL injection"""
    try:
        uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise ValueError("Invalid user_id format")


def _match_transfers(db, user_id: str) -> List[Dict[str, Any]]:
    """
    Match cross-account transfers.
    Logic: Find pairs where one is negative (outflow) and one is positive (inflow)
    on the same date with matching amounts.
    """
    _validate_user_id(user_id)

    # Query all potential transfer transactions
    sql = f"""
        SELECT
            id, date, description, amount, category, transaction_type, source_account
        FROM app_bank_transactions
        WHERE user_id = '{user_id}'
          AND (transaction_type = 'transfer' OR category IN ('Card Payment', 'Transfer'))
        ORDER BY date DESC, amount
    """

    result = db.execute_sql(sql)
    records = result.get('data', {}).get('records', [])

    if not records:
        return []

    # Group by date and absolute amount
    date_amount_groups = {}
    for txn in records:
        date = txn.get('date', '')
        amount = float(txn.get('amount', 0))
        abs_amount = abs(amount)
        key = f"{date}|{abs_amount:.2f}"

        if key not in date_amount_groups:
            date_amount_groups[key] = []
        date_amount_groups[key].append(txn)

    # Find matching pairs
    matches = []
    processed_ids = set()

    for key, txns in date_amount_groups.items():
        if len(txns) < 2:
            continue

        # Split into outflows (negative) and inflows (positive)
        outflows = [t for t in txns if float(t.get('amount', 0)) < 0]
        inflows = [t for t in txns if float(t.get('amount', 0)) > 0]

        # Match pairs
        for out_txn in outflows:
            out_id = out_txn.get('id')
            if out_id in processed_ids:
                continue

            out_desc = (out_txn.get('description', '') or '').upper()
            out_account = out_txn.get('source_account', '')

            for in_txn in inflows:
                in_id = in_txn.get('id')
                if in_id in processed_ids:
                    continue

                in_desc = (in_txn.get('description', '') or '').upper()
                in_account = in_txn.get('source_account', '')

                # Check if this matches known transfer patterns
                confidence = 0.0
                pattern_match = None

                for pattern in TRANSFER_PATTERNS:
                    from_match = any(kw in out_desc for kw in pattern['from_keywords'])
                    to_match = (in_account == pattern['to_account'] and
                               any(kw in in_desc for kw in pattern['to_keywords']))

                    if from_match and to_match:
                        confidence = 0.95
                        pattern_match = f"{out_account} → {in_account}"
                        break

                # Generic transfer detection (same date, same amount, opposite signs)
                if confidence == 0.0:
                    # Check if descriptions suggest transfer
                    transfer_keywords = ['PAYMENT', 'TRANSFER', 'APPLECARD', 'CHASE', 'DISCOVER']
                    if any(kw in out_desc for kw in transfer_keywords) or any(kw in in_desc for kw in transfer_keywords):
                        confidence = 0.75
                        pattern_match = f"{out_account} → {in_account}"

                if confidence > 0:
                    matches.append({
                        "from_transaction": {
                            "id": out_id,
                            "date": out_txn.get('date', ''),
                            "description": out_txn.get('description', ''),
                            "amount": round(float(out_txn.get('amount', 0)), 2),
                            "source_account": out_account,
                        },
                        "to_transaction": {
                            "id": in_id,
                            "date": in_txn.get('date', ''),
                            "description": in_txn.get('description', ''),
                            "amount": round(float(in_txn.get('amount', 0)), 2),
                            "source_account": in_account,
                        },
                        "confidence": confidence,
                        "pattern": pattern_match,
                        "amount": round(abs(float(out_txn.get('amount', 0))), 2),
                    })
                    processed_ids.add(out_id)
                    processed_ids.add(in_id)
                    break

    return matches


def _detect_double_counts(db, user_id: str, transfer_ids: set) -> List[Dict[str, Any]]:
    """
    Detect potential double-counts: same expense appears as both credit card charge
    and bank account withdrawal.

    Excludes known transfers (from transfer matching).
    """
    _validate_user_id(user_id)

    # Query credit card transactions (expenses)
    credit_card_accounts = ['Apple Card', 'Chase Sapphire', 'Discover']
    card_list = "', '".join(credit_card_accounts)

    sql_cards = f"""
        SELECT
            id, date, description, merchant, amount, category, source_account
        FROM app_bank_transactions
        WHERE user_id = '{user_id}'
          AND source_account IN ('{card_list}')
          AND transaction_type = 'expense'
          AND category NOT IN ('Card Payment', 'Transfer')
        ORDER BY date DESC
    """

    result_cards = db.execute_sql(sql_cards)
    card_txns = result_cards.get('data', {}).get('records', [])

    # Query bank account transactions (withdrawals)
    bank_accounts = ['BofA Checking', 'SoFi Savings']
    bank_list = "', '".join(bank_accounts)

    sql_banks = f"""
        SELECT
            id, date, description, merchant, amount, category, source_account
        FROM app_bank_transactions
        WHERE user_id = '{user_id}'
          AND source_account IN ('{bank_list}')
          AND transaction_type = 'expense'
          AND category NOT IN ('Card Payment', 'Transfer')
        ORDER BY date DESC
    """

    result_banks = db.execute_sql(sql_banks)
    bank_txns = result_banks.get('data', {}).get('records', [])

    # Match credit card charges to bank withdrawals
    double_counts = []

    for card_txn in card_txns:
        card_id = card_txn.get('id')
        if card_id in transfer_ids:
            continue

        card_date = card_txn.get('date', '')
        card_amount = abs(float(card_txn.get('amount', 0)))
        card_merchant = (card_txn.get('merchant', '') or '').upper()

        try:
            card_dt = datetime.strptime(card_date, '%Y-%m-%d')
        except (ValueError, TypeError):
            continue

        # Look for matching bank transaction within ±3 days
        for bank_txn in bank_txns:
            bank_id = bank_txn.get('id')
            if bank_id in transfer_ids:
                continue

            bank_date = bank_txn.get('date', '')
            bank_amount = abs(float(bank_txn.get('amount', 0)))
            bank_merchant = (bank_txn.get('merchant', '') or '').upper()

            try:
                bank_dt = datetime.strptime(bank_date, '%Y-%m-%d')
            except (ValueError, TypeError):
                continue

            # Check date window (±3 days)
            date_diff = abs((card_dt - bank_dt).days)
            if date_diff > 3:
                continue

            # Check amount match (exact or within $0.01)
            amount_diff = abs(card_amount - bank_amount)
            if amount_diff > 0.01:
                continue

            # Require merchant similarity for double-count detection
            # Without merchant match, same-amount transactions across accounts are just coincidence
            confidence = 0.0

            if card_merchant and bank_merchant:
                if card_merchant == bank_merchant:
                    confidence = 0.95
                elif card_merchant in bank_merchant or bank_merchant in card_merchant:
                    confidence = 0.85
                elif any(word in bank_merchant for word in card_merchant.split() if len(word) > 3):
                    confidence = 0.75

            if confidence >= 0.7:
                double_counts.append({
                    "credit_card_transaction": {
                        "id": card_id,
                        "date": card_date,
                        "description": card_txn.get('description', ''),
                        "merchant": card_txn.get('merchant', ''),
                        "amount": round(card_amount, 2),
                        "source_account": card_txn.get('source_account', ''),
                        "category": card_txn.get('category', ''),
                    },
                    "bank_transaction": {
                        "id": bank_id,
                        "date": bank_date,
                        "description": bank_txn.get('description', ''),
                        "merchant": bank_txn.get('merchant', ''),
                        "amount": round(bank_amount, 2),
                        "source_account": bank_txn.get('source_account', ''),
                        "category": bank_txn.get('category', ''),
                    },
                    "confidence": confidence,
                    "date_diff_days": date_diff,
                    "amount": round(card_amount, 2),
                })

    return double_counts


def _match_receipts(db, user_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Match AI-analyzed receipts to bank transactions.
    Returns: (matched_pairs, unmatched_receipts)
    """
    _validate_user_id(user_id)

    # Query receipts
    sql_receipts = f"""
        SELECT
            id, vendor, total_amount, receipt_date, image_url, created_at
        FROM app_receipts
        WHERE user_id = '{user_id}'
        ORDER BY receipt_date DESC
    """

    result_receipts = db.execute_sql(sql_receipts)
    receipts = result_receipts.get('data', {}).get('records', [])

    if not receipts:
        return [], []

    # Query bank transactions (expenses only)
    sql_txns = f"""
        SELECT
            id, date, description, merchant, amount, category, source_account
        FROM app_bank_transactions
        WHERE user_id = '{user_id}'
          AND transaction_type = 'expense'
        ORDER BY date DESC
    """

    result_txns = db.execute_sql(sql_txns)
    transactions = result_txns.get('data', {}).get('records', [])

    # Match receipts to transactions
    matches = []
    matched_receipt_ids = set()
    matched_txn_ids = set()

    for receipt in receipts:
        receipt_id = receipt.get('id')
        receipt_date = receipt.get('receipt_date', '')
        receipt_amount = float(receipt.get('total_amount', 0))
        vendor = (receipt.get('vendor', '') or '').upper()

        try:
            receipt_dt = datetime.strptime(receipt_date, '%Y-%m-%d')
        except (ValueError, TypeError):
            continue

        best_match = None
        best_confidence = 0.0

        for txn in transactions:
            txn_id = txn.get('id')
            if txn_id in matched_txn_ids:
                continue

            txn_date = txn.get('date', '')
            txn_amount = abs(float(txn.get('amount', 0)))
            merchant = (txn.get('merchant', '') or '').upper()

            try:
                txn_dt = datetime.strptime(txn_date, '%Y-%m-%d')
            except (ValueError, TypeError):
                continue

            # Check date window (±3 days)
            date_diff = abs((receipt_dt - txn_dt).days)
            if date_diff > 3:
                continue

            # Check amount match (within $1 tolerance)
            amount_diff = abs(receipt_amount - txn_amount)
            if amount_diff > 1.0:
                continue

            # Calculate confidence
            confidence = 0.0

            # Exact amount match
            if amount_diff < 0.01:
                confidence += 0.5
            elif amount_diff < 0.1:
                confidence += 0.4
            elif amount_diff < 1.0:
                confidence += 0.3

            # Date proximity
            if date_diff == 0:
                confidence += 0.3
            elif date_diff == 1:
                confidence += 0.2
            elif date_diff <= 3:
                confidence += 0.1

            # Merchant name match
            if vendor and merchant:
                if vendor == merchant:
                    confidence += 0.3
                elif vendor in merchant or merchant in vendor:
                    confidence += 0.2
                elif any(word in merchant for word in vendor.split() if len(word) > 3):
                    confidence += 0.1

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = {
                    "receipt": {
                        "id": receipt_id,
                        "vendor": receipt.get('vendor', ''),
                        "total_amount": round(receipt_amount, 2),
                        "receipt_date": receipt_date,
                        "image_url": receipt.get('image_url', ''),
                    },
                    "transaction": {
                        "id": txn_id,
                        "date": txn_date,
                        "description": txn.get('description', ''),
                        "merchant": txn.get('merchant', ''),
                        "amount": round(txn_amount, 2),
                        "source_account": txn.get('source_account', ''),
                        "category": txn.get('category', ''),
                    },
                    "confidence": round(confidence, 2),
                    "date_diff_days": date_diff,
                    "amount_diff": round(amount_diff, 2),
                }

        if best_match and best_confidence >= 0.5:
            matches.append(best_match)
            matched_receipt_ids.add(receipt_id)
            matched_txn_ids.add(best_match['transaction']['id'])

    # Collect unmatched receipts
    unmatched = [
        {
            "id": r.get('id'),
            "vendor": r.get('vendor', ''),
            "total_amount": round(float(r.get('total_amount', 0)), 2),
            "receipt_date": r.get('receipt_date', ''),
            "image_url": r.get('image_url', ''),
        }
        for r in receipts
        if r.get('id') not in matched_receipt_ids
    ]

    return matches, unmatched


@require_auth
def run_reconciliation(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/reconciliation/run
    Runs all three reconciliation analyses and returns results.
    """
    db = context['db']
    user_id = get_user_id(event) or ''

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return respond(400, {"error": str(e)})

    try:
        # 1. Match transfers
        transfer_matches = _match_transfers(db, user_id)
        transfer_ids = set()
        for match in transfer_matches:
            transfer_ids.add(match['from_transaction']['id'])
            transfer_ids.add(match['to_transaction']['id'])

        # 2. Detect double-counts (exclude transfer IDs)
        double_counts = _detect_double_counts(db, user_id, transfer_ids)

        # 3. Match receipts to transactions
        receipt_matches, unmatched_receipts = _match_receipts(db, user_id)

        return respond(200, {
            "transfer_matches": transfer_matches,
            "double_counts": double_counts,
            "receipt_matches": receipt_matches,
            "unmatched_receipts": unmatched_receipts,
            "summary": {
                "total_transfer_matches": len(transfer_matches),
                "total_double_counts": len(double_counts),
                "total_receipt_matches": len(receipt_matches),
                "total_unmatched_receipts": len(unmatched_receipts),
            }
        })

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def get_reconciliation_summary(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/reconciliation/summary
    Returns high-level reconciliation summary.
    """
    db = context['db']
    user_id = get_user_id(event) or ''

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return respond(400, {"error": str(e)})

    try:
        # Run reconciliation
        transfer_matches = _match_transfers(db, user_id)
        transfer_ids = set()
        for match in transfer_matches:
            transfer_ids.add(match['from_transaction']['id'])
            transfer_ids.add(match['to_transaction']['id'])

        double_counts = _detect_double_counts(db, user_id, transfer_ids)
        receipt_matches, unmatched_receipts = _match_receipts(db, user_id)

        # Calculate totals
        total_transfer_amount = sum(m['amount'] for m in transfer_matches)
        total_double_count_amount = sum(d['amount'] for d in double_counts)
        total_matched_receipt_amount = sum(m['receipt']['total_amount'] for m in receipt_matches)
        total_unmatched_receipt_amount = sum(r['total_amount'] for r in unmatched_receipts)

        return respond(200, {
            "transfers": {
                "count": len(transfer_matches),
                "total_amount": round(total_transfer_amount, 2),
            },
            "double_counts": {
                "count": len(double_counts),
                "total_amount": round(total_double_count_amount, 2),
                "net_adjustment": round(total_double_count_amount, 2),  # Amount inflating spending
            },
            "receipts": {
                "matched_count": len(receipt_matches),
                "matched_amount": round(total_matched_receipt_amount, 2),
                "unmatched_count": len(unmatched_receipts),
                "unmatched_amount": round(total_unmatched_receipt_amount, 2),
            },
        })

    except Exception as e:
        logger.error(f"Summary failed: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def get_transfer_matches(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/reconciliation/transfers
    Returns transfer matches in detail.
    """
    db = context['db']
    user_id = get_user_id(event) or ''

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return respond(400, {"error": str(e)})

    try:
        transfer_matches = _match_transfers(db, user_id)

        # Sort by date descending
        transfer_matches.sort(key=lambda m: m['from_transaction']['date'], reverse=True)

        return respond(200, {
            "transfers": transfer_matches,
            "total": len(transfer_matches),
        })

    except Exception as e:
        logger.error(f"Transfer matches failed: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def get_receipt_matches(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/reconciliation/receipts
    Returns receipt-to-transaction matches.
    """
    db = context['db']
    user_id = get_user_id(event) or ''

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return respond(400, {"error": str(e)})

    try:
        receipt_matches, unmatched_receipts = _match_receipts(db, user_id)

        # Sort by date descending
        receipt_matches.sort(key=lambda m: m['receipt']['receipt_date'], reverse=True)
        unmatched_receipts.sort(key=lambda r: r['receipt_date'], reverse=True)

        return respond(200, {
            "matched": receipt_matches,
            "unmatched": unmatched_receipts,
            "total_matched": len(receipt_matches),
            "total_unmatched": len(unmatched_receipts),
        })

    except Exception as e:
        logger.error(f"Receipt matches failed: {e}")
        return respond(500, {"error": str(e)})

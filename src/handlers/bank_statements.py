"""
Bank Statement CSV Upload, Processing, and Transaction Storage

Supports: Apple Card, Chase, BofA, Discover, SoFi
Parses CSV → categorizes → stores in app_bank_transactions for historical analysis
"""

import csv
import io
import json
import re
import uuid
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional

from utils.http import respond, get_user_id
from utils.timestamps import utc_now, utc_date
from lib.auth_provider import require_auth
from lib.logger import logger

# ── Category Rules ──────────────────────────────────────────────────────────
CATEGORY_RULES = [
    {"category": "Card Payment", "keywords": ["APPLECARD GSBANK", "PAYMENT THANK YOU", "AUTOMATIC PAYMENT", "BEST BUY DES:PAYMENT", "AFFIRM DES:PAYMENT", "INTERNET PAYMENT - THANK YOU", "CASHBACK BONUS REDEMPTION"]},
    {"category": "Transfer", "keywords": ["FID BKG SVC", "JPMORGAN CHASE", "DISCOVER", "DIGITAL FEDERAL", "ROBINHOOD", "WISE INC", "BANK OF AMERICA", "CHASE CREDIT CRD", "VENMO", "INTERWARE DEVELO", "LINK.COM", "ACH DEPOSIT INTERNET TRANSFER", "TRANSFER SATYA", "INSTANT PAYMENT; ROBINHOOD", "BKOFAMERICA ATM DEPOSIT", "SOFI BANK", "RETURN OF POSTED CHECK"]},
    {"category": "Income", "keywords": ["TRACELINK-OSV", "TRACELINK INC", "IRS  TREAS 310", "IRS TREAS 310", "BKOFAMERICA MOBILE", "INTEREST EARNED"]},
    {"category": "Zelle Send", "keywords": ["ZELLE PAYMENT TO"]},
    {"category": "Zelle Receive", "keywords": ["ZELLE PAYMENT FROM"]},
    {"category": "Housing/Rent", "keywords": ["FIRST EQUITY"]},
    {"category": "Groceries", "keywords": ["COSTCO WHSE", "COSTCO WHOLESALE", "WWW COSTCO COM", "COSTCO *ANNUAL", "MARKET BASKET", "WHOLEFDS", "WHOLE FOODS", "TRADER JOE", "SHAWS", "PATEL BROTHERS", "TIRUMALA FOODS", "EZ INDIAN GROCERY", "GLOBAL HALAL MEATS", "WAL-MART", "WALMART", "TOWNE MARKET", "DESI HALAL MART", "SPICE LAND", "BJS WHOLESALE", "GLOBAL FLAVORS", "BROOKDALE FRUIT", "MCQUESTEN FARM", "IC* COSTCO BY INSTACAR", "FAMILY DOLLAR", "H MART", "APNA BAZAR"]},
    {"category": "Dining", "keywords": ["PARADISE BIRYANI", "HONEST KITCHEN", "DESI CHOWRASTHA", "BLAZE PIZZA", "TATTE BAKERY", "HAYWARD'S ICE CREAM", "HAYWARDS ICE CREAM", "EZCATER", "RELISH BY EZCATER", "LINDT", "ORIGIN THAI", "GODAVARI", "LABELLE WINERY", "SUBWAY", "KANTIPUR CAFE", "MCDONALD", "DOMINO'S", "DOMINOS", "TST*A2B", "CLASSIC BIRYANI", "CHIPOTLE", "SOUTHERN SPICE", "PRIYA INDIAN", "MASALA CAFE", "HALAL GUYS", "TUSCAN MARKET", "LA CARRETA", "JUST SALAD", "VIC S WAFFLE", "WOW!! TIKKA", "DUNKIN", "STARBUCKS"]},
    {"category": "Gas/Fuel", "keywords": ["BJ'S FUEL", "BJS FUEL", "NOURIA STORE", "EXXON", "SHELL", "SUNOCO", "COSTCO GAS"]},
    {"category": "Software/Tech", "keywords": ["CURSOR", "APPLE.COM/BILL", "GENSPARK", "PULUMI", "OPENAI", "ANTHROPIC", "NETFLIX", "LOVABLE"]},
    {"category": "Shopping", "keywords": ["AMAZON", "AMZN", "TARGET", "TJMAXX", "TJ MAXX", "DOLLAR TREE", "LEGO", "SIERRA", "FAMILY CRAFT", "CARTER", "OLD NAVY", "BURLINGTON", "MARSHALLS", "MACYS", "NEW BALANCE", "LEGGINGS HOME", "MENS WEARHOUSE", "ZAGG", "REI #", "REI.COM", "APPLE STORE", "QR INDIA", "INF PLANS", "BEST BUY", "FOSSIL", "KOHLS", "DSW", "DICKS SPORTING", "FIVE BELOW", "STAPLES", "BOSE CORP", "EBAY", "IKEA", "ONEQUINCE", "PUSHMYCART", "NH LIQUOR", "LOWES", "HOME DEPOT", "MICHAELS STORES", "AFFIRM"]},
    {"category": "Medical", "keywords": ["CVS/PHARMACY", "CVS PHARMACY", "EXECUTIVE HEALTH", "GENTLE DENTAL", "CAREWELL URGENT", "DEXCOM", "OURARING", "OURA RING", "AEROFLOW", "BOSTON CHILDRENS"]},
    {"category": "Insurance", "keywords": ["PROGRESSIVE INS", "PROGRESSIVE *INS", "STILLWATER INSURANCE"]},
    {"category": "Utilities", "keywords": ["DISNEYPLUS", "DISNEY+", "MINT MOBILE", "COMCAST", "CITY OF NASHUA"]},
    {"category": "Auto", "keywords": ["GRANITE SUBARU", "SPOTHERO", "CHILDRENS PARKING", "LOGAN PKG", "U-HAUL", "GARAGE AT POST", "UBER", "NH TURNPIKE", "EZ PASS", "SPARKLING IMAGE CAR WASH"]},
    {"category": "Personal Care", "keywords": ["GREAT CLIPS"]},
    {"category": "Education", "keywords": ["SHRI DWARKAMAI", "WISE OWL ACADEMY", "NOVA TRAMPOLINE", "BIG BLUE SWIM", "UML CAMPUS REC"]},
    {"category": "Charity", "keywords": ["GOFNDME", "SRI LAKSHMI TEMPLE", "ZEFFY"]},
    {"category": "Fees", "keywords": ["ANNUAL MEMBERSHIP FEE", "OVERDRAFT ITEM FEE", "CREDIT BALANCE REFUND"]},
    {"category": "Other", "keywords": ["BKOFAMERICA ATM"]},
]

MERCHANT_MAP = [
    # Grocery
    (["COSTCO WHSE", "COSTCO WHOLESALE", "WWW COSTCO", "COSTCO *ANNUAL"], "Costco"),
    (["TRADER JOE"], "Trader Joe's"),
    (["PATEL BROTHERS"], "Patel Brothers"),
    (["WHOLEFDS", "WHOLE FOODS"], "Whole Foods"),
    (["EZ INDIAN"], "EZ Indian Grocery"),
    (["MARKET BASKET"], "Market Basket"),
    (["SHAWS"], "Shaw's"),
    (["H MART"], "H Mart"),
    (["BJS WHOLESALE"], "BJ's Wholesale"),
    (["IC* COSTCO"], "Instacart (Costco)"),
    (["WAL-MART", "WALMART"], "Walmart"),
    # Shopping
    (["AMAZON", "AMZN"], "Amazon"),
    (["TARGET"], "Target"),
    (["APPLE STORE"], "Apple Store"),
    (["BEST BUY"], "Best Buy"),
    (["DOLLAR TREE"], "Dollar Tree"),
    (["IKEA"], "IKEA"),
    (["HOME DEPOT"], "Home Depot"),
    (["LOWES"], "Lowe's"),
    # Dining
    (["STARBUCKS"], "Starbucks"),
    (["DUNKIN"], "Dunkin'"),
    (["CHIPOTLE"], "Chipotle"),
    (["SUBWAY"], "Subway"),
    (["MCDONALD"], "McDonald's"),
    (["PARADISE BIRYANI"], "Paradise Biryani"),
    (["GODAVARI"], "Godavari"),
    # Software
    (["CURSOR"], "Cursor"),
    (["NETFLIX"], "Netflix"),
    (["OPENAI"], "OpenAI"),
    (["ANTHROPIC"], "Anthropic"),
    (["APPLE.COM/BILL"], "Apple Services"),
    # Utilities
    (["COMCAST"], "Comcast"),
    (["MINT MOBILE"], "Mint Mobile"),
    (["DISNEYPLUS", "DISNEY+"], "Disney+"),
    # Medical
    (["CVS"], "CVS Pharmacy"),
    (["DEXCOM"], "Dexcom"),
    # Insurance
    (["PROGRESSIVE"], "Progressive"),
]


def categorize(description: str) -> str:
    upper = description.upper()
    for rule in CATEGORY_RULES:
        for kw in rule["keywords"]:
            if kw.upper() in upper:
                return rule["category"]
    return "Other"


def get_transaction_type(category: str, amount: float) -> str:
    if category == "Income":
        return "income"
    if category == "Zelle Receive":
        return "income"
    if category in ("Transfer", "Card Payment"):
        return "transfer"
    if category == "Zelle Send":
        return "expense"
    if amount < 0:
        return "expense"
    if amount > 0:
        return "refund"
    return "other"


def normalize_merchant(description: str) -> str:
    upper = description.upper()
    for keywords, name in MERCHANT_MAP:
        for kw in keywords:
            if kw in upper:
                return name

    # Zelle patterns
    zelle_to = re.search(r'Zelle payment to ([^;]+?)(?:\s+(?:for|Conf))', description, re.IGNORECASE)
    if zelle_to:
        return "Zelle -> " + zelle_to.group(1).strip()
    zelle_from = re.search(r'Zelle payment from ([^;]+?)(?:\s+(?:for|Conf))', description, re.IGNORECASE)
    if zelle_from:
        return "Zelle <- " + zelle_from.group(1).strip()

    # Fallback: clean up
    cleaned = re.split(r'\s{2,}', description)[0]
    cleaned = re.sub(r'\s*(#\d+|00\d+).*', '', cleaned)
    cleaned = re.sub(r'\d{5,}.*', '', cleaned).strip()
    return cleaned[:40] if cleaned else description[:40]


def parse_date_mdy(date_str: str) -> Optional[str]:
    """Parse MM/DD/YYYY → YYYY-MM-DD"""
    date_str = date_str.strip()
    if not date_str or '/' not in date_str:
        return None
    parts = date_str.split('/')
    if len(parts) != 3:
        return None
    m, d, y = parts
    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"


def parse_amount(val: str) -> float:
    if not val:
        return 0.0
    return float(str(val).replace(',', '').replace('"', '').strip())


# ── Bank-specific CSV parsers ────────────────────────────────────────────

def _detect_bank_format(header: str, rows: List[Dict]) -> str:
    """Detect bank format from CSV headers"""
    cols = set(header.lower().split(',')) if isinstance(header, str) else set()
    if rows:
        cols = {k.lower().strip() for k in rows[0].keys()}

    if 'amount (usd)' in cols:
        return 'apple_card'
    if 'trans. date' in cols:
        return 'discover'
    if 'running bal.' in cols:
        return 'bofa'
    if 'transaction date' in cols and 'post date' in cols:
        return 'chase'
    # SoFi has Date, Description, Amount columns with YYYY-MM-DD dates
    if rows and 'date' in cols and 'amount' in cols:
        sample_date = rows[0].get('Date', rows[0].get('date', ''))
        if sample_date and re.match(r'\d{4}-\d{2}-\d{2}', sample_date):
            return 'sofi'

    return 'generic'


def parse_apple_card(rows: List[Dict]) -> List[Dict]:
    txns = []
    for r in rows:
        txn_type = (r.get('Type', '') or '').strip()
        raw_amt = parse_amount(r.get('Amount (USD)', '0'))
        if txn_type == 'Purchase':
            amount = -abs(raw_amt)
        elif txn_type == 'Payment':
            amount = raw_amt  # already negative
        elif txn_type == 'Credit':
            amount = abs(raw_amt)
        elif txn_type == 'Debit':
            amount = raw_amt
        else:
            amount = -abs(raw_amt)

        desc = (r.get('Description', '') or '').strip()
        date = parse_date_mdy(r.get('Transaction Date', ''))
        if not date:
            continue

        txns.append({
            "date": date,
            "description": desc,
            "amount": round(amount, 2),
            "source_account": "Apple Card",
        })
    return txns


def parse_chase(rows: List[Dict]) -> List[Dict]:
    txns = []
    for r in rows:
        date_str = (r.get('Transaction Date', '') or '').strip()
        if not date_str or '/' not in date_str:
            continue
        date = parse_date_mdy(date_str)
        if not date:
            continue
        amount = parse_amount(r.get('Amount', '0'))
        desc = (r.get('Description', '') or '').strip()
        txns.append({
            "date": date,
            "description": desc,
            "amount": round(amount, 2),
            "source_account": "Chase Sapphire",
        })
    return txns


def parse_bofa(csv_text: str) -> List[Dict]:
    """BofA has a summary header section before actual data"""
    # Find the real header
    header_idx = csv_text.find('Date,Description,Amount,Running Bal.')
    if header_idx > 0:
        csv_text = csv_text[header_idx:]

    reader = csv.DictReader(io.StringIO(csv_text))
    txns = []
    for r in reader:
        date_str = (r.get('Date', '') or '').strip()
        if not date_str or '/' not in date_str:
            continue
        desc = (r.get('Description', '') or '').strip()
        if desc.startswith('Beginning balance') or desc.startswith('Ending balance'):
            continue
        date = parse_date_mdy(date_str)
        if not date:
            continue
        amount = parse_amount(r.get('Amount', '0'))
        if amount == 0 and not desc:
            continue
        txns.append({
            "date": date,
            "description": desc,
            "amount": round(amount, 2),
            "source_account": "BofA Checking",
        })
    return txns


def parse_discover(rows: List[Dict]) -> List[Dict]:
    txns = []
    for r in rows:
        date_str = (r.get('Trans. Date', '') or '').strip()
        if not date_str or '/' not in date_str:
            continue
        date = parse_date_mdy(date_str)
        if not date:
            continue
        raw_amt = parse_amount(r.get('Amount', '0'))
        # Discover: positive = charge, negative = credit. Flip sign.
        amount = round(-raw_amt, 2)
        desc = (r.get('Description', '') or '').strip()
        txns.append({
            "date": date,
            "description": desc,
            "amount": amount,
            "source_account": "Discover",
        })
    return txns


def parse_sofi(rows: List[Dict]) -> List[Dict]:
    txns = []
    for r in rows:
        date = (r.get('Date', '') or '').strip()
        if not date:
            continue
        desc = (r.get('Description', '') or '').strip()
        amount = parse_amount(r.get('Amount', '0'))
        txns.append({
            "date": date,  # Already YYYY-MM-DD
            "description": desc,
            "amount": round(amount, 2),
            "source_account": "SoFi Savings",
        })
    return txns


def parse_generic(rows: List[Dict]) -> List[Dict]:
    """Generic parser: expects Date, Description, Amount columns"""
    txns = []
    for r in rows:
        # Try common column names
        date_str = r.get('Date', r.get('date', r.get('Transaction Date', '')))
        desc = r.get('Description', r.get('description', r.get('Memo', '')))
        amt_str = r.get('Amount', r.get('amount', r.get('Amount (USD)', '0')))

        if not date_str or not desc:
            continue

        date_str = str(date_str).strip()
        # Try to parse date
        if '/' in date_str:
            date = parse_date_mdy(date_str)
        else:
            date = date_str  # Assume YYYY-MM-DD

        if not date:
            continue

        amount = parse_amount(str(amt_str))
        txns.append({
            "date": date,
            "description": str(desc).strip(),
            "amount": round(amount, 2),
            "source_account": "Unknown",
        })
    return txns


def process_csv(csv_text: str, source_hint: Optional[str] = None) -> List[Dict]:
    """Parse CSV text and return normalized transaction records"""
    # Try to detect BofA first (has special header handling)
    if 'Date,Description,Amount,Running Bal.' in csv_text:
        raw_txns = parse_bofa(csv_text)
    else:
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        if not rows:
            return []

        bank = source_hint or _detect_bank_format("", rows)

        if bank == 'apple_card':
            raw_txns = parse_apple_card(rows)
        elif bank == 'chase':
            raw_txns = parse_chase(rows)
        elif bank == 'discover':
            raw_txns = parse_discover(rows)
        elif bank == 'sofi':
            raw_txns = parse_sofi(rows)
        else:
            raw_txns = parse_generic(rows)

    # Categorize and enrich
    today = utc_date()
    for txn in raw_txns:
        # Fix future dates (year typo)
        if txn["date"] > today:
            year = int(txn["date"][:4]) - 1
            txn["date"] = str(year) + txn["date"][4:]

        txn["category"] = categorize(txn["description"])
        txn["transaction_type"] = get_transaction_type(txn["category"], txn["amount"])
        txn["merchant"] = normalize_merchant(txn["description"])

    return raw_txns


# ── API Handlers ────────────────────────────────────────────────────────────

@require_auth
def upload_csv(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST /v1/bank-statements/upload
    Body: { "csv_data": "<base64 or raw CSV>", "source_account": "optional hint", "account_name": "optional" }
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return respond(400, {"error": "Invalid JSON body"})

    csv_data = body.get('csv_data', '')
    source_hint = body.get('source_account')
    account_name = body.get('account_name')

    if not csv_data:
        return respond(400, {"error": "csv_data is required"})

    # Decode if base64
    if not csv_data.startswith('Date') and not csv_data.startswith('"Date') and ',' not in csv_data[:100]:
        try:
            # Handle data URL format
            if 'base64,' in csv_data:
                csv_data = csv_data.split('base64,', 1)[1]
            csv_data = base64.b64decode(csv_data).decode('utf-8')
        except Exception:
            return respond(400, {"error": "Invalid CSV data - could not decode"})

    # Parse and categorize
    transactions = process_csv(csv_data, source_hint)
    if not transactions:
        return respond(400, {"error": "No transactions found in CSV"})

    # Generate batch ID for this upload
    batch_id = str(uuid.uuid4())
    now = utc_now()

    # Deduplicate against existing transactions using targeted SQL
    # Only check the specific (date, description, amount) combos from this CSV
    existing = set()
    try:
        # Build a targeted query: only fetch existing rows that match dates in this upload
        upload_dates = list({txn['date'] for txn in transactions})
        if upload_dates:
            date_list = ", ".join(f"'{d}'" for d in upload_dates)
            sql = (
                f"SELECT date, description, ROUND(CAST(amount AS DOUBLE), 2) AS amount "
                f"FROM app_bank_transactions "
                f"WHERE user_id = '{user_id}' AND date IN ({date_list})"
            )
            result = db.execute_sql(sql)
            records = result.get('data', {}).get('records', [])
            for r in records:
                amt = round(float(r.get('amount', 0)), 2)
                key = f"{r.get('date')}|{r.get('description')}|{amt}"
                existing.add(key)
        logger.info(f"[dedup] Found {len(existing)} existing transactions matching upload dates")
    except Exception as e:
        logger.warning(f"[dedup] SQL query failed, skipping dedup: {e}")

    # Build records, skipping duplicates
    records = []
    skipped = 0
    for txn in transactions:
        amt = round(float(txn['amount']), 2)
        key = f"{txn['date']}|{txn['description']}|{amt}"
        if key in existing:
            skipped += 1
            continue

        records.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "date": txn["date"],
            "description": txn["description"],
            "merchant": txn["merchant"],
            "amount": txn["amount"],
            "category": txn["category"],
            "transaction_type": txn["transaction_type"],
            "source_account": txn.get("source_account", source_hint or "Unknown"),
            "upload_batch_id": batch_id,
            "created_at": now,
        })

    if not records:
        return respond(200, {
            "message": "All transactions already exist (duplicates skipped)",
            "batch_id": batch_id,
            "total_parsed": len(transactions),
            "imported": 0,
            "skipped": skipped,
        })

    # Write in batches of 100
    total_written = 0
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        result = db.write("app_bank_transactions", batch)
        if result.get('success'):
            total_written += len(batch)
        else:
            logger.error(f"Error writing batch {i}: {result.get('error')}")

    # Update or create bank account record
    detected_account = records[0]["source_account"] if records else "Unknown"
    acct_name = account_name or detected_account
    _upsert_bank_account(db, user_id, acct_name, detected_account, len(records), now)

    return respond(200, {
        "message": f"Imported {total_written} transactions",
        "batch_id": batch_id,
        "total_parsed": len(transactions),
        "imported": total_written,
        "skipped": skipped,
        "source_account": detected_account,
    })


def _upsert_bank_account(db, user_id: str, account_name: str, institution: str, txn_count: int, now: str):
    """Create or update bank account record"""
    try:
        result = db.execute_sql(
            "SELECT * FROM app_bank_accounts WHERE user_id = ? AND account_name = ? LIMIT 1",
            params=[user_id, account_name]
        )
        records = result.get('data', {}).get('records', [])

        if records:
            existing = records[0]
            db.write("app_bank_accounts", [{
                "id": existing["id"],
                "user_id": user_id,
                "account_name": account_name,
                "institution": institution,
                "transaction_count": (existing.get("transaction_count", 0) or 0) + txn_count,
                "last_upload_at": now,
                "updated_at": now,
                "created_at": existing.get("created_at", now),
            }])
        else:
            db.write("app_bank_accounts", [{
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "account_name": account_name,
                "account_type": "checking" if "check" in account_name.lower() or "saving" in account_name.lower() else "credit",
                "institution": institution,
                "transaction_count": txn_count,
                "last_upload_at": now,
                "created_at": now,
                "updated_at": now,
            }])
    except Exception as e:
        logger.error(f"Error upserting bank account: {e}")


@require_auth
def list_transactions(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/bank-transactions
    Query params: ?limit=1000&source_account=...&category=...&transaction_type=...
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    query_params = event.get('queryStringParameters') or {}
    limit = min(int(query_params.get('limit', '5000')), 10000)

    try:
        conditions = ["user_id = ?"]
        params = [user_id]

        if query_params.get('source_account'):
            conditions.append("source_account = ?")
            params.append(query_params['source_account'])
        if query_params.get('category'):
            conditions.append("category = ?")
            params.append(query_params['category'])
        if query_params.get('transaction_type'):
            conditions.append("transaction_type = ?")
            params.append(query_params['transaction_type'])

        sql = f"SELECT * FROM app_bank_transactions WHERE {' AND '.join(conditions)} ORDER BY date DESC LIMIT {int(limit)}"
        result = db.execute_sql(sql, params=params)
        records = result.get('data', {}).get('records', [])
        return respond(200, {"transactions": records, "total": len(records)})
    except Exception as e:
        logger.error(f"Error listing transactions: {e}")
        return respond(500, {"error": str(e)})


@require_auth
def list_accounts(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/bank-accounts
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        result = db.execute_sql(
            "SELECT * FROM app_bank_accounts WHERE user_id = ? ORDER BY updated_at DESC LIMIT 50",
            params=[user_id]
        )
        records = result.get('data', {}).get('records', [])
        return respond(200, {"accounts": records, "total": len(records)})
    except Exception as e:
        return respond(500, {"error": str(e)})


@require_auth
def delete_batch(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    DELETE /v1/bank-statements/batch/:batch_id — Delete all transactions from a specific upload
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'
    batch_id = event.get('pathParameters', {}).get('batch_id')

    if not batch_id:
        return respond(400, {"error": "batch_id is required"})

    try:
        result = db.delete("app_bank_transactions", filters=[
            {"field": "user_id", "operator": "eq", "value": user_id},
            {"field": "upload_batch_id", "operator": "eq", "value": batch_id},
        ])
        if result.get('success'):
            return respond(200, {"message": f"Deleted batch {batch_id}"})
        else:
            return respond(500, {"error": "Failed to delete batch"})
    except Exception as e:
        return respond(500, {"error": str(e)})


EXPENSE_CATEGORIES = [
    "Housing/Rent", "Groceries", "Dining", "Gas/Fuel", "Software/Tech",
    "Shopping", "Medical", "Insurance", "Utilities", "Auto", "Personal Care",
    "Education", "Charity", "Zelle Send", "Fees", "Other"
]

CATEGORY_KEY_MAP = {
    "Housing/Rent": "housing", "Groceries": "groceries", "Dining": "dining",
    "Shopping": "shopping", "Software/Tech": "software", "Gas/Fuel": "gas",
    "Medical": "medical", "Insurance": "insurance", "Utilities": "utilities",
    "Auto": "auto", "Personal Care": "personal_care", "Education": "education",
    "Charity": "charity", "Zelle Send": "zelle_send", "Fees": "fees", "Other": "other"
}

CATEGORY_COLORS = {
    "Housing/Rent": "#7c3aed", "Groceries": "#10b981", "Dining": "#f59e0b",
    "Shopping": "#6366f1", "Software/Tech": "#8b5cf6", "Gas/Fuel": "#ef4444",
    "Medical": "#ec4899", "Insurance": "#0ea5e9", "Utilities": "#14b8a6",
    "Auto": "#f97316", "Personal Care": "#64748b", "Education": "#a855f7",
    "Charity": "#f472b6", "Zelle Send": "#d946ef", "Fees": "#78716c", "Other": "#6b7280"
}

RECURRING_KEYWORDS = {
    "CURSOR": ("Cursor", "Software/Tech"),
    "COMCAST": ("Comcast", "Utilities"),
    "DISNEYPLUS": ("Disney+", "Utilities"),
    "DISNEY+": ("Disney+", "Utilities"),
    "MINT MOBILE": ("Mint Mobile", "Utilities"),
    "APPLE.COM/BILL": ("Apple Services", "Software/Tech"),
    "FIRST EQUITY": ("Rent (First Equity)", "Housing/Rent"),
    "NETFLIX": ("Netflix", "Software/Tech"),
}


@require_auth
def get_dashboard_data(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /v1/bank-statements/dashboard
    Returns pre-aggregated dashboard data using SQL GROUP BY queries.
    Pushes heavy aggregation into DuckDB engine instead of Python loops.
    """
    db = context['db']
    user_id = get_user_id(event) or 'local-dev-user'

    try:
        # 1. Monthly aggregation via SQL GROUP BY
        monthly_sql = f"""
            SELECT
                strftime(CAST(date AS DATE), '%b %Y') AS month,
                strftime(CAST(date AS DATE), '%Y-%m') AS month_sort,
                SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN transaction_type = 'expense' THEN ABS(amount) ELSE 0 END) AS expenses,
                SUM(CASE WHEN transaction_type = 'refund' THEN ABS(amount) ELSE 0 END) AS refunds,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Housing/Rent' THEN ABS(amount) ELSE 0 END) AS housing,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Groceries' THEN ABS(amount) ELSE 0 END) AS groceries,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Dining' THEN ABS(amount) ELSE 0 END) AS dining,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Shopping' THEN ABS(amount) ELSE 0 END) AS shopping,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Software/Tech' THEN ABS(amount) ELSE 0 END) AS software,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Gas/Fuel' THEN ABS(amount) ELSE 0 END) AS gas,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Medical' THEN ABS(amount) ELSE 0 END) AS medical,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Insurance' THEN ABS(amount) ELSE 0 END) AS insurance,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Utilities' THEN ABS(amount) ELSE 0 END) AS utilities,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Auto' THEN ABS(amount) ELSE 0 END) AS auto,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Personal Care' THEN ABS(amount) ELSE 0 END) AS personal_care,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Education' THEN ABS(amount) ELSE 0 END) AS education,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Charity' THEN ABS(amount) ELSE 0 END) AS charity,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Zelle Send' THEN ABS(amount) ELSE 0 END) AS zelle_send,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Fees' THEN ABS(amount) ELSE 0 END) AS fees,
                SUM(CASE WHEN transaction_type = 'expense' AND category = 'Other' THEN ABS(amount) ELSE 0 END) AS other
            FROM app_bank_transactions
            WHERE user_id = '{user_id}'
            GROUP BY month, month_sort
            ORDER BY month_sort ASC
        """
        monthly_result = db.execute_sql(monthly_sql)
        monthly_rows = monthly_result.get('data', {}).get('records', [])

        if not monthly_rows:
            return respond(200, {"transactions": [], "monthlyData": [], "dateRange": None})

        # Build monthly data from SQL results
        cat_fields = list(CATEGORY_KEY_MAP.values())
        monthly_data = []
        for row in monthly_rows:
            m = {"month": row.get("month", "")}
            income = float(row.get("income", 0) or 0)
            refunds = float(row.get("refunds", 0) or 0)
            expenses_total = 0
            for cf in cat_fields:
                val = max(0, round(float(row.get(cf, 0) or 0), 2))
                m[cf] = val
                expenses_total += val
            # Subtract refunds from expenses
            m["expenses"] = round(max(0, expenses_total - refunds), 2)
            m["income"] = round(income, 2)
            m["net"] = round(income - m["expenses"], 2)
            monthly_data.append(m)

        # 2. Category totals via SQL
        category_sql = f"""
            SELECT category, ROUND(SUM(ABS(amount)), 2) AS total
            FROM app_bank_transactions
            WHERE user_id = '{user_id}' AND transaction_type = 'expense'
            GROUP BY category
            ORDER BY total DESC
        """
        cat_result = db.execute_sql(category_sql)
        cat_rows = cat_result.get('data', {}).get('records', [])
        category_totals = [
            {"name": r["category"], "amount": float(r.get("total", 0) or 0), "color": CATEGORY_COLORS.get(r["category"], "#6b7280")}
            for r in cat_rows if float(r.get("total", 0) or 0) > 0
        ]

        # 3. Outflow by month via SQL
        outflow_sql = f"""
            SELECT
                strftime(CAST(date AS DATE), '%b %Y') AS month,
                strftime(CAST(date AS DATE), '%Y-%m') AS month_sort,
                ROUND(SUM(ABS(amount)), 2) AS total,
                ROUND(SUM(CASE WHEN transaction_type = 'transfer' AND (UPPER(description) LIKE '%FID BKG SVC%' OR UPPER(description) LIKE '%ROBINHOOD%') THEN ABS(amount) ELSE 0 END), 2) AS investments,
                ROUND(SUM(CASE WHEN transaction_type = 'transfer' AND (UPPER(description) LIKE '%APPLECARD%' OR UPPER(description) LIKE '%CHASE CREDIT%' OR UPPER(description) LIKE '%DISCOVER%' OR UPPER(description) LIKE '%PAYMENT THANK%') THEN ABS(amount) ELSE 0 END), 2) AS card_payments,
                ROUND(SUM(CASE WHEN category = 'Housing/Rent' THEN ABS(amount) ELSE 0 END), 2) AS rent,
                ROUND(SUM(CASE WHEN category = 'Zelle Send' THEN ABS(amount) ELSE 0 END), 2) AS zelle,
                ROUND(SUM(CASE WHEN transaction_type = 'expense' AND category NOT IN ('Housing/Rent', 'Zelle Send') THEN ABS(amount) ELSE 0 END), 2) AS expenses,
                ROUND(SUM(CASE WHEN transaction_type = 'transfer' AND NOT (UPPER(description) LIKE '%FID BKG SVC%' OR UPPER(description) LIKE '%ROBINHOOD%' OR UPPER(description) LIKE '%APPLECARD%' OR UPPER(description) LIKE '%CHASE CREDIT%' OR UPPER(description) LIKE '%DISCOVER%' OR UPPER(description) LIKE '%PAYMENT THANK%') THEN ABS(amount) ELSE 0 END), 2) AS other_transfers
            FROM app_bank_transactions
            WHERE user_id = '{user_id}' AND amount < 0
            GROUP BY month, month_sort
            ORDER BY month_sort ASC
        """
        outflow_result = db.execute_sql(outflow_sql)
        outflow_rows = outflow_result.get('data', {}).get('records', [])
        outflow_by_month = [{
            "month": r.get("month", ""),
            "investments": float(r.get("investments", 0) or 0),
            "cardPayments": float(r.get("card_payments", 0) or 0),
            "rent": float(r.get("rent", 0) or 0),
            "zelle": float(r.get("zelle", 0) or 0),
            "expenses": float(r.get("expenses", 0) or 0),
            "otherTransfers": float(r.get("other_transfers", 0) or 0),
            "total": float(r.get("total", 0) or 0),
        } for r in outflow_rows]

        # 4. Recurring detection via SQL GROUP BY
        recurring_sql = f"""
            SELECT
                description,
                category,
                COUNT(*) AS occurrences,
                ROUND(AVG(ABS(amount)), 2) AS avg_amount,
                MIN(date) AS first_date,
                MAX(date) AS last_date
            FROM app_bank_transactions
            WHERE user_id = '{user_id}' AND transaction_type = 'expense'
            GROUP BY description, category
            HAVING COUNT(*) >= 2
            ORDER BY avg_amount DESC
        """
        recurring_result = db.execute_sql(recurring_sql)
        recurring_rows = recurring_result.get('data', {}).get('records', [])
        recurring_items = _build_recurring_from_sql(recurring_rows)

        # 5. Date range via SQL MIN/MAX
        range_sql = f"SELECT MIN(date) AS start_date, MAX(date) AS end_date FROM app_bank_transactions WHERE user_id = '{user_id}'"
        range_result = db.execute_sql(range_sql)
        range_rows = range_result.get('data', {}).get('records', [])
        date_range = None
        if range_rows:
            date_range = {"start": range_rows[0].get("start_date", ""), "end": range_rows[0].get("end_date", "")}

        # 6. Fetch transactions for frontend drill-down (still needed for transaction list tab)
        txn_sql = f"""
            SELECT date, description, merchant, amount, category, source_account, transaction_type
            FROM app_bank_transactions
            WHERE user_id = '{user_id}'
            ORDER BY date DESC
        """
        txn_result = db.execute_sql(txn_sql)
        txn_rows = txn_result.get('data', {}).get('records', [])

        return respond(200, {
            "monthlyData": monthly_data,
            "categoryTotals": category_totals,
            "recurringItems": recurring_items,
            "accountBalances": {"bofaChecking": 0, "sofiSavings": 0, "asOf": date_range["end"] if date_range else ""},
            "incomeByMonth": [],
            "outflowByMonth": outflow_by_month,
            "investmentSummary": {"totalInvested": 0, "byDestination": [], "count": 0},
            "dateRange": date_range,
            "transactions": [{
                "date": t.get("date", ""),
                "description": t.get("description", ""),
                "merchant": t.get("merchant", ""),
                "amount": t.get("amount", 0),
                "category": t.get("category", ""),
                "sourceAccount": t.get("source_account", ""),
                "transactionType": t.get("transaction_type", ""),
            } for t in txn_rows],
        })

    except Exception as e:
        logger.error(f"Error building dashboard: {e}")
        return respond(500, {"error": str(e)})


def _build_recurring_from_sql(recurring_rows: List[Dict]) -> List[Dict]:
    """Build recurring items from SQL GROUP BY results"""
    result = []
    for row in recurring_rows:
        desc = (row.get("description", "") or "").upper()
        occurrences = int(row.get("occurrences", 0) or 0)
        avg_amount = float(row.get("avg_amount", 0) or 0)
        first_date = row.get("first_date", "")
        last_date = row.get("last_date", "")

        # Match against known recurring keywords
        matched_name = None
        matched_type = None
        for kw, (name, cat) in RECURRING_KEYWORDS.items():
            if kw in desc:
                matched_name = name
                matched_type = cat
                break

        if not matched_name:
            continue

        # Estimate cadence from date spread
        try:
            d1 = datetime.strptime(first_date, '%Y-%m-%d')
            d2 = datetime.strptime(last_date, '%Y-%m-%d')
            span_days = (d2 - d1).days
            avg_days = span_days / (occurrences - 1) if occurrences > 1 else 30
        except (ValueError, TypeError):
            avg_days = 30

        cadence = "yearly" if avg_days > 300 else "quarterly" if avg_days > 50 else "monthly"
        result.append({
            "merchant": matched_name,
            "cadence": cadence,
            "type": matched_type,
            "avgAmount": round(avg_amount, 2),
        })

    result.sort(key=lambda r: r['avgAmount'], reverse=True)
    return result

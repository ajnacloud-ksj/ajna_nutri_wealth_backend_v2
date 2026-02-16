"""
Receipt Schema for Structured Outputs
Defines the JSON schema for receipt analysis responses
"""

# OpenAI Structured Output Schema for Receipts
RECEIPT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant_name": {
            "type": "string",
            "description": "Store/vendor name exactly as shown"
        },
        "store_address": {
            "type": ["string", "null"],
            "description": "Full address if visible"
        },
        "store_phone": {
            "type": ["string", "null"],
            "description": "Phone number if visible"
        },
        "store_location": {
            "type": "object",
            "properties": {
                "city": {"type": ["string", "null"]},
                "state": {"type": ["string", "null"]},
                "postal_code": {"type": ["string", "null"]},
                "country": {"type": ["string", "null"]}
            },
            "required": []
        },
        "purchase_date": {
            "type": "string",
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
            "description": "Date in YYYY-MM-DD format"
        },
        "purchase_time": {
            "type": ["string", "null"],
            "pattern": "^\\d{2}:\\d{2}:\\d{2}$",
            "description": "Time in HH:MM:SS format"
        },
        "receipt_number": {
            "type": ["string", "null"],
            "description": "Receipt/transaction number"
        },
        "cashier": {
            "type": ["string", "null"],
            "description": "Cashier name/ID if shown"
        },
        "register": {
            "type": ["string", "null"],
            "description": "Register/terminal number if shown"
        },
        "financial_summary": {
            "type": "object",
            "properties": {
                "subtotal": {
                    "type": "number",
                    "description": "Pre-tax amount"
                },
                "tax_amount": {
                    "type": "number",
                    "description": "Total tax"
                },
                "tax_rate": {
                    "type": ["number", "null"],
                    "description": "Tax percentage if calculable"
                },
                "discount_amount": {
                    "type": "number",
                    "description": "Total discounts/savings"
                },
                "tip_amount": {
                    "type": "number",
                    "description": "Tip if applicable"
                },
                "total_amount": {
                    "type": "number",
                    "description": "Final total"
                },
                "currency": {
                    "type": "string",
                    "default": "USD",
                    "description": "Currency code"
                }
            },
            "required": ["subtotal", "tax_amount", "total_amount"]
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full item name/description"
                    },
                    "sku": {
                        "type": ["string", "null"],
                        "description": "SKU/barcode if visible"
                    },
                    "quantity": {
                        "type": "number",
                        "default": 1,
                        "description": "Item quantity"
                    },
                    "unit_price": {
                        "type": "number",
                        "description": "Price per unit"
                    },
                    "total_price": {
                        "type": "number",
                        "description": "Total price for this item"
                    },
                    "discount": {
                        "type": ["number", "null"],
                        "description": "Item-specific discount"
                    },
                    "tax": {
                        "type": ["number", "null"],
                        "description": "Item-specific tax if shown"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["Groceries", "Produce", "Meat", "Dairy", "Beverages", "Snacks",
                                "Electronics", "Clothing", "Home", "Health", "Beauty", "Other"],
                        "description": "Item category"
                    },
                    "department": {
                        "type": ["string", "null"],
                        "description": "Department if shown on receipt"
                    },
                    "is_taxable": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether item was taxed"
                    }
                },
                "required": ["name", "total_price", "category"]
            }
        },
        "payment": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["Cash", "Credit", "Debit", "Check", "Mobile", "Other"],
                    "description": "Payment method"
                },
                "card_type": {
                    "type": ["string", "null"],
                    "enum": ["Visa", "Mastercard", "Amex", "Discover", None],
                    "description": "Card type if applicable"
                },
                "card_last_digits": {
                    "type": ["string", "null"],
                    "pattern": "^\\d{4}$",
                    "description": "Last 4 digits if shown"
                },
                "transaction_id": {
                    "type": ["string", "null"],
                    "description": "Payment transaction ID"
                },
                "approval_code": {
                    "type": ["string", "null"],
                    "description": "Payment approval code if shown"
                }
            },
            "required": ["method"]
        },
        "receipt_category": {
            "type": "string",
            "enum": ["Grocery", "Restaurant", "Retail", "Gas", "Pharmacy", "Entertainment", "Services", "Other"],
            "description": "Overall receipt category"
        },
        "loyalty_info": {
            "type": ["object", "null"],
            "properties": {
                "member_id": {"type": ["string", "null"]},
                "points_earned": {"type": ["number", "null"]},
                "points_balance": {"type": ["number", "null"]}
            }
        },
        "notes": {
            "type": ["string", "null"],
            "description": "Any additional observations"
        }
    },
    "required": ["merchant_name", "purchase_date", "financial_summary", "items", "payment", "receipt_category"],
    "additionalProperties": False
}
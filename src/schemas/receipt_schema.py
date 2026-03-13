"""
Receipt Schema for OpenAI Structured Outputs (strict mode)

All properties must be listed in "required".
Nullable fields use {"anyOf": [{"type": "string"}, {"type": "null"}]}.
No "default", "pattern", or "additionalProperties" at nested levels in strict mode.
"""

# Helper for nullable string
_nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_nullable_number = {"anyOf": [{"type": "number"}, {"type": "null"}]}
_nullable_boolean = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}


RECEIPT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "merchant_name": {
            "type": "string",
            "description": "Store or brand name (e.g. 'OLD Navy', 'Walmart'). Must be the business name, NEVER a country, city, or address."
        },
        "store_address": {
            **_nullable_string,
            "description": "Full address if visible"
        },
        "store_phone": {
            **_nullable_string,
            "description": "Phone number if visible"
        },
        "store_location": {
            "type": "object",
            "properties": {
                "city": {**_nullable_string, "description": "City name"},
                "state": {**_nullable_string, "description": "State/province"},
                "postal_code": {**_nullable_string, "description": "ZIP/postal code"},
                "country": {**_nullable_string, "description": "Country name or code"}
            },
            "required": ["city", "state", "postal_code", "country"],
            "additionalProperties": False
        },
        "purchase_date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format"
        },
        "purchase_time": {
            **_nullable_string,
            "description": "Time in HH:MM:SS format"
        },
        "receipt_number": {
            **_nullable_string,
            "description": "Receipt/transaction number"
        },
        "cashier": {
            **_nullable_string,
            "description": "Cashier name/ID if shown"
        },
        "register": {
            **_nullable_string,
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
                    **_nullable_number,
                    "description": "Tax percentage if calculable"
                },
                "discount_amount": {
                    "type": "number",
                    "description": "Total discounts/savings (0 if none)"
                },
                "tip_amount": {
                    "type": "number",
                    "description": "Tip if applicable (0 if none)"
                },
                "total_amount": {
                    "type": "number",
                    "description": "Final total"
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code (e.g. USD, EUR)"
                }
            },
            "required": ["subtotal", "tax_amount", "tax_rate", "discount_amount", "tip_amount", "total_amount", "currency"],
            "additionalProperties": False
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
                        **_nullable_string,
                        "description": "SKU/barcode if visible"
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Item quantity (1 if not specified)"
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
                        **_nullable_number,
                        "description": "Item-specific discount"
                    },
                    "tax": {
                        **_nullable_number,
                        "description": "Item-specific tax if shown"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["Groceries", "Produce", "Meat", "Dairy", "Beverages", "Snacks",
                                "Electronics", "Clothing", "Home", "Health", "Beauty", "Other"],
                        "description": "Item category"
                    },
                    "department": {
                        **_nullable_string,
                        "description": "Department if shown on receipt"
                    },
                    "is_taxable": {
                        "type": "boolean",
                        "description": "Whether item was taxed"
                    }
                },
                "required": ["name", "sku", "quantity", "unit_price", "total_price", "discount", "tax", "category", "department", "is_taxable"],
                "additionalProperties": False
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
                    **_nullable_string,
                    "description": "Card type (Visa, Mastercard, Amex, Discover) or null"
                },
                "card_last_digits": {
                    **_nullable_string,
                    "description": "Last 4 digits if shown"
                },
                "transaction_id": {
                    **_nullable_string,
                    "description": "Payment transaction ID"
                },
                "approval_code": {
                    **_nullable_string,
                    "description": "Payment approval code if shown"
                }
            },
            "required": ["method", "card_type", "card_last_digits", "transaction_id", "approval_code"],
            "additionalProperties": False
        },
        "receipt_category": {
            "type": "string",
            "enum": ["Grocery", "Restaurant", "Retail", "Gas", "Pharmacy", "Entertainment", "Services", "Other"],
            "description": "Overall receipt category"
        },
        "loyalty_info": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "member_id": {**_nullable_string, "description": "Loyalty/member number"},
                        "points_earned": {**_nullable_number, "description": "Points earned this transaction"},
                        "points_balance": {**_nullable_number, "description": "Total points balance if shown"}
                    },
                    "required": ["member_id", "points_earned", "points_balance"],
                    "additionalProperties": False
                },
                {"type": "null"}
            ],
            "description": "Loyalty program info if available"
        },
        "notes": {
            **_nullable_string,
            "description": "Any additional observations"
        }
    },
    "required": [
        "merchant_name", "store_address", "store_phone", "store_location",
        "purchase_date", "purchase_time", "receipt_number", "cashier", "register",
        "financial_summary", "items", "payment", "receipt_category",
        "loyalty_info", "notes"
    ],
    "additionalProperties": False
}

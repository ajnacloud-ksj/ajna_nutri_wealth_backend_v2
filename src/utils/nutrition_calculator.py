"""
Utility to calculate nutrition totals from food entries on the fly
"""

import json
from typing import Dict, Any

def compute_nutrition_totals(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute nutrition totals from extracted_nutrients.food_items
    This is done on the fly to avoid data duplication
    """
    # Start with existing values or 0
    totals = {
        'calories': entry.get('calories', 0),
        'total_protein': entry.get('total_protein', 0),
        'total_carbohydrates': entry.get('total_carbohydrates', 0),
        'total_fats': entry.get('total_fats', 0),
        'total_fiber': entry.get('total_fiber', 0),
        'total_sodium': entry.get('total_sodium', 0)
    }

    # If we already have non-zero totals, return them
    if totals['total_protein'] > 0 or totals['total_carbohydrates'] > 0 or totals['total_fats'] > 0:
        return totals

    # Parse extracted_nutrients if it's a string
    extracted = entry.get('extracted_nutrients')
    if not extracted:
        return totals

    if isinstance(extracted, str):
        try:
            extracted = json.loads(extracted)
        except:
            return totals

    # Calculate from food_items
    food_items = extracted.get('food_items', [])
    if not food_items:
        return totals

    # Compute totals
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

    # Update totals with computed values
    totals['total_protein'] = total_protein
    totals['total_carbohydrates'] = total_carbohydrates
    totals['total_fats'] = total_fats
    totals['total_fiber'] = total_fiber
    totals['total_sodium'] = total_sodium

    return totals

def enrich_food_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a food entry with computed nutrition totals
    """
    # Compute totals
    totals = compute_nutrition_totals(entry)

    # Add computed totals to entry
    entry.update(totals)

    return entry

def enrich_food_entries(entries: list) -> list:
    """
    Enrich multiple food entries with computed nutrition totals
    """
    return [enrich_food_entry(entry) for entry in entries]
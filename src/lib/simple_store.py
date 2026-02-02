"""
Simple In-Memory Database - No Ibex, No Complex Setup
Perfect for development and small-scale deployment
"""

import json
import os
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional, Any

class SimpleStore:
    """
    Thread-safe in-memory store with optional file persistence
    No complex schemas, no required fields, just works!
    """

    def __init__(self, persist_file: str = "data/food_app.json"):
        self.persist_file = persist_file
        self.lock = Lock()
        self.data = {
            "food_entries": {},
            "users": {},
            "analysis_queue": {}
        }
        self._load_from_file()

    def _load_from_file(self):
        """Load data from file if it exists"""
        if os.path.exists(self.persist_file):
            try:
                with open(self.persist_file, 'r') as f:
                    self.data = json.load(f)
                print(f"✅ Loaded data from {self.persist_file}")
            except Exception as e:
                print(f"⚠️ Could not load data: {e}")

    def _save_to_file(self):
        """Save data to file for persistence"""
        try:
            os.makedirs(os.path.dirname(self.persist_file), exist_ok=True)
            with open(self.persist_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Could not save data: {e}")

    def write(self, table: str, records: List[Dict[str, Any]]) -> Dict:
        """
        Write records to a table
        No schema validation - just stores what you give it!
        """
        with self.lock:
            if table not in self.data:
                self.data[table] = {}

            for record in records:
                record_id = record.get('id', str(datetime.utcnow().timestamp()))
                # Add metadata
                record['_updated_at'] = datetime.utcnow().isoformat()
                if record_id not in self.data[table]:
                    record['_created_at'] = datetime.utcnow().isoformat()

                self.data[table][record_id] = record

            self._save_to_file()

        return {"success": True, "count": len(records)}

    def query(self, table: str, filters: List[Dict] = None,
              sort: List[Dict] = None, limit: int = 100) -> Dict:
        """
        Query records from a table
        Simple filtering and sorting
        """
        with self.lock:
            if table not in self.data:
                return {"success": True, "data": {"records": []}}

            # Get all records as list
            records = list(self.data[table].values())

            # Apply filters
            if filters:
                for f in filters:
                    field = f['field']
                    op = f['operator']
                    value = f['value']

                    if op == 'eq':
                        records = [r for r in records if r.get(field) == value]
                    elif op == 'neq':
                        records = [r for r in records if r.get(field) != value]
                    elif op == 'gt':
                        records = [r for r in records if r.get(field, 0) > value]
                    elif op == 'lt':
                        records = [r for r in records if r.get(field, 0) < value]
                    elif op == 'contains':
                        records = [r for r in records if value in str(r.get(field, ''))]

            # Apply sorting
            if sort:
                for s in reversed(sort):  # Apply in reverse order for multiple sorts
                    field = s['field']
                    reverse = s.get('order', 'asc') == 'desc'
                    records.sort(key=lambda x: x.get(field, ''), reverse=reverse)

            # Apply limit
            records = records[:limit]

            return {
                "success": True,
                "data": {
                    "records": records
                }
            }

    def get(self, table: str, record_id: str) -> Optional[Dict]:
        """Get a single record by ID"""
        with self.lock:
            if table in self.data and record_id in self.data[table]:
                return self.data[table][record_id]
            return None

    def delete(self, table: str, record_id: str) -> Dict:
        """Delete a record"""
        with self.lock:
            if table in self.data and record_id in self.data[table]:
                del self.data[table][record_id]
                self._save_to_file()
                return {"success": True}
            return {"success": False, "error": "Record not found"}

    def update(self, table: str, record_id: str, updates: Dict) -> Dict:
        """Update a record"""
        with self.lock:
            if table in self.data and record_id in self.data[table]:
                self.data[table][record_id].update(updates)
                self.data[table][record_id]['_updated_at'] = datetime.utcnow().isoformat()
                self._save_to_file()
                return {"success": True}
            return {"success": False, "error": "Record not found"}

    def clear_table(self, table: str) -> Dict:
        """Clear all records in a table"""
        with self.lock:
            if table in self.data:
                self.data[table] = {}
                self._save_to_file()
                return {"success": True}
            return {"success": False, "error": "Table not found"}

    def get_stats(self) -> Dict:
        """Get database statistics"""
        with self.lock:
            stats = {}
            for table, records in self.data.items():
                stats[table] = len(records)
            return stats


# Singleton instance
_store_instance = None

def get_store() -> SimpleStore:
    """Get the singleton store instance"""
    global _store_instance
    if _store_instance is None:
        _store_instance = SimpleStore()
    return _store_instance
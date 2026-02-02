#!/bin/bash

# Cleanup script to remove old/unused files after modernization

echo "🧹 Cleaning up old files..."

# Remove old handlers
echo "Removing old handlers..."
rm -f src/handlers/ai.py  # Replaced by analyze_improved
rm -f src/handlers/analyze_direct.py  # Replaced by analyze_improved
rm -f src/handlers/data_fixed.py  # Replaced by modern data.py

# Remove old AI service (keeping only optimized)
echo "Removing old AI service..."
rm -f src/lib/ai.py  # Replaced by ai_optimized.py

# Remove old server
echo "Removing old server..."
rm -f local_server.py  # Replaced by local_server_secure.py

# Remove old simple store if exists
rm -f src/lib/simple_store.py  # Not needed

echo "✅ Cleanup complete!"
echo ""
echo "Remaining files:"
echo "  Handlers:"
ls -la src/handlers/*.py | grep -v __pycache__
echo ""
echo "  Core services:"
ls -la src/lib/*.py | grep -v __pycache__
echo ""
echo "To run the modernized server:"
echo "  AUTH_MODE=local python3 local_server_secure.py"
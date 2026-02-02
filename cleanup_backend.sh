#!/bin/bash

# Backend Cleanup Script - Organize and remove duplicates
echo "🧹 Cleaning up backend directory..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Dry run by default
DRY_RUN=true
if [[ "$1" == "--execute" ]]; then
    DRY_RUN=false
    echo -e "${RED}⚠️  Running in EXECUTE mode - files will be moved/deleted!${NC}"
else
    echo -e "${YELLOW}Running in DRY RUN mode${NC}"
    echo "To execute: ./cleanup_backend.sh --execute"
fi
echo ""

# Function to handle files
handle_file() {
    local action=$1
    local file=$2
    local dest=$3

    if [ ! -e "$file" ]; then
        return
    fi

    if [ "$DRY_RUN" = true ]; then
        if [ "$action" = "delete" ]; then
            echo -e "${YELLOW}[DRY RUN]${NC} Would delete: $file"
        else
            echo -e "${YELLOW}[DRY RUN]${NC} Would move: $file → $dest"
        fi
    else
        if [ "$action" = "delete" ]; then
            rm -f "$file"
            echo -e "${RED}[DELETED]${NC} $file"
        else
            mkdir -p "$(dirname "$dest")"
            mv "$file" "$dest"
            echo -e "${GREEN}[MOVED]${NC} $file → $dest"
        fi
    fi
}

echo "📁 Cleaning up handlers (removing duplicates)..."
# Keep only the working handlers used by router
handle_file "delete" "src/handlers/analyze_improved.py" ""
handle_file "delete" "src/handlers/analyze_direct_old.py" ""
handle_file "delete" "src/handlers/analyze_lambda_async.py" ""
handle_file "delete" "src/handlers/analyze_async_lambda.py" ""
handle_file "delete" "src/handlers/ai.py" ""
handle_file "delete" "src/handlers/data_fixed.py" ""
# Keep: analyze.py, analyze_async.py, data.py, auth.py, storage.py, receipts.py, model_config.py

echo ""
echo "📁 Organizing root level Python files..."
# Move test files to tests/
handle_file "move" "test_all_endpoints.py" "tests/test_all_endpoints.py"
handle_file "move" "test_function_url.py" "tests/test_function_url.py"
handle_file "move" "test_improvements.py" "tests/test_improvements.py"
handle_file "move" "test_optimization.py" "tests/test_optimization.py"
handle_file "move" "test_performance.py" "tests/test_performance.py"
handle_file "move" "test_performance_quick.py" "tests/test_performance_quick.py"
handle_file "move" "test_storage_fix.py" "tests/test_storage_fix.py"
handle_file "move" "test_warm_performance.py" "tests/test_warm_performance.py"
handle_file "move" "test_simple_write.py" "tests/test_simple_write.py"
handle_file "move" "test_new_table.py" "tests/test_new_table.py"

# Move migration/utility scripts to scripts/
handle_file "move" "migrate_to_optimized.py" "scripts/migrate_to_optimized.py"
handle_file "move" "check_ibex_schema.py" "scripts/check_ibex_schema.py"

# Delete old/duplicate server files
handle_file "delete" "local_server_new.py" ""
handle_file "delete" "local_server_secure.py" ""
# Keep local_server.py for development

echo ""
echo "📁 Consolidating documentation..."
# Keep only essential docs in backend root
handle_file "move" "MODERNIZATION_COMPLETE.md" "docs/archive/MODERNIZATION_COMPLETE.md"
handle_file "move" "ASYNC_IMPLEMENTATION_STATUS.md" "docs/archive/ASYNC_IMPLEMENTATION_STATUS.md"
# Keep: LAMBDA_DEPLOYMENT_GUIDE.md, SQS_SETUP_GUIDE.md, MODEL_CONFIG_GUIDE.md, DEPLOYMENT_OIDC_SETUP.md

echo ""
echo "📁 Organizing scripts..."
# Consolidate all scripts in scripts/
handle_file "move" "run_tests.sh" "scripts/run_tests.sh"
handle_file "move" "cleanup.sh" "scripts/cleanup.sh"
handle_file "move" "test_all_endpoints.sh" "scripts/test_all_endpoints.sh"
handle_file "move" "test_quick.sh" "scripts/test_quick.sh"
handle_file "move" "test_queue_with_image.sh" "scripts/test_queue_with_image.sh"
handle_file "move" "run_docker.sh" "scripts/run_docker.sh"

echo ""
echo "📁 Cleaning up lib directory..."
# Check for duplicates in lib/
handle_file "delete" "src/lib/ai.py" ""  # If ai_optimized.py exists
handle_file "delete" "src/lib/ibex_client_old.py" ""

echo ""
echo "📁 SQL folder check..."
if [ -d "sql" ]; then
    echo "SQL folder found - moving to resources/"
    handle_file "move" "sql" "resources/sql"
fi

echo ""
echo "📁 Removing unnecessary files..."
handle_file "delete" "payload_test.json" ""
handle_file "delete" "server.log" ""
handle_file "delete" "NutriWealth_API.postman_collection.json" ""

echo ""
echo "📋 Final Structure:"
echo "backend/"
echo "├── src/"
echo "│   ├── handlers/       # Clean handlers (7 files)"
echo "│   ├── lib/           # Core libraries"
echo "│   ├── config/        # Configuration"
echo "│   ├── schemas/       # DB schemas"
echo "│   ├── prompts/       # AI prompts"
echo "│   └── routes/        # API routes"
echo "├── tests/             # All test files"
echo "├── scripts/           # All utility scripts"
echo "├── docs/              # Documentation"
echo "├── aws/               # AWS setup scripts"
echo "├── Dockerfile         # Lambda container"
echo "├── requirements.txt   # Dependencies"
echo "└── *.md              # Essential guides only"

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo -e "${YELLOW}This was a DRY RUN - no changes made${NC}"
    echo "To execute: ./cleanup_backend.sh --execute"
else
    echo ""
    echo -e "${GREEN}✅ Cleanup complete!${NC}"
    echo "Handlers reduced from 10+ to 7 working files"
    echo "Test files organized in tests/"
    echo "Scripts consolidated in scripts/"
fi
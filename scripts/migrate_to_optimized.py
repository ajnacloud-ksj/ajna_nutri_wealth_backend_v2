#!/usr/bin/env python3
"""
Safe migration script to switch from regular IbexClient to OptimizedIbexClient
Run this to test the optimized client before fully switching over
"""

import sys
import os
import time
import json
import statistics
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lib.ibex_client import IbexClient
from lib.ibex_client_optimized import OptimizedIbexClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get settings from environment
class Settings:
    IBEX_API_URL = os.getenv('IBEX_API_URL', 'https://smartlink.ajna.cloud/ibexdb')
    IBEX_API_KEY = os.getenv('IBEX_API_KEY', 'sk-v5G1QnG6qLEjYf70Bqrij')
    IBEX_TENANT_ID = os.getenv('IBEX_TENANT_ID', 'test-tenant')
    IBEX_NAMESPACE = os.getenv('IBEX_NAMESPACE', 'default')

settings = Settings()

def compare_performance():
    """Compare performance between original and optimized clients"""

    print("="*60)
    print("PERFORMANCE COMPARISON TEST")
    print("="*60)

    # Initialize both clients
    print("\n📝 Initializing clients...")

    # Original client
    original_client = IbexClient(
        api_url=settings.IBEX_API_URL,
        api_key=settings.IBEX_API_KEY,
        tenant_id=settings.IBEX_TENANT_ID,
        namespace=settings.IBEX_NAMESPACE
    )

    # Optimized client
    optimized_client = OptimizedIbexClient(
        api_url=settings.IBEX_API_URL,
        api_key=settings.IBEX_API_KEY,
        tenant_id=settings.IBEX_TENANT_ID,
        namespace=settings.IBEX_NAMESPACE
    )

    # Enable direct Lambda if in AWS environment
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        optimized_client.enable_direct_lambda('ibex-db-lambda')

    print("✅ Clients initialized")

    # Test scenarios
    test_results = {}

    # Test 1: Simple Query
    print("\n📊 Test 1: Simple Query Performance")
    test_table = "food_entries"
    test_filter = [{"field": "user_id", "operator": "eq", "value": "test-user-1"}]

    # Original client timing
    original_times = []
    for i in range(5):
        start = time.perf_counter()
        result = original_client.query(test_table, filters=test_filter, limit=10)
        end = time.perf_counter()
        original_times.append((end - start) * 1000)
        print(f"  Original Run {i+1}: {original_times[-1]:.2f}ms")

    # Optimized client timing (with cold cache)
    optimized_client.clear_cache()
    optimized_times_cold = []
    for i in range(5):
        start = time.perf_counter()
        result = optimized_client.query(test_table, filters=test_filter, limit=10)
        end = time.perf_counter()
        optimized_times_cold.append((end - start) * 1000)
        print(f"  Optimized Run {i+1} (cold): {optimized_times_cold[-1]:.2f}ms")

    # Optimized client timing (with warm cache)
    optimized_times_warm = []
    for i in range(5):
        start = time.perf_counter()
        result = optimized_client.query(test_table, filters=test_filter, limit=10)
        end = time.perf_counter()
        optimized_times_warm.append((end - start) * 1000)
        print(f"  Optimized Run {i+1} (warm): {optimized_times_warm[-1]:.2f}ms")

    # Calculate statistics
    test_results["simple_query"] = {
        "original_avg": statistics.mean(original_times),
        "optimized_cold_avg": statistics.mean(optimized_times_cold),
        "optimized_warm_avg": statistics.mean(optimized_times_warm),
        "improvement_cold": ((statistics.mean(original_times) - statistics.mean(optimized_times_cold)) / statistics.mean(original_times)) * 100,
        "improvement_warm": ((statistics.mean(original_times) - statistics.mean(optimized_times_warm)) / statistics.mean(original_times)) * 100
    }

    # Test 2: Batch Operations
    print("\n📊 Test 2: Batch Write Performance")

    # Create test data
    test_records = [
        {
            "id": f"perf-test-{i}",
            "description": f"Performance test item {i}",
            "calories": 100 + i,
            "created_at": datetime.utcnow().isoformat()
        }
        for i in range(10)
    ]

    # Original client - individual writes
    start = time.perf_counter()
    for record in test_records:
        original_client.write("food_entries", [record])
    end = time.perf_counter()
    original_batch_time = (end - start) * 1000
    print(f"  Original (10 individual writes): {original_batch_time:.2f}ms")

    # Optimized client - batch write
    start = time.perf_counter()
    operations = [
        {"operation": "WRITE", "table": "food_entries", "record": record}
        for record in test_records
    ]
    optimized_client.batch_write(operations)
    end = time.perf_counter()
    optimized_batch_time = (end - start) * 1000
    print(f"  Optimized (1 batch write): {optimized_batch_time:.2f}ms")

    test_results["batch_write"] = {
        "original_time": original_batch_time,
        "optimized_time": optimized_batch_time,
        "improvement": ((original_batch_time - optimized_batch_time) / original_batch_time) * 100
    }

    # Clean up test data
    for record in test_records:
        original_client.delete("food_entries", [{"field": "id", "operator": "eq", "value": record["id"]}])

    # Print summary
    print("\n" + "="*60)
    print("PERFORMANCE SUMMARY")
    print("="*60)

    print("\n📈 Query Performance:")
    print(f"  Original Average: {test_results['simple_query']['original_avg']:.2f}ms")
    print(f"  Optimized (cold cache): {test_results['simple_query']['optimized_cold_avg']:.2f}ms")
    print(f"  Optimized (warm cache): {test_results['simple_query']['optimized_warm_avg']:.2f}ms")
    print(f"  Improvement (cold): {test_results['simple_query']['improvement_cold']:.1f}%")
    print(f"  Improvement (warm): {test_results['simple_query']['improvement_warm']:.1f}%")

    print("\n📈 Batch Performance:")
    print(f"  Original (10 calls): {test_results['batch_write']['original_time']:.2f}ms")
    print(f"  Optimized (1 batch): {test_results['batch_write']['optimized_time']:.2f}ms")
    print(f"  Improvement: {test_results['batch_write']['improvement']:.1f}%")

    # Get cache statistics
    stats = optimized_client.get_stats()
    print("\n📊 Cache Statistics:")
    print(f"  Cache Hits: {stats['cache_stats']['hits']}")
    print(f"  Cache Misses: {stats['cache_stats']['misses']}")
    print(f"  Cache Hit Rate: {stats.get('cache_hit_rate', 0)*100:.1f}%")
    print(f"  Cache Size: {stats['cache_size']} items")
    print(f"  Cache Memory: {stats['cache_memory_kb']:.2f} KB")

    return test_results

def verify_compatibility():
    """Verify that optimized client produces same results as original"""

    print("\n" + "="*60)
    print("COMPATIBILITY VERIFICATION")
    print("="*60)

    # Initialize both clients
    original_client = IbexClient(
        api_url=settings.IBEX_API_URL,
        api_key=settings.IBEX_API_KEY,
        tenant_id=settings.IBEX_TENANT_ID,
        namespace=settings.IBEX_NAMESPACE
    )

    optimized_client = OptimizedIbexClient(
        api_url=settings.IBEX_API_URL,
        api_key=settings.IBEX_API_KEY,
        tenant_id=settings.IBEX_TENANT_ID,
        namespace=settings.IBEX_NAMESPACE
    )

    # Clear cache for fair comparison
    optimized_client.clear_cache()

    # Test various operations
    tests_passed = 0
    tests_failed = 0

    # Test 1: List tables
    print("\n✔️ Testing: list_tables()")
    original_result = original_client.list_tables()
    optimized_result = optimized_client.list_tables()

    if original_result == optimized_result:
        print("  ✅ Results match")
        tests_passed += 1
    else:
        print("  ❌ Results differ!")
        tests_failed += 1

    # Test 2: Query
    print("\n✔️ Testing: query()")
    test_filter = [{"field": "user_id", "operator": "eq", "value": "test-user-1"}]
    original_result = original_client.query("food_entries", filters=test_filter, limit=5)
    optimized_result = optimized_client.query("food_entries", filters=test_filter, limit=5, use_cache=False)

    if original_result == optimized_result:
        print("  ✅ Results match")
        tests_passed += 1
    else:
        print("  ❌ Results differ!")
        tests_failed += 1

    # Summary
    print("\n" + "="*60)
    print(f"Compatibility Test Results: {tests_passed} passed, {tests_failed} failed")

    if tests_failed == 0:
        print("✅ Optimized client is fully compatible!")
        return True
    else:
        print("❌ Compatibility issues detected. Review before migration.")
        return False

def main():
    """Main migration process"""

    print("\n🚀 Food App - IbexClient Optimization Migration")
    print("="*60)

    # Step 1: Verify compatibility
    print("\nStep 1: Verifying compatibility...")
    compatible = verify_compatibility()

    if not compatible:
        print("\n❌ Migration aborted due to compatibility issues")
        return 1

    # Step 2: Compare performance
    print("\nStep 2: Comparing performance...")
    results = compare_performance()

    # Step 3: Migration recommendation
    print("\n" + "="*60)
    print("MIGRATION RECOMMENDATION")
    print("="*60)

    avg_improvement = statistics.mean([
        results['simple_query']['improvement_warm'],
        results['batch_write']['improvement']
    ])

    if avg_improvement > 20:
        print(f"\n✅ RECOMMENDED: Average improvement of {avg_improvement:.1f}%")
        print("\nTo complete migration:")
        print("1. Update app.py to import OptimizedIbexClient")
        print("2. Replace IbexClient with OptimizedIbexClient")
        print("3. Test all endpoints with test_all_endpoints.py")
        print("4. Monitor cache memory usage in production")

        print("\n📝 Migration code change needed in app.py:")
        print("```python")
        print("# Change this:")
        print("from lib.ibex_client import IbexClient")
        print("")
        print("# To this:")
        print("from lib.ibex_client_optimized import OptimizedIbexClient as IbexClient")
        print("```")
    else:
        print(f"\n⚠️  Limited improvement ({avg_improvement:.1f}%). Review if migration is worth it.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
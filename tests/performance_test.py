#!/usr/bin/env python3
"""
Performance Test Suite for NutriWealth Backend
Tests response times and throughput with updated Ibex DB
"""

import time
import json
import requests
import statistics
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BASE_URL = "http://localhost:8080"
AUTH_HEADER = {"Authorization": "Bearer dev-user-1"}
HEADERS = {**AUTH_HEADER, "Content-Type": "application/json"}

# Test results storage
results = {
    "model_config": [],
    "receipts": [],
    "food_analysis": [],
    "async_analysis": [],
    "concurrent": []
}


def measure_request(name: str, method: str, url: str, data: Dict = None) -> Dict[str, Any]:
    """Measure a single request's performance"""
    start_time = time.time()

    try:
        if method == "GET":
            response = requests.get(url, headers=AUTH_HEADER, timeout=60)
        else:
            response = requests.post(url, headers=HEADERS, json=data, timeout=60)

        elapsed = (time.time() - start_time) * 1000  # Convert to ms

        return {
            "name": name,
            "status": response.status_code,
            "time_ms": round(elapsed, 2),
            "success": response.status_code == 200,
            "size_bytes": len(response.content)
        }
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        return {
            "name": name,
            "status": 0,
            "time_ms": round(elapsed, 2),
            "success": False,
            "error": str(e)
        }


def test_model_config():
    """Test model configuration endpoints"""
    print("\n📊 Testing Model Configuration...")

    tests = [
        ("List Models", "GET", f"{BASE_URL}/v1/models/config"),
        ("Get Food Model", "GET", f"{BASE_URL}/v1/models/config/food"),
        ("Get Receipt Model", "GET", f"{BASE_URL}/v1/models/config/receipt"),
        ("List Available", "GET", f"{BASE_URL}/v1/models/available"),
    ]

    for name, method, url in tests:
        result = measure_request(name, method, url)
        results["model_config"].append(result)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {name}: {result['time_ms']}ms")


def test_receipts():
    """Test receipt endpoints"""
    print("\n🧾 Testing Receipt Endpoints...")

    tests = [
        ("List All Receipts", "GET", f"{BASE_URL}/v1/receipts"),
        ("List 2 Receipts", "GET", f"{BASE_URL}/v1/receipts?limit=2"),
        ("List with Offset", "GET", f"{BASE_URL}/v1/receipts?limit=2&offset=2"),
    ]

    for name, method, url in tests:
        result = measure_request(name, method, url)
        results["receipts"].append(result)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {name}: {result['time_ms']}ms ({result.get('size_bytes', 0)} bytes)")


def test_food_analysis():
    """Test food analysis endpoint"""
    print("\n🍎 Testing Food Analysis...")

    tests = [
        ("Apple", {"description": "Apple"}),
        ("Banana", {"description": "Banana"}),
        ("Chicken Biryani", {"description": "Chicken biryani with raita"}),
        ("Complex Meal", {"description": "Grilled salmon with quinoa, broccoli, and lemon butter sauce"}),
    ]

    for name, data in tests:
        result = measure_request(f"Analyze {name}", "POST", f"{BASE_URL}/v1/analyze", data)
        results["food_analysis"].append(result)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {name}: {result['time_ms']}ms")


def test_async_analysis():
    """Test async analysis endpoint"""
    print("\n⚡ Testing Async Analysis...")

    tests = [
        ("Orange", {"description": "Orange"}),
        ("Pizza", {"description": "Pepperoni pizza slice"}),
        ("Salad", {"description": "Caesar salad with grilled chicken"}),
    ]

    for name, data in tests:
        result = measure_request(f"Async {name}", "POST", f"{BASE_URL}/v1/analyze/async", data)
        results["async_analysis"].append(result)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {name}: {result['time_ms']}ms")


def test_concurrent_requests():
    """Test concurrent request handling"""
    print("\n🔄 Testing Concurrent Requests...")

    def make_request(item):
        return measure_request(
            f"Concurrent {item}",
            "POST",
            f"{BASE_URL}/v1/analyze/async",
            {"description": item}
        )

    items = ["Apple", "Banana", "Orange", "Grape", "Mango"]

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request, item) for item in items]

        for future in as_completed(futures):
            result = future.result()
            results["concurrent"].append(result)
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['name']}: {result['time_ms']}ms")

    total_time = (time.time() - start_time) * 1000
    print(f"  Total concurrent time: {total_time:.2f}ms for {len(items)} requests")


def print_summary():
    """Print performance summary"""
    print("\n" + "="*60)
    print("📊 PERFORMANCE TEST SUMMARY")
    print("="*60)

    for category, category_results in results.items():
        if not category_results:
            continue

        times = [r["time_ms"] for r in category_results if "time_ms" in r]
        success_count = sum(1 for r in category_results if r.get("success", False))

        if times:
            print(f"\n{category.upper().replace('_', ' ')}:")
            print(f"  ✅ Success Rate: {success_count}/{len(category_results)} ({success_count*100/len(category_results):.0f}%)")
            print(f"  ⏱️  Min: {min(times):.2f}ms")
            print(f"  ⏱️  Max: {max(times):.2f}ms")
            print(f"  ⏱️  Avg: {statistics.mean(times):.2f}ms")
            if len(times) > 1:
                print(f"  ⏱️  Median: {statistics.median(times):.2f}ms")


def main():
    print("🚀 Starting Performance Tests with Updated Ibex DB")
    print("="*60)

    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/v1/models/config", headers=AUTH_HEADER, timeout=5)
        if response.status_code != 200:
            print("❌ Backend is not responding correctly!")
            return
    except:
        print("❌ Backend is not running on port 8080!")
        print("   Please start the backend first: python3 src/main.py")
        return

    print("✅ Backend is running and responsive")

    # Run tests
    test_model_config()
    test_receipts()
    test_food_analysis()
    test_async_analysis()
    test_concurrent_requests()

    # Print summary
    print_summary()

    # Overall performance assessment
    print("\n" + "="*60)
    print("🎯 PERFORMANCE ASSESSMENT")
    print("="*60)

    all_times = []
    for category_results in results.values():
        all_times.extend([r["time_ms"] for r in category_results if "time_ms" in r])

    if all_times:
        avg_time = statistics.mean(all_times)

        if avg_time < 1000:
            print("⚡ EXCELLENT: Average response time under 1 second")
        elif avg_time < 5000:
            print("✅ GOOD: Average response time under 5 seconds")
        elif avg_time < 10000:
            print("⚠️  MODERATE: Average response time under 10 seconds")
        else:
            print("❌ SLOW: Average response time over 10 seconds")

        print(f"\n📊 Overall Average: {avg_time:.2f}ms ({avg_time/1000:.2f}s)")

        # Categorize by speed
        fast = [t for t in all_times if t < 1000]
        medium = [t for t in all_times if 1000 <= t < 10000]
        slow = [t for t in all_times if t >= 10000]

        print(f"\n⚡ Fast (<1s): {len(fast)} requests")
        print(f"⏱️  Medium (1-10s): {len(medium)} requests")
        print(f"🐌 Slow (>10s): {len(slow)} requests")


if __name__ == "__main__":
    main()
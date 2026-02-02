#!/usr/bin/env python3
"""
Performance Testing Suite for NutriWealth Backend
Measures latency, throughput, and other metrics for CRUD operations
"""

import time
import json
import requests
import statistics
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Any, Tuple
import random
import string

# Configuration
BASE_URL = "http://localhost:8080"
AUTH_TOKEN = "dev-user-1"
HEADERS = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

class PerformanceTester:
    def __init__(self):
        self.results = {}
        self.created_ids = []

    def measure_request(self, method: str, url: str, **kwargs) -> Tuple[float, int, Any]:
        """Measure a single request's latency"""
        start_time = time.perf_counter()

        try:
            response = requests.request(method, url, headers=HEADERS, **kwargs)
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000  # Convert to milliseconds

            return latency, response.status_code, response.json() if response.text else None
        except Exception as e:
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000
            return latency, 0, str(e)

    def run_iterations(self, name: str, method: str, url: str, iterations: int = 10, **kwargs) -> Dict:
        """Run multiple iterations of a request and collect metrics"""
        latencies = []
        status_codes = []
        errors = 0

        print(f"\n📊 Testing: {name}")
        print(f"   Iterations: {iterations}")

        for i in range(iterations):
            latency, status, response = self.measure_request(method, url, **kwargs)
            latencies.append(latency)
            status_codes.append(status)

            if status not in [200, 201, 204]:
                errors += 1

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"   Progress: {i + 1}/{iterations}")

        # Calculate statistics
        metrics = {
            "name": name,
            "method": method,
            "url": url,
            "iterations": iterations,
            "errors": errors,
            "success_rate": ((iterations - errors) / iterations) * 100,
            "latency": {
                "min": min(latencies),
                "max": max(latencies),
                "mean": statistics.mean(latencies),
                "median": statistics.median(latencies),
                "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                "p95": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
                "p99": sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0,
            }
        }

        return metrics

    def generate_random_string(self, length: int = 10) -> str:
        """Generate random string for testing"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def test_create_operations(self):
        """Test CREATE operations with different payload sizes"""
        print("\n" + "="*60)
        print("CREATE OPERATIONS PERFORMANCE")
        print("="*60)

        # Small payload
        small_payload = {
            "description": "Test food",
            "calories": 100
        }
        metrics = self.run_iterations(
            "Create Food Entry (Small Payload)",
            "POST",
            f"{BASE_URL}/v1/food_entries",
            iterations=50,
            json=small_payload
        )
        self.results["create_small"] = metrics

        # Medium payload
        medium_payload = {
            "description": "Grilled Chicken Salad with Mixed Greens",
            "calories": 350,
            "total_protein": 35,
            "total_carbohydrates": 15,
            "total_fats": 18,
            "total_fiber": 5,
            "total_sodium": 450,
            "meal_type": "lunch",
            "meal_date": "2026-01-29",
            "meal_time": "12:30"
        }
        metrics = self.run_iterations(
            "Create Food Entry (Medium Payload)",
            "POST",
            f"{BASE_URL}/v1/food_entries",
            iterations=50,
            json=medium_payload
        )
        self.results["create_medium"] = metrics

        # Large payload (with ingredients)
        large_payload = {
            "description": "Complex meal with many ingredients " * 10,
            "calories": 750,
            "total_protein": 45,
            "total_carbohydrates": 85,
            "total_fats": 32,
            "total_fiber": 12,
            "total_sodium": 890,
            "meal_type": "dinner",
            "meal_date": "2026-01-29",
            "meal_time": "19:00",
            "ingredients": json.dumps([
                {"name": f"Ingredient {i}", "amount": f"{i*10}g", "calories": i*20}
                for i in range(20)
            ]),
            "notes": "This is a test note " * 50
        }
        metrics = self.run_iterations(
            "Create Food Entry (Large Payload)",
            "POST",
            f"{BASE_URL}/v1/food_entries",
            iterations=50,
            json=large_payload
        )
        self.results["create_large"] = metrics

    def test_read_operations(self):
        """Test READ operations"""
        print("\n" + "="*60)
        print("READ OPERATIONS PERFORMANCE")
        print("="*60)

        # First create some test data
        print("\n📝 Creating test data...")
        for i in range(10):
            response = requests.post(
                f"{BASE_URL}/v1/food_entries",
                headers=HEADERS,
                json={
                    "description": f"Test food {i}",
                    "calories": 100 + i * 10
                }
            )
            if response.status_code == 201:
                data = response.json()
                self.created_ids.append(data.get("id"))

        print(f"   Created {len(self.created_ids)} test records")

        # Test list operations
        metrics = self.run_iterations(
            "List Food Entries (No Filter)",
            "GET",
            f"{BASE_URL}/v1/food_entries",
            iterations=100
        )
        self.results["read_list"] = metrics

        # Test list with pagination
        metrics = self.run_iterations(
            "List Food Entries (Limit 5)",
            "GET",
            f"{BASE_URL}/v1/food_entries?limit=5",
            iterations=100
        )
        self.results["read_list_paginated"] = metrics

        # Test get by ID
        if self.created_ids:
            test_id = self.created_ids[0]
            metrics = self.run_iterations(
                "Get Food Entry by ID",
                "GET",
                f"{BASE_URL}/v1/food_entries/{test_id}",
                iterations=100
            )
            self.results["read_by_id"] = metrics

    def test_update_operations(self):
        """Test UPDATE operations"""
        print("\n" + "="*60)
        print("UPDATE OPERATIONS PERFORMANCE")
        print("="*60)

        if not self.created_ids:
            print("   No test data available for updates")
            return

        # Small update
        small_update = {"calories": 200}
        test_id = self.created_ids[0] if self.created_ids else None

        if test_id:
            metrics = self.run_iterations(
                "Update Food Entry (Small)",
                "PUT",
                f"{BASE_URL}/v1/food_entries/{test_id}",
                iterations=50,
                json=small_update
            )
            self.results["update_small"] = metrics

        # Large update
        large_update = {
            "description": "Updated description " * 20,
            "calories": 500,
            "total_protein": 50,
            "total_carbohydrates": 60,
            "total_fats": 25,
            "notes": "Updated notes " * 50
        }

        if len(self.created_ids) > 1:
            test_id = self.created_ids[1]
            metrics = self.run_iterations(
                "Update Food Entry (Large)",
                "PUT",
                f"{BASE_URL}/v1/food_entries/{test_id}",
                iterations=50,
                json=large_update
            )
            self.results["update_large"] = metrics

    def test_delete_operations(self):
        """Test DELETE operations"""
        print("\n" + "="*60)
        print("DELETE OPERATIONS PERFORMANCE")
        print("="*60)

        # Create items to delete
        delete_ids = []
        for i in range(50):
            response = requests.post(
                f"{BASE_URL}/v1/food_entries",
                headers=HEADERS,
                json={"description": f"To delete {i}", "calories": 100}
            )
            if response.status_code == 201:
                delete_ids.append(response.json().get("id"))

        print(f"   Created {len(delete_ids)} items to delete")

        if delete_ids:
            # Measure delete performance
            latencies = []
            for item_id in delete_ids[:50]:  # Test up to 50 deletes
                start_time = time.perf_counter()
                response = requests.delete(
                    f"{BASE_URL}/v1/food_entries/{item_id}",
                    headers=HEADERS
                )
                end_time = time.perf_counter()
                latency = (end_time - start_time) * 1000
                latencies.append(latency)

            if latencies:
                metrics = {
                    "name": "Delete Food Entry",
                    "method": "DELETE",
                    "iterations": len(latencies),
                    "latency": {
                        "min": min(latencies),
                        "max": max(latencies),
                        "mean": statistics.mean(latencies),
                        "median": statistics.median(latencies),
                        "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                        "p95": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
                        "p99": sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0,
                    }
                }
                self.results["delete"] = metrics

    def test_concurrent_operations(self):
        """Test concurrent request handling"""
        print("\n" + "="*60)
        print("CONCURRENT OPERATIONS PERFORMANCE")
        print("="*60)

        def make_request(i):
            """Make a single request"""
            return self.measure_request(
                "POST",
                f"{BASE_URL}/v1/food_entries",
                json={"description": f"Concurrent test {i}", "calories": 100 + i}
            )

        # Test different concurrency levels
        for workers in [1, 5, 10, 20]:
            print(f"\n📊 Testing with {workers} concurrent requests")
            start_time = time.perf_counter()

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(make_request, i) for i in range(50)]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            end_time = time.perf_counter()
            total_time = (end_time - start_time) * 1000

            latencies = [r[0] for r in results]
            successful = sum(1 for r in results if r[1] in [200, 201])

            metrics = {
                "name": f"Concurrent Requests ({workers} workers)",
                "workers": workers,
                "total_requests": 50,
                "total_time_ms": total_time,
                "throughput_rps": 50 / (total_time / 1000),
                "successful": successful,
                "failed": 50 - successful,
                "latency": {
                    "min": min(latencies),
                    "max": max(latencies),
                    "mean": statistics.mean(latencies),
                    "median": statistics.median(latencies),
                    "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                }
            }

            self.results[f"concurrent_{workers}"] = metrics

    def test_complex_queries(self):
        """Test complex query operations"""
        print("\n" + "="*60)
        print("COMPLEX QUERY PERFORMANCE")
        print("="*60)

        # Test with filters and sorting
        metrics = self.run_iterations(
            "List with Sort and Filter",
            "GET",
            f"{BASE_URL}/v1/food_entries?meal_type=lunch&order_by=created_at&order_dir=desc&limit=10",
            iterations=50
        )
        self.results["complex_query"] = metrics

        # Test receipts with items (JOIN-like operation)
        # First create a receipt
        receipt_response = requests.post(
            f"{BASE_URL}/v1/receipts",
            headers=HEADERS,
            json={"vendor": "Test Store", "total_amount": 100}
        )

        if receipt_response.status_code == 201:
            receipt_id = receipt_response.json().get("id")

            # Add items
            for i in range(5):
                requests.post(
                    f"{BASE_URL}/v1/receipt_items",
                    headers=HEADERS,
                    json={"receipt_id": receipt_id, "name": f"Item {i}", "price": 10 + i}
                )

            # Test get receipt with items
            metrics = self.run_iterations(
                "Get Receipt with Items (JOIN)",
                "GET",
                f"{BASE_URL}/v1/receipts/{receipt_id}",
                iterations=50
            )
            self.results["complex_join"] = metrics

    def print_results(self):
        """Print formatted results"""
        print("\n" + "="*60)
        print("PERFORMANCE TEST RESULTS SUMMARY")
        print("="*60)

        # Group results by operation type
        operations = {
            "CREATE": ["create_small", "create_medium", "create_large"],
            "READ": ["read_list", "read_list_paginated", "read_by_id"],
            "UPDATE": ["update_small", "update_large"],
            "DELETE": ["delete"],
            "COMPLEX": ["complex_query", "complex_join"]
        }

        for op_type, keys in operations.items():
            print(f"\n{op_type} Operations:")
            print("-" * 50)

            for key in keys:
                if key in self.results:
                    result = self.results[key]
                    latency = result.get("latency", {})

                    print(f"\n📊 {result['name']}")
                    print(f"   Method: {result.get('method', 'N/A')}")
                    print(f"   Iterations: {result.get('iterations', 0)}")

                    if "success_rate" in result:
                        print(f"   Success Rate: {result['success_rate']:.1f}%")

                    print(f"   Latency (ms):")
                    print(f"      Min: {latency.get('min', 0):.2f}")
                    print(f"      Max: {latency.get('max', 0):.2f}")
                    print(f"      Mean: {latency.get('mean', 0):.2f}")
                    print(f"      Median: {latency.get('median', 0):.2f}")
                    print(f"      StdDev: {latency.get('stdev', 0):.2f}")
                    print(f"      P95: {latency.get('p95', 0):.2f}")
                    print(f"      P99: {latency.get('p99', 0):.2f}")

        # Print concurrent results
        print("\n\nCONCURRENT Operations:")
        print("-" * 50)

        for workers in [1, 5, 10, 20]:
            key = f"concurrent_{workers}"
            if key in self.results:
                result = self.results[key]
                print(f"\n📊 {result['name']}")
                print(f"   Total Requests: {result['total_requests']}")
                print(f"   Total Time: {result['total_time_ms']:.2f} ms")
                print(f"   Throughput: {result['throughput_rps']:.2f} req/s")
                print(f"   Success/Failed: {result['successful']}/{result['failed']}")

                latency = result.get("latency", {})
                print(f"   Avg Latency: {latency.get('mean', 0):.2f} ms")

    def save_results(self):
        """Save results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"performance_results_{timestamp}.json"

        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n📁 Results saved to: {filename}")

    def cleanup(self):
        """Clean up test data"""
        print("\n🧹 Cleaning up test data...")

        # Delete created food entries
        for item_id in self.created_ids:
            try:
                requests.delete(f"{BASE_URL}/v1/food_entries/{item_id}", headers=HEADERS)
            except:
                pass

        print(f"   Cleaned up {len(self.created_ids)} test records")

    def run_all_tests(self):
        """Run all performance tests"""
        print("\n" + "="*60)
        print("🚀 NUTRIWEALTH BACKEND PERFORMANCE TESTING")
        print("="*60)
        print(f"Target: {BASE_URL}")
        print(f"User: {AUTH_TOKEN}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Check server connection
            response = requests.get(f"{BASE_URL}/v1/auth/config", timeout=5)
            if response.status_code != 200:
                print("❌ Server not responding correctly")
                return
            print("✅ Server connection verified")

            # Run test suites
            self.test_create_operations()
            self.test_read_operations()
            self.test_update_operations()
            self.test_delete_operations()
            self.test_complex_queries()
            self.test_concurrent_operations()

            # Display results
            self.print_results()

            # Save results
            self.save_results()

        except Exception as e:
            print(f"\n❌ Error during testing: {e}")

        finally:
            # Cleanup
            self.cleanup()

        print("\n" + "="*60)
        print("✅ Performance testing completed!")
        print("="*60)


if __name__ == "__main__":
    tester = PerformanceTester()
    tester.run_all_tests()
#!/usr/bin/env python3
"""
Stress test for aare-core verification engine.

Tests:
1. Single-threaded throughput (verifications/second)
2. Multi-process concurrent load (Z3 is not thread-safe)
3. Memory usage under load
4. Latency percentiles (p50, p95, p99)
5. Different ontology sizes (small vs large HIPAA)

Run:
    python tests/stress_test.py
    python tests/stress_test.py --requests 10000 --workers 8
"""
import argparse
import time
import statistics
import multiprocessing
import sys
import os
import tracemalloc
from dataclasses import dataclass
from typing import List

# Add src to path for local testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from aare_core import OntologyLoader, LLMParser, SMTVerifier


@dataclass
class StressTestResult:
    total_requests: int
    completed: int
    errors: int
    total_time_sec: float
    requests_per_second: float
    latencies_ms: List[float]
    memory_peak_mb: float

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p95(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]

    @property
    def p99(self) -> float:
        if not self.latencies_ms:
            return 0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[idx]

    @property
    def avg(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0


# Test inputs - mix of compliant and non-compliant (both are valid tests)
TEST_INPUTS = [
    # Compliant cases (verified=True)
    ("Loan approved: 3% rate, DTI 35%, credit score 720", "mortgage-compliance-v1"),
    ("DTI is 30%, credit score 750, standard terms", "mortgage-compliance-v1"),
    ("The value is 50, option A is selected.", "example"),

    # Non-compliant cases (verified=False, but still valid verifications)
    ("Approved despite DTI of 55%", "mortgage-compliance-v1"),
    ("DTI is 50%, credit score 600", "mortgage-compliance-v1"),
    ("The value is 150, prohibited action taken", "example"),
]


def run_single_verification(loader, parser, verifier, input_text, ontology_name):
    """Run a single verification and return latency in ms"""
    start = time.perf_counter()

    ontology = loader.load(ontology_name)
    data = parser.parse(input_text, ontology)
    result = verifier.verify(data, ontology)

    end = time.perf_counter()
    latency_ms = (end - start) * 1000

    return latency_ms, result['verified']


def stress_test_single_thread(num_requests: int) -> StressTestResult:
    """Single-threaded stress test"""
    print(f"\n{'='*60}")
    print(f"SINGLE-THREADED TEST: {num_requests} requests")
    print('='*60)

    loader = OntologyLoader()
    parser = LLMParser()
    verifier = SMTVerifier()

    # Warm up
    print("Warming up...")
    for _ in range(10):
        ontology = loader.load("example")
        data = parser.parse("value is 50", ontology)
        verifier.verify(data, ontology)

    # Clear LRU cache to get clean measurements
    loader.load.cache_clear()

    tracemalloc.start()
    latencies = []
    completed = 0
    errors = 0

    start_time = time.perf_counter()

    for i in range(num_requests):
        input_text, ontology_name = TEST_INPUTS[i % len(TEST_INPUTS)]
        try:
            latency, verified = run_single_verification(
                loader, parser, verifier, input_text, ontology_name
            )
            latencies.append(latency)
            completed += 1
        except Exception as e:
            errors += 1
            print(f"Error: {e}")

        if (i + 1) % 1000 == 0:
            print(f"  Completed {i + 1}/{num_requests}...")

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_time = end_time - start_time

    return StressTestResult(
        total_requests=num_requests,
        completed=completed,
        errors=errors,
        total_time_sec=total_time,
        requests_per_second=num_requests / total_time,
        latencies_ms=latencies,
        memory_peak_mb=peak / 1024 / 1024
    )


def worker_process(args):
    """Worker function for multiprocessing - each process has its own Z3 instance"""
    worker_id, requests_per_worker = args

    # Each process gets its own instances (Z3 is not thread-safe but is process-safe)
    loader = OntologyLoader()
    parser = LLMParser()
    verifier = SMTVerifier()

    latencies = []
    completed = 0
    errors = 0

    for i in range(requests_per_worker):
        input_text, ontology_name = TEST_INPUTS[(worker_id * requests_per_worker + i) % len(TEST_INPUTS)]
        try:
            latency, verified = run_single_verification(
                loader, parser, verifier, input_text, ontology_name
            )
            latencies.append(latency)
            completed += 1
        except Exception:
            errors += 1

    return latencies, completed, errors


def stress_test_multi_process(num_requests: int, num_workers: int) -> StressTestResult:
    """Multi-process stress test (Z3 is not thread-safe, so we use processes)"""
    print(f"\n{'='*60}")
    print(f"MULTI-PROCESS TEST: {num_requests} requests, {num_workers} workers")
    print('='*60)

    requests_per_worker = num_requests // num_workers

    tracemalloc.start()
    start_time = time.perf_counter()

    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.map(worker_process, [(i, requests_per_worker) for i in range(num_workers)])

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Aggregate results
    all_latencies = []
    total_completed = 0
    total_errors = 0
    for latencies, completed, errors in results:
        all_latencies.extend(latencies)
        total_completed += completed
        total_errors += errors

    total_time = end_time - start_time
    actual_requests = requests_per_worker * num_workers

    return StressTestResult(
        total_requests=actual_requests,
        completed=total_completed,
        errors=total_errors,
        total_time_sec=total_time,
        requests_per_second=actual_requests / total_time,
        latencies_ms=all_latencies,
        memory_peak_mb=peak / 1024 / 1024
    )


def stress_test_hipaa(num_requests: int) -> StressTestResult:
    """Test with large HIPAA ontology (50+ constraints)"""
    print(f"\n{'='*60}")
    print(f"HIPAA ONTOLOGY TEST: {num_requests} requests (50+ constraints)")
    print('='*60)

    loader = OntologyLoader()
    parser = LLMParser()
    verifier = SMTVerifier()

    # HIPAA test input
    hipaa_input = "Patient John Doe SSN 123-45-6789 diagnosed with diabetes. Treatment plan shared with Dr. Smith."

    tracemalloc.start()
    latencies = []
    completed = 0
    errors = 0

    start_time = time.perf_counter()

    for i in range(num_requests):
        try:
            latency, verified = run_single_verification(
                loader, parser, verifier, hipaa_input, "hipaa-v1"
            )
            latencies.append(latency)
            completed += 1
        except Exception as e:
            errors += 1
            print(f"Error: {e}")

        if (i + 1) % 100 == 0:
            print(f"  Completed {i + 1}/{num_requests}...")

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_time = end_time - start_time

    return StressTestResult(
        total_requests=num_requests,
        completed=completed,
        errors=errors,
        total_time_sec=total_time,
        requests_per_second=num_requests / total_time,
        latencies_ms=latencies,
        memory_peak_mb=peak / 1024 / 1024
    )


def print_results(result: StressTestResult, test_name: str):
    """Pretty print test results"""
    print(f"\n--- {test_name} Results ---")
    print(f"Total Requests:     {result.total_requests:,}")
    print(f"Completed:          {result.completed:,}")
    print(f"Errors:             {result.errors:,}")
    print(f"Total Time:         {result.total_time_sec:.2f}s")
    print(f"Throughput:         {result.requests_per_second:,.1f} req/sec")
    print(f"")
    print(f"Latency (ms):")
    print(f"  Average:          {result.avg:.2f}")
    print(f"  p50 (median):     {result.p50:.2f}")
    print(f"  p95:              {result.p95:.2f}")
    print(f"  p99:              {result.p99:.2f}")
    if result.latencies_ms:
        print(f"  Min:              {min(result.latencies_ms):.2f}")
        print(f"  Max:              {max(result.latencies_ms):.2f}")
    print(f"")
    print(f"Memory Peak:        {result.memory_peak_mb:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="Stress test aare-core")
    parser.add_argument("--requests", "-n", type=int, default=1000,
                        help="Number of requests (default: 1000)")
    parser.add_argument("--workers", "-w", type=int, default=4,
                        help="Number of worker processes for concurrent test (default: 4)")
    parser.add_argument("--hipaa-requests", type=int, default=100,
                        help="Number of requests for HIPAA test (default: 100)")
    parser.add_argument("--skip-hipaa", action="store_true",
                        help="Skip HIPAA large ontology test")
    parser.add_argument("--skip-multiprocess", action="store_true",
                        help="Skip multi-process test")
    args = parser.parse_args()

    print("="*60)
    print("       aare-core STRESS TEST")
    print("="*60)
    print(f"Configuration:")
    print(f"  Requests:         {args.requests:,}")
    print(f"  Workers:          {args.workers}")
    print(f"  HIPAA Requests:   {args.hipaa_requests}")

    # Test 1: Single-threaded
    result1 = stress_test_single_thread(args.requests)
    print_results(result1, "Single-Threaded")

    # Test 2: Multi-process (Z3 is not thread-safe)
    result2 = None
    if not args.skip_multiprocess:
        result2 = stress_test_multi_process(args.requests, args.workers)
        print_results(result2, f"Multi-Process ({args.workers} workers)")

    # Test 3: HIPAA (large ontology)
    result3 = None
    if not args.skip_hipaa:
        result3 = stress_test_hipaa(args.hipaa_requests)
        print_results(result3, "HIPAA (50+ constraints)")

    # Summary
    print("\n" + "="*60)
    print("                    SUMMARY")
    print("="*60)
    print(f"{'Test':<30} {'Throughput':<20} {'p99 Latency':<15}")
    print("-"*60)
    print(f"{'Single-threaded':<30} {result1.requests_per_second:>10,.1f} req/s    {result1.p99:>8.2f} ms")
    if result2:
        print(f"{'Multi-process':<30} {result2.requests_per_second:>10,.1f} req/s    {result2.p99:>8.2f} ms")
    if result3:
        print(f"{'HIPAA (50+ constraints)':<30} {result3.requests_per_second:>10,.1f} req/s    {result3.p99:>8.2f} ms")
    print("="*60)


if __name__ == "__main__":
    main()

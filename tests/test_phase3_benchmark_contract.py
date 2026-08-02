"""Fast contract tests for the Phase 3 benchmark framework."""

from pathlib import Path
import tempfile
import unittest

from benchmarks.benchmark_helpers import (
    CSV_FIELDS,
    PROJECT_ROOT,
    aggregate_measurements,
    create_memory_chart,
    create_runtime_chart,
    deployment_order_hash,
    measure_call,
    selected_comparison_sizes,
    validate_deployment_order,
    validate_trials,
)
from benchmarks.benchmark_phase3 import parse_arguments
from src.synthetic_workload_generator import generate_workload


class Phase3BenchmarkContractTests(unittest.TestCase):
    def test_csv_field_names_match_required_schema(self) -> None:
        self.assertEqual(len(CSV_FIELDS), 23)
        self.assertEqual(CSV_FIELDS[0], "engine")
        self.assertEqual(CSV_FIELDS[-1], "error_message")
        self.assertIn("deployment_order_hash", CSV_FIELDS)

    def test_result_paths_are_repository_relative(self) -> None:
        from benchmarks import benchmark_helpers

        for name in (
            "BENCHMARK_CSV_PATH",
            "RUNTIME_CHART_PATH",
            "MEMORY_CHART_PATH",
            "SCALING_CHART_PATH",
            "STRESS_SUMMARY_PATH",
        ):
            path = getattr(benchmark_helpers, name)
            self.assertTrue(path.is_relative_to(PROJECT_ROOT))

    def test_deployment_hash_is_deterministic_and_order_sensitive(self) -> None:
        first = deployment_order_hash(["a", "b", "c"])
        self.assertEqual(first, deployment_order_hash(["a", "b", "c"]))
        self.assertNotEqual(first, deployment_order_hash(["b", "a", "c"]))
        self.assertEqual(len(first), 64)

    def test_size_filtering(self) -> None:
        self.assertEqual(selected_comparison_sizes(500), (100, 500))
        self.assertEqual(
            selected_comparison_sizes(None),
            (100, 500, 1000, 2000),
        )
        with self.assertRaises(ValueError):
            selected_comparison_sizes(99)

    def test_invalid_trial_counts_are_rejected(self) -> None:
        for value in (0, -1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_trials(value)

    def test_cli_controls_parse(self) -> None:
        arguments = parse_arguments(["--trials", "2", "--max-size", "500"])
        self.assertEqual(arguments.trials, 2)
        self.assertEqual(arguments.max_size, 500)
        self.assertFalse(arguments.stress_only)

    def test_invalid_deployment_order_detects_parity_problem(self) -> None:
        workload = generate_workload(5, "chain")
        valid = [row["service_id"] for row in workload.resources]
        self.assertTrue(validate_deployment_order(valid, workload))
        self.assertFalse(validate_deployment_order(list(reversed(valid)), workload))
        self.assertFalse(validate_deployment_order(valid[:-1], workload))

    def test_measurement_is_nonnegative(self) -> None:
        elapsed, peak, result = measure_call(lambda: sum(range(100)))
        self.assertGreaterEqual(elapsed, 0.0)
        self.assertGreaterEqual(peak, 0)
        self.assertEqual(result, 4950)

    def test_aggregation_uses_maximum_peak_memory(self) -> None:
        summary = aggregate_measurements([0.1, 0.2], [10, 25])
        self.assertEqual(summary["peak_memory_bytes"], 25)
        self.assertAlmostEqual(summary["median_time_seconds"], 0.15)

    def test_chart_functions_accept_synthetic_rows(self) -> None:
        rows = []
        for profile in (
            "chain",
            "layered_sparse",
            "layered_dense",
            "wide_independent",
        ):
            for engine in ("baseline", "optimized"):
                rows.append(
                    {
                        "engine": engine,
                        "profile": profile,
                        "resource_count": 100,
                        "operation": "schedule_all",
                        "median_time_seconds": 0.01,
                        "peak_memory_bytes": 1024,
                        "status": "completed",
                    }
                )
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime.png"
            memory = Path(directory) / "memory.png"
            create_runtime_chart(rows, runtime)
            create_memory_chart(rows, memory)
            self.assertGreater(runtime.stat().st_size, 0)
            self.assertGreater(memory.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

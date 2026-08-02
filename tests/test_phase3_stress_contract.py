"""Fast configuration and correctness contracts for Phase 3 stress runs."""

from pathlib import Path
import tempfile
import unittest

from benchmarks.benchmark_helpers import (
    STRESS_PROFILES,
    STRESS_SIZES,
    build_engine_from_workload,
    create_scaling_chart,
    validate_deployment_order,
)
from src.synthetic_workload_generator import generate_workload


class Phase3StressContractTests(unittest.TestCase):
    def test_required_stress_sizes_are_configured(self) -> None:
        self.assertEqual(STRESS_SIZES, (5000, 10000, 25000))

    def test_required_stress_profiles_are_configured(self) -> None:
        self.assertEqual(
            STRESS_PROFILES,
            ("chain", "layered_sparse", "wide_independent"),
        )

    def test_iterative_chain_schedule_has_no_recursion_dependency(self) -> None:
        workload = generate_workload(250, "chain")
        engine = build_engine_from_workload(workload, "optimized")
        order = []
        for _ in range(workload.resource_count):
            selected = engine.start_next_resource()
            assert selected is not None
            engine.mark_deployed(selected[0])
            order.append(selected[0])
        self.assertTrue(validate_deployment_order(order, workload))
        self.assertTrue(engine.validate_internal_state())

    def test_wide_schedule_selects_each_resource_once(self) -> None:
        workload = generate_workload(100, "wide_independent")
        engine = build_engine_from_workload(workload, "optimized")
        order = []
        for _ in range(workload.resource_count):
            selected = engine.start_next_resource()
            assert selected is not None
            order.append(selected[0])
            engine.mark_deployed(selected[0])
        self.assertEqual(len(order), len(set(order)))
        self.assertTrue(engine.all_deployed())

    def test_scaling_chart_accepts_configured_case_shape(self) -> None:
        cases = [
            {
                "profile": profile,
                "resource_count": size,
                "runtime_seconds": size / 10000,
            }
            for profile in STRESS_PROFILES
            for size in STRESS_SIZES
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scaling.png"
            create_scaling_chart(cases, output)
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

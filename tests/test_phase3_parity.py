"""Behavioral parity tests for Phase 2 and Phase 3 engines."""

from pathlib import Path
import tempfile
import unittest

from src import ReadinessState
from src.bulk_cloud_resource_loader import load_optimized_engine_from_csv
from src.cloud_resource_loader import load_engine_from_csv
from src.synthetic_workload_generator import (
    SyntheticWorkload,
    generate_workload,
    write_workload_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_pair(workload: SyntheticWorkload):
    """Load identical temporary CSV inputs into both engine versions."""
    directory = tempfile.TemporaryDirectory()
    root = Path(directory.name)
    resource_path, dependency_path = write_workload_csv(
        workload,
        root / "resources.csv",
        root / "dependencies.csv",
    )
    baseline = load_engine_from_csv(resource_path, dependency_path)
    optimized = load_optimized_engine_from_csv(resource_path, dependency_path)
    return directory, baseline, optimized


def deploy_all(engine) -> list[str]:
    """Deploy every resource and return the deterministic selection order."""
    order: list[str] = []
    while not engine.all_deployed():
        selected = engine.start_next_resource()
        if selected is None:
            raise AssertionError("engine stalled before complete deployment")
        service_id, _ = selected
        if service_id in order:
            raise AssertionError(f"duplicate selection: {service_id}")
        engine.mark_deployed(service_id)
        order.append(service_id)
    return order


class Phase3ParityTests(unittest.TestCase):
    def compare_profile(self, profile: str, size: int = 30) -> None:
        directory, baseline, optimized = load_pair(
            generate_workload(size, profile, seed=532)
        )
        self.addCleanup(directory.cleanup)
        self.assertEqual(baseline.summary(), optimized.summary())
        baseline_order = deploy_all(baseline)
        optimized_order = deploy_all(optimized)
        self.assertEqual(baseline_order, optimized_order)
        self.assertEqual(baseline.summary(), optimized.summary())
        self.assertTrue(optimized.validate_internal_state())

    def test_committed_phase2_dataset_initial_state_matches(self) -> None:
        resources = PROJECT_ROOT / "data" / "phase2_cloud_resources.csv"
        dependencies = PROJECT_ROOT / "data" / "phase2_dependencies.csv"
        baseline = load_engine_from_csv(resources, dependencies)
        optimized = load_optimized_engine_from_csv(resources, dependencies)
        self.assertEqual(baseline.summary(), optimized.summary())
        self.assertEqual(
            baseline.select_next_resource(),
            optimized.select_next_resource(),
        )

    def test_chain_parity(self) -> None:
        self.compare_profile("chain")

    def test_sparse_layered_parity(self) -> None:
        self.compare_profile("layered_sparse")

    def test_dense_layered_parity(self) -> None:
        self.compare_profile("layered_dense")

    def test_wide_independent_parity(self) -> None:
        self.compare_profile("wide_independent")

    def test_single_resource_parity(self) -> None:
        self.compare_profile("wide_independent", 1)

    def test_equal_priority_ties_match(self) -> None:
        workload = generate_workload(12, "wide_independent")
        equal_rows = tuple(dict(row, priority="2") for row in workload.resources)
        equal_workload = SyntheticWorkload(
            workload.profile,
            workload.seed,
            equal_rows,
            workload.dependencies,
        )
        directory, baseline, optimized = load_pair(equal_workload)
        self.addCleanup(directory.cleanup)
        self.assertEqual(deploy_all(baseline), deploy_all(optimized))

    def test_priority_changes_preserve_selection_parity(self) -> None:
        directory, baseline, optimized = load_pair(
            generate_workload(20, "wide_independent")
        )
        self.addCleanup(directory.cleanup)
        for index in range(0, 20, 3):
            service_id = f"resource-{index:06d}"
            priority = index % 4 + 1
            baseline.update_priority(service_id, priority)
            optimized.update_priority(service_id, priority)
        self.assertEqual(
            baseline.select_next_resource(),
            optimized.select_next_resource(),
        )
        self.assertEqual(deploy_all(baseline), deploy_all(optimized))

    def test_failure_retry_readiness_parity(self) -> None:
        directory, baseline, optimized = load_pair(
            generate_workload(4, "chain")
        )
        self.addCleanup(directory.cleanup)
        for engine in (baseline, optimized):
            selected = engine.start_next_resource()
            assert selected is not None
            prerequisite = selected[0]
            engine.mark_failed(prerequisite)
            self.assertEqual(
                engine.get_readiness("resource-000001").state,
                ReadinessState.BLOCKED,
            )
            engine.retry_failed(prerequisite)
            self.assertEqual(
                engine.get_readiness("resource-000001").state,
                ReadinessState.WAITING,
            )
            selected = engine.start_next_resource()
            assert selected is not None
            engine.mark_deployed(selected[0])
            self.assertEqual(
                engine.get_readiness("resource-000001").state,
                ReadinessState.READY,
            )
        self.assertEqual(baseline.summary(), optimized.summary())

    def test_coordinated_deletion_parity(self) -> None:
        directory, baseline, optimized = load_pair(
            generate_workload(5, "chain")
        )
        self.addCleanup(directory.cleanup)
        for engine in (baseline, optimized):
            self.assertTrue(engine.remove_resource("resource-000002"))
        self.assertEqual(baseline.summary(), optimized.summary())
        self.assertEqual(deploy_all(baseline), deploy_all(optimized))

    def test_all_initially_ready_summary_parity(self) -> None:
        directory, baseline, optimized = load_pair(
            generate_workload(25, "wide_independent")
        )
        self.addCleanup(directory.cleanup)
        self.assertEqual(baseline.get_eligible_resources(),
                         optimized.get_eligible_resources())
        self.assertEqual(baseline.summary(), optimized.summary())


if __name__ == "__main__":
    unittest.main()

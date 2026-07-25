"""Integration tests using the committed Phase 2 datasets."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from examples.phase2_poc_demo import run_phase2_simulation
from src import ReadinessState, load_engine_from_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_PATH = PROJECT_ROOT / "data" / "phase2_cloud_resources.csv"
DEPENDENCIES_PATH = PROJECT_ROOT / "data" / "phase2_dependencies.csv"


class Phase2IntegrationTests(unittest.TestCase):
    def load_engine(self):
        return load_engine_from_csv(RESOURCES_PATH, DEPENDENCIES_PATH)

    def deploy_next(self, engine) -> str:
        selected = engine.start_next_resource()
        assert selected is not None
        service_id, _ = selected
        engine.mark_deployed(service_id)
        return service_id

    def test_committed_dataset_is_complete_and_acyclic(self) -> None:
        engine = self.load_engine()
        order = engine.topological_order()

        self.assertEqual(engine.summary()["resource_count"], 10)
        self.assertEqual(engine.summary()["dependency_count"], 9)
        self.assertFalse(engine.graph.has_cycle())
        self.assertEqual(len(order), 10)
        self.assertEqual(len(set(order)), 10)

    def test_topological_order_respects_every_committed_edge(self) -> None:
        engine = self.load_engine()
        order = engine.topological_order()
        positions = {service_id: index for index, service_id in enumerate(order)}

        with DEPENDENCIES_PATH.open(newline="", encoding="utf-8") as handle:
            for edge in csv.DictReader(handle):
                self.assertLess(
                    positions[edge["prerequisite"]],
                    positions[edge["dependent"]],
                )

    def test_initial_eligibility_and_priority_selection(self) -> None:
        engine = self.load_engine()

        self.assertEqual(
            engine.get_eligible_resources(),
            ["network-core", "notification-topic"],
        )
        self.assertEqual(engine.select_next_resource(), ("network-core", 1))

    def test_failure_blocks_dependent_and_retry_permits_progress(self) -> None:
        engine = self.load_engine()
        self.assertEqual(self.deploy_next(engine), "network-core")
        self.assertEqual(self.deploy_next(engine), "identity-boundary")

        selected = engine.start_next_resource()
        self.assertEqual(selected, ("secrets-store", 1))
        engine.mark_failed("secrets-store")
        self.assertEqual(
            engine.get_readiness("backend-api").state,
            ReadinessState.BLOCKED,
        )

        engine.retry_failed("secrets-store")
        self.assertEqual(
            engine.get_readiness("secrets-store").state,
            ReadinessState.READY,
        )

    def test_complete_simulation_writes_reproducible_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = run_phase2_simulation(
                RESOURCES_PATH,
                DEPENDENCIES_PATH,
                directory,
                verbose=False,
            )
            trace_path = Path(directory) / "phase2_execution_trace.csv"
            summary_path = Path(directory) / "phase2_summary.json"

            with trace_path.open(newline="", encoding="utf-8") as handle:
                trace_rows = list(csv.DictReader(handle))
            with summary_path.open(encoding="utf-8") as handle:
                reloaded_summary = json.load(handle)

        self.assertTrue(summary["all_deployed"])
        self.assertEqual(summary["resource_count"], 10)
        self.assertEqual(len(summary["deployment_order"]), 10)
        self.assertEqual(summary["failure_count"], 1)
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(len(trace_rows), summary["trace_row_count"])
        self.assertEqual(reloaded_summary, summary)


if __name__ == "__main__":
    unittest.main()

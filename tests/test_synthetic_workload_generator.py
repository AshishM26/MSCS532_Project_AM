"""Tests for deterministic Phase 3 synthetic workloads."""

import csv
from pathlib import Path
import tempfile
import unittest

from src.deployment_graph import DeploymentGraph
from src.synthetic_workload_generator import (
    WORKLOAD_PROFILES,
    generate_workload,
    write_workload_csv,
)


class SyntheticWorkloadGeneratorTests(unittest.TestCase):
    def test_supported_profiles_are_complete(self) -> None:
        self.assertEqual(
            WORKLOAD_PROFILES,
            (
                "chain",
                "layered_sparse",
                "layered_dense",
                "wide_independent",
            ),
        )

    def test_generation_is_deterministic_for_seed(self) -> None:
        first = generate_workload(100, "layered_sparse", seed=11)
        second = generate_workload(100, "layered_sparse", seed=11)
        different = generate_workload(100, "layered_sparse", seed=12)

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_chain_has_expected_edges(self) -> None:
        workload = generate_workload(10, "chain")
        self.assertEqual(workload.dependency_count, 9)
        self.assertEqual(
            workload.dependencies[0],
            ("resource-000000", "resource-000001"),
        )

    def test_wide_independent_has_no_edges(self) -> None:
        workload = generate_workload(25, "wide_independent")
        self.assertEqual(workload.dependency_count, 0)

    def test_layered_dense_is_denser_than_sparse(self) -> None:
        sparse = generate_workload(200, "layered_sparse", seed=7)
        dense = generate_workload(200, "layered_dense", seed=7)
        self.assertGreater(dense.dependency_count, sparse.dependency_count)

    def test_every_profile_is_acyclic(self) -> None:
        for profile in WORKLOAD_PROFILES:
            with self.subTest(profile=profile):
                workload = generate_workload(250, profile, seed=9)
                graph = DeploymentGraph()
                for resource in workload.resources:
                    graph.add_service(resource["service_id"])
                for prerequisite, dependent in workload.dependencies:
                    graph.add_dependency(prerequisite, dependent)
                self.assertFalse(graph.has_cycle())
                self.assertEqual(len(graph.topological_order()), 250)

    def test_csv_output_preserves_rows_and_edges(self) -> None:
        workload = generate_workload(20, "layered_sparse")
        with tempfile.TemporaryDirectory() as directory:
            resources_path = Path(directory) / "resources.csv"
            dependencies_path = Path(directory) / "dependencies.csv"
            write_workload_csv(workload, resources_path, dependencies_path)
            with resources_path.open(newline="", encoding="utf-8") as handle:
                resources = list(csv.DictReader(handle))
            with dependencies_path.open(newline="", encoding="utf-8") as handle:
                dependencies = list(csv.DictReader(handle))

        self.assertEqual(len(resources), workload.resource_count)
        self.assertEqual(len(dependencies), workload.dependency_count)

    def test_invalid_inputs_are_rejected(self) -> None:
        for invalid in (0, -1):
            with self.assertRaises(ValueError):
                generate_workload(invalid, "chain")
        with self.assertRaises(TypeError):
            generate_workload(True, "chain")
        with self.assertRaises(ValueError):
            generate_workload(10, "unknown")


if __name__ == "__main__":
    unittest.main()

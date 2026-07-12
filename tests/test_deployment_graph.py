"""Tests for DeploymentGraph."""

import unittest

from src.deployment_graph import (
    DependencyCycleError,
    DeploymentGraph,
    DuplicateDependencyError,
)


class DeploymentGraphTests(unittest.TestCase):
    def test_add_service_and_dependency_registers_nodes(self) -> None:
        graph = DeploymentGraph()
        graph.add_service("standalone")
        graph.add_dependency("database", "api")

        self.assertEqual(graph.get_dependents("database"), ["api"])
        self.assertEqual(graph.get_prerequisites("api"), ["database"])
        self.assertIn("standalone", graph.topological_order())

    def test_duplicate_dependency_is_rejected(self) -> None:
        graph = DeploymentGraph()
        graph.add_dependency("database", "api")

        with self.assertRaises(DuplicateDependencyError):
            graph.add_dependency("database", "api")

    def test_cycle_detection_and_order_failure(self) -> None:
        graph = DeploymentGraph()
        graph.add_dependency("a", "b")
        graph.add_dependency("b", "c")
        graph.add_dependency("c", "a")

        self.assertTrue(graph.has_cycle())
        with self.assertRaises(DependencyCycleError):
            graph.topological_order()

    def test_topological_order_respects_every_edge(self) -> None:
        graph = DeploymentGraph()
        edges = [("network", "database"), ("database", "api"), ("api", "web")]
        for prerequisite, dependent in edges:
            graph.add_dependency(prerequisite, dependent)

        order = graph.topological_order()
        positions = {service: index for index, service in enumerate(order)}

        self.assertFalse(graph.has_cycle())
        for prerequisite, dependent in edges:
            self.assertLess(positions[prerequisite], positions[dependent])

    def test_unknown_service_has_no_neighbors(self) -> None:
        graph = DeploymentGraph()
        self.assertEqual(graph.get_dependents("unknown"), [])
        self.assertEqual(graph.get_prerequisites("unknown"), [])


if __name__ == "__main__":
    unittest.main()

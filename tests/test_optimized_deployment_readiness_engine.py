"""Tests for incremental Phase 3 readiness and persistent heap behavior."""

import unittest

from src import DeploymentGraph, ServiceRegistry
from src.deployment_graph import DependencyCycleError
from src.deployment_readiness_engine import ReadinessState
from src.optimized_deployment_readiness_engine import (
    OptimizedDeploymentReadinessEngine,
)


def metadata(priority: int = 2, status: str = "pending") -> dict[str, object]:
    return {
        "resource_type": "application",
        "environment": "test",
        "version": "1.0.0",
        "status": status,
        "owner": "platform",
        "priority": priority,
        "region": "generic-region-1",
        "criticality": "normal",
    }


class OptimizedDeploymentReadinessEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = OptimizedDeploymentReadinessEngine()

    def register(self, service_id: str, priority: int = 2) -> None:
        self.engine.register_resource(service_id, metadata(priority))

    def deploy_next(self) -> str:
        selected = self.engine.start_next_resource()
        assert selected is not None
        service_id, _ = selected
        self.engine.mark_deployed(service_id)
        return service_id

    def test_initialization_from_valid_graph_and_registry(self) -> None:
        graph = DeploymentGraph()
        registry = ServiceRegistry()
        for service_id in ("database", "api"):
            registry.register_service(service_id, metadata())
            graph.add_service(service_id)
        graph.add_dependency("database", "api")

        engine = OptimizedDeploymentReadinessEngine(graph, registry)
        self.assertEqual(engine.get_eligible_resources(), ["database"])
        self.assertTrue(engine.validate_internal_state())

    def test_inconsistent_graph_and_registry_are_rejected(self) -> None:
        graph = DeploymentGraph()
        registry = ServiceRegistry()
        graph.add_service("graph-only")
        registry.register_service("registry-only", metadata())
        with self.assertRaisesRegex(ValueError, "identifiers"):
            OptimizedDeploymentReadinessEngine(graph, registry)

    def test_cached_ready_and_waiting_states(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.assertEqual(
            self.engine.get_readiness("database").state,
            ReadinessState.READY,
        )
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.WAITING,
        )

    def test_deterministic_prerequisite_output_order(self) -> None:
        for service_id in ("first", "second", "target"):
            self.register(service_id, 1)
        self.engine.add_dependency("first", "target")
        self.engine.add_dependency("second", "target")

        first = self.engine.start_next_resource()
        self.assertEqual(first, ("first", 1))
        self.engine.mark_failed("first")
        second = self.engine.start_next_resource()
        self.assertEqual(second, ("second", 1))
        self.engine.mark_failed("second")

        result = self.engine.get_readiness("target")
        self.assertEqual(result.incomplete_prerequisites, ("first", "second"))
        self.assertEqual(result.failed_prerequisites, ("first", "second"))

    def test_heap_priority_and_insertion_order(self) -> None:
        self.register("low", 4)
        self.register("first-high", 1)
        self.register("second-high", 1)
        self.assertEqual(self.engine.select_next_resource(), ("first-high", 1))
        self.assertEqual(self.deploy_next(), "first-high")
        self.assertEqual(self.engine.select_next_resource(), ("second-high", 1))

    def test_repeated_select_does_not_change_state(self) -> None:
        self.register("api", 1)
        self.assertEqual(self.engine.select_next_resource(), ("api", 1))
        self.assertEqual(self.engine.select_next_resource(), ("api", 1))
        self.assertEqual(self.engine.get_resource("api")["status"], "pending")

    def test_start_removes_resource_from_ready_membership(self) -> None:
        self.register("api", 1)
        self.assertEqual(self.engine.start_next_resource(), ("api", 1))
        self.assertEqual(self.engine.get_eligible_resources(), [])
        self.assertIsNone(self.engine.select_next_resource())

    def test_deployment_updates_only_direct_dependents(self) -> None:
        for service_id in ("database", "api", "unrelated"):
            self.register(service_id)
        self.engine.add_dependency("database", "api")
        scans_before = self.engine.metrics.eligible_full_scans
        requests_before = self.engine.metrics.readiness_requests

        self.assertEqual(self.deploy_next(), "database")
        self.assertEqual(self.engine.metrics.eligible_full_scans, scans_before)
        self.assertEqual(self.engine.metrics.readiness_requests, requests_before)
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.READY,
        )

    def test_failure_retry_and_recovery_update_cached_states(self) -> None:
        self.register("database", 1)
        self.register("api", 2)
        self.engine.add_dependency("database", "api")
        self.engine.start_next_resource()
        self.engine.mark_failed("database")
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.BLOCKED,
        )

        self.engine.retry_failed("database")
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.WAITING,
        )
        self.deploy_next()
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.READY,
        )

    def test_deployed_and_failed_resource_states(self) -> None:
        self.register("deployed", 1)
        self.register("failed", 2)
        self.engine.start_next_resource()
        self.engine.mark_deployed("deployed")
        self.engine.start_next_resource()
        self.engine.mark_failed("failed")
        self.assertEqual(
            self.engine.get_readiness("deployed").state,
            ReadinessState.DEPLOYED,
        )
        self.assertEqual(
            self.engine.get_readiness("failed").state,
            ReadinessState.FAILED,
        )

    def test_priority_update_uses_lazy_invalidation(self) -> None:
        self.register("first", 1)
        self.register("second", 2)
        self.engine.update_priority("first", 4)

        self.assertEqual(self.engine.select_next_resource(), ("second", 2))
        self.assertGreaterEqual(self.engine.metrics.stale_heap_pops, 1)
        self.assertEqual(self.deploy_next(), "second")
        self.assertEqual(self.engine.select_next_resource(), ("first", 4))

    def test_invalid_priority_and_state_updates_are_rejected(self) -> None:
        self.register("api")
        for priority in (0, 5, True):
            with self.assertRaises(ValueError):
                self.engine.update_priority("api", priority)
        with self.assertRaises(ValueError):
            self.engine.mark_deployed("api")
        with self.assertRaises(ValueError):
            self.engine.retry_failed("api")
        self.engine.start_next_resource()
        with self.assertRaises(ValueError):
            self.engine.update_priority("api", 1)

    def test_dependency_addition_and_removal_update_readiness(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.WAITING,
        )
        self.assertTrue(self.engine.remove_dependency("database", "api"))
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.READY,
        )

    def test_cyclic_dependency_is_rolled_back(self) -> None:
        for service_id in ("a", "b", "c"):
            self.register(service_id)
        self.engine.add_dependency("a", "b")
        self.engine.add_dependency("b", "c")
        with self.assertRaises(DependencyCycleError):
            self.engine.add_dependency("c", "a")
        self.assertFalse(self.engine.graph.has_cycle())
        self.assertTrue(self.engine.validate_internal_state())

    def test_resource_removal_updates_dependents(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.assertTrue(self.engine.remove_resource("database"))
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.READY,
        )
        self.assertFalse(self.engine.remove_resource("database"))

    def test_in_progress_removal_is_rejected(self) -> None:
        self.register("api")
        self.engine.start_next_resource()
        with self.assertRaises(ValueError):
            self.engine.remove_resource("api")

    def test_rebuild_indexes_restores_derived_state(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.engine._ready.clear()
        self.assertFalse(self.engine.validate_internal_state())
        self.engine.rebuild_indexes()
        self.assertTrue(self.engine.validate_internal_state())
        self.assertEqual(self.engine.get_eligible_resources(), ["database"])

    def test_all_deployed_and_summary(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.assertFalse(self.engine.all_deployed())
        self.deploy_next()
        self.deploy_next()
        summary = self.engine.summary()
        self.assertTrue(summary["all_deployed"])
        self.assertEqual(summary["resource_count"], 2)
        self.assertEqual(summary["dependency_count"], 1)
        self.assertEqual(summary["status_counts"]["deployed"], 2)
        self.assertTrue(self.engine.validate_internal_state())


if __name__ == "__main__":
    unittest.main()

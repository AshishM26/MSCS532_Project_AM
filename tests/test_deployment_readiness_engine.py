"""Tests for the integrated DeploymentReadinessEngine."""

import unittest

from src.deployment_graph import DependencyCycleError
from src.deployment_readiness_engine import (
    DeploymentReadinessEngine,
    ReadinessState,
)


def metadata(priority: int = 2, status: str = "pending") -> dict[str, object]:
    """Return valid generic resource metadata."""
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


class DeploymentReadinessEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DeploymentReadinessEngine()

    def register(self, service_id: str, priority: int = 2) -> None:
        self.engine.register_resource(service_id, metadata(priority))

    def deploy_next(self) -> str:
        selected = self.engine.start_next_resource()
        assert selected is not None
        service_id, _ = selected
        self.engine.mark_deployed(service_id)
        return service_id

    def test_register_and_retrieve_resource(self) -> None:
        self.register("api")
        resource = self.engine.get_resource("api")

        assert resource is not None
        self.assertEqual(resource["status"], "pending")
        self.assertEqual(self.engine.topological_order(), ["api"])

    def test_registration_rejects_duplicates_and_nonpending_status(self) -> None:
        self.register("api")
        with self.assertRaises(ValueError):
            self.register("api")
        with self.assertRaises(ValueError):
            self.engine.register_resource("database", metadata(status="deployed"))
        self.assertIsNone(self.engine.get_resource("database"))

    def test_dependency_requires_known_endpoints(self) -> None:
        self.register("api")
        with self.assertRaises(KeyError):
            self.engine.add_dependency("missing", "api")
        with self.assertRaises(KeyError):
            self.engine.add_dependency("api", "missing")

    def test_cycle_is_rejected_and_rolled_back(self) -> None:
        for service_id in ("a", "b", "c"):
            self.register(service_id)
        self.engine.add_dependency("a", "b")
        self.engine.add_dependency("b", "c")

        with self.assertRaises(DependencyCycleError):
            self.engine.add_dependency("c", "a")

        self.assertFalse(self.engine.graph.has_cycle())
        self.assertEqual(self.engine.graph.get_dependents("c"), [])
        self.assertEqual(self.engine.graph.get_prerequisites("a"), [])

    def test_readiness_rules_for_ready_and_waiting(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")

        self.assertEqual(
            self.engine.get_readiness("database").state,
            ReadinessState.READY,
        )
        waiting = self.engine.get_readiness("api")
        self.assertEqual(waiting.state, ReadinessState.WAITING)
        self.assertEqual(waiting.incomplete_prerequisites, ("database",))

        self.deploy_next()
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.READY,
        )

    def test_failure_blocks_then_retry_and_deployment_restore_readiness(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")

        selected = self.engine.start_next_resource()
        self.assertEqual(selected, ("database", 2))
        self.engine.mark_failed("database")
        blocked = self.engine.get_readiness("api")
        self.assertEqual(blocked.state, ReadinessState.BLOCKED)
        self.assertEqual(blocked.failed_prerequisites, ("database",))

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

    def test_eligible_and_priority_selection_are_deterministic(self) -> None:
        self.register("first-high", 1)
        self.register("second-high", 1)
        self.register("low", 4)

        self.assertEqual(
            self.engine.get_eligible_resources(),
            ["first-high", "second-high", "low"],
        )
        self.assertEqual(
            self.engine.select_next_resource(),
            ("first-high", 1),
        )
        self.assertEqual(
            self.engine.get_resource("first-high")["status"],
            "pending",
        )

    def test_start_and_terminal_transitions(self) -> None:
        self.register("api")
        self.assertEqual(self.engine.start_next_resource(), ("api", 2))
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.IN_PROGRESS,
        )
        self.engine.mark_deployed("api")
        self.assertEqual(
            self.engine.get_readiness("api").state,
            ReadinessState.DEPLOYED,
        )

    def test_invalid_state_transitions_are_rejected(self) -> None:
        self.register("api")
        with self.assertRaises(ValueError):
            self.engine.mark_deployed("api")
        with self.assertRaises(ValueError):
            self.engine.mark_failed("api")
        with self.assertRaises(ValueError):
            self.engine.retry_failed("api")

        self.engine.start_next_resource()
        self.engine.mark_deployed("api")
        with self.assertRaises(ValueError):
            self.engine.mark_failed("api")
        with self.assertRaises(ValueError):
            self.engine.retry_failed("api")

    def test_priority_update_changes_selection_and_is_validated(self) -> None:
        self.register("first", 3)
        self.register("second", 2)
        self.assertEqual(self.engine.select_next_resource(), ("second", 2))

        self.engine.update_priority("first", 1)
        self.assertEqual(self.engine.select_next_resource(), ("first", 1))
        for invalid in (0, 5, True):
            with self.assertRaises(ValueError):
                self.engine.update_priority("second", invalid)

    def test_priority_update_rejects_active_and_deployed_resources(self) -> None:
        self.register("api")
        self.engine.start_next_resource()
        with self.assertRaises(ValueError):
            self.engine.update_priority("api", 1)
        self.engine.mark_deployed("api")
        with self.assertRaises(ValueError):
            self.engine.update_priority("api", 1)

    def test_coordinated_removal_updates_graph_and_registry(self) -> None:
        for service_id in ("database", "api", "web"):
            self.register(service_id)
        self.engine.add_dependency("database", "api")
        self.engine.add_dependency("api", "web")

        self.assertTrue(self.engine.remove_resource("api"))
        self.assertIsNone(self.engine.get_resource("api"))
        self.assertEqual(self.engine.graph.get_dependents("database"), [])
        self.assertEqual(self.engine.graph.get_prerequisites("web"), [])
        self.assertFalse(self.engine.remove_resource("api"))

    def test_in_progress_removal_is_rejected(self) -> None:
        self.register("api")
        self.engine.start_next_resource()
        with self.assertRaises(ValueError):
            self.engine.remove_resource("api")

    def test_all_deployed_and_summary(self) -> None:
        self.register("database")
        self.register("api")
        self.engine.add_dependency("database", "api")
        self.assertFalse(self.engine.all_deployed())

        self.deploy_next()
        self.deploy_next()
        summary = self.engine.summary()
        self.assertTrue(self.engine.all_deployed())
        self.assertEqual(summary["resource_count"], 2)
        self.assertEqual(summary["dependency_count"], 1)
        self.assertEqual(summary["status_counts"]["deployed"], 2)
        self.assertEqual(summary["readiness_counts"]["deployed"], 2)


if __name__ == "__main__":
    unittest.main()

"""Coordinator for dependency readiness, resource state, and task urgency."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .deployment_graph import DependencyCycleError, DeploymentGraph
from .deployment_priority_queue import DeploymentPriorityQueue
from .service_registry import ServiceRegistry


class ReadinessState(Enum):
    """Derived readiness and execution states for a registered resource."""

    READY = "ready"
    WAITING = "waiting"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    DEPLOYED = "deployed"
    FAILED = "failed"


@dataclass(frozen=True)
class ReadinessResult:
    """Describe a resource's current derived readiness."""

    service_id: str
    state: ReadinessState
    incomplete_prerequisites: tuple[str, ...] = ()
    failed_prerequisites: tuple[str, ...] = ()


class DeploymentReadinessEngine:
    """Coordinate Phase 1 structures without duplicating their storage."""

    VALID_PRIORITIES = frozenset({1, 2, 3, 4})
    VALID_STATUSES = frozenset({"pending", "in_progress", "deployed", "failed"})

    def __init__(
        self,
        graph: DeploymentGraph | None = None,
        registry: ServiceRegistry | None = None,
    ) -> None:
        self.graph = graph if graph is not None else DeploymentGraph()
        self.registry = registry if registry is not None else ServiceRegistry()

    def _require_resource(self, service_id: str) -> dict[str, Any]:
        resource = self.registry.get_service(service_id)
        if resource is None:
            raise KeyError(f"unknown resource: {service_id}")
        return resource

    def register_resource(
        self, service_id: str, metadata: dict[str, Any]
    ) -> None:
        """Register pending metadata, then add its graph node."""
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")
        if metadata.get("status") != "pending":
            raise ValueError("new resources must have initial status 'pending'")
        self.registry.register_service(service_id, metadata)
        self.graph.add_service(service_id)

    def add_dependency(self, prerequisite: str, dependent: str) -> None:
        """Add an edge between registered resources and reject cycles."""
        self._require_resource(prerequisite)
        self._require_resource(dependent)
        self.graph.add_dependency(prerequisite, dependent)
        if self.graph.has_cycle():
            self.graph.remove_dependency(prerequisite, dependent)
            raise DependencyCycleError(
                "dependency would create a cycle: "
                f"{prerequisite} -> {dependent}"
            )

    def remove_dependency(self, prerequisite: str, dependent: str) -> bool:
        """Remove a dependency while leaving endpoint resources registered."""
        return self.graph.remove_dependency(prerequisite, dependent)

    def remove_resource(self, service_id: str) -> bool:
        """Remove an idle resource and all its dependency edges."""
        resource = self.registry.get_service(service_id)
        if resource is None:
            return False
        if resource["status"] == "in_progress":
            raise ValueError(f"cannot remove in-progress resource: {service_id}")
        self.graph.remove_service(service_id)
        self.registry.remove_service(service_id)
        return True

    def get_resource(self, service_id: str) -> dict[str, Any] | None:
        """Return a safe metadata copy, or None if the resource is unknown."""
        return self.registry.get_service(service_id)

    def update_priority(self, service_id: str, priority: int) -> None:
        """Update urgency while a resource is pending or failed."""
        resource = self._require_resource(service_id)
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority not in self.VALID_PRIORITIES
        ):
            raise ValueError("priority must be an integer from 1 to 4")
        if resource["status"] not in {"pending", "failed"}:
            raise ValueError(
                "priority can only be updated for pending or failed resources"
            )
        self.registry.update_metadata(service_id, {"priority": priority})

    def get_readiness(self, service_id: str) -> ReadinessResult:
        """Derive readiness from execution state and direct prerequisites."""
        resource = self._require_resource(service_id)
        status = resource["status"]
        direct_states = {
            prerequisite: self._require_resource(prerequisite)["status"]
            for prerequisite in self.graph.get_prerequisites(service_id)
        }

        if status == "deployed":
            return ReadinessResult(service_id, ReadinessState.DEPLOYED)
        if status == "failed":
            return ReadinessResult(service_id, ReadinessState.FAILED)
        if status == "in_progress":
            return ReadinessResult(service_id, ReadinessState.IN_PROGRESS)
        if status != "pending":
            raise ValueError(
                f"unsupported execution status for {service_id}: {status}"
            )

        incomplete = tuple(
            prerequisite
            for prerequisite, state in direct_states.items()
            if state != "deployed"
        )
        failed = tuple(
            prerequisite
            for prerequisite, state in direct_states.items()
            if state == "failed"
        )
        if failed:
            state = ReadinessState.BLOCKED
        elif incomplete:
            state = ReadinessState.WAITING
        else:
            state = ReadinessState.READY
        return ReadinessResult(service_id, state, incomplete, failed)

    def get_eligible_resources(self) -> list[str]:
        """Return READY identifiers in registry insertion order."""
        return [
            resource["service_id"]
            for resource in self.registry.list_services()
            if self.get_readiness(resource["service_id"]).state
            is ReadinessState.READY
        ]

    def select_next_resource(self) -> tuple[str, int] | None:
        """Select the highest-urgency ready resource without changing state.

        Rebuilding the ready heap costs O(r log r) for r ready resources but
        immediately reflects priority changes and keeps Phase 2 behavior simple.
        """
        queue = DeploymentPriorityQueue()
        for service_id in self.get_eligible_resources():
            resource = self._require_resource(service_id)
            queue.enqueue(service_id, resource["priority"])
        return queue.dequeue()

    def start_next_resource(self) -> tuple[str, int] | None:
        """Select a ready resource and move it from pending to in_progress."""
        selected = self.select_next_resource()
        if selected is None:
            return None
        service_id, _ = selected
        self.registry.update_status(service_id, "in_progress")
        return selected

    def mark_deployed(self, service_id: str) -> None:
        """Move an in-progress resource to its terminal deployed state."""
        resource = self._require_resource(service_id)
        if resource["status"] != "in_progress":
            raise ValueError(
                f"resource must be in_progress before deployment: {service_id}"
            )
        self.registry.update_status(service_id, "deployed")

    def mark_failed(self, service_id: str) -> None:
        """Move an in-progress resource to failed."""
        resource = self._require_resource(service_id)
        if resource["status"] != "in_progress":
            raise ValueError(
                f"resource must be in_progress before failure: {service_id}"
            )
        self.registry.update_status(service_id, "failed")

    def retry_failed(self, service_id: str) -> None:
        """Return a failed resource to pending so readiness is recalculated."""
        resource = self._require_resource(service_id)
        if resource["status"] != "failed":
            raise ValueError(f"only failed resources can be retried: {service_id}")
        self.registry.update_status(service_id, "pending")

    def topological_order(self) -> list[str]:
        """Return a valid order from the underlying graph."""
        return self.graph.topological_order()

    def all_deployed(self) -> bool:
        """Return whether every registered resource is deployed."""
        return all(
            resource["status"] == "deployed"
            for resource in self.registry.list_services()
        )

    def summary(self) -> dict[str, Any]:
        """Return counts and current readiness for reproducible reporting."""
        resources = self.registry.list_services()
        status_counts = {status: 0 for status in sorted(self.VALID_STATUSES)}
        readiness_counts = {state.value: 0 for state in ReadinessState}
        dependency_count = 0

        for resource in resources:
            service_id = resource["service_id"]
            status = resource["status"]
            status_counts.setdefault(status, 0)
            status_counts[status] += 1
            readiness = self.get_readiness(service_id)
            readiness_counts[readiness.state.value] += 1
            dependency_count += len(self.graph.get_dependents(service_id))

        return {
            "resource_count": len(resources),
            "dependency_count": dependency_count,
            "status_counts": status_counts,
            "readiness_counts": readiness_counts,
            "eligible_resources": self.get_eligible_resources(),
            "all_deployed": self.all_deployed(),
        }

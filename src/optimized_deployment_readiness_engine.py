"""Incrementally indexed Phase 3 deployment readiness engine."""

import heapq
from typing import Any

from .deployment_graph import DependencyCycleError, DeploymentGraph
from .deployment_readiness_engine import (
    DeploymentReadinessEngine,
    ReadinessResult,
    ReadinessState,
)
from .phase3_metrics import EngineMetrics
from .service_registry import ServiceRegistry


HeapEntry = tuple[int, int, int, str]


class OptimizedDeploymentReadinessEngine(DeploymentReadinessEngine):
    """Preserve Phase 2 behavior with incremental derived indexes.

    Graph and registry remain the authoritative stores. Cached prerequisite
    state, ready membership, and a versioned persistent heap are derived state
    that can be rebuilt at any time.
    """

    def __init__(
        self,
        graph: DeploymentGraph | None = None,
        registry: ServiceRegistry | None = None,
    ) -> None:
        super().__init__(graph, registry)
        self.metrics = EngineMetrics()
        self._insertion_order: dict[str, int] = {}
        self._incomplete: dict[str, set[str]] = {}
        self._failed: dict[str, set[str]] = {}
        self._incomplete_order: dict[str, dict[str, None]] = {}
        self._failed_order: dict[str, dict[str, None]] = {}
        self._ready: set[str] = set()
        self._generation: dict[str, int] = {}
        self._heap: list[HeapEntry] = []
        self.rebuild_indexes()

    def _push_heap(self, service_id: str) -> None:
        resource = self._require_resource(service_id)
        entry = (
            resource["priority"],
            self._insertion_order[service_id],
            self._generation[service_id],
            service_id,
        )
        heapq.heappush(self._heap, entry)
        self.metrics.heap_pushes += 1
        self.metrics.maximum_heap_size = max(
            self.metrics.maximum_heap_size,
            len(self._heap),
        )

    def _make_ready(self, service_id: str) -> None:
        if service_id in self._ready:
            return
        self._ready.add(service_id)
        self._generation[service_id] += 1
        self._push_heap(service_id)

    def _invalidate_ready(self, service_id: str) -> None:
        if service_id in self._ready:
            self._ready.remove(service_id)
            self._generation[service_id] += 1

    def _refresh_ready(self, service_id: str) -> None:
        resource = self._require_resource(service_id)
        should_be_ready = (
            resource["status"] == "pending"
            and not self._incomplete[service_id]
        )
        if should_be_ready:
            self._make_ready(service_id)
        else:
            self._invalidate_ready(service_id)

    def _entry_is_valid(self, entry: HeapEntry) -> bool:
        priority, _, generation, service_id = entry
        if self._generation.get(service_id) != generation:
            return False
        if service_id not in self._ready:
            return False
        resource = self.registry.get_service(service_id)
        return bool(
            resource is not None
            and resource["status"] == "pending"
            and resource["priority"] == priority
        )

    def _clean_stale_entries(self) -> None:
        while self._heap and not self._entry_is_valid(self._heap[0]):
            heapq.heappop(self._heap)
            self.metrics.heap_pops += 1
            self.metrics.stale_heap_pops += 1

    def rebuild_indexes(self) -> None:
        """Reconstruct all derived indexes from graph and registry state."""
        resources = self.registry.list_services()
        registry_ids = [resource["service_id"] for resource in resources]
        graph_ids = self.graph.topological_order()
        if set(registry_ids) != set(graph_ids):
            raise ValueError("graph and registry resource identifiers must match")

        previous_generations = getattr(self, "_generation", {})
        self._insertion_order = {
            service_id: position
            for position, service_id in enumerate(registry_ids)
        }
        self._incomplete = {}
        self._failed = {}
        self._incomplete_order = {}
        self._failed_order = {}
        self._ready = set()
        self._generation = {
            service_id: previous_generations.get(service_id, -1) + 1
            for service_id in registry_ids
        }
        self._heap = []

        for resource in resources:
            service_id = resource["service_id"]
            incomplete_order: dict[str, None] = {}
            failed_order: dict[str, None] = {}
            for prerequisite in self.graph.get_prerequisites(service_id):
                state = self._require_resource(prerequisite)["status"]
                self.metrics.prerequisite_status_checks += 1
                if state != "deployed":
                    incomplete_order[prerequisite] = None
                if state == "failed":
                    failed_order[prerequisite] = None
            self._incomplete_order[service_id] = incomplete_order
            self._failed_order[service_id] = failed_order
            self._incomplete[service_id] = set(incomplete_order)
            self._failed[service_id] = set(failed_order)
            if resource["status"] == "pending" and not incomplete_order:
                self._ready.add(service_id)

        for service_id in registry_ids:
            if service_id in self._ready:
                self._push_heap(service_id)
        self.metrics.index_rebuilds += 1

    def register_resource(
        self, service_id: str, metadata: dict[str, Any]
    ) -> None:
        """Register a pending resource and initialize its derived indexes."""
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")
        if metadata.get("status") != "pending":
            raise ValueError("new resources must have initial status 'pending'")
        self.registry.register_service(service_id, metadata)
        self.graph.add_service(service_id)
        self._insertion_order[service_id] = len(self._insertion_order)
        self._incomplete[service_id] = set()
        self._failed[service_id] = set()
        self._incomplete_order[service_id] = {}
        self._failed_order[service_id] = {}
        self._ready.add(service_id)
        self._generation[service_id] = 0
        self._push_heap(service_id)

    def add_dependency(self, prerequisite: str, dependent: str) -> None:
        """Add a validated edge and update only the dependent's indexes."""
        prerequisite_record = self._require_resource(prerequisite)
        self._require_resource(dependent)
        self.graph.add_dependency(prerequisite, dependent)
        self.metrics.full_cycle_validations += 1
        if self.graph.has_cycle():
            self.graph.remove_dependency(prerequisite, dependent)
            raise DependencyCycleError(
                "dependency would create a cycle: "
                f"{prerequisite} -> {dependent}"
            )

        status = prerequisite_record["status"]
        if status != "deployed":
            self._incomplete[dependent].add(prerequisite)
            self._incomplete_order[dependent][prerequisite] = None
        if status == "failed":
            self._failed[dependent].add(prerequisite)
            self._failed_order[dependent][prerequisite] = None
        self._refresh_ready(dependent)

    def remove_dependency(self, prerequisite: str, dependent: str) -> bool:
        """Remove an edge and update only the former dependent."""
        removed = self.graph.remove_dependency(prerequisite, dependent)
        if not removed:
            return False
        self._incomplete[dependent].discard(prerequisite)
        self._failed[dependent].discard(prerequisite)
        self._incomplete_order[dependent].pop(prerequisite, None)
        self._failed_order[dependent].pop(prerequisite, None)
        self._refresh_ready(dependent)
        return True

    def remove_resource(self, service_id: str) -> bool:
        """Coordinate removal while updating direct dependents incrementally."""
        resource = self.registry.get_service(service_id)
        if resource is None:
            return False
        if resource["status"] == "in_progress":
            raise ValueError(f"cannot remove in-progress resource: {service_id}")

        dependents = self.graph.get_dependents(service_id)
        self._invalidate_ready(service_id)
        for dependent in dependents:
            self._incomplete[dependent].discard(service_id)
            self._failed[dependent].discard(service_id)
            self._incomplete_order[dependent].pop(service_id, None)
            self._failed_order[dependent].pop(service_id, None)
            self.metrics.dependent_updates += 1

        self.graph.remove_service(service_id)
        self.registry.remove_service(service_id)
        self._insertion_order.pop(service_id, None)
        self._incomplete.pop(service_id, None)
        self._failed.pop(service_id, None)
        self._incomplete_order.pop(service_id, None)
        self._failed_order.pop(service_id, None)
        self._generation.pop(service_id, None)
        for dependent in dependents:
            self._refresh_ready(dependent)
        return True

    def update_priority(self, service_id: str, priority: int) -> None:
        """Update priority with O(log r) lazy heap versioning when ready."""
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
        self._generation[service_id] += 1
        if service_id in self._ready:
            self._push_heap(service_id)

    def get_readiness(self, service_id: str) -> ReadinessResult:
        """Return readiness from cached prerequisite state."""
        self.metrics.readiness_requests += 1
        resource = self._require_resource(service_id)
        status = resource["status"]
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

        incomplete = tuple(self._incomplete_order[service_id])
        failed = tuple(self._failed_order[service_id])
        if failed:
            state = ReadinessState.BLOCKED
        elif incomplete:
            state = ReadinessState.WAITING
        else:
            state = ReadinessState.READY
        return ReadinessResult(service_id, state, incomplete, failed)

    def get_eligible_resources(self) -> list[str]:
        """Return cached READY membership in registry insertion order."""
        self.metrics.eligible_full_scans += 1
        return [
            service_id
            for service_id in self._insertion_order
            if service_id in self._ready
        ]

    def select_next_resource(self) -> tuple[str, int] | None:
        """Peek at the persistent heap after amortized stale cleanup."""
        self._clean_stale_entries()
        if not self._heap:
            return None
        priority, _, _, service_id = self._heap[0]
        return service_id, priority

    def start_next_resource(self) -> tuple[str, int] | None:
        """Pop and start the valid best ready resource."""
        self._clean_stale_entries()
        if not self._heap:
            return None
        priority, _, _, service_id = heapq.heappop(self._heap)
        self.metrics.heap_pops += 1
        self._ready.remove(service_id)
        self.registry.update_status(service_id, "in_progress")
        return service_id, priority

    def mark_deployed(self, service_id: str) -> None:
        """Deploy a resource and update only its direct dependents."""
        resource = self._require_resource(service_id)
        if resource["status"] != "in_progress":
            raise ValueError(
                f"resource must be in_progress before deployment: {service_id}"
            )
        self.registry.update_status(service_id, "deployed")
        self.metrics.resources_processed += 1
        for dependent in self.graph.get_dependents(service_id):
            self._incomplete[dependent].discard(service_id)
            self._failed[dependent].discard(service_id)
            self._incomplete_order[dependent].pop(service_id, None)
            self._failed_order[dependent].pop(service_id, None)
            self.metrics.dependent_updates += 1
            self._refresh_ready(dependent)

    def mark_failed(self, service_id: str) -> None:
        """Fail an active resource and block only its direct dependents."""
        resource = self._require_resource(service_id)
        if resource["status"] != "in_progress":
            raise ValueError(
                f"resource must be in_progress before failure: {service_id}"
            )
        self.registry.update_status(service_id, "failed")
        for dependent in self.graph.get_dependents(service_id):
            self._incomplete[dependent].add(service_id)
            self._incomplete_order[dependent][service_id] = None
            self._failed[dependent].add(service_id)
            self._failed_order[dependent][service_id] = None
            self.metrics.dependent_updates += 1
            self._refresh_ready(dependent)

    def retry_failed(self, service_id: str) -> None:
        """Retry a failed resource and unblock its direct dependents."""
        resource = self._require_resource(service_id)
        if resource["status"] != "failed":
            raise ValueError(f"only failed resources can be retried: {service_id}")
        self.registry.update_status(service_id, "pending")
        for dependent in self.graph.get_dependents(service_id):
            self._failed[dependent].discard(service_id)
            self._failed_order[dependent].pop(service_id, None)
            self.metrics.dependent_updates += 1
            self._refresh_ready(dependent)
        self._refresh_ready(service_id)

    def summary(self) -> dict[str, Any]:
        """Return a Phase 2-compatible state summary."""
        resources = self.registry.list_services()
        status_counts = {status: 0 for status in sorted(self.VALID_STATUSES)}
        readiness_counts = {state.value: 0 for state in ReadinessState}
        dependency_count = 0
        for resource in resources:
            service_id = resource["service_id"]
            status_counts[resource["status"]] += 1
            readiness_counts[self.get_readiness(service_id).state.value] += 1
            dependency_count += len(self.graph.get_dependents(service_id))
        return {
            "resource_count": len(resources),
            "dependency_count": dependency_count,
            "status_counts": status_counts,
            "readiness_counts": readiness_counts,
            "eligible_resources": self.get_eligible_resources(),
            "all_deployed": self.all_deployed(),
        }

    def validate_internal_state(self) -> bool:
        """Verify every derived index and the valid heap root."""
        resources = self.registry.list_services()
        registry_ids = [resource["service_id"] for resource in resources]
        if set(registry_ids) != set(self.graph.topological_order()):
            return False
        if registry_ids != list(self._insertion_order):
            return False

        expected_ready: set[str] = set()
        for resource in resources:
            service_id = resource["service_id"]
            expected_incomplete: dict[str, None] = {}
            expected_failed: dict[str, None] = {}
            for prerequisite in self.graph.get_prerequisites(service_id):
                state = self._require_resource(prerequisite)["status"]
                if state != "deployed":
                    expected_incomplete[prerequisite] = None
                if state == "failed":
                    expected_failed[prerequisite] = None
            if self._incomplete.get(service_id) != set(expected_incomplete):
                return False
            if self._failed.get(service_id) != set(expected_failed):
                return False
            if self._incomplete_order.get(service_id) != expected_incomplete:
                return False
            if self._failed_order.get(service_id) != expected_failed:
                return False
            if resource["status"] == "pending" and not expected_incomplete:
                expected_ready.add(service_id)
        if self._ready != expected_ready:
            return False

        self._clean_stale_entries()
        expected_selection = None
        if expected_ready:
            expected_selection = min(
                (
                    self._require_resource(service_id)["priority"],
                    self._insertion_order[service_id],
                    service_id,
                )
                for service_id in expected_ready
            )
        actual_selection = None
        if self._heap:
            priority, position, _, service_id = self._heap[0]
            actual_selection = priority, position, service_id
        return actual_selection == expected_selection

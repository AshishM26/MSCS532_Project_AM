"""Directed graph for service deployment dependencies."""

from collections import deque


class DuplicateDependencyError(ValueError):
    """Raised when an existing dependency edge is added again."""


class DependencyCycleError(ValueError):
    """Raised when a deployment order cannot be produced due to a cycle."""


class DeploymentGraph:
    """Represent service prerequisites with directed adjacency lists.

    Services and dependencies are stored in insertion order. Therefore, when
    more than one topological order is valid, the result is deterministic for a
    given sequence of calls. Adding a dependency automatically registers both
    endpoint services.
    """

    def __init__(self) -> None:
        self._dependents: dict[str, dict[str, None]] = {}
        self._prerequisites: dict[str, dict[str, None]] = {}

    @staticmethod
    def _validate_name(service_name: str) -> None:
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValueError("service_name must be a non-empty string")

    def add_service(self, service_name: str) -> None:
        """Add a service if absent in average-case O(1) time."""
        self._validate_name(service_name)
        self._dependents.setdefault(service_name, {})
        self._prerequisites.setdefault(service_name, {})

    def add_dependency(self, prerequisite: str, dependent: str) -> None:
        """Add prerequisite -> dependent in average-case O(1) time.

        Missing endpoint services are registered automatically. Duplicate edges
        are rejected so an accidental repeated declaration is visible.
        """
        self._validate_name(prerequisite)
        self._validate_name(dependent)
        self.add_service(prerequisite)
        self.add_service(dependent)
        if dependent in self._dependents[prerequisite]:
            raise DuplicateDependencyError(
                f"dependency already exists: {prerequisite} -> {dependent}"
            )
        self._dependents[prerequisite][dependent] = None
        self._prerequisites[dependent][prerequisite] = None

    def get_dependents(self, service_name: str) -> list[str]:
        """Return direct dependents in O(d) time, or an empty list if unknown."""
        self._validate_name(service_name)
        return list(self._dependents.get(service_name, {}))

    def get_prerequisites(self, service_name: str) -> list[str]:
        """Return direct prerequisites in O(d) time, or [] if unknown."""
        self._validate_name(service_name)
        return list(self._prerequisites.get(service_name, {}))

    def remove_dependency(self, prerequisite: str, dependent: str) -> bool:
        """Remove an edge while preserving both endpoint nodes.

        Average-case time is O(1) because both adjacency structures use
        dictionaries.
        """
        self._validate_name(prerequisite)
        self._validate_name(dependent)
        if dependent not in self._dependents.get(prerequisite, {}):
            return False

        del self._dependents[prerequisite][dependent]
        del self._prerequisites[dependent][prerequisite]
        return True

    def remove_service(self, service_name: str) -> bool:
        """Remove a service and every connected edge.

        Time is O(in-degree + out-degree) for the removed service.
        """
        self._validate_name(service_name)
        if service_name not in self._dependents:
            return False

        for prerequisite in tuple(self._prerequisites[service_name]):
            del self._dependents[prerequisite][service_name]
        for dependent in tuple(self._dependents[service_name]):
            del self._prerequisites[dependent][service_name]

        del self._dependents[service_name]
        del self._prerequisites[service_name]
        return True

    def _kahn_order(self) -> list[str]:
        """Return all nodes reachable by Kahn's algorithm in O(V + E) time."""
        in_degree = {
            service: len(prerequisites)
            for service, prerequisites in self._prerequisites.items()
        }
        eligible = deque(
            service for service in self._dependents if in_degree[service] == 0
        )
        order: list[str] = []

        while eligible:
            prerequisite = eligible.popleft()
            order.append(prerequisite)
            for dependent in self._dependents[prerequisite]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    eligible.append(dependent)
        return order

    def has_cycle(self) -> bool:
        """Return whether the graph contains a cycle in O(V + E) time."""
        return len(self._kahn_order()) != len(self._dependents)

    def topological_order(self) -> list[str]:
        """Return a valid deployment order in O(V + E) time.

        Raises:
            DependencyCycleError: If no topological order exists.
        """
        order = self._kahn_order()
        if len(order) != len(self._dependents):
            raise DependencyCycleError(
                "cannot produce a deployment order: dependency graph has a cycle"
            )
        return order

"""Stable min-heap for eligible deployment tasks."""

import heapq
from itertools import count


class DeploymentPriorityQueue:
    """Prioritize tasks from 1 (critical) through 4 (low).

    Equal-priority tasks are returned in first-in, first-out order using a
    monotonically increasing insertion counter.
    """

    VALID_PRIORITIES = frozenset({1, 2, 3, 4})

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._counter = count()

    @classmethod
    def _validate(cls, service_id: str, priority: int) -> None:
        if not isinstance(service_id, str) or not service_id.strip():
            raise ValueError("service_id must be a non-empty string")
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority not in cls.VALID_PRIORITIES
        ):
            raise ValueError("priority must be an integer from 1 to 4")

    def enqueue(self, service_id: str, priority: int) -> None:
        """Add a deployment task in O(log n) time."""
        self._validate(service_id, priority)
        heapq.heappush(self._heap, (priority, next(self._counter), service_id))

    def peek(self) -> tuple[str, int] | None:
        """Return (service_id, priority) for the next task in O(1) time."""
        if not self._heap:
            return None
        priority, _, service_id = self._heap[0]
        return service_id, priority

    def dequeue(self) -> tuple[str, int] | None:
        """Remove and return (service_id, priority) in O(log n) time."""
        if not self._heap:
            return None
        priority, _, service_id = heapq.heappop(self._heap)
        return service_id, priority

    def is_empty(self) -> bool:
        """Return whether the queue has no tasks in O(1) time."""
        return not self._heap

    def size(self) -> int:
        """Return the number of queued tasks in O(1) time."""
        return len(self._heap)

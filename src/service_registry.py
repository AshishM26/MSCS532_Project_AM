"""Hash-table-backed registry for service metadata."""

from copy import deepcopy
from typing import Any


class ServiceRegistry:
    """Store and retrieve validated service records using a dictionary.

    Lookup, insertion, update, membership, and removal are O(1) on average,
    excluding the cost of copying a record's nested metadata.
    """

    REQUIRED_FIELDS = frozenset(
        {"environment", "version", "status", "owner", "priority"}
    )
    VALID_PRIORITIES = frozenset({1, 2, 3, 4})

    def __init__(self) -> None:
        self._services: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _validate_service_id(service_id: str) -> None:
        if not isinstance(service_id, str) or not service_id.strip():
            raise ValueError("service_id must be a non-empty string")

    @classmethod
    def _validate_record(cls, record: dict[str, Any]) -> None:
        missing = cls.REQUIRED_FIELDS - record.keys()
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"missing required metadata fields: {fields}")
        priority = record["priority"]
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority not in cls.VALID_PRIORITIES
        ):
            raise ValueError("priority must be an integer from 1 to 4")

    def register_service(self, service_id: str, metadata: dict[str, Any]) -> None:
        """Register a new service; raise ValueError for invalid/duplicate data."""
        self._validate_service_id(service_id)
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")
        if service_id in self._services:
            raise ValueError(f"service is already registered: {service_id}")

        record = deepcopy(metadata)
        supplied_id = record.get("service_id", service_id)
        if supplied_id != service_id:
            raise ValueError("metadata service_id must match service_id argument")
        record["service_id"] = service_id
        self._validate_record(record)
        self._services[service_id] = record

    def get_service(self, service_id: str) -> dict[str, Any] | None:
        """Return a safe copy of a service record, or None when it is absent."""
        self._validate_service_id(service_id)
        record = self._services.get(service_id)
        return deepcopy(record) if record is not None else None

    def update_status(self, service_id: str, status: str) -> None:
        """Update a service status; raise KeyError if the service is absent."""
        self._validate_service_id(service_id)
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        if service_id not in self._services:
            raise KeyError(f"unknown service: {service_id}")
        self._services[service_id]["status"] = status

    def update_metadata(self, service_id: str, updates: dict[str, Any]) -> None:
        """Merge validated metadata updates into an existing service record."""
        self._validate_service_id(service_id)
        if not isinstance(updates, dict):
            raise TypeError("updates must be a dictionary")
        if service_id not in self._services:
            raise KeyError(f"unknown service: {service_id}")
        if "service_id" in updates and updates["service_id"] != service_id:
            raise ValueError("service_id cannot be changed")

        candidate = deepcopy(self._services[service_id])
        candidate.update(deepcopy(updates))
        self._validate_record(candidate)
        self._services[service_id] = candidate

    def remove_service(self, service_id: str) -> bool:
        """Remove a service in average-case O(1) time; report whether found."""
        self._validate_service_id(service_id)
        return self._services.pop(service_id, None) is not None

    def contains(self, service_id: str) -> bool:
        """Return membership in average-case O(1) time."""
        self._validate_service_id(service_id)
        return service_id in self._services

    def list_services(self) -> list[dict[str, Any]]:
        """Return safe copies of all records in insertion order in O(n + m)."""
        return deepcopy(list(self._services.values()))

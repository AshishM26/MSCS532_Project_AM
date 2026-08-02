"""Validate-first bulk CSV loading for the optimized Phase 3 engine."""

import csv
from pathlib import Path

from .cloud_resource_loader import (
    DEPENDENCY_COLUMNS,
    RESOURCE_COLUMNS,
    _clean_required_row,
    _require_columns,
)
from .deployment_graph import DeploymentGraph, DuplicateDependencyError
from .deployment_readiness_engine import DeploymentReadinessEngine
from .optimized_deployment_readiness_engine import (
    OptimizedDeploymentReadinessEngine,
)
from .service_registry import ServiceRegistry


def _read_resources(path: Path) -> list[tuple[str, dict[str, object]]]:
    """Parse and validate every resource row without changing engine state."""
    parsed: list[tuple[str, dict[str, object]]] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, RESOURCE_COLUMNS, "resource")
        for row_number, row in enumerate(reader, start=2):
            cleaned = _clean_required_row(
                row, RESOURCE_COLUMNS, "resource", row_number
            )
            service_id = cleaned["service_id"]
            if service_id in seen:
                raise ValueError(f"service is already registered: {service_id}")
            seen.add(service_id)

            raw_priority = cleaned["priority"]
            try:
                priority = int(raw_priority)
            except ValueError as error:
                raise ValueError(
                    f"resource CSV row {row_number} has invalid priority: "
                    f"{raw_priority!r}"
                ) from error
            if priority not in DeploymentReadinessEngine.VALID_PRIORITIES:
                raise ValueError(
                    f"resource CSV row {row_number} priority must be 1 to 4"
                )
            if cleaned["status"] != "pending":
                raise ValueError(
                    f"resource CSV row {row_number} status must be 'pending'"
                )

            metadata: dict[str, object] = {
                key: value
                for key, value in cleaned.items()
                if key != "service_id"
            }
            metadata["priority"] = priority
            parsed.append((service_id, metadata))
    if not parsed:
        raise ValueError("resource CSV must contain at least one data row")
    return parsed


def _read_dependencies(
    path: Path,
    service_ids: set[str],
) -> list[tuple[str, str]]:
    """Parse all edges and validate uniqueness and known endpoints."""
    parsed: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, DEPENDENCY_COLUMNS, "dependency")
        for row_number, row in enumerate(reader, start=2):
            cleaned = _clean_required_row(
                row, DEPENDENCY_COLUMNS, "dependency", row_number
            )
            prerequisite = cleaned["prerequisite"]
            dependent = cleaned["dependent"]
            edge = prerequisite, dependent
            if edge in seen:
                raise DuplicateDependencyError(
                    f"dependency already exists: {prerequisite} -> {dependent}"
                )
            if prerequisite not in service_ids:
                raise KeyError(f"unknown resource: {prerequisite}")
            if dependent not in service_ids:
                raise KeyError(f"unknown resource: {dependent}")
            seen.add(edge)
            parsed.append(edge)
    return parsed


def load_optimized_engine_from_csv(
    resources_path: str | Path,
    dependencies_path: str | Path,
) -> OptimizedDeploymentReadinessEngine:
    """Build an optimized engine after validating both complete datasets.

    Resource and dependency records are validated before any graph mutation.
    All edges are then inserted in O(V + E) expected time and the optimized
    engine performs one final O(V + E) topological validation while building
    its derived indexes.
    """
    resources = _read_resources(Path(resources_path))
    service_ids = {service_id for service_id, _ in resources}
    dependencies = _read_dependencies(Path(dependencies_path), service_ids)

    graph = DeploymentGraph()
    registry = ServiceRegistry()
    for service_id, metadata in resources:
        registry.register_service(service_id, metadata)
        graph.add_service(service_id)
    for prerequisite, dependent in dependencies:
        graph.add_dependency(prerequisite, dependent)

    engine = OptimizedDeploymentReadinessEngine(graph, registry)
    engine.metrics.full_cycle_validations = 1
    return engine

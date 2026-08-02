"""Deterministic synthetic DAG generation for Phase 3 evaluation."""

import csv
from dataclasses import dataclass
from pathlib import Path
import random


RESOURCE_FIELDNAMES = [
    "service_id",
    "resource_type",
    "environment",
    "version",
    "status",
    "owner",
    "priority",
    "region",
    "criticality",
]
DEPENDENCY_FIELDNAMES = ["prerequisite", "dependent"]
WORKLOAD_PROFILES = (
    "chain",
    "layered_sparse",
    "layered_dense",
    "wide_independent",
)


@dataclass(frozen=True)
class SyntheticWorkload:
    """Contain generated resource rows and ordered dependency edges."""

    profile: str
    seed: int
    resources: tuple[dict[str, str], ...]
    dependencies: tuple[tuple[str, str], ...]

    @property
    def resource_count(self) -> int:
        return len(self.resources)

    @property
    def dependency_count(self) -> int:
        return len(self.dependencies)


def _resource_row(index: int, rng: random.Random) -> dict[str, str]:
    """Create one generic resource record."""
    resource_types = (
        "network",
        "identity",
        "security",
        "database",
        "application",
        "observability",
        "backup",
        "messaging",
    )
    owners = ("platform", "security", "data", "application", "operations")
    criticalities = ("critical", "high", "normal", "low")
    return {
        "service_id": f"resource-{index:06d}",
        "resource_type": resource_types[index % len(resource_types)],
        "environment": "staging",
        "version": f"1.{index % 10}.0",
        "status": "pending",
        "owner": owners[index % len(owners)],
        "priority": str(rng.randint(1, 4)),
        "region": "generic-region-1",
        "criticality": criticalities[index % len(criticalities)],
    }


def _layered_dependencies(
    service_ids: list[str],
    rng: random.Random,
    maximum_prerequisites: int,
) -> list[tuple[str, str]]:
    """Build an acyclic layered graph with bounded previous-layer fan-in."""
    resource_count = len(service_ids)
    layer_width = max(2, int(resource_count**0.5))
    layers = [
        service_ids[start : start + layer_width]
        for start in range(0, resource_count, layer_width)
    ]
    dependencies: list[tuple[str, str]] = []
    for layer_index in range(1, len(layers)):
        previous = layers[layer_index - 1]
        for dependent in layers[layer_index]:
            limit = min(maximum_prerequisites, len(previous))
            count = rng.randint(1, limit)
            selected = sorted(
                rng.sample(previous, count),
                key=previous.index,
            )
            dependencies.extend(
                (prerequisite, dependent) for prerequisite in selected
            )
    return dependencies


def generate_workload(
    resource_count: int,
    profile: str,
    *,
    seed: int = 532,
) -> SyntheticWorkload:
    """Generate one deterministic, generic, acyclic workload."""
    if not isinstance(resource_count, int) or isinstance(resource_count, bool):
        raise TypeError("resource_count must be an integer")
    if resource_count < 1:
        raise ValueError("resource_count must be at least 1")
    if profile not in WORKLOAD_PROFILES:
        raise ValueError(f"unknown workload profile: {profile}")

    rng = random.Random(seed)
    resources = tuple(_resource_row(index, rng) for index in range(resource_count))
    service_ids = [row["service_id"] for row in resources]

    if profile == "chain":
        dependencies = list(zip(service_ids, service_ids[1:]))
    elif profile == "layered_sparse":
        dependencies = _layered_dependencies(service_ids, rng, 3)
    elif profile == "layered_dense":
        dependencies = _layered_dependencies(service_ids, rng, 8)
    else:
        dependencies = []

    return SyntheticWorkload(
        profile=profile,
        seed=seed,
        resources=resources,
        dependencies=tuple(dependencies),
    )


def write_workload_csv(
    workload: SyntheticWorkload,
    resources_path: str | Path,
    dependencies_path: str | Path,
) -> tuple[Path, Path]:
    """Write a workload using the Phase 2-compatible CSV schemas."""
    resource_file = Path(resources_path)
    dependency_file = Path(dependencies_path)
    resource_file.parent.mkdir(parents=True, exist_ok=True)
    dependency_file.parent.mkdir(parents=True, exist_ok=True)

    with resource_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESOURCE_FIELDNAMES)
        writer.writeheader()
        writer.writerows(workload.resources)
    with dependency_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEPENDENCY_FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            {
                "prerequisite": prerequisite,
                "dependent": dependent,
            }
            for prerequisite, dependent in workload.dependencies
        )
    return resource_file, dependency_file

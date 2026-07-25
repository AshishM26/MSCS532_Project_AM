"""Strict CSV loading for the Phase 2 cloud-resource proof of concept."""

import csv
from pathlib import Path

from .deployment_readiness_engine import DeploymentReadinessEngine


RESOURCE_COLUMNS = frozenset(
    {
        "service_id",
        "resource_type",
        "environment",
        "version",
        "status",
        "owner",
        "priority",
        "region",
        "criticality",
    }
)
DEPENDENCY_COLUMNS = frozenset({"prerequisite", "dependent"})


def _require_columns(
    fieldnames: list[str] | None,
    required: frozenset[str],
    dataset_name: str,
) -> None:
    """Raise ValueError when a CSV header omits required columns."""
    available = set(fieldnames or [])
    missing = required - available
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{dataset_name} CSV missing required columns: {names}")


def _clean_required_row(
    row: dict[str | None, str | None],
    required: frozenset[str],
    dataset_name: str,
    row_number: int,
) -> dict[str, str]:
    """Strip values and reject blank required fields or extra unnamed values."""
    if None in row:
        raise ValueError(
            f"{dataset_name} CSV row {row_number} has extra unnamed values"
        )

    cleaned = {
        key: (value.strip() if value is not None else "")
        for key, value in row.items()
        if key is not None
    }
    blank = sorted(column for column in required if not cleaned.get(column))
    if blank:
        names = ", ".join(blank)
        raise ValueError(
            f"{dataset_name} CSV row {row_number} has blank fields: {names}"
        )
    return cleaned


def load_engine_from_csv(
    resources_path: str | Path,
    dependencies_path: str | Path,
) -> DeploymentReadinessEngine:
    """Load and validate a complete engine from two CSV files.

    A new internal engine is returned only after both datasets pass validation,
    so callers never receive a partially initialized result.
    """
    engine = DeploymentReadinessEngine()
    resource_file = Path(resources_path)
    dependency_file = Path(dependencies_path)
    resource_count = 0

    with resource_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, RESOURCE_COLUMNS, "resource")
        for row_number, row in enumerate(reader, start=2):
            cleaned = _clean_required_row(
                row,
                RESOURCE_COLUMNS,
                "resource",
                row_number,
            )
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

            service_id = cleaned.pop("service_id")
            metadata: dict[str, object] = dict(cleaned)
            metadata["priority"] = priority
            engine.register_resource(service_id, metadata)
            resource_count += 1

    if resource_count == 0:
        raise ValueError("resource CSV must contain at least one data row")

    with dependency_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(reader.fieldnames, DEPENDENCY_COLUMNS, "dependency")
        for row_number, row in enumerate(reader, start=2):
            cleaned = _clean_required_row(
                row,
                DEPENDENCY_COLUMNS,
                "dependency",
                row_number,
            )
            engine.add_dependency(
                cleaned["prerequisite"],
                cleaned["dependent"],
            )

    return engine

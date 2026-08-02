"""Tests for the validate-first Phase 3 CSV loader."""

import csv
from pathlib import Path
import tempfile
import unittest

from src.cloud_resource_loader import DEPENDENCY_COLUMNS, RESOURCE_COLUMNS
from src.deployment_graph import (
    DependencyCycleError,
    DuplicateDependencyError,
)
from src.bulk_cloud_resource_loader import (
    load_optimized_engine_from_csv,
)


VALID_ROWS = [
    {
        "service_id": "database",
        "resource_type": "database",
        "environment": "test",
        "version": "1.0",
        "status": "pending",
        "owner": "data",
        "priority": "2",
        "region": "generic-region-1",
        "criticality": "high",
    },
    {
        "service_id": "api",
        "resource_type": "application",
        "environment": "test",
        "version": "1.0",
        "status": "pending",
        "owner": "application",
        "priority": "1",
        "region": "generic-region-1",
        "criticality": "critical",
    },
]


class OptimizedCloudResourceLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temporary_directory.name)
        self.resources_path = directory / "resources.csv"
        self.dependencies_path = directory / "dependencies.csv"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def write_csv(
        path: Path,
        fieldnames: list[str],
        rows: list[dict[str, str]],
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def write_valid(
        self,
        resources: list[dict[str, str]] | None = None,
        dependencies: list[dict[str, str]] | None = None,
    ) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_ROWS if resources is None else resources,
        )
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            dependencies
            if dependencies is not None
            else [{"prerequisite": "database", "dependent": "api"}],
        )

    def test_valid_files_build_indexed_engine(self) -> None:
        self.write_valid()
        engine = load_optimized_engine_from_csv(
            self.resources_path, self.dependencies_path
        )
        self.assertEqual(engine.get_eligible_resources(), ["database"])
        self.assertEqual(engine.select_next_resource(), ("database", 2))
        self.assertTrue(engine.validate_internal_state())
        self.assertEqual(engine.metrics.full_cycle_validations, 1)

    def test_insertion_and_dependency_order_are_preserved(self) -> None:
        rows = VALID_ROWS + [dict(VALID_ROWS[1], service_id="worker")]
        edges = [
            {"prerequisite": "database", "dependent": "worker"},
            {"prerequisite": "api", "dependent": "worker"},
        ]
        self.write_valid(rows, edges)
        engine = load_optimized_engine_from_csv(
            self.resources_path, self.dependencies_path
        )
        self.assertEqual(
            engine.graph.get_prerequisites("worker"),
            ["database", "api"],
        )

    def test_empty_resource_file_is_rejected(self) -> None:
        self.write_valid([], [])
        with self.assertRaisesRegex(ValueError, "at least one"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_missing_columns_are_rejected(self) -> None:
        columns = sorted(RESOURCE_COLUMNS - {"owner"})
        row = {key: value for key, value in VALID_ROWS[0].items()
               if key != "owner"}
        self.write_csv(self.resources_path, columns, [row])
        self.write_csv(self.dependencies_path, ["prerequisite"], [])
        with self.assertRaisesRegex(ValueError, "owner"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_missing_dependency_column_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path, sorted(RESOURCE_COLUMNS), VALID_ROWS
        )
        self.write_csv(self.dependencies_path, ["prerequisite"], [])
        with self.assertRaisesRegex(ValueError, "dependent"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_blank_required_field_is_rejected(self) -> None:
        self.write_valid([dict(VALID_ROWS[0], service_id=" ")], [])
        with self.assertRaisesRegex(ValueError, "service_id"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_invalid_priority_text_and_range_are_rejected(self) -> None:
        for priority, message in (("urgent", "invalid"), ("5", "1 to 4")):
            with self.subTest(priority=priority):
                self.write_valid([dict(VALID_ROWS[0], priority=priority)], [])
                with self.assertRaisesRegex(ValueError, message):
                    load_optimized_engine_from_csv(
                        self.resources_path, self.dependencies_path
                    )

    def test_nonpending_status_is_rejected(self) -> None:
        self.write_valid([dict(VALID_ROWS[0], status="deployed")], [])
        with self.assertRaisesRegex(ValueError, "pending"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_duplicate_service_is_rejected(self) -> None:
        self.write_valid([VALID_ROWS[0], dict(VALID_ROWS[0])], [])
        with self.assertRaisesRegex(ValueError, "already registered"):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_unknown_dependency_endpoints_are_rejected(self) -> None:
        for edge in (
            {"prerequisite": "missing", "dependent": "api"},
            {"prerequisite": "database", "dependent": "missing"},
        ):
            with self.subTest(edge=edge):
                self.write_valid(dependencies=[edge])
                with self.assertRaises(KeyError):
                    load_optimized_engine_from_csv(
                        self.resources_path, self.dependencies_path
                    )

    def test_duplicate_dependency_is_rejected(self) -> None:
        edge = {"prerequisite": "database", "dependent": "api"}
        self.write_valid(dependencies=[edge, edge])
        with self.assertRaises(DuplicateDependencyError):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )

    def test_cycle_is_rejected_after_bulk_edge_insertion(self) -> None:
        self.write_valid(
            dependencies=[
                {"prerequisite": "database", "dependent": "api"},
                {"prerequisite": "api", "dependent": "database"},
            ]
        )
        with self.assertRaises(DependencyCycleError):
            load_optimized_engine_from_csv(
                self.resources_path, self.dependencies_path
            )


if __name__ == "__main__":
    unittest.main()

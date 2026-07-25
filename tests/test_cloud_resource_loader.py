"""Tests for strict Phase 2 CSV loading."""

import csv
from pathlib import Path
import tempfile
import unittest

from src.cloud_resource_loader import (
    DEPENDENCY_COLUMNS,
    RESOURCE_COLUMNS,
    load_engine_from_csv,
)
from src.deployment_graph import (
    DependencyCycleError,
    DuplicateDependencyError,
)


VALID_RESOURCE_ROWS = [
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


class CloudResourceLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.resources_path = self.directory / "resources.csv"
        self.dependencies_path = self.directory / "dependencies.csv"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_csv(
        self,
        path: Path,
        fieldnames: list[str],
        rows: list[dict[str, str]],
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def write_valid_files(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            [{"prerequisite": "database", "dependent": "api"}],
        )

    def test_valid_files_build_complete_engine(self) -> None:
        self.write_valid_files()
        engine = load_engine_from_csv(
            self.resources_path,
            self.dependencies_path,
        )

        self.assertEqual(engine.summary()["resource_count"], 2)
        self.assertEqual(engine.summary()["dependency_count"], 1)
        self.assertEqual(engine.graph.get_prerequisites("api"), ["database"])
        self.assertEqual(engine.get_resource("api")["resource_type"], "application")

    def test_missing_resource_column_is_rejected(self) -> None:
        columns = sorted(RESOURCE_COLUMNS - {"owner"})
        rows = [{key: value for key, value in VALID_RESOURCE_ROWS[0].items()
                 if key != "owner"}]
        self.write_csv(self.resources_path, columns, rows)
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "owner"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_missing_dependency_column_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        self.write_csv(self.dependencies_path, ["prerequisite"], [])

        with self.assertRaisesRegex(ValueError, "dependent"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_blank_service_id_is_rejected(self) -> None:
        row = dict(VALID_RESOURCE_ROWS[0], service_id=" ")
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), [row])
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "service_id"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_invalid_priority_text_is_rejected(self) -> None:
        row = dict(VALID_RESOURCE_ROWS[0], priority="urgent")
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), [row])
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "invalid priority"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_out_of_range_priority_is_rejected(self) -> None:
        row = dict(VALID_RESOURCE_ROWS[0], priority="5")
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), [row])
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "1 to 4"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_duplicate_service_id_is_rejected(self) -> None:
        rows = [VALID_RESOURCE_ROWS[0], dict(VALID_RESOURCE_ROWS[0])]
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), rows)
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "already registered"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_nonpending_initial_status_is_rejected(self) -> None:
        row = dict(VALID_RESOURCE_ROWS[0], status="deployed")
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), [row])
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "pending"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_unknown_prerequisite_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            [{"prerequisite": "missing", "dependent": "api"}],
        )

        with self.assertRaises(KeyError):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_unknown_dependent_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            [{"prerequisite": "database", "dependent": "missing"}],
        )

        with self.assertRaises(KeyError):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_duplicate_dependency_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        edge = {"prerequisite": "database", "dependent": "api"}
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            [edge, edge],
        )

        with self.assertRaises(DuplicateDependencyError):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_cyclic_dependency_dataset_is_rejected(self) -> None:
        self.write_csv(
            self.resources_path,
            sorted(RESOURCE_COLUMNS),
            VALID_RESOURCE_ROWS,
        )
        self.write_csv(
            self.dependencies_path,
            sorted(DEPENDENCY_COLUMNS),
            [
                {"prerequisite": "database", "dependent": "api"},
                {"prerequisite": "api", "dependent": "database"},
            ],
        )

        with self.assertRaises(DependencyCycleError):
            load_engine_from_csv(self.resources_path, self.dependencies_path)

    def test_empty_resource_file_is_rejected(self) -> None:
        self.write_csv(self.resources_path, sorted(RESOURCE_COLUMNS), [])
        self.write_csv(self.dependencies_path, sorted(DEPENDENCY_COLUMNS), [])

        with self.assertRaisesRegex(ValueError, "at least one"):
            load_engine_from_csv(self.resources_path, self.dependencies_path)


if __name__ == "__main__":
    unittest.main()

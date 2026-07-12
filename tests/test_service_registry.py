"""Tests for ServiceRegistry."""

import unittest

from src.service_registry import ServiceRegistry


def metadata(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "environment": "test",
        "version": "1.0.0",
        "status": "pending",
        "owner": "platform",
        "priority": 2,
    }
    result.update(overrides)
    return result


class ServiceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ServiceRegistry()

    def test_registration_and_lookup_return_safe_copy(self) -> None:
        original = metadata(tags=["core"])
        self.registry.register_service("api", original)
        original["status"] = "changed outside"

        found = self.registry.get_service("api")
        self.assertIsNotNone(found)
        assert found is not None
        found["tags"].append("mutated")

        stored = self.registry.get_service("api")
        assert stored is not None
        self.assertEqual(stored["status"], "pending")
        self.assertEqual(stored["tags"], ["core"])

    def test_status_and_metadata_updates(self) -> None:
        self.registry.register_service("api", metadata())
        self.registry.update_status("api", "deployed")
        self.registry.update_metadata("api", {"version": "1.1.0", "priority": 1})

        found = self.registry.get_service("api")
        assert found is not None
        self.assertEqual(found["status"], "deployed")
        self.assertEqual(found["version"], "1.1.0")
        self.assertEqual(found["priority"], 1)

    def test_missing_service_behavior(self) -> None:
        self.assertIsNone(self.registry.get_service("missing"))
        self.assertFalse(self.registry.contains("missing"))
        self.assertFalse(self.registry.remove_service("missing"))
        with self.assertRaises(KeyError):
            self.registry.update_status("missing", "deployed")

    def test_required_fields_and_duplicates_are_rejected(self) -> None:
        incomplete = metadata()
        del incomplete["owner"]
        with self.assertRaises(ValueError):
            self.registry.register_service("api", incomplete)

        self.registry.register_service("api", metadata())
        with self.assertRaises(ValueError):
            self.registry.register_service("api", metadata())

    def test_remove_and_list_services(self) -> None:
        self.registry.register_service("api", metadata())
        self.assertEqual(len(self.registry.list_services()), 1)
        self.assertTrue(self.registry.remove_service("api"))
        self.assertFalse(self.registry.contains("api"))


if __name__ == "__main__":
    unittest.main()

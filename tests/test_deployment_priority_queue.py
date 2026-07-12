"""Tests for DeploymentPriorityQueue."""

import unittest

from src.deployment_priority_queue import DeploymentPriorityQueue


class DeploymentPriorityQueueTests(unittest.TestCase):
    def test_priority_ordering(self) -> None:
        queue = DeploymentPriorityQueue()
        queue.enqueue("low", 4)
        queue.enqueue("critical", 1)
        queue.enqueue("medium", 3)

        self.assertEqual(queue.peek(), ("critical", 1))
        self.assertEqual(queue.dequeue(), ("critical", 1))
        self.assertEqual(queue.dequeue(), ("medium", 3))
        self.assertEqual(queue.dequeue(), ("low", 4))

    def test_equal_priorities_are_fifo(self) -> None:
        queue = DeploymentPriorityQueue()
        queue.enqueue("first", 2)
        queue.enqueue("second", 2)

        self.assertEqual(queue.dequeue(), ("first", 2))
        self.assertEqual(queue.dequeue(), ("second", 2))

    def test_invalid_priority_is_rejected(self) -> None:
        queue = DeploymentPriorityQueue()
        for invalid in (0, 5, True):
            with self.subTest(priority=invalid):
                with self.assertRaises(ValueError):
                    queue.enqueue("service", invalid)

    def test_empty_queue_behavior_and_size(self) -> None:
        queue = DeploymentPriorityQueue()
        self.assertTrue(queue.is_empty())
        self.assertEqual(queue.size(), 0)
        self.assertIsNone(queue.peek())
        self.assertIsNone(queue.dequeue())

        queue.enqueue("service", 2)
        self.assertFalse(queue.is_empty())
        self.assertEqual(queue.size(), 1)


if __name__ == "__main__":
    unittest.main()

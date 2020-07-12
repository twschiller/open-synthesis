from django.test import TestCase

from openach import tasks
from openach.util import first_occurrences


class UtilMethodTests(TestCase):
    def test_first_occurrences_empty(self):
        """Test that first_instances() returns an empty list when an empty list is provided."""
        self.assertEqual(first_occurrences([]), [])

    def test_first_occurrences(self):
        """Test that first_instances() only preserves the first occurrence in the list."""
        self.assertEqual(first_occurrences(["a", "a"]), ["a"])
        self.assertEqual(first_occurrences(["a", "b", "a"]), ["a", "b"])


class CeleryTestCase(TestCase):
    def test_celery_example(self):
        """Test that the ``example_task`` task runs with no errors, and returns the correct result."""
        result = tasks.example_task.delay(8, 8)

        self.assertEqual(result.get(), 16)
        self.assertTrue(result.successful())

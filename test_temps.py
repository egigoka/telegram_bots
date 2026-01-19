import datetime
import unittest

from temps import should_skip_service


class TestShouldSkipService(unittest.TestCase):
    """Test cases for the should_skip_service function."""

    def test_active_service_should_be_skipped(self):
        """An active service should always be skipped (it's running fine)."""
        result = should_skip_service(
            active="active",
            triggered_by=None,
            since_delta=None,
            run_every=300
        )
        self.assertTrue(result)

    def test_active_service_with_trigger_should_be_skipped(self):
        """An active service with a trigger should be skipped."""
        result = should_skip_service(
            active="active",
            triggered_by="some.timer",
            since_delta=datetime.timedelta(seconds=100),
            run_every=300
        )
        self.assertTrue(result)

    def test_inactive_with_trigger_should_be_skipped(self):
        """An inactive service with a trigger should be skipped (waiting for trigger)."""
        result = should_skip_service(
            active="inactive",
            triggered_by="some.timer",
            since_delta=datetime.timedelta(seconds=1000),
            run_every=300
        )
        self.assertTrue(result)

    def test_inactive_without_trigger_should_not_be_skipped(self):
        """An inactive service without a trigger should be reported."""
        result = should_skip_service(
            active="inactive",
            triggered_by=None,
            since_delta=datetime.timedelta(seconds=1000),
            run_every=300
        )
        self.assertFalse(result)

    def test_activating_within_run_every_should_be_skipped(self):
        """A service that's been activating for less than run_every should be skipped."""
        result = should_skip_service(
            active="activating",
            triggered_by=None,
            since_delta=datetime.timedelta(seconds=100),
            run_every=300
        )
        self.assertTrue(result)

    def test_activating_exactly_at_run_every_should_be_skipped(self):
        """A service that's been activating for exactly run_every seconds should be skipped."""
        result = should_skip_service(
            active="activating",
            triggered_by=None,
            since_delta=datetime.timedelta(seconds=300),
            run_every=300
        )
        self.assertTrue(result)

    def test_activating_beyond_run_every_should_not_be_skipped(self):
        """A service that's been activating for more than run_every should be reported."""
        result = should_skip_service(
            active="activating",
            triggered_by=None,
            since_delta=datetime.timedelta(seconds=301),
            run_every=300
        )
        self.assertFalse(result)

    def test_activating_with_no_since_delta_should_not_be_skipped(self):
        """An activating service with no since_delta (parse error) should be reported."""
        result = should_skip_service(
            active="activating",
            triggered_by=None,
            since_delta=None,
            run_every=300
        )
        self.assertFalse(result)

    def test_failed_service_should_not_be_skipped(self):
        """A failed service should always be reported."""
        result = should_skip_service(
            active="failed",
            triggered_by=None,
            since_delta=datetime.timedelta(seconds=100),
            run_every=300
        )
        self.assertFalse(result)

    def test_failed_service_even_with_trigger_should_not_be_skipped(self):
        """A failed service should be reported even if it has a trigger."""
        result = should_skip_service(
            active="failed",
            triggered_by="some.timer",
            since_delta=datetime.timedelta(seconds=100),
            run_every=300
        )
        self.assertFalse(result)

    def test_activating_long_time_with_trigger_should_not_be_skipped(self):
        """An activating service that's been stuck for a long time should be reported."""
        result = should_skip_service(
            active="activating",
            triggered_by="some.timer",
            since_delta=datetime.timedelta(seconds=600),
            run_every=300
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

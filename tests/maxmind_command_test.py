"""Tests for maxmind_command.py"""

import unittest

import maxmind_command


class MockCommand:
    """Mock command object that provides ip_field attribute."""

    def __init__(self, ip_field: str = "ip") -> None:
        self.ip_field = ip_field


class TestMaxmindCommand(unittest.TestCase):
    def test_valid_ip_google_dns(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "8.8.8.8"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "US")

    def test_valid_ip_opendns(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "208.67.222.222"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "US")

    def test_valid_ip_canadian(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "99.199.114.251"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "CA")

    def test_invalid_ip_format(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "not.an.ip"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_invalid_ip_out_of_range(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "999.999.999.999"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_invalid_ip_empty_string(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": ""}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_private_ip_192_168(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "192.168.1.1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_private_ip_10_x(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "10.0.0.1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_private_ip_localhost(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "127.0.0.1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_missing_ip_field(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"other_field": "value"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_multiple_events(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [
            {"ip": "8.8.8.8"},
            {"ip": "invalid"},
            {"other": "field"},
        ]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 3)
        self.assertIn("country_code", results[0])
        self.assertNotIn("country_code", results[1])
        self.assertNotIn("country_code", results[2])

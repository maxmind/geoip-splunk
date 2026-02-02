"""Tests for maxmind_command.py

Uses test data from the MaxMind-DB submodule. Test IPs are from
GeoIP2-Country-Test.mmdb which contains known test data.
"""

import unittest

import maxmind_command


class MockCommand:
    """Mock command object that provides ip_field attribute."""

    def __init__(self, ip_field: str = "ip") -> None:
        self.ip_field = ip_field


class TestMaxmindCommand(unittest.TestCase):
    # Test IPs from GeoIP2-Country-Test.mmdb source data:
    # - 214.78.120.0/22 -> US
    # - 2001:218::/32 -> JP
    # - 2001:220::1/128 -> KR

    def test_valid_ipv4_us(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "214.78.120.1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "US")

    def test_valid_ipv6_jp(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "2001:218::1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "JP")

    def test_valid_ipv6_kr(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "2001:220::1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "KR")

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

    def test_ip_not_in_database(self) -> None:
        """Test an IP that's valid but not in the test database."""
        command = MockCommand(ip_field="ip")
        events = [{"ip": "8.8.8.8"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertNotIn("country_code", results[0])

    def test_private_ip_not_in_database(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [{"ip": "192.168.1.1"}]
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
            {"ip": "214.78.120.1"},  # Valid US IP
            {"ip": "invalid"},  # Invalid IP
            {"other": "field"},  # Missing IP field
        ]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["country_code"], "US")
        self.assertNotIn("country_code", results[1])
        self.assertNotIn("country_code", results[2])

    def test_custom_ip_field(self) -> None:
        command = MockCommand(ip_field="src_ip")
        events = [{"src_ip": "214.78.120.1"}]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "US")

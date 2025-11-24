#!/usr/bin/env python
"""Test script for maxmind_command.py

Tests the GeoIP lookup functionality with various IP addresses.
"""

import sys
import os

# Add the package bin and lib directories to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
bin_dir = os.path.join(script_dir, 'demo_addon_for_splunk', 'package', 'bin')
lib_dir = os.path.join(script_dir, 'demo_addon_for_splunk', 'package', 'lib')
sys.path.insert(0, bin_dir)
sys.path.insert(0, lib_dir)

import maxmind_command


class MockCommand:
    """Mock command object that provides ip_field attribute."""
    def __init__(self, ip_field='ip'):
        self.ip_field = ip_field


def test_valid_ips():
    """Test with valid IP addresses that should have country codes."""
    print("Testing valid IP addresses...")

    test_cases = [
        {'ip': '8.8.8.8', 'expected': 'US', 'description': 'Google DNS'},
        {'ip': '208.67.222.222', 'expected': 'US', 'description': 'OpenDNS'},
        {'ip': '99.199.114.251', 'expected': 'CA', 'description': 'Canadian IP'},
    ]

    command = MockCommand(ip_field='ip')

    for test in test_cases:
        events = [{'ip': test['ip']}]
        results = list(maxmind_command.stream(command, iter(events)))

        if len(results) == 1:
            result = results[0]
            if 'country_code' in result:
                actual = result['country_code']
                status = '✓' if actual == test['expected'] else '✗'
                print(f"  {status} {test['description']} ({test['ip']}): "
                      f"expected {test['expected']}, got {actual}")
            else:
                print(f"  ✗ {test['description']} ({test['ip']}): "
                      f"no country_code in result")
        else:
            print(f"  ✗ {test['description']} ({test['ip']}): "
                  f"unexpected number of results: {len(results)}")


def test_invalid_ips():
    """Test with invalid IP addresses."""
    print("\nTesting invalid IP addresses...")

    test_cases = [
        {'ip': 'not.an.ip', 'description': 'Invalid format'},
        {'ip': '999.999.999.999', 'description': 'Out of range'},
        {'ip': '', 'description': 'Empty string'},
    ]

    command = MockCommand(ip_field='ip')

    for test in test_cases:
        events = [{'ip': test['ip']}]
        results = list(maxmind_command.stream(command, iter(events)))

        if len(results) == 1:
            result = results[0]
            if 'country_code' not in result:
                print(f"  ✓ {test['description']} ({test['ip']}): "
                      f"correctly skipped")
            else:
                print(f"  ✗ {test['description']} ({test['ip']}): "
                      f"unexpected country_code: {result['country_code']}")
        else:
            print(f"  ✗ {test['description']} ({test['ip']}): "
                  f"unexpected number of results: {len(results)}")


def test_private_ips():
    """Test with private IP addresses not in database."""
    print("\nTesting private IP addresses...")

    test_cases = [
        {'ip': '192.168.1.1', 'description': 'Private IPv4'},
        {'ip': '10.0.0.1', 'description': 'Private IPv4 (10.x)'},
        {'ip': '127.0.0.1', 'description': 'Localhost'},
    ]

    command = MockCommand(ip_field='ip')

    for test in test_cases:
        events = [{'ip': test['ip']}]
        results = list(maxmind_command.stream(command, iter(events)))

        if len(results) == 1:
            result = results[0]
            if 'country_code' not in result:
                print(f"  ✓ {test['description']} ({test['ip']}): "
                      f"correctly not found in database")
            else:
                print(f"  ✗ {test['description']} ({test['ip']}): "
                      f"unexpected country_code: {result['country_code']}")
        else:
            print(f"  ✗ {test['description']} ({test['ip']}): "
                  f"unexpected number of results: {len(results)}")


def test_missing_field():
    """Test with events that don't have the IP field."""
    print("\nTesting missing IP field...")

    command = MockCommand(ip_field='ip')
    events = [{'other_field': 'value'}]
    results = list(maxmind_command.stream(command, iter(events)))

    if len(results) == 1:
        result = results[0]
        if 'country_code' not in result:
            print(f"  ✓ Event without IP field: correctly skipped")
        else:
            print(f"  ✗ Event without IP field: "
                  f"unexpected country_code: {result['country_code']}")
    else:
        print(f"  ✗ Event without IP field: "
              f"unexpected number of results: {len(results)}")


def test_multiple_events():
    """Test processing multiple events."""
    print("\nTesting multiple events...")

    command = MockCommand(ip_field='ip')
    events = [
        {'ip': '8.8.8.8'},
        {'ip': 'invalid'},
        {'other': 'field'},
    ]

    results = list(maxmind_command.stream(command, iter(events)))

    if len(results) == 3:
        print(f"  ✓ Processed all {len(results)} events")

        # Check first event (should have country code)
        if 'country_code' in results[0]:
            print(f"    ✓ Event 1 has country_code: {results[0]['country_code']}")
        else:
            print(f"    ✗ Event 1 missing country_code")

        # Check second event (invalid IP, should not have country code)
        if 'country_code' not in results[1]:
            print(f"    ✓ Event 2 (invalid IP) correctly has no country_code")
        else:
            print(f"    ✗ Event 2 unexpectedly has country_code")

        # Check third event (no IP field, should not have country code)
        if 'country_code' not in results[2]:
            print(f"    ✓ Event 3 (no IP field) correctly has no country_code")
        else:
            print(f"    ✗ Event 3 unexpectedly has country_code")
    else:
        print(f"  ✗ Expected 3 results, got {len(results)}")


if __name__ == '__main__':
    print("=" * 60)
    print("MaxMind Command Test Suite")
    print("=" * 60)

    try:
        test_valid_ips()
        test_invalid_ips()
        test_private_ips()
        test_missing_field()
        test_multiple_events()

        print("\n" + "=" * 60)
        print("Test suite completed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

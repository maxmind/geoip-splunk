"""Tests for maxmind_command.py.

Uses test data from the MaxMind-DB submodule. Test IPs are from
GeoIP2-Country-Test.mmdb which contains known test data.
"""

from typing import TYPE_CHECKING

import maxmind_command
import pytest

if TYPE_CHECKING:
    from maxmind_command import Metadata, SearchInfo


class MockSearchInfo:
    """Mock Splunk search info."""

    app: str = "demo_addon_for_splunk"
    session_key: str = "test_session_key"


class MockMetadata:
    """Mock Splunk command metadata."""

    searchinfo: "SearchInfo"

    def __init__(self) -> None:
        self.searchinfo = MockSearchInfo()


class MockCommand:
    """Mock command object that provides field, prefix, and databases attributes."""

    metadata: "Metadata"

    def __init__(
        self,
        field: str = "ip",
        prefix: str = "",
        databases: str = "GeoIP2-Country-Test",
    ) -> None:
        self.field = field
        self.prefix = prefix
        self.databases = databases
        self.metadata = MockMetadata()


# Expected results from GeoIP2-Country-Test.mmdb for test IPs.
# These include the original event fields plus all MaxMind fields.
EXPECTED_US = {
    "ip": "214.78.120.1",
    "continent.code": "NA",
    "continent.geoname_id": 6255149,
    "continent.names.de": "Nordamerika",
    "continent.names.en": "North America",
    "continent.names.es": "Norteamérica",
    "continent.names.fr": "Amérique du Nord",
    "continent.names.ja": "北アメリカ",
    "continent.names.pt-BR": "América do Norte",
    "continent.names.ru": "Северная Америка",
    "continent.names.zh-CN": "北美洲",
    "country.geoname_id": 6252001,
    "country.iso_code": "US",
    "country.names.de": "Vereinigte Staaten",
    "country.names.en": "United States",
    "country.names.es": "Estados Unidos",
    "country.names.fr": "États Unis",
    "country.names.ja": "アメリカ",
    "country.names.pt-BR": "EUA",
    "country.names.ru": "США",
    "country.names.zh-CN": "美国",
    "registered_country.geoname_id": 6252001,
    "registered_country.iso_code": "US",
    "registered_country.names.de": "Vereinigte Staaten",
    "registered_country.names.en": "United States",
    "registered_country.names.es": "Estados Unidos",
    "registered_country.names.fr": "États Unis",
    "registered_country.names.ja": "アメリカ",
    "registered_country.names.pt-BR": "EUA",
    "registered_country.names.ru": "США",
    "registered_country.names.zh-CN": "美国",
    "network": "214.78.120.0/22",
}

EXPECTED_JP = {
    "ip": "2001:218::1",
    "continent.code": "AS",
    "continent.geoname_id": 6255147,
    "continent.names.de": "Asien",
    "continent.names.en": "Asia",
    "continent.names.es": "Asia",
    "continent.names.fr": "Asie",
    "continent.names.ja": "アジア",
    "continent.names.pt-BR": "Ásia",
    "continent.names.ru": "Азия",
    "continent.names.zh-CN": "亚洲",
    "country.geoname_id": 1861060,
    "country.iso_code": "JP",
    "country.names.de": "Japan",
    "country.names.en": "Japan",
    "country.names.es": "Japón",
    "country.names.fr": "Japon",
    "country.names.ja": "日本",
    "country.names.pt-BR": "Japão",
    "country.names.ru": "Япония",
    "country.names.zh-CN": "日本",
    "registered_country.geoname_id": 1861060,
    "registered_country.iso_code": "JP",
    "registered_country.names.de": "Japan",
    "registered_country.names.en": "Japan",
    "registered_country.names.es": "Japón",
    "registered_country.names.fr": "Japon",
    "registered_country.names.ja": "日本",
    "registered_country.names.pt-BR": "Japão",
    "registered_country.names.ru": "Япония",
    "registered_country.names.zh-CN": "日本",
    "network": "2001:218::/32",
}

EXPECTED_KR = {
    "ip": "2001:220::1",
    "continent.code": "AS",
    "continent.geoname_id": 6255147,
    "continent.names.de": "Asien",
    "continent.names.en": "Asia",
    "continent.names.es": "Asia",
    "continent.names.fr": "Asie",
    "continent.names.ja": "アジア",
    "continent.names.pt-BR": "Ásia",
    "continent.names.ru": "Азия",
    "continent.names.zh-CN": "亚洲",
    "country.geoname_id": 1835841,
    "country.iso_code": "KR",
    "country.names.de": "Republik Korea",
    "country.names.en": "South Korea",
    "country.names.es": "Corea, República de",
    "country.names.fr": "Corée du Sud",
    "country.names.ja": "大韓民国",
    "country.names.pt-BR": "Coréia, República da",
    "country.names.ru": "Южная Корея",
    "country.names.zh-CN": "韩国",
    "registered_country.geoname_id": 1835841,
    "registered_country.iso_code": "KR",
    "registered_country.names.de": "Republik Korea",
    "registered_country.names.en": "South Korea",
    "registered_country.names.es": "Corea, República de",
    "registered_country.names.fr": "Corée du Sud",
    "registered_country.names.ja": "大韓民国",
    "registered_country.names.pt-BR": "Coréia, República da",
    "registered_country.names.ru": "Южная Корея",
    "registered_country.names.zh-CN": "韩国",
    "network": "2001:220::1/128",
}


def test_valid_ipv4_us() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

    assert results == [EXPECTED_US]


def test_valid_ipv6_jp() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "2001:218::1"}])))

    assert results == [EXPECTED_JP]


def test_valid_ipv6_kr() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "2001:220::1"}])))

    assert results == [EXPECTED_KR]


def test_invalid_ip_format() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "not.an.ip"}])))

    assert results == [{"ip": "not.an.ip"}]


def test_invalid_ip_out_of_range() -> None:
    command = MockCommand(field="ip")
    events = iter([{"ip": "999.999.999.999"}])
    results = list(maxmind_command.stream(command, events))

    assert results == [{"ip": "999.999.999.999"}]


def test_invalid_ip_empty_string() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": ""}])))

    assert results == [{"ip": ""}]


def test_ip_not_in_database() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "8.8.8.8"}])))

    assert results == [{"ip": "8.8.8.8"}]


def test_private_ip_not_in_database() -> None:
    command = MockCommand(field="ip")
    results = list(maxmind_command.stream(command, iter([{"ip": "192.168.1.1"}])))

    assert results == [{"ip": "192.168.1.1"}]


def test_missing_field() -> None:
    command = MockCommand(field="ip")
    events = iter([{"other_field": "value"}])
    results = list(maxmind_command.stream(command, events))

    assert results == [{"other_field": "value"}]


def test_multiple_events() -> None:
    command = MockCommand(field="ip")
    events = [
        {"ip": "214.78.120.1"},
        {"ip": "invalid"},
        {"other": "field"},
    ]
    results = list(maxmind_command.stream(command, iter(events)))

    assert results == [EXPECTED_US, {"ip": "invalid"}, {"other": "field"}]


def test_default_field() -> None:
    command = MockCommand()
    results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

    assert results == [EXPECTED_US]


def test_custom_field() -> None:
    command = MockCommand(field="src_ip")
    events = iter([{"src_ip": "214.78.120.1"}])
    results = list(maxmind_command.stream(command, events))

    expected = {k: v for k, v in EXPECTED_US.items() if k != "ip"}
    expected["src_ip"] = "214.78.120.1"
    assert results == [expected]


def test_prefix() -> None:
    command = MockCommand(prefix="maxmind_")
    results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

    expected: dict[str, object] = {"ip": "214.78.120.1"}
    for key, value in EXPECTED_US.items():
        if key != "ip":
            expected[f"maxmind_{key}"] = value
    assert results == [expected]


def test_flatten_record_flat_dict() -> None:
    record = {"a": 1, "b": 2}
    result = dict(maxmind_command._flatten_record(record))

    assert result == {"a": 1, "b": 2}


def test_flatten_record_nested_dict() -> None:
    record = {"country": {"iso_code": "US", "names": {"en": "United States"}}}
    result = dict(maxmind_command._flatten_record(record))

    assert result == {"country.iso_code": "US", "country.names.en": "United States"}


def test_flatten_record_empty_dict() -> None:
    result = dict(maxmind_command._flatten_record({}))

    assert result == {}


def test_multiple_databases() -> None:
    """Test that fields from multiple databases are merged."""
    # 89.160.20.112 is in both Country-Test and City-Test
    # City has additional fields like city.names.en
    command = MockCommand(databases="GeoIP2-Country-Test,GeoIP2-City-Test")
    results = list(maxmind_command.stream(command, iter([{"ip": "89.160.20.112"}])))

    assert len(results) == 1
    result = results[0]
    # Should have country fields from both (City overwrites Country)
    assert result["country.iso_code"] == "SE"
    # Should have city fields from City-Test (Country doesn't have these)
    assert result["city.names.en"] == "Linköping"


def test_multiple_databases_smallest_network() -> None:
    """Test that the most specific (smallest) network is returned."""
    # 89.160.20.112 is in:
    # - GeoIP2-Country-Test with /28
    # - GeoIP2-ISP-Test with /29 (more specific)
    # Should return /29 (the most specific)
    command = MockCommand(databases="GeoIP2-Country-Test,GeoIP2-ISP-Test")
    results = list(maxmind_command.stream(command, iter([{"ip": "89.160.20.112"}])))

    assert len(results) == 1
    assert results[0]["network"] == "89.160.20.112/29"


def test_multiple_databases_last_wins() -> None:
    """Test that later databases overwrite earlier ones for conflicting fields."""
    # Use City and Country which both have country.iso_code
    # The second database in the list should win
    command = MockCommand(databases="GeoIP2-City-Test,GeoIP2-Country-Test")
    results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

    assert len(results) == 1
    # Both have this field, Country-Test (second) should win
    assert results[0]["country.iso_code"] == "US"


def test_database_not_found() -> None:
    """Test that a missing database raises an error."""
    command = MockCommand(databases="NonExistent-Database")

    with pytest.raises(FileNotFoundError, match="Database not found"):
        list(maxmind_command.stream(command, iter([{"ip": "1.2.3.4"}])))


def test_invalid_database_name() -> None:
    """Test that invalid database names are rejected."""
    command = MockCommand(databases="../etc/passwd")

    with pytest.raises(ValueError, match="Invalid database name"):
        list(maxmind_command.stream(command, iter([{"ip": "1.2.3.4"}])))


def test_ip_in_one_database_only() -> None:
    """Test lookup when IP is only in one of multiple databases."""
    # 214.78.120.1 is in Country but not in Anonymous-IP
    command = MockCommand(databases="GeoIP2-Country-Test,GeoIP2-Anonymous-IP-Test")
    results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

    assert len(results) == 1
    result = results[0]
    # Should have country fields
    assert result["country.iso_code"] == "US"
    # Should not have anonymous fields (not in that database)
    assert "is_anonymous" not in result


def test_flatten_record_list_of_dicts() -> None:
    """Test that lists of dicts are flattened with numeric indices."""
    record = {"subdivisions": [{"iso_code": "CA", "names": {"en": "California"}}]}
    result = dict(maxmind_command._flatten_record(record))

    assert result == {
        "subdivisions.0.iso_code": "CA",
        "subdivisions.0.names.en": "California",
        "subdivisions.-1.iso_code": "CA",
        "subdivisions.-1.names.en": "California",
    }


def test_flatten_record_multiple_list_items() -> None:
    """Test that multiple list items get sequential indices."""
    record = {"subdivisions": [{"iso_code": "CA"}, {"iso_code": "SF"}]}
    result = dict(maxmind_command._flatten_record(record))

    assert result == {
        "subdivisions.0.iso_code": "CA",
        "subdivisions.1.iso_code": "SF",
        "subdivisions.-1.iso_code": "SF",
    }


def test_flatten_record_simple_list() -> None:
    """Test that simple lists are flattened with indices."""
    record = {"tags": ["a", "b", "c"]}
    result = dict(maxmind_command._flatten_record(record))

    assert result == {"tags.0": "a", "tags.1": "b", "tags.2": "c"}


def test_subdivisions_flattened() -> None:
    """Test that subdivisions from City database are properly flattened."""
    # 89.160.20.112 has subdivisions in GeoIP2-City-Test
    command = MockCommand(databases="GeoIP2-City-Test")
    results = list(maxmind_command.stream(command, iter([{"ip": "89.160.20.112"}])))

    assert len(results) == 1
    result = results[0]
    # Subdivisions should be flattened with numeric index
    assert result["subdivisions.0.iso_code"] == "E"
    assert result["subdivisions.0.names.en"] == "Östergötland County"
    # Last subdivision is also available at -1
    assert result["subdivisions.-1.iso_code"] == "E"
    assert result["subdivisions.-1.names.en"] == "Östergötland County"

"""Tests for maxmind_command.py.

Uses test data from the MaxMind-DB submodule. Test IPs are from
GeoIP2-Country-Test.mmdb which contains known test data.
"""

import maxmind_command


class MockCommand:
    """Mock command object that provides field and prefix attributes."""

    def __init__(self, field: str = "ip", prefix: str = "") -> None:
        self.field = field
        self.prefix = prefix


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

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


class TestMaxmindCommand(unittest.TestCase):
    def test_valid_ipv4_us(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "214.78.120.1"}])))

        self.assertEqual(results, [EXPECTED_US])

    def test_valid_ipv6_jp(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "2001:218::1"}])))

        self.assertEqual(results, [EXPECTED_JP])

    def test_valid_ipv6_kr(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "2001:220::1"}])))

        self.assertEqual(results, [EXPECTED_KR])

    def test_invalid_ip_format(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "not.an.ip"}])))

        self.assertEqual(results, [{"ip": "not.an.ip"}])

    def test_invalid_ip_out_of_range(self) -> None:
        command = MockCommand(ip_field="ip")
        events = iter([{"ip": "999.999.999.999"}])
        results = list(maxmind_command.stream(command, events))

        self.assertEqual(results, [{"ip": "999.999.999.999"}])

    def test_invalid_ip_empty_string(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": ""}])))

        self.assertEqual(results, [{"ip": ""}])

    def test_ip_not_in_database(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "8.8.8.8"}])))

        self.assertEqual(results, [{"ip": "8.8.8.8"}])

    def test_private_ip_not_in_database(self) -> None:
        command = MockCommand(ip_field="ip")
        results = list(maxmind_command.stream(command, iter([{"ip": "192.168.1.1"}])))

        self.assertEqual(results, [{"ip": "192.168.1.1"}])

    def test_missing_ip_field(self) -> None:
        command = MockCommand(ip_field="ip")
        events = iter([{"other_field": "value"}])
        results = list(maxmind_command.stream(command, events))

        self.assertEqual(results, [{"other_field": "value"}])

    def test_multiple_events(self) -> None:
        command = MockCommand(ip_field="ip")
        events = [
            {"ip": "214.78.120.1"},
            {"ip": "invalid"},
            {"other": "field"},
        ]
        results = list(maxmind_command.stream(command, iter(events)))

        self.assertEqual(results, [EXPECTED_US, {"ip": "invalid"}, {"other": "field"}])

    def test_custom_ip_field(self) -> None:
        command = MockCommand(ip_field="src_ip")
        events = iter([{"src_ip": "214.78.120.1"}])
        results = list(maxmind_command.stream(command, events))

        expected = {k: v for k, v in EXPECTED_US.items() if k != "ip"}
        expected["src_ip"] = "214.78.120.1"
        self.assertEqual(results, [expected])


class TestFlattenRecord(unittest.TestCase):
    def test_flat_dict(self) -> None:
        record = {"a": 1, "b": 2}
        result = dict(maxmind_command._flatten_record(record))
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_nested_dict(self) -> None:
        record = {"country": {"iso_code": "US", "names": {"en": "United States"}}}
        result = dict(maxmind_command._flatten_record(record))
        self.assertEqual(
            result,
            {"country.iso_code": "US", "country.names.en": "United States"},
        )

    def test_empty_dict(self) -> None:
        result = dict(maxmind_command._flatten_record({}))
        self.assertEqual(result, {})

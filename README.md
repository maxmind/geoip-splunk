# GeoIP for Splunk

## Description

This is a Splunk add-on for [MaxMind GeoIP
database](https://www.maxmind.com/en/geoip-databases) lookups. It provides
IP geolocation and enrichment using MaxMind's GeoIP and GeoLite databases,
including country, city, anonymous IP detection, ISP, and more.

The add-on provides a streaming search command (`geoip`) that enriches events
with data from one or more MaxMind databases.

## Search Command: `geoip`

The `geoip` command is a streaming search command that enriches events with
data from MaxMind databases.

### Syntax

```
| geoip [prefix=<string>] [field=<string>] databases=<databases>
```

### Arguments

**databases** (required)

Comma-separated list of MaxMind database names to query.

> **IMPORTANT:** When specifying multiple databases, quote the value.

- Example: `databases=GeoIP2-Country`
- Example: `databases="GeoIP2-City,GeoIP2-Anonymous-IP"`

**field** (optional, default: `ip`)

The event field containing the IP address to look up.

- Example: `field=src_ip`

**prefix** (optional, default: empty)

A prefix to prepend to all output field names.

- Example: `prefix=maxmind_`

### Output Fields

The command adds fields from the MaxMind database using dot-notation.
Common fields include:

| Field | Description |
|-------|-------------|
| `country.iso_code` | Two-letter country code (e.g., "US") |
| `country.names.en` | Country name in English |
| `continent.code` | Two-letter continent code (e.g., "NA") |
| `city.names.en` | City name |
| `subdivisions.0.iso_code` | First subdivision code (e.g., "CA" for California) |
| `subdivisions.0.names.en` | First subdivision name |
| `is_anonymous`, `is_vpn`, etc. | Anonymous IP flags (Anonymous-IP database) |
| `network` | The matched CIDR block (e.g., "192.0.2.0/24") |

Subdivisions use numeric indices (0, 1, 2, ...) in the field name.
Subdivisions are ordered from largest to smallest, so `subdivisions.0` is
typically the state/province. The last (most specific) subdivision is also
available at index -1 (e.g., `subdivisions.-1.iso_code`).

The `network` field contains the most specific (smallest) network matched
across all queried databases.

### Multiple Databases

When querying multiple databases, fields from all databases are merged
into the event. If the same field exists in multiple databases, the
value from the last database in the list is used.

### Examples

Look up country information for the ip field:

```
| makeresults | eval ip="8.8.8.8" | geoip databases=GeoIP2-Country
```

Look up city information using a custom field:

```
| ... | geoip field=client_ip databases=GeoIP2-City
```

Combine country and anonymous IP detection with a prefix:

```
| ... | geoip prefix=geo_ databases="GeoIP2-Country,GeoIP2-Anonymous-IP"
```

This produces fields like `geo_country.iso_code` and `geo_is_anonymous`.

### Error Handling

- Events with missing or empty IP fields are passed through unchanged.
- Events with invalid IP addresses are passed through unchanged.
- Events with IPs not found in any database are passed through unchanged.
- If a specified database does not exist, the command raises an error.

### Supported Databases

All MaxMind databases are supported.

Database files must be placed in the add-on's data directory.

## Incompatibility Notice

This add-on is incompatible with
[MaxMind GeoIP2 Add-on for Splunk (TA-geoip2)](https://splunkbase.splunk.com/app/6169).
Both add-ons provide a `geoip` search command, so only one can be installed at
a time.

## Support

Please report all issues with this code using the
[GitHub issue tracker](https://github.com/maxmind/geoip-splunk/issues).

If you are having an issue with the MaxMind database or service that is not
specific to this add-on, please see
[MaxMind support](https://www.maxmind.com/en/support).

## Requirements

- Splunk 10.2 or later

## Contributing

Bug reports and pull requests are welcome on
[GitHub](https://github.com/maxmind/geoip-splunk).

## Versioning

This add-on uses [Semantic Versioning](https://semver.org/).

## Copyright and License

Copyright (c) 2026 MaxMind, Inc.

This add-on is available as open source under the terms of the
[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0) or
the [MIT License](https://opensource.org/licenses/MIT), at your option.

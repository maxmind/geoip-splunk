# GeoIP for Splunk

## Description

This is a Splunk add-on for [MaxMind GeoIP
database](https://www.maxmind.com/en/geoip-databases) lookups. It provides
IP geolocation and enrichment using MaxMind's GeoIP and GeoLite databases,
including country, city, anonymous IP detection, ISP, and more.

The add-on provides a streaming search command (`maxmind`) that enriches events
with data from one or more MaxMind databases.

## Usage

See [geoip/package/README.md](geoip/package/README.md) for documentation on
the `maxmind` search command, including syntax, arguments, output fields, and
examples.

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

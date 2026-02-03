GeoIP for Splunk
======================

This add-on provides IP geolocation and enrichment using MaxMind databases.


Search Command: maxmind
-----------------------

The maxmind command is a streaming search command that enriches events with
data from MaxMind databases.

Syntax:

    | maxmind [prefix=<string>] [field=<string>] databases=<databases>

Arguments:

    databases (required)
        Comma-separated list of MaxMind database names to query.
        IMPORTANT: When specifying multiple databases, quote the value.
        Example: databases=GeoIP2-Country
        Example: databases="GeoIP2-City,GeoIP2-Anonymous-IP"

    field (optional, default: ip)
        The event field containing the IP address to look up.
        Example: field=src_ip

    prefix (optional, default: empty)
        A prefix to prepend to all output field names.
        Example: prefix=maxmind_

Output Fields:

    The command adds fields from the MaxMind database using dot-notation.
    Common fields include:

    - country.iso_code: Two-letter country code (e.g., "US")
    - country.names.en: Country name in English
    - continent.code: Two-letter continent code (e.g., "NA")
    - city.names.en: City name
    - subdivisions.0.iso_code: First subdivision code (e.g., "CA" for California)
    - subdivisions.0.names.en: First subdivision name
    - is_anonymous, is_vpn, etc.: Anonymous IP flags (Anonymous-IP database)
    - network: The matched CIDR block (e.g., "192.0.2.0/24")

    Subdivisions use numeric indices (0, 1, 2, ...) in the field name.
    Subdivisions are ordered from largest to smallest, so subdivisions.0 is
    typically the state/province. The last (most specific) subdivision is also
    available at index -1 (e.g., subdivisions.-1.iso_code).

    The network field contains the most specific (smallest) network matched
    across all queried databases.

Multiple Databases:

    When querying multiple databases, fields from all databases are merged
    into the event. If the same field exists in multiple databases, the
    value from the last database in the list is used.

Examples:

    Look up country information for the ip field:

        | makeresults | eval ip="8.8.8.8" | maxmind databases=GeoIP2-Country

    Look up city information using a custom field:

        | ... | maxmind field=client_ip databases=GeoIP2-City

    Combine country and anonymous IP detection with a prefix:

        | ... | maxmind prefix=geo_ databases="GeoIP2-Country,GeoIP2-Anonymous-IP"

    This produces fields like geo_country.iso_code and geo_is_anonymous.

Error Handling:

    - Events with missing or empty IP fields are passed through unchanged.
    - Events with invalid IP addresses are passed through unchanged.
    - Events with IPs not found in any database are passed through unchanged.
    - If a specified database does not exist, the command raises an error.

Supported Databases:

    All MaxMind databases are supported.

    Database files must be placed in the add-on's data directory.

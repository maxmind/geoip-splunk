#!/usr/bin/env python

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import geoip2.database
import geoip2.errors

# Open the GeoIP2 database once at module level
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, '..', 'data', 'GeoLite2-Country.mmdb')
_reader = geoip2.database.Reader(db_path)


def stream(command, events):
    """Stream function called by the UCC-generated wrapper.

    Args:
        command: The MaxmindCommand instance with options
        events: Generator of event dictionaries

    Yields:
        Modified event dictionaries with country_code field added
    """
    # Get the IP field name from the command options
    ip_field = command.ip_field

    # Process each event
    for event in events:
        # Get the IP address from the specified field
        ip_address = event.get(ip_field)

        if ip_address:
            try:
                # Perform the GeoIP2 lookup
                response = _reader.country(ip_address)

                # Add the country code to the event
                if response.country.iso_code:
                    event['country_code'] = response.country.iso_code

            except geoip2.errors.AddressNotFoundError:
                # IP not found in database - skip adding fields
                pass
            except (ValueError, geoip2.errors.GeoIP2Error):
                # Invalid IP address or other GeoIP2 error - skip adding fields
                pass

        yield event

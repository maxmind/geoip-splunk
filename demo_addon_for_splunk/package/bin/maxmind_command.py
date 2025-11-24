#!/usr/bin/env python

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import maxminddb

# Open the MaxMind database once at module level
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, '..', 'data', 'GeoLite2-Country.mmdb')
_reader = maxminddb.open_database(db_path)


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
                # Perform the MaxMind database lookup
                record = _reader.get(ip_address)

                # Add the country code to the event if found
                if record and record.get('country', {}).get('iso_code'):
                    event['country_code'] = record['country']['iso_code']

            except ValueError:
                # Invalid IP address - skip adding fields
                pass

        yield event

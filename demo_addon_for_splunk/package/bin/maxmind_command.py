import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import maxminddb

# Open the database once at module level
#
# TODO: We need to be able to re-open this when there are updates.
#
# TODO: We need to be able to handle multiple databases.
#
# TODO: We need to be able to download databases rather than assume they are
# available in the add-on directly.
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
    ip_field = command.ip_field

    for event in events:
        ip_address = event.get(ip_field)

        if ip_address:
            try:
                record = _reader.get(ip_address)

                # Add the country code to the event if found
                if record and record.get('country', {}).get('iso_code'):
                    event['country_code'] = record['country']['iso_code']

            except ValueError:
                pass

        yield event

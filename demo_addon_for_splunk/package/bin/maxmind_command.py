import ipaddress
import os
import sys

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
db_path = os.environ.get(
    'MAXMIND_DB_PATH',
    os.path.join(script_dir, '..', 'data', 'GeoLite2-Country.mmdb'),
)
_reader = maxminddb.open_database(db_path)


def stream(command, events):
    """Enrich events with data from a MaxMind database.

    Looks up the IP address in the MaxMind database and adds all fields found
    to the event using dot-notation (e.g., country.iso_code, country.names.en,
    continent.code). Also adds a 'network' field with the matched CIDR block.

    If no result is found (invalid IP, IP not in database, or missing IP field),
    the event is yielded unchanged.

    Args:
        command: The MaxmindCommand instance with options
        events: Generator of event dictionaries

    Yields:
        Event dictionaries, enriched with database fields when a match is found
    """
    ip_field = command.ip_field

    for event in events:
        ip_address = event.get(ip_field)

        if ip_address:
            try:
                record, prefix_len = _reader.get_with_prefix_len(ip_address)

                if record:
                    for key, value in _flatten_record(record):
                        event[key] = value

                    network = ipaddress.ip_network(
                        f"{ip_address}/{prefix_len}",
                        strict=False,
                    )
                    event['network'] = str(network)

            except ValueError:
                pass

        yield event


def _flatten_record(record, prefix=''):
    """Flatten a nested record dict into dot-notation keys.

    Args:
        record: A dictionary that may contain nested dictionaries
        prefix: The prefix to prepend to keys (for recursion)

    Yields:
        Tuples of (flattened_key, value) for all leaf values
    """
    for key, value in record.items():
        full_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten_record(value, f"{full_key}.")
        else:
            yield full_key, value

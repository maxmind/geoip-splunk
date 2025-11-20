#!/usr/bin/env python

# from https://github.com/splunk/splunk-app-examples/blob/master/custom_search_commands/python/customsearchcommands_template/bin/stream.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, StreamingCommand, Configuration, Option, validators
import geoip2.database
import geoip2.errors


@Configuration()
class MaxmindCommand(StreamingCommand):
    """ Lookup IP addresses in MaxMind GeoIP2 database

    ##Syntax

    | maxmind ip_field=<field>

    ##Description

    Performs GeoIP2 lookups on IP addresses and adds geographic information fields.
    Currently returns the country code for each IP address.

    ##Example

    | makeresults | eval ip="8.8.8.8" | maxmind ip_field=ip

    """
    ip_field = Option(
        doc='''
        **Syntax:** **ip_field=***<fieldname>*
        **Description:** Name of the field containing the IP address to look up.
        **Default:** clientip
        ''',
        require=False,
        default='clientip',
        validate=validators.Fieldname()
    )

    def __init__(self):
        super(MaxmindCommand, self).__init__()
        # Open the GeoIP2 database - located in data directory relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, '..', 'data', 'GeoLite2-Country.mmdb')
        self.reader = geoip2.database.Reader(db_path)

    def stream(self, events):
        # Process each event
        for event in events:
            # Get the IP address from the specified field
            ip_address = event.get(self.ip_field)

            if ip_address:
                try:
                    # Perform the GeoIP2 lookup
                    response = self.reader.country(ip_address)

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

    def __del__(self):
        # Close the database reader when done
        if hasattr(self, 'reader'):
            self.reader.close()

dispatch(MaxmindCommand, sys.argv, sys.stdin, sys.stdout, __name__)

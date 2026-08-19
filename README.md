# MaxMind GeoIP App

## Description

This is a Splunk app for [MaxMind GeoIP
database](https://www.maxmind.com/en/geoip-databases) lookups. It provides
IP geolocation and enrichment using MaxMind's GeoIP and GeoLite databases,
including country, city, anonymous IP detection, ISP, and more.

The app provides a streaming search command (`geoip`) that enriches events
with data from one or more MaxMind databases.

The app can be found on
[Splunkbase](https://splunkbase.splunk.com/app/8554).

## Quick Start

1. Install the app and restart Splunk
2. Go to **Apps > MaxMind GeoIP App > Configuration**
3. Enter your MaxMind **Account ID** and **License Key**
4. Go to **Configuration > Databases** and add the databases you want
5. Click **Save**

Database updates run automatically every hour. Once you've completed the
steps above, your databases will be downloaded within a few minutes.

You can find your Account ID and generate license keys in your
[MaxMind account portal](https://www.maxmind.com/en/account).

## Configuration

### Databases

Add the databases you want to download:

1. Go to **Configuration > Databases**
2. Click **Add** and enter the database name

Common databases:

| Database | Description |
|----------|-------------|
| `GeoLite2-City` | Free city-level geolocation |
| `GeoLite2-Country` | Free country-level geolocation |
| `GeoLite2-ASN` | Free ASN lookup |
| `GeoIP2-City` | Paid city-level geolocation (more accurate) |
| `GeoIP2-Country` | Paid country-level geolocation |
| `GeoIP2-Anonymous-IP` | VPN, proxy, and Tor detection |
| `GeoIP2-ISP` | ISP and organization lookup |

### Database Updates

Databases are checked for updates every hour and stored in the app's
`databases/` directory. They are preserved across upgrades.

In Search Head Cluster environments, each member downloads its own databases
independently.

## Search Command: `geoip`

The `geoip` command is a streaming search command that enriches events with
data from MaxMind databases.

### Syntax

```spl
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

```spl
| makeresults | eval ip="8.8.8.8" | geoip databases=GeoIP2-Country
```

Look up city information using a custom field:

```spl
| ... | geoip field=client_ip databases=GeoIP2-City
```

Combine country and anonymous IP detection with a prefix:

```spl
| ... | geoip prefix=geo_ databases="GeoIP2-Country,GeoIP2-Anonymous-IP"
```

This produces fields like `geo_country.iso_code` and `geo_is_anonymous`.

### Error Handling

- Events with missing or empty IP fields are passed through without
  enrichment.
- Events with invalid IP addresses are passed through without enrichment.
- Events with IPs not found in any database are passed through without
  enrichment.
- If a specified database does not exist, the command raises an error.

### Supported Databases

All MaxMind databases are supported. Make sure the database name in your
search matches the name configured in the Databases tab.

## Search Command: `geoipdebug`

The `geoipdebug` command is a generating search command that reports
diagnostic information about the app: which databases are present and how
old they are, software versions, and the app's non-secret settings. Use it
to check whether a node has up-to-date databases, and include its output
when reporting a problem with the app.

### Syntax

```spl
| geoipdebug [indexers=<bool>]
```

### Arguments

**indexers** (optional, default: `false`)

When true, the command also runs on the search peers (indexers), where it
reports what each peer's knowledge bundle carries. See [Checking the
Indexers](#checking-the-indexers).

### Output

The command generates one event per item. Every event has a `component`
field saying what it describes and a `hostname` field saying which node
reported it. A field that cannot be read shows `unknown` or an `error`
field instead of failing the search. Boolean fields hold the strings
`true` and `false`.

**component=database** - one event per configured database:

| Field | Description |
|-------|-------------|
| `database` | The database name (e.g., "GeoLite2-City") |
| `database_source` | Where the name came from: `configured` (the app's database list, so a never-downloaded database still gets an event) or `directory` (the `.mmdb` files present on this node - what indexers report, and the fallback when the configured list cannot be read) |
| `present` | Whether the database file exists on this node |
| `build_time` | When MaxMind built this copy of the database (ISO 8601 UTC) |
| `database_type` | The database type recorded in the file |
| `file_path` | The path of the database file on this node |
| `file_size_bytes` | The size of the database file |
| `file_mtime` | When the file was last written on this node. On the search head that is when the updater last downloaded it; on a search peer the file comes from the knowledge bundle |
| `error` | Why the database or its metadata could not be read |

An old `build_time` under a recent `file_mtime` means MaxMind has not
published a newer build. On the search head, an old `file_mtime` means
the updater has not downloaded anything recently on this node.

**component=system** - one event:

| Field | Description |
|-------|-------------|
| `app_version` | The GeoIP app's version |
| `splunk_version` | The Splunk server version |
| `python_version` | The Python interpreter version the app runs under |
| `database_directory` | The directory this node reads databases from |
| `on_indexer` | Whether this event came from an indexer |

**component=settings** - one event (not reported by indexers, where the
app's configuration is not available):

| Field | Description |
|-------|-------------|
| `loglevel` | The app's configured log level |
| `run_on_indexers` | The "Run on indexers" setting |
| `databases_configured` | Comma-separated configured database names |
| `credentials_configured` | Whether a usable MaxMind account ID and license key are configured (the same checks the updater applies) - the values themselves are never output |

### Examples

Show the databases on the search head:

```spl
| geoipdebug
| where component="database"
| table database present build_time file_mtime error
```

In a search head cluster, a search reports only the member it runs on. To
compare members, run the search on each member.

### Checking the Indexers

With `indexers=true`, the command runs on the search head and on each
search peer. The peers report the database copies their knowledge bundle
carries; the `hostname` field says which node reported each event:

```spl
| geoipdebug indexers=true
| table hostname component database present build_time error
```

While **Run on indexers** is disabled, the databases are not in the
knowledge bundle, so the peers report no database events. That is the
expected result, not a failure. See [Running on
Indexers](#running-on-indexers).

## Running on Indexers

By default, the `geoip` command runs only on the search head. You can
optionally run it on the indexers, which lets Splunk enrich events where
they are stored instead of first sending them to the search head.

To enable this, go to **Configuration > Distributed Search**, check
**Run on indexers**, and restart the search head (every member, in a
search head cluster). The restart is required because Splunk only reads
the replication rules that put the databases into the knowledge bundle at
startup. Disabling the setting takes effect immediately - the command
stops running on the indexers right away, and the databases stay in the
knowledge bundle until the next restart, which is only wasted bundle
space.

In a distributed deployment, `geoip` searches fail with a "Database not
found on this indexer" error between enabling the setting and completing
the restart: the command starts distributing immediately, but the
databases cannot enter the knowledge bundle until the restart. On a single
instance with no search peers there is nothing to distribute to, so
nothing changes and nothing fails. On Splunk Cloud, restart the search heads
yourself with the Admin Config Service (ACS) API: its `restart-now`
endpoint restarts a standalone search head or performs a rolling restart
of a search head cluster (requires the `sc_admin` role).

### How Replication Works

Splunk ships search-time configuration to the indexers in the knowledge
bundle. The bundle always includes the small set of libraries the `geoip`
command needs (about 0.9 MB); enabling **Run on indexers** adds the
MaxMind databases to it.

Bundle replication is triggered by searches: after a database downloads,
the next search dispatched to the indexers pushes an updated bundle. That
same search still runs against the bundle the indexers already have,
which means:

- The first search after adding a new database can fail with a "Database
  not found on this indexer" error. Retry once the bundle push
  completes - typically well under a minute.
- Updates to a database the indexers already have never cause this error.
  The indexers keep using the previous version of a database until the
  updated bundle arrives.

Searches that never touch the indexers (for example, plain
`| makeresults`) do not trigger a bundle push.

### Bundle Size Limits

The databases are copied to every indexer in the knowledge bundle, so large
databases increase the bundle size significantly. Splunk limits bundle size
(`maxBundleSize`, default 2048 MB) and logs warnings well before that;
Splunk Cloud enforces a hard limit (3 GB at the time of writing), beyond
which the bundle is not pushed and the indexers keep using the previous one
(see the service limits table in "Splunk Cloud Platform Service Details" on
the Splunk help site). If bundle size is a problem, leave **Run on
indexers** disabled: the databases then stay out of the knowledge bundle
entirely and the command runs only on the search head.

## Incompatibility Notice

This app is incompatible with
[MaxMind GeoIP2 Add-on for Splunk (TA-geoip2)](https://splunkbase.splunk.com/app/6169).
Both provide a `geoip` search command, so only one can be installed at a
time.

## Support

Please report all issues with this code using the
[GitHub issue tracker](https://github.com/maxmind/geoip-splunk/issues).

If you are having an issue with the MaxMind database or service that is not
specific to this app, please see
[MaxMind support](https://www.maxmind.com/en/support).

## Requirements

- Splunk 10.2 or later

## Contributing

Bug reports and pull requests are welcome on
[GitHub](https://github.com/maxmind/geoip-splunk).

## Versioning

This app uses [Semantic Versioning](https://semver.org/).

## Copyright and License

Copyright (c) 2026 MaxMind, Inc.

This app is available as open source under the terms of the [Apache
License, Version 2.0](LICENSE-APACHE) or the [MIT License](LICENSE-MIT), at
your option.

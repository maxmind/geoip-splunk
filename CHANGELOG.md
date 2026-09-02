# Changelog

## 1.3.0 (2026-09-02)

- Fix the `geoip` command silently dropping fields from some events. The Splunk
  SDK locks the set of output fields to the fields of the first result in each
  chunk, so any event whose lookup produced a field the chunk's first event did
  not have lost that field. Most visibly, one event with a missing, invalid, or
  not-found IP at the head of a chunk stripped all enrichment from every other
  event in it, with no error anywhere; less visibly, fields that vary between
  matched IPs (city, subdivisions, postal) were dropped from events whose chunk
  started with an IP that lacked them. All events in a chunk now carry the same
  field set, with empty values where a field does not apply.
- Add the `geoipdebug` diagnostic search command. It generates one event per
  configured database with its build time, type, and file details, plus events
  with the app, Splunk, and Python versions and the app's non-secret settings.
  With `indexers=true` it runs on the indexers and reports the database copies
  their knowledge bundle carries.
- Fix the "Run on indexers" setting sometimes never taking effect on the
  indexers, even after the required search head restart.

## 1.2.0 (2026-07-29)

- Revert the scripted-input experiment from 1.1.3. The scripted input did not
  run on every search head cluster member in Splunk Cloud either, so the
  `geoipupdate_input` modular input's default instance is re-enabled, and the
  `[script://...]` stanza and its `geoipupdate_script.py` wrapper are removed.
- Fix the `geoip` command being distributed to indexers, where it fails because
  the databases are not there. Under SCP2 (`chunked = true`), Splunk decides
  distribution from the SDK's getinfo response, not `commands.conf`, so the
  `local = true` setting added in 1.1.0 was ignored. The command now reports
  itself search-head-only by default, so prepending `| localop` is no longer
  needed.
- Store MaxMind databases in the app's `databases/` directory instead of
  `local/data/`. A directory of the app's own is outside search head cluster
  replication summaries and outside Splunk's default knowledge bundle allowlist,
  so replication of the databases is controlled entirely by the app, and the new
  path is resolved relative to the app root so it also works when the command
  runs from a knowledge bundle on an indexer. Databases found in the old
  location are moved to the new one automatically - by the updater's next run or
  by the first `geoip` search that would otherwise miss them - so upgrades keep
  working without waiting for a re-download.
- Add opt-in support for running the `geoip` command on indexers. A new
  "Distributed Search" configuration tab provides a "Run on indexers" checkbox,
  off by default because large databases increase the knowledge bundle size and
  replication can exceed bundle size limits. Enabling it requires restarting the
  search head (every member, in a search head cluster), because Splunk only
  reads the replication rules that put the databases into the knowledge bundle
  at startup.

## 1.1.3 (2026-06-30)

- Add a scripted-input variant (`[script://...]`) of the database updater as a
  wrapper (`geoipupdate_script.py`) around the existing `run_database_update()`
  logic, and disable the `geoipupdate_input` modular input's default instance.
  This tests whether a scripted input runs on every search head cluster member
  in Splunk Cloud, unlike the modular input which only runs on one. The updater
  should continue to function through this alternate mechanism.

## 1.1.2 (2026-06-25)

- Declare `run_only_one` as a scheme argument in the `geoipupdate_input` modular
  input's Python scheme (`get_scheme`), in addition to the `inputs.conf.spec`
  entry added in 1.1.1. Splunk appears to only honor modular input settings
  other than the standard `name`, `interval`, `index`, and `sourcetype` when
  they are declared as scheme arguments, so setting `run_only_one` in
  `inputs.conf` alone was not enough for it to take effect. Splunk's own add-ons
  (for example, the Splunk Add-on for CrowdStrike FDR) declare `run_only_one`
  this way. On Splunk Cloud Victoria this appears to be required for
  `run_only_one = false` to be respected so that each search head cluster member
  runs the input and downloads its own databases.

## 1.1.1 (2026-06-23)

- Declare the `interval`, `disabled`, and `run_only_one` settings in the
  `geoipupdate_input` modular input's `inputs.conf.spec` so the input's
  supported parameters are documented in the spec file. This is to see if
  including `run_only_one` will make the database update modular input run on
  all search heads in a search head cluster.

## 1.1.0 (2026-04-01)

- Set `local = true` for the `geoip` search command so it runs on the search
  head instead of distributed peers. This avoids failures in distributed
  searches when indexers do not have the MaxMind databases or updater-managed
  app state available locally.

## 1.0.0 (2026-03-16)

- Initial release.

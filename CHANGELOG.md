# Changelog

## 1.1.4 (unreleased)

* Store MaxMind databases in the app's `databases/` directory instead of
  `local/data/`. A directory of the app's own is outside search head
  cluster replication summaries and outside Splunk's default knowledge
  bundle allowlist, so replication of the databases is controlled entirely
  by the app, and the new path is resolved relative to the app root so it
  also works when the command runs from a knowledge bundle on an indexer.
  This is groundwork for optional indexer execution. There is no
  migration: databases in the old location are ignored and fresh copies
  are downloaded to `databases/` by the hourly update.
* Ship `default/server.conf` instead of relying on the UCC-generated one
  (UCC skips generating it when the package provides its own). In addition
  to the two `conf_replication_include` lines UCC generated, it now
  replicates `distsearch.conf` across search head cluster members (needed
  for the upcoming indexer execution toggle).
* Ship `default/distsearch.conf` with knowledge bundle replication rules:
  the minimal set of libraries the `geoip` command needs at search time on
  an indexer (`splunklib`, `maxminddb`, `geoip_utils.py`; about 1.6 MB) is
  added to the replication allowlist, along with a `geoip_mmdb` key for
  the databases that defaults to a pattern matching nothing (indexer
  execution will be opt-in). Splunk's default rules replicate app `bin/`
  and `lookups/` directories but not `lib/` or the app's `databases/`
  directory, which is why the command could not previously run on indexers
  even before `distributed=False`.
* Add a "Distributed Search" tab to the configuration UI with a "Run on
  indexers" checkbox (`[distribution] run_on_indexers` in
  `geoip_settings.conf`, off by default). The following changes wire it to
  knowledge bundle replication and command distribution.
* Wire the "Run on indexers" setting to knowledge bundle replication:
  saving the setting overrides the `geoip_mmdb` replication allowlist key
  in `local/distsearch.conf` - the real `databases/*.mmdb` pattern when
  enabled, the shipped match-nothing pattern when disabled.
* Decide command distribution at search time from the "Run on indexers"
  setting. The post-build hook (renamed to
  `make_command_distribution_toggleable`) now also injects a `prepare()`
  method into the generated command wrapper; the Splunk SDK calls it
  before answering the getinfo exchange, and it sets the `distributed`
  configuration setting from `geoip_settings.conf`. The
  `@Configuration(distributed=False)` rewrite from earlier in 1.1.4
  remains as a fail-safe default. On an indexer, `prepare()` reports
  distributed streaming without touching REST (the app's conf endpoints
  do not exist there); indexer invocations are identified by the
  `remote_` prefix on their search id. Any failure to read the setting
  falls back to search-head-only execution.
* Improve the error when a database file is missing. On an indexer, the
  error explains that the database has not reached the indexer's
  knowledge bundle yet - expected on the first search after enabling
  "Run on indexers" or adding a new database - and how to resolve it. On
  the search head, it points at the app configuration page.
* Revert the scripted-input experiment from 1.1.3. The scripted input did
  not run on every search head cluster member in Splunk Cloud either, so
  the `geoipupdate_input` modular input's default instance is re-enabled,
  and the `[script://...]` stanza and its `geoipupdate_script.py` wrapper
  are removed.
* Force the `geoip` search command to run only on the search head by injecting
  `@Configuration(distributed=False)` into the generated command wrapper during
  the post-build hook. The `local = true` setting added in 1.1.0 is an
  SCP1-only setting that Splunk ignores for chunked (SCP2) commands, so the
  command was still being distributed to indexers and users had to prepend
  `| localop`. Reporting the command as `stateful` is the built-in equivalent
  of `localop` and removes that requirement.

## 1.1.3 (2026-06-30)

* Add a scripted-input variant (`[script://...]`) of the database updater
  as a wrapper (`geoipupdate_script.py`) around the existing
  `run_database_update()` logic, and disable the `geoipupdate_input`
  modular input's default instance. This tests whether a scripted input
  runs on every search head cluster member in Splunk Cloud, unlike the
  modular input which only runs on one. The updater should continue to
  function through this alternate mechanism.

## 1.1.2 (2026-06-25)

* Declare `run_only_one` as a scheme argument in the `geoipupdate_input`
  modular input's Python scheme (`get_scheme`), in addition to the
  `inputs.conf.spec` entry added in 1.1.1. Splunk appears to only honor
  modular input settings other than the standard `name`, `interval`,
  `index`, and `sourcetype` when they are declared as scheme arguments, so
  setting `run_only_one` in `inputs.conf` alone was not enough for it to
  take effect. Splunk's own add-ons (for example, the Splunk Add-on for
  CrowdStrike FDR) declare `run_only_one` this way. On Splunk Cloud
  Victoria this appears to be required for `run_only_one = false` to be
  respected so that each search head cluster member runs the input and
  downloads its own databases.

## 1.1.1 (2026-06-23)

* Declare the `interval`, `disabled`, and `run_only_one` settings in the
  `geoipupdate_input` modular input's `inputs.conf.spec` so the input's
  supported parameters are documented in the spec file. This is to see if
  including `run_only_one` will make the database update modular input run
  on all search heads in a search head cluster.

## 1.1.0 (2026-04-01)

* Set `local = true` for the `geoip` search command so it runs on the search
  head instead of distributed peers. This avoids failures in distributed
  searches when indexers do not have the MaxMind databases or updater-managed
  app state available locally.

## 1.0.0 (2026-03-16)

* Initial release.

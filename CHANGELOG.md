# Changelog

## 1.1.2

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

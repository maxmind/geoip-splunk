# Changelog

## 1.1.1

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

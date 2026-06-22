# Changelog

## 1.2.0

* Force the `geoip` search command to run only on the search head by injecting
  `@Configuration(distributed=False)` into the generated command wrapper during
  the post-build hook. The `local = true` setting added in 1.1.0 is an
  SCP1-only setting that Splunk ignores for chunked (SCP2) commands, so the
  command was still being distributed to indexers and users had to prepend
  `| localop`. Reporting the command as `stateful` is the built-in equivalent
  of `localop` and removes that requirement.

## 1.1.0 (2026-04-01)

* Set `local = true` for the `geoip` search command so it runs on the search
  head instead of distributed peers. This avoids failures in distributed
  searches when indexers do not have the MaxMind databases or updater-managed
  app state available locally.

## 1.0.0 (2026-03-16)

* Initial release.

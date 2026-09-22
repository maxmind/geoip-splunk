---
name: update-deps
description:
  Update all project dependencies (mise tools, uv/pyproject dev dependencies,
  app runtime requirements) and verify the build. Use when asked to update,
  bump, or refresh dependencies.
---

# Updating Dependencies

Dependencies live in two places (see "Dependencies" in CLAUDE.md): `mise.toml`
(dev tools) and `pyproject.toml` with `uv.lock` (build/dev dependencies and, in
the `runtime` dependency group, the app's runtime dependencies).
`geoip/package/lib/requirements.txt` is generated from the lock by `build.sh`,
so never edit it.

Dependabot covers `pyproject.toml` and `uv.lock` (the `uv` ecosystem in
`.github/dependabot.yml`). Its weekly job bumps only the direct dependencies,
the packages `pyproject.toml` names. Its security updates also bump a transitive
package that has an advisory. Nothing covers `mise.toml` or the other transitive
dependencies, so those are the parts to update by hand. The transitive
dependencies of the runtime group (aiohttp, grpcio, opentelemetry, ...) ship in
the app and only advance when the lock is upgraded.

To update the mise tools:

```bash
# Check for latest versions of mise tools
mise latest aqua:astral-sh/uv
mise latest github:houseabsolute/precious
mise latest node
mise latest npm:prettier

# After updating mise.toml, regenerate the lock file
mise lock

# Install the new versions
mise install
```

To upgrade the transitive Python dependencies:

```bash
# Upgrade every locked Python package. Dependabot's weekly job only opens
# PRs for direct dependencies, so this is the only way a transitive one
# without a security advisory moves. It also moves direct dependencies
# within their ranges. Review the uv.lock diff.
uv lock --upgrade
```

Then verify:

```bash
# Bring the venv in line with the lock files. --group lint is required:
# ruff, mypy, and splunk-appinspect are in the lint group, which a bare
# "uv sync" does not install (and uninstalls if it is already there), so the
# verify chain below would fail with "Failed to spawn: ruff".
uv sync --group lint

# Verify everything works
precious tidy -g && precious lint -g && uv run pytest tests && ./build.sh

# Then AppInspect, on the tarball ./build.sh just produced. It is not part of
# "precious lint -g" and it is the check most likely to catch a dependency
# bump, since it inspects the vendored runtime libraries.
precious lint --command appinspect geoip-<version>.tar.gz
```

**Important**: Keep Python on 3.13.x as that is the latest major version Splunk
supports.

A ruff bump can turn a rule on rather than off: `select = ["ALL"]` picks up
every rule ruff promotes out of preview, so a Dependabot ruff PR can fail
`precious lint` on code that did not change. Add the rule to the `ignore` list
in `pyproject.toml` with a comment saying why, as the existing entries do.

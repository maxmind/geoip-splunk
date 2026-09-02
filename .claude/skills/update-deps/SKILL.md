---
name: update-deps
description:
  Update all project dependencies (mise tools, uv/pyproject dev dependencies,
  app runtime requirements) and verify the build. Use when asked to update,
  bump, or refresh dependencies.
---

# Updating Dependencies

Dependencies live in three places (see "Dependencies" in CLAUDE.md): `mise.toml`
(dev tools), `pyproject.toml` (build/dev dependencies), and
`package/lib/requirements.txt` (app runtime dependencies).

Dependabot covers two of the three (see `.github/dependabot.yml`): the `uv`
ecosystem at `/` opens PRs for `pyproject.toml` and `uv.lock`, and the `pip`
ecosystem at `/geoip/package/lib` for `requirements.txt`. Nothing covers
`mise.toml`, so the mise tools are the part to update by hand. Leave the
Dependabot-owned files alone unless there is a specific reason not to wait for
its PR.

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
supports. When updating `maxminddb`, `pygeoipupdate`, or `solnlib` in both
`pyproject.toml` (dev) and `requirements.txt` (runtime), ensure versions stay in
sync; `tests/requirements_test.py` fails when a `requirements.txt` pin differs
from the version `uv.lock` resolves.

A ruff bump can turn a rule on rather than off: `select = ["ALL"]` picks up
every rule ruff promotes out of preview, so a Dependabot ruff PR can fail
`precious lint` on code that did not change. Add the rule to the `ignore` list
in `pyproject.toml` with a comment saying why, as the existing entries do.

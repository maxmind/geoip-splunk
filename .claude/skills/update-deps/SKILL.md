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

To update all dependencies:

```bash
# Check for latest versions of mise tools
mise latest aqua:astral-sh/uv
mise latest github:houseabsolute/precious
mise latest node
mise latest npm:prettier

# After updating mise.toml, regenerate the lock file
mise lock

# Check for latest Python package versions (example)
curl -s https://pypi.org/pypi/ruff/json | python3 -c "import sys, json; print(json.load(sys.stdin)['info']['version'])"

# After updating pyproject.toml, sync the lock file. --group lint is required:
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
supports. When updating `maxminddb` or `pygeoipupdate` in both `pyproject.toml`
(dev) and `requirements.txt` (runtime), ensure versions stay in sync.

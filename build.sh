#!/bin/bash

set -eu -o pipefail

rm -rf output *.tar.gz
find geoip/package -type d -name "__pycache__" -prune -exec rm -rf {} +
# UCC installs lib/requirements.txt into the package. The file is generated
# from the runtime dependency group in uv.lock, so the package ships the
# versions the test suite ran against.
dev-bin/export-requirements.sh

# ucc-gen upgrades pip before the install and, given no version, takes the
# newest release on PyPI: outside the lock and its release-age rule, and it
# is the pip that then does the hash-checked install. Pass the locked pip
# so that step installs nothing. pip is a project dependency, and
# "uv run --locked" syncs the venv to the lock (or fails on a stale lock)
# before reading the version, so this is the locked pip, not whatever the
# venv happened to hold.
pip_version=$(uv run --locked -- python -c \
    "from importlib.metadata import version; print(version('pip'))")
uv run -- ucc-gen build --source geoip/package --ta-version 1.3.0 \
    --pip-version "$pip_version"

# Verify the post-build hook (geoip/additional_packaging.py) rewrote the
# generated command wrappers. UCC calls that hook inside a
# "try: ... except ImportError", so an ImportError raised anywhere inside it
# is swallowed with an INFO log and the build still exits 0 - shipping the
# wrappers with UCC's bare @Configuration(). For geoip that makes the SDK
# report distributable streaming and fails every search on indexers that
# have no databases; for geoipdebug (a GeneratingCommand, whose SCP2
# distributed already defaults to false) it silently turns indexers=true
# into a search-head-only no-op. The hook cannot catch that itself, so
# check from out here, where nothing can swallow it.
for marker in \
    'from geoip_command import prepare, stream' \
    '@Configuration(distributed=False)' \
    '    def prepare(self):'; do
    if ! grep -qF -- "$marker" output/geoip/bin/geoip.py; then
        echo "build.sh: $marker missing from output/geoip/bin/geoip.py;" \
            "make_command_distribution_toggleable did not run" >&2
        exit 1
    fi
done

for marker in \
    'from geoipdebug_command import generate, prepare' \
    '@Configuration(distributed=False)' \
    '    def prepare(self):'; do
    if ! grep -qF -- "$marker" output/geoip/bin/geoipdebug.py; then
        echo "build.sh: $marker missing from output/geoip/bin/geoipdebug.py;" \
            "make_command_distribution_toggleable did not run" >&2
        exit 1
    fi
done

# The geoipdebug command reads the app version from [launcher] in
# default/app.conf, resolved relative to bin/ (_APP_CONF_PATH in
# geoipdebug_command.py). UCC writes the key at build time - the source
# tree's app.conf has no version key, so no test can catch UCC moving or
# dropping it; without this check every install would report
# app_version=unknown.
if ! sed -n '/^\[launcher\]/,/^\[/p' output/geoip/default/app.conf \
    | grep -q '^version = '; then
    echo "build.sh: no version key under [launcher] in" \
        "output/geoip/default/app.conf; geoipdebug would report" \
        "app_version=unknown" >&2
    exit 1
fi

# The package must hold exactly the exported closure: one dist-info per pin
# that applies to this platform, at the pinned version, and no other package.
# pip's hash-checking mode is meant to guarantee this; check from out here so
# a UCC or pip change cannot ship something else silently.
uv run --locked -- python dev-bin/check_vendored_lib.py

# Clean up pip-installed files that AppInspect doesn't like
# - .hash directories from aiohttp (Cython build artifacts)
# - Files/directories starting with "." are prohibited in Splunk Cloud apps
find output/geoip/lib -type d -name ".hash" -prune -exec rm -rf {} +
# - lib/bin holds the console scripts pip installs for packages that declare
#   them (idna, pygeoipupdate). Nothing in the app runs them, and their
#   shebang is the absolute path of the build machine's venv Python.
rm -rf output/geoip/lib/bin

uv run -- ucc-gen package --path output/geoip

#!/bin/bash

set -eu -o pipefail

rm -rf output *.tar.gz
find geoip/package -type d -name "__pycache__" -prune -exec rm -rf {} +
uv run -- ucc-gen build --source geoip/package --ta-version 1.2.0

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

# Clean up pip-installed files that AppInspect doesn't like
# - .hash directories from aiohttp (Cython build artifacts)
# - Files/directories starting with "." are prohibited in Splunk Cloud apps
find output/geoip/lib -type d -name ".hash" -prune -exec rm -rf {} +

uv run -- ucc-gen package --path output/geoip

#!/bin/bash

set -eu -o pipefail

rm -rf output *.tar.gz
find geoip/package -type d -name "__pycache__" -prune -exec rm -rf {} +
uv run -- ucc-gen build --source geoip/package --ta-version 1.2.0

# Verify the post-build hook (geoip/additional_packaging.py) rewrote the
# generated command wrapper. UCC calls that hook inside a
# "try: ... except ImportError", so an ImportError raised anywhere inside it
# is swallowed with an INFO log and the build still exits 0 - shipping the
# wrapper with UCC's bare @Configuration(), which makes the SDK report
# distributable streaming and fails every geoip search on indexers that have
# no databases. The hook cannot catch that itself, so check from out here,
# where nothing can swallow it.
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

# Clean up pip-installed files that AppInspect doesn't like
# - .hash directories from aiohttp (Cython build artifacts)
# - Files/directories starting with "." are prohibited in Splunk Cloud apps
find output/geoip/lib -type d -name ".hash" -prune -exec rm -rf {} +

uv run -- ucc-gen package --path output/geoip

#!/bin/bash

set -eu -o pipefail

rm -rf output *.tar.gz
find geoip/package -type d -name "__pycache__" -prune -exec rm -rf {} +
uv run -- ucc-gen build --source geoip/package --ta-version 1.0.0

# Clean up pip-installed files that AppInspect doesn't like
# - .hash directories from aiohttp (Cython build artifacts)
# - Files/directories starting with "." are prohibited in Splunk Cloud apps
find output/geoip/lib -type d -name ".hash" -prune -exec rm -rf {} +

uv run -- ucc-gen package --path output/geoip

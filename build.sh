#!/bin/bash

set -eu -o pipefail

rm -rf output *.tar.gz
find geoip/package -type d -name "__pycache__" -prune -exec rm -rf {} +
uv run -- ucc-gen build --source geoip/package --ta-version 1.0.0
uv run -- ucc-gen package --path output/geoip

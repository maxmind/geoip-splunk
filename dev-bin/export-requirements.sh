#!/bin/bash

# Export the app's runtime dependencies from uv.lock into the requirements
# file that UCC vendors into the package. The file is not tracked: build.sh
# runs this before ucc-gen, and tests/requirements_test.py runs it to check
# the export. Pass a path to write somewhere else.
#
# --locked makes the export fail if pyproject.toml and uv.lock disagree, so a
# build never ships from a stale lock. The hashes put pip into hash-checking
# mode: it verifies every download against the lock and refuses to install
# anything the file does not list.

set -eu -o pipefail

cd "$(dirname "$0")/.."

uv export \
    --only-group runtime \
    --locked \
    --no-emit-project \
    --no-annotate \
    --quiet \
    --output-file "${1:-geoip/package/lib/requirements.txt}"

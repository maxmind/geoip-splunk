#!/bin/bash

set -eu -o pipefail

uv run -- ucc-gen build --source demo_addon_for_splunk/package --ta-version 1.0.0
uv run -- ucc-gen package --path output/demo_addon_for_splunk

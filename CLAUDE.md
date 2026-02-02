# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Important**: When you learn something new about this project or make changes that affect information documented here, update this file at the same time to keep it accurate.

## Project Overview

This is a Splunk Add-on for MaxMind GeoIP lookups, built using the Splunk UCC (Universal Configuration Console) framework. It provides a custom streaming search command (`maxmind`) that enriches events with data from MaxMind databases (country, city, anonymous IP, ISP, etc.).

## The maxmind Command

```
| maxmind [prefix=<string>] [field=<string>] databases=<databases>
```

- `databases` (required): Comma-separated list of database names. **Must be quoted if multiple** (e.g., `databases="GeoIP2-Country,GeoIP2-Anonymous-IP"`)
- `field` (optional, default `ip`): Event field containing the IP address
- `prefix` (optional, default empty): Prefix for output field names

Behavior:
- Queries each database and merges all fields into the event
- When databases have conflicting fields, the last database wins
- The `network` field contains the most specific (smallest) CIDR block across all databases
- Database names are validated to only allow alphanumeric characters and hyphens (security measure against path traversal)
- Events with missing, empty, invalid, or not-found IPs pass through unchanged

End-user documentation is in `package/README.txt`.

### Command Architecture

The command implementation in `maxmind_command.py` exposes a `stream(command, events)` function that the UCC-generated wrapper calls. The `command` parameter follows a `Protocol` with `databases`, `field`, and `prefix` attributes.

Database readers are cached at module level in `_readers`. This means:
- Databases are opened once and reused across events (good for performance)
- If a database file is updated on disk, the old data continues to be served until the process restarts
- The TODOs in the code note that database reloading needs to be implemented

## Build Commands

```bash
# Setup environment
mise install                      # Install Python 3.13
uv sync                           # Install build dependencies
git submodule update --init       # Initialize test data submodule

# Build the add-on
./build.sh      # Generates output/ directory and .tar.gz package

# Run tests
uv run tox -e 3.13

# Lint
uv run tox -e lint

# Install to Splunk (requires Splunk 10.2)
splunk install app /path/to/demo_addon_for_splunk-1.0.0.tar.gz
splunk install app /path/to/demo_addon_for_splunk-1.0.0.tar.gz -update true  # Update existing
```

## Project Structure

```
demo_addon_for_splunk/
├── globalConfig.json      # Main configuration file for UCC framework
├── package/
│   ├── app.manifest       # Add-on metadata (author, version, description)
│   ├── README.txt         # End-user documentation (included in package)
│   ├── default/
│   │   ├── app.conf       # Splunk app configuration (merged with generated)
│   │   └── commands.conf  # Search command configuration (replaces generated)
│   ├── bin/               # Python scripts (inputs, custom commands)
│   ├── lib/
│   │   └── requirements.txt  # Python dependencies for the add-on
│   ├── static/            # Icons and images
│   └── data/              # Data files (e.g., MaxMind databases)
```

## Tests

Tests live in `tests/` and use pytest. Test data comes from the `MaxMind-DB` git submodule at `tests/data/`.

```
tests/
├── conftest.py              # Sets MAXMIND_DB_DIR to test database directory
├── data/                    # MaxMind-DB submodule (git submodule)
│   └── test-data/           # Contains test .mmdb files
└── maxmind_command_test.py  # Tests using various test databases
```

The `MAXMIND_DB_DIR` environment variable overrides the database directory, allowing tests to use test databases from the MaxMind-DB submodule instead of production databases.

Test IPs from GeoIP2-Country-Test.mmdb:
- `214.78.120.1` (in `214.78.120.0/22`) → US
- `2001:218::1` (in `2001:218::/32`) → JP
- `2001:220::1` (in `2001:220::1/128`) → KR

For multi-database testing, `89.160.20.112` is useful as it exists in multiple test databases:
- GeoIP2-Country-Test (`/28`) → SE
- GeoIP2-City-Test (`/28`) → SE, Linköping
- GeoIP2-ISP-Test (`/29`) → Linköping Universitet

This IP is good for testing field merging and smallest-network selection.

## Linting

Uses ruff (linting + formatting) and mypy (type checking), orchestrated via tox (`uv run tox -e lint`). UCC-generated files like `demo_input_helper.py` are excluded from linting in `pyproject.toml`.

## Key Configuration Files

### globalConfig.json

The main UCC configuration file. Defines:
- Input types and their parameters
- Configuration tabs (accounts, logging)
- Custom search commands (use `defaultValue` not `default` for argument defaults)
- UI settings

### package/app.manifest

JSON file with add-on metadata. Note: The `version` field here should match `globalConfig.json` for consistency, but UCC uses the version from `globalConfig.json` as the source of truth and overwrites `app.manifest` during build.

```json
{
  "info": {
    "author": [{"name": "...", "email": "...", "company": "..."}],
    "title": "...",
    "description": "..."
  }
}
```

### package/default/app.conf

Custom settings merged into the generated `app.conf`. Example:
```ini
[launcher]
author = William Storey
```

### package/default/commands.conf

Custom search command configuration. Unlike `app.conf`, UCC **replaces** (not merges) this file, so you must include all required settings:
```ini
[maxmind]
filename = maxmind.py
chunked = true
python.version = python3
python.required = 3.13
```

- `chunked = true` is required for streaming commands using the Splunk SDK
- `python.version` is for backward compatibility with Splunk < 10.2
- `python.required` is used by Splunk 10.2+ (takes precedence over `python.version`)

## Dependencies

- **Build dependencies**: in `pyproject.toml` (managed by uv)
- **Add-on runtime dependencies**: in `package/lib/requirements.txt` (installed into add-on's lib/)

When updating dependencies, check both locations to ensure they stay in sync.

## UCC Framework Behavior

- UCC generates `.conf` files in the output `default/` directory
- For `app.conf`: UCC merges your settings with generated ones
- For `commands.conf`: UCC **replaces** the generated file entirely with yours (include all required settings)
- UCC automatically sets `python.version = python3` in generated `commands.conf` and `inputs.conf`
- Warning about "not auto generated by UCC framework" for custom settings is expected
- `ucc-gen init` creates a `README.md` in the addon source directory, but it's not needed and doesn't get included in the output package. Use `package/README.txt` for end-user documentation instead.

### Custom Search Command File Naming

UCC generates a wrapper script for custom search commands. The naming works as follows:

- `globalConfig.json` specifies `commandName` (e.g., `"maxmind"`) and `fileName` (e.g., `"maxmind_command.py"`)
- UCC generates a wrapper named `<commandName>.py` (e.g., `maxmind.py`) that imports from your `fileName`
- `commands.conf` must reference the **wrapper** name (`filename = maxmind.py`), not the source file

The generated wrapper (`output/.../bin/maxmind.py`) looks like:
```python
from maxmind_command import stream

class MaxmindCommand(StreamingCommand):
    def stream(self, events):
        return stream(self, events)
```

So the source file (`maxmind_command.py`) and wrapper (`maxmind.py`) are intentionally different files.

## Splunk Python Version Configuration

In Splunk 10.2+, `python.version` is deprecated. Use `python.required` instead:
- `python.required = 3.13` uses just the version number (not "python3.13")
- Default `python.version = python3` resolves to Python 3.9 in Splunk 10.2, not the latest
- Include both settings for backward compatibility with older Splunk versions
- The `maxminddb` 3.0.0 package requires Python 3.10+ (uses `kw_only` in dataclasses)

## Reinstalling the Add-on

When reinstalling, fully remove the old app first to avoid cached libraries:
```bash
splunk remove app demo_addon_for_splunk
splunk restart
splunk install app /path/to/demo_addon_for_splunk-1.0.0.tar.gz
```

## Key Constraints

- Always run linters (`uv run tox -e lint`), tests (`uv run tox -e 3.13`), and `./build.sh` before considering any changes complete
- The `author` field in `package/default/app.conf` must exactly match the first author name in `package/app.manifest`

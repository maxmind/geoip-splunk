"""Post-build hook for UCC framework to copy files from repo root."""

import shutil
from pathlib import Path


def additional_packaging(ta_name: str) -> None:
    """Copy LICENSE files and README.md from repo root into the built app."""
    repo_root = Path(__file__).parent.parent
    output_dir = Path("output") / ta_name

    for license_file in ["LICENSE-MIT", "LICENSE-APACHE"]:
        src = repo_root / license_file
        shutil.copy(src, output_dir / "LICENSES" / license_file)

    shutil.copy(repo_root / "README.md", output_dir / "README.md")

    make_command_search_head_only(output_dir)


def make_command_search_head_only(output_dir: Path) -> None:
    """Force the geoip search command to run only on the search head.

    UCC generates the command wrapper (bin/geoip.py) with a bare
    ``@Configuration()`` decorator. Under Search Command Protocol v2
    (``chunked = true``) the Splunk SDK then reports the command as
    distributable streaming, so Splunk pushes it down to the indexers. The
    MaxMind databases live in the search head's app ``local/data`` directory,
    not on the indexers, so without this users have to prepend ``| localop``
    to every search.

    Passing ``distributed=False`` makes the SDK report the command type as
    ``stateful`` (search-head-only) - the built-in equivalent of ``localop``.
    ``local = true`` in commands.conf does not achieve this: it is an SCP1-only
    setting and is ignored for chunked commands.

    UCC has no globalConfig knob for this and its template hardcodes
    ``@Configuration()``, so we rewrite the generated wrapper here.
    """
    wrapper = output_dir / "bin" / "geoip.py"
    source = wrapper.read_text()
    marker = "@Configuration()"
    if marker not in source:
        msg = (
            f"Expected {marker!r} in {wrapper}; the UCC custom command "
            "template may have changed - update make_command_search_head_only."
        )
        raise RuntimeError(msg)
    wrapper.write_text(source.replace(marker, "@Configuration(distributed=False)"))

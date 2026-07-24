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

    make_command_distribution_toggleable(output_dir)


def make_command_distribution_toggleable(output_dir: Path) -> None:
    """Let the geoip command decide at search time whether to distribute.

    Under Search Command Protocol v2 (``chunked = true``), whether Splunk
    pushes the command to the indexers is controlled by the ``distributed``
    configuration setting in the command's getinfo reply, not by
    commands.conf (``local = true`` is SCP1-only and ignored). The Splunk
    SDK calls a command's ``prepare()`` method before writing that reply,
    so a prepare() that sets ``self.configuration.distributed`` from the
    "Run on indexers" setting decides distribution per search.

    UCC generates the command wrapper (bin/geoip.py) from a fixed template
    with no extension point, so this hook rewrites the generated wrapper:

    - import ``prepare`` from geoip_command.py alongside ``stream``
    - inject a ``prepare()`` method that delegates to it
    - change the bare ``@Configuration()`` decorator to
      ``@Configuration(distributed=False)`` as a fail-safe default in case
      prepare() somehow does not run (search-head-only is always safe)

    Each marker is verified so a UCC template change fails the build loudly
    rather than silently regressing.
    """
    wrapper = output_dir / "bin" / "geoip.py"
    source = wrapper.read_text()
    source = _replace_marker(
        source,
        wrapper,
        "from geoip_command import stream",
        "from geoip_command import prepare, stream",
    )
    source = _replace_marker(
        source,
        wrapper,
        "@Configuration()",
        "@Configuration(distributed=False)",
    )
    source = _replace_marker(
        source,
        wrapper,
        "    def stream(self, events):",
        "    def prepare(self):\n"
        "        prepare(self)\n"
        "\n"
        "    def stream(self, events):",
    )
    wrapper.write_text(source)


def _replace_marker(source: str, wrapper: Path, marker: str, replacement: str) -> str:
    """Replace marker in source, raising if it is not present."""
    if marker not in source:
        msg = (
            f"Expected {marker!r} in {wrapper}; the UCC custom command "
            "template may have changed - update "
            "make_command_distribution_toggleable."
        )
        raise RuntimeError(msg)
    return source.replace(marker, replacement)

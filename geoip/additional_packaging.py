"""Post-build hook for UCC framework to copy files from repo root.

Keep the imports here stdlib-only. UCC calls this hook inside a
"try: ... except ImportError" (ucc_framework/commands/build.py), so an
ImportError raised transitively from in here is swallowed with an INFO log
and the build still exits 0 with the rewrite below silently skipped.
build.sh verifies the rewrite afterwards, outside that try, as a backstop.
"""

import json
import shutil
from pathlib import Path

_GLOBAL_CONFIG_PATH = Path(__file__).resolve().parent / "globalConfig.json"

# UCC's wrapper templates by commandType: the entry point the wrapper
# imports from the command's source module, and the line of the generated
# wrapper the prepare() method is injected before.
_COMMAND_ENTRY_POINTS = {
    "streaming": ("stream", "    def stream(self, events):"),
    "generating": ("generate", "    def generate(self):"),
}


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
    """Let the commands decide at search time whether to distribute.

    Under Search Command Protocol v2 (``chunked = true``), whether Splunk
    pushes a command to the indexers is controlled by the ``distributed``
    configuration setting in the command's getinfo reply, not by
    commands.conf (``local = true`` is SCP1-only and ignored). The Splunk
    SDK calls a command's ``prepare()`` method before writing that reply,
    so a prepare() that sets ``self.configuration.distributed`` decides
    distribution per search: the geoip command reads the "Run on indexers"
    setting, and the geoipdebug command reads its own ``indexers``
    argument.

    UCC generates the command wrappers (bin/geoip.py, bin/geoipdebug.py)
    from fixed templates with no extension point, so this hook rewrites
    the generated wrappers:

    - import ``prepare`` from the command's source module alongside its
      entry point
    - inject a ``prepare()`` method that delegates to it
    - change the bare ``@Configuration()`` decorator to
      ``@Configuration(distributed=False)`` as a fail-safe default in case
      prepare() somehow does not run (search-head-only is always safe)

    The command list is read from globalConfig.json rather than hardcoded,
    so a command added there cannot ship without the rewrite - a
    StreamingCommand wrapper left with UCC's bare ``@Configuration()``
    reports distributable streaming and is dispatched to indexers whose
    bundle carries almost none of lib/. A commandType this map does not
    cover raises KeyError (which UCC's except ImportError does not
    swallow), and each marker is verified so a UCC template change fails
    the build loudly rather than silently regressing.
    """
    commands = json.loads(_GLOBAL_CONFIG_PATH.read_text())["customSearchCommand"]
    for command in commands:
        entry_point, method_marker = _COMMAND_ENTRY_POINTS[command["commandType"]]
        module = command["fileName"].removesuffix(".py")
        imports = ", ".join(sorted([entry_point, "prepare"]))
        _inject_prepare(
            output_dir / "bin" / (command["commandName"] + ".py"),
            import_marker=f"from {module} import {entry_point}",
            import_replacement=f"from {module} import {imports}",
            method_marker=method_marker,
        )


def _inject_prepare(
    wrapper: Path,
    *,
    import_marker: str,
    import_replacement: str,
    method_marker: str,
) -> None:
    """Rewrite a generated command wrapper to delegate prepare().

    Imports ``prepare`` from the command's source module, injects a
    ``prepare()`` method before the wrapper's entry method, and changes
    the bare ``@Configuration()`` decorator to
    ``@Configuration(distributed=False)``.
    """
    source = wrapper.read_text()
    source = _replace_marker(
        source,
        wrapper,
        import_marker,
        import_replacement,
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
        method_marker,
        "    def prepare(self):\n        prepare(self)\n\n" + method_marker,
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

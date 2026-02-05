"""Post-build hook for UCC framework to copy LICENSE files from repo root."""

import shutil
from pathlib import Path


def additional_packaging(ta_name: str) -> None:
    """Copy LICENSE files from repo root into the built add-on."""
    repo_root = Path(__file__).parent.parent
    output_licenses = Path("output") / ta_name / "LICENSES"

    for license_file in ["LICENSE-MIT", "LICENSE-APACHE"]:
        src = repo_root / license_file
        shutil.copy(src, output_licenses / license_file)

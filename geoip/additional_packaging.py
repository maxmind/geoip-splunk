"""Post-build hook for UCC framework to copy files from repo root."""

import shutil
from pathlib import Path


def additional_packaging(ta_name: str) -> None:
    """Copy LICENSE files and README.md from repo root into the built add-on."""
    repo_root = Path(__file__).parent.parent
    output_dir = Path("output") / ta_name

    for license_file in ["LICENSE-MIT", "LICENSE-APACHE"]:
        src = repo_root / license_file
        shutil.copy(src, output_dir / "LICENSES" / license_file)

    shutil.copy(repo_root / "README.md", output_dir / "README.md")

import sys
from pathlib import Path

# Add the package bin and lib directories to the path
repo_root = Path(__file__).parent.parent
bin_dir = repo_root / "demo_addon_for_splunk" / "package" / "bin"
lib_dir = repo_root / "demo_addon_for_splunk" / "package" / "lib"
sys.path.insert(0, str(bin_dir))
sys.path.insert(0, str(lib_dir))

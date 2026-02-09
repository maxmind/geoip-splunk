import os
import sys
from pathlib import Path

# Set the test database directory before importing maxmind_command
repo_root = Path(__file__).parent.parent
test_db_dir = repo_root / "tests" / "data" / "test-data"
os.environ["MAXMIND_DB_DIR"] = str(test_db_dir)

# Add the package bin and lib directories to the path
bin_dir = repo_root / "geoip" / "package" / "bin"
lib_dir = repo_root / "geoip" / "package" / "lib"
sys.path.insert(0, str(bin_dir))
sys.path.insert(0, str(lib_dir))

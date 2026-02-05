import os
import sys
from pathlib import Path

# Set the test database directory before importing maxmind_command
repo_root = Path(__file__).parent.parent
test_db_dir = repo_root / "tests" / "data" / "test-data"
os.environ["MAXMIND_DB_DIR"] = str(test_db_dir)

# Add the package bin directory to the path
bin_dir = repo_root / "geoip" / "package" / "bin"
sys.path.insert(0, str(bin_dir))

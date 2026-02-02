import os
import sys
from pathlib import Path

# Set the test database path before importing maxmind_command
repo_root = Path(__file__).parent.parent
test_db = repo_root / "tests" / "data" / "test-data" / "GeoIP2-Country-Test.mmdb"
os.environ["MAXMIND_DB_PATH"] = str(test_db)

# Add the package bin directory to the path
bin_dir = repo_root / "demo_addon_for_splunk" / "package" / "bin"
sys.path.insert(0, str(bin_dir))

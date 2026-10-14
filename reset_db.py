"""Reset the working database to the original shop data before a full run."""
import shutil
import sys

sys.path.insert(0, "backend")
from config import DB_PATH, ORIGINAL_DB  # noqa: E402

shutil.copyfile(ORIGINAL_DB, DB_PATH)
DB_PATH.chmod(0o644)
print(f"Reset {DB_PATH.name} from {ORIGINAL_DB.name}")

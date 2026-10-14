"""Shared settings for the HW5 backend, agents and MCP link.

Both the backend and the MCP server use the working copy. The original
database is never written to; reset copies it back over the working copy.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

HW_DIR = Path(__file__).resolve().parent.parent
ORIGINAL_DB = HW_DIR / "data" / "campus_customs.db"
DB_PATH = HW_DIR / "data" / "campus_customs_new.db"
MCP_SERVER = HW_DIR / "MCP_server" / "server.py"
PYTHON = HW_DIR / ".venv" / "bin" / "python"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AUDIT_PATH = HW_DIR / "output" / "audit_trail.json"

# Every agent runs on this one model through Portkey. No other model appears anywhere.
MODEL_NAME = "gpt-5.6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Token guardrails, shared across all five agents for one ticket run.
REQUEST_LIMIT = 40          # model calls per ticket
TOOL_CALLS_LIMIT = 60       # MCP + delegate calls per ticket
TOTAL_TOKENS_LIMIT = 400_000
MAX_DELEGATIONS = 6         # delegate calls per ticket
MAX_DEPTH = 3               # boss -> specialist -> specialist -> specialist
MAX_OUTPUT_TOKENS = 4_000   # per model response

FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def load_env() -> None:
    """Load .env files from hw-5 up to the home directory (course-root .env holds PORTKEY_API_KEY)."""
    for folder in [HW_DIR, *HW_DIR.parents]:
        if (folder / ".env").is_file():
            load_dotenv(folder / ".env")
        if folder == Path.home():
            break


load_env()
PORTKEY_API_KEY = os.environ.get("PORTKEY_API_KEY")

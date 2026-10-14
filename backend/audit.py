"""Append-only audit trail at output/audit_trail.json (a JSON array; never wiped)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from config import AUDIT_PATH

_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clip(value: Any, limit: int = 1500) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "...[clipped]"


def _load() -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    try:
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Never destroy history: keep the unreadable file aside and start a new array.
        AUDIT_PATH.rename(AUDIT_PATH.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json"))
        return []


def append(event: dict) -> dict:
    with _lock:
        entries = _load()
        event = {"seq": (entries[-1]["seq"] + 1) if entries else 1, "ts": now_iso(), **event}
        entries.append(event)
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = AUDIT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
        tmp.replace(AUDIT_PATH)
        return event


def read(run_id: str | None = None, ticket_id: int | None = None, after: int = 0) -> list[dict]:
    with _lock:
        entries = _load()
    return [e for e in entries
            if e.get("seq", 0) > after
            and (run_id is None or e.get("run_id") == run_id)
            and (ticket_id is None or e.get("ticket_id") == ticket_id)]

"""
Session persistence for ish-harness.
Saves and loads conversation history as JSON files.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .providers import Message


def _sessions_dir(cfg_sessions_dir: str) -> Path:
    p = Path(os.path.expanduser(cfg_sessions_dir))
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_session(
    messages: list[Message],
    name: Optional[str],
    provider: str,
    model: str,
    sessions_dir: str = "~/.harness/sessions",
) -> Path:
    """Serialise and save a session. Returns the file path."""
    sdir = _sessions_dir(sessions_dir)
    if not name:
        name = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = sdir / f"{name}.json"

    data = {
        "name":     name,
        "saved_at": datetime.now().isoformat(),
        "provider": provider,
        "model":    model,
        "messages": [
            {
                "role":    m.role,
                "content": m.content,
                **({"tool_calls":    m.tool_calls}   if m.tool_calls    else {}),
                **({"tool_call_id": m.tool_call_id}  if m.tool_call_id  else {}),
                **({"name":         m.name}          if m.name          else {}),
            }
            for m in messages
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def load_session(name: str, sessions_dir: str = "~/.harness/sessions") -> tuple[list[Message], dict]:
    """Load a session. Returns (messages, meta_dict)."""
    sdir = _sessions_dir(sessions_dir)
    path = sdir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Session not found: {name}")

    data = json.loads(path.read_text())
    messages = [
        Message(
            role=m["role"],
            content=m.get("content", ""),
            tool_calls=m.get("tool_calls"),
            tool_call_id=m.get("tool_call_id"),
            name=m.get("name"),
        )
        for m in data.get("messages", [])
    ]
    meta = {k: v for k, v in data.items() if k != "messages"}
    return messages, meta


def list_sessions(sessions_dir: str = "~/.harness/sessions") -> list[dict]:
    """Return a sorted list of session metadata dicts."""
    sdir = _sessions_dir(sessions_dir)
    sessions = []
    for f in sorted(sdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "name":     data.get("name", f.stem),
                "saved_at": data.get("saved_at", ""),
                "provider": data.get("provider", "?"),
                "model":    data.get("model", "?"),
                "messages": len(data.get("messages", [])),
            })
        except Exception:
            pass
    return sessions


def autosave(
    messages: list[Message],
    provider: str,
    model: str,
    sessions_dir: str = "~/.harness/sessions",
):
    """Write a rolling autosave file."""
    try:
        save_session(messages, "_autosave", provider, model, sessions_dir)
    except Exception:
        pass

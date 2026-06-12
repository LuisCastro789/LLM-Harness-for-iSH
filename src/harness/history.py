"""
readline / history integration for ish-harness.

Uses the standard `readline` module (available in Alpine Python).
Falls back gracefully if readline is unavailable (e.g. minimal builds).
"""

import os
from pathlib import Path

_rl_available = False

try:
    import readline
    _rl_available = True
except ImportError:
    pass


def setup_readline(history_file: str, max_history: int = 1000):
    """Configure readline with persistent history and sensible keybindings."""
    if not _rl_available:
        return

    hist_path = Path(os.path.expanduser(history_file))
    hist_path.parent.mkdir(parents=True, exist_ok=True)

    if hist_path.exists():
        try:
            readline.read_history_file(str(hist_path))
        except Exception:
            pass

    readline.set_history_length(max_history)

    # Basic tab completion placeholder — can be expanded
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set editing-mode emacs")

    # Register history save at interpreter exit
    import atexit
    atexit.register(_save_history, str(hist_path))


def _save_history(path: str):
    if not _rl_available:
        return
    try:
        readline.write_history_file(path)
    except Exception:
        pass


def add_history(line: str):
    if not _rl_available:
        return
    try:
        readline.add_history(line)
    except Exception:
        pass

"""
Tests for ish-harness core modules.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness.config import load_config, _defaults, Config
from harness.providers import Message
from harness.agent import _parse_tool_call
from harness.tools import ShellTool, ReadFileTool, WriteFileTool, GrepTool, ListDirTool, dispatch_tool
from harness.themes import get_theme, THEMES
from harness.sessions import save_session, load_session, list_sessions


# ── config ────────────────────────────────────────────────────────────────────

def test_default_config():
    cfg = _defaults()
    assert isinstance(cfg, Config)
    assert "openai" in cfg.providers
    assert "gemma" in cfg.providers
    assert "anthropic" in cfg.providers
    assert "gemini" in cfg.providers
    assert "ollama" in cfg.providers


def test_load_config_missing_file():
    cfg = load_config(Path("/tmp/does_not_exist_harness.toml"))
    assert cfg is not None
    assert cfg.default_provider == "openai"


def test_provider_config():
    cfg = _defaults()
    pcfg = cfg.get_provider("openai")
    assert pcfg.api_key_env == "OPENAI_API_KEY"
    assert pcfg.base_url == "https://api.openai.com/v1"


# ── tools ─────────────────────────────────────────────────────────────────────

def test_shell_tool_echo():
    tool = ShellTool()
    result = tool.run({"command": "echo hello"})
    assert "hello" in result


def test_shell_tool_timeout():
    tool = ShellTool()
    result = tool.run({"command": "sleep 10", "timeout": 1})
    assert "timed out" in result.lower() or "error" in result.lower()


def test_write_and_read_file():
    with tempfile.TemporaryDirectory() as tmp:
        wt = WriteFileTool()
        rt = ReadFileTool()

        path = os.path.join(tmp, "test.txt")
        wt.run({"path": path, "content": "line1\nline2\n"})

        result = rt.run({"path": path})
        assert "line1" in result
        assert "line2" in result


def test_grep_tool():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.txt")
        Path(path).write_text("hello world\nfoo bar\nhello again\n")
        tool = GrepTool()
        result = tool.run({"pattern": "hello", "path": path, "recursive": False})
        assert "hello" in result


def test_list_dir():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp + "/a.txt").write_text("a")
        Path(tmp + "/b.txt").write_text("b")
        tool = ListDirTool()
        result = tool.run({"path": tmp})
        assert "a.txt" in result
        assert "b.txt" in result


def test_dispatch_unknown_tool():
    result = dispatch_tool("nonexistent_tool", {})
    assert "unknown tool" in result


# ── provider helpers ──────────────────────────────────────────────────────────

def test_parse_openai_tool_call():
    tc = {
        "id": "call_abc",
        "type": "function",
        "function": {"name": "shell", "arguments": '{"command": "ls"}'},
    }
    call_id, name, args = _parse_tool_call(tc)
    assert call_id == "call_abc"
    assert name == "shell"
    assert args == {"command": "ls"}


def test_parse_anthropic_tool_call():
    tc = {
        "type": "tool_use",
        "id": "toolu_01",
        "name": "read_file",
        "input": {"path": "/tmp/test.txt"},
    }
    call_id, name, args = _parse_tool_call(tc)
    assert call_id == "toolu_01"
    assert name == "read_file"
    assert args == {"path": "/tmp/test.txt"}


# ── themes ────────────────────────────────────────────────────────────────────

def test_all_themes_load():
    for name in ("dark", "light", "monokai", "solarized"):
        theme = get_theme(name)
        assert theme.name == name
        assert theme.reset


def test_unknown_theme_fallback():
    theme = get_theme("doesnotexist")
    assert theme.name == "dark"


# ── sessions ─────────────────────────────────────────────────────────────────

def test_save_and_load_session():
    with tempfile.TemporaryDirectory() as tmp:
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        path = save_session(messages, "test_session", "openai", "gpt-4o", sessions_dir=tmp)
        assert path.exists()

        loaded, meta = load_session("test_session", sessions_dir=tmp)
        assert len(loaded) == 2
        assert loaded[0].role == "user"
        assert loaded[0].content == "Hello"
        assert meta["provider"] == "openai"


def test_list_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        msgs = [Message(role="user", content="test")]
        save_session(msgs, "sess1", "anthropic", "claude-3-5-sonnet-20241022", sessions_dir=tmp)
        save_session(msgs, "sess2", "gemma", "google/gemma-3-27b-it", sessions_dir=tmp)

        sessions = list_sessions(sessions_dir=tmp)
        names = [s["name"] for s in sessions]
        assert "sess1" in names
        assert "sess2" in names

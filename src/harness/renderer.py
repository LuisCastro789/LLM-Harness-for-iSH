"""
TUI rendering layer for ish-harness.

Handles all terminal output using ANSI escape codes + Unicode box-drawing.
Designed for the iSH VT100 terminal (no curses, no external deps).
"""

import os
import sys
import shutil
import textwrap
import time
from typing import Optional

from .themes import Theme, get_theme, THEMES


class Renderer:
    """
    Stateful terminal renderer.

    Writes directly to stdout. Works in any VT100/ANSI terminal including iSH.
    """

    # Box-drawing chars (single-line)
    H = "─"
    V = "│"
    TL = "╭"
    TR = "╮"
    BL = "╰"
    BR = "╯"
    TEE_L = "├"
    TEE_R = "┤"

    def __init__(self, theme_name: str = "dark"):
        self.theme: Theme = get_theme(theme_name)
        self._stream_active = False
        self._last_stream_len = 0

    def set_theme(self, name: str):
        self.theme = get_theme(name)

    # ── terminal info ─────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        try:
            return shutil.get_terminal_size((80, 24)).columns
        except Exception:
            return 80

    # ── raw output helpers ────────────────────────────────────────────────────

    def _w(self, text: str):
        sys.stdout.write(text)
        sys.stdout.flush()

    def _wl(self, text: str = ""):
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def _styled(self, code: str, text: str) -> str:
        t = self.theme
        return f"{code}{text}{t.reset}"

    # ── structural elements ───────────────────────────────────────────────────

    def rule(self, label: str = "", char: str = "─"):
        t = self.theme
        w = self.width
        if label:
            inner = f" {label} "
            line_len = max(0, (w - len(inner)) // 2)
            line = char * line_len
            self._wl(self._styled(t.border, line) + self._styled(t.muted, inner) + self._styled(t.border, line))
        else:
            self._wl(self._styled(t.border, char * w))

    def header(self):
        t = self.theme
        w = self.width
        self._wl()
        self.rule()
        title = "  ish-harness  "
        subtitle = "  agentic LLM CLI for iSH  "
        self._wl(self._styled(t.ai_label, title.center(w)))
        self._wl(self._styled(t.muted, subtitle.center(w)))
        self.rule()
        self._wl()

    def box(self, lines: list[str], title: str = "", style: str = ""):
        """Draw a rounded box around lines of text."""
        t = self.theme
        code = style or t.border
        w = self.width - 4
        inner_w = w

        def _border(s: str) -> str:
            return self._styled(code, s)

        title_str = ""
        if title:
            title_str = f" {self._styled(t.info, title)} "

        top = self.TL + self.H * 2 + title_str + self.H * max(0, inner_w - 2 - len(title)) + self.TR
        self._wl(_border(self.TL + self.H * 2) + (title_str if title else "") + _border(self.H * max(0, inner_w - 2 - len(title)) + self.TR))

        for line in lines:
            wrapped = textwrap.wrap(line, width=inner_w - 2) or [""]
            for seg in wrapped:
                padding = " " * (inner_w - 2 - len(seg))
                self._wl(_border(self.V + " ") + seg + padding + _border(" " + self.V))

        self._wl(_border(self.BL + self.H * (inner_w) + self.BR))

    def info(self, msg: str):
        t = self.theme
        self._wl(self._styled(t.info, f"ℹ  {msg}"))

    def warn(self, msg: str):
        t = self.theme
        self._wl(self._styled(t.warn, f"⚠  {msg}"))

    def error(self, msg: str):
        t = self.theme
        self._wl(self._styled(t.error, f"✗  {msg}"))

    def success(self, msg: str):
        t = self.theme
        self._wl(self._styled(t.success, f"✓  {msg}"))

    # ── conversation display ──────────────────────────────────────────────────

    def user_turn(self, text: str):
        t = self.theme
        w = self.width
        self._wl()
        self._wl(self._styled(t.user_label, "╭─ You ") + self._styled(t.border, self.H * max(0, w - 7)))
        for line in text.splitlines() or [""]:
            self._wl(self._styled(t.border, self.V + " ") + line)
        self._wl(self._styled(t.border, self.BL + self.H * (w - 2)))

    def ai_turn_start(self, provider_name: str = "AI"):
        t = self.theme
        w = self.width
        self._wl()
        label = f"╭─ {provider_name} "
        self._wl(self._styled(t.ai_label, label) + self._styled(t.border, self.H * max(0, w - len(label))))
        self._w(self._styled(t.border, self.V + " "))
        self._stream_active = True
        self._last_stream_len = 0

    def stream_token(self, token: str):
        """Write a streaming token, handling newlines within the box."""
        t = self.theme
        if not self._stream_active:
            return
        for ch in token:
            if ch == "\n":
                self._wl()
                self._w(self._styled(t.border, self.V + " "))
                self._last_stream_len = 0
            else:
                self._w(ch)
                self._last_stream_len += 1

    def ai_turn_end(self, response=None):
        t = self.theme
        w = self.width
        self._wl()
        if response:
            stats = []
            if response.input_tokens or response.output_tokens:
                stats.append(f"↑{response.input_tokens} ↓{response.output_tokens} tok")
            if response.elapsed:
                stats.append(f"{response.elapsed:.1f}s")
            if stats:
                stat_str = "  " + " · ".join(stats) + "  "
                bottom = self.BL + self.H * max(0, w - 2 - len(stat_str)) + stat_str
                self._wl(self._styled(t.border, self.BL + self.H * max(0, w - 2 - len(stat_str))) + self._styled(t.muted, stat_str.rstrip()))
                self._stream_active = False
                return
        self._wl(self._styled(t.border, self.BL + self.H * (w - 2)))
        self._stream_active = False

    def tool_call_display(self, name: str, args: dict):
        t = self.theme
        import json
        self._wl()
        self._wl(self._styled(t.tool_label, f"  ⚙  tool: {name}"))
        try:
            pretty = json.dumps(args, indent=2)
        except Exception:
            pretty = str(args)
        for line in pretty.splitlines():
            self._wl(self._styled(t.code, f"     {line}"))

    def tool_result_display(self, name: str, result: str, max_lines: int = 15):
        t = self.theme
        lines = result.splitlines()
        truncated = len(lines) > max_lines
        shown = lines[:max_lines]
        self._wl(self._styled(t.tool_result, f"  ↳  {name} result:"))
        for line in shown:
            self._wl(self._styled(t.tool_result, f"     {line}"))
        if truncated:
            self._wl(self._styled(t.muted, f"     … ({len(lines) - max_lines} more lines)"))
        self._wl()

    # ── confirmation prompt ───────────────────────────────────────────────────

    def confirm(self, tool_name: str, args: dict) -> bool:
        """Ask user to approve a potentially destructive tool call. Returns True if approved."""
        t = self.theme
        import json
        self._wl()
        self._wl(self._styled(t.warn, f"  ⚠  The agent wants to run tool: {tool_name}"))
        try:
            preview = json.dumps(args, indent=2)
        except Exception:
            preview = str(args)
        for line in preview.splitlines():
            self._wl(self._styled(t.code, f"     {line}"))
        self._w(self._styled(t.warn, "  Allow? [y/N] "))
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        return answer in ("y", "yes")

    # ── prompt ────────────────────────────────────────────────────────────────

    def prompt_input(self, prefix: str = "") -> str:
        t = self.theme
        self._wl()
        indicator = self._styled(t.prompt, "❯ ")
        if prefix:
            self._w(self._styled(t.muted, f"  {prefix}\n"))
        self._w(indicator)
        try:
            return input()
        except EOFError:
            return "/exit"

    # ── slash-command help ────────────────────────────────────────────────────

    def help_text(self, providers: list[str]):
        t = self.theme
        self._wl()
        self.rule("commands")
        cmds = [
            ("/help",              "Show this help"),
            ("/exit  or  /quit",   "Exit harness"),
            ("/clear",             "Clear conversation history"),
            ("/reset",             "Hard reset (history + tool counter)"),
            ("/provider <name>",   f"Switch provider  [{', '.join(providers)}]"),
            ("/model <name>",      "Override model for current session"),
            ("/theme <name>",      "Switch theme  [dark, light, monokai, solarized]"),
            ("/tools",             "List available agent tools"),
            ("/sessions",          "List saved sessions"),
            ("/save [name]",       "Save current session"),
            ("/load <name>",       "Load a saved session"),
            ("/status",            "Show current config & provider"),
            ("/system <text>",     "Override system prompt for this session"),
            ("/multiline",         "Enter multi-line input mode (end with .)"),
        ]
        max_cmd = max(len(c) for c, _ in cmds)
        for cmd, desc in cmds:
            self._wl(
                self._styled(t.highlight, f"  {cmd:<{max_cmd + 2}}") +
                self._styled(t.muted, desc)
            )
        self._wl()

    def tool_list(self, tool_names: list[str]):
        t = self.theme
        self.rule("tools")
        from .tools import TOOL_MAP
        for name in tool_names:
            tool = TOOL_MAP.get(name)
            desc = tool.description if tool else ""
            self._wl(self._styled(t.tool_label, f"  {name:<16}") + self._styled(t.muted, desc))
        self._wl()

    def status(self, provider_name: str, model: str, theme: str, history_len: int):
        t = self.theme
        self.rule("status")
        pairs = [
            ("provider", provider_name),
            ("model",    model),
            ("theme",    theme),
            ("history",  f"{history_len} messages"),
        ]
        for k, v in pairs:
            self._wl(self._styled(t.info, f"  {k:<12}") + self._styled(t.highlight, v))
        self._wl()

    def multiline_prompt(self) -> str:
        """Multi-line input mode. User ends with a lone '.' on a line."""
        t = self.theme
        self._wl(self._styled(t.info, "  Multi-line mode. Enter '.' on a blank line to finish."))
        lines = []
        while True:
            self._w(self._styled(t.muted, "  … "))
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if line == ".":
                break
            lines.append(line)
        return "\n".join(lines)

    def spinner(self, message: str = "Thinking"):
        """Returns a context manager that shows an animated spinner."""
        return _Spinner(self, message)


class _Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, renderer: Renderer, message: str):
        self.r = renderer
        self.message = message
        self._thread = None
        self._stop = False

    def __enter__(self):
        import threading
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        t = self.r.theme
        i = 0
        while not self._stop:
            frame = self.FRAMES[i % len(self.FRAMES)]
            msg = f"\r  {self.r._styled(t.info, frame)}  {self.r._styled(t.muted, self.message)}  "
            self.r._w(msg)
            time.sleep(0.08)
            i += 1

    def __exit__(self, *_):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=0.5)
        self.r._w("\r" + " " * (len(self.message) + 8) + "\r")
        sys.stdout.flush()

"""
Agent tools available to LLMs inside ish-harness.

Each tool exposes:
  - schema()    → dict  (OpenAI function-calling / Anthropic tool schema)
  - run(args)   → str   (result returned to the LLM)
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional


# ── shell exec ────────────────────────────────────────────────────────────────

class ShellTool:
    name = "shell"
    description = "Execute a shell command and return stdout/stderr. Use for file operations, running scripts, installing packages, etc."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute"},
                        "workdir": {"type": "string", "description": "Working directory (default: current dir)"},
                        "timeout": {"type": "integer", "description": "Max seconds to wait (default: 30)"},
                    },
                    "required": ["command"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        cmd = args["command"]
        cwd = args.get("workdir") or workdir or os.getcwd()
        timeout = int(args.get("timeout", 30))
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=timeout
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            parts = []
            if out:
                parts.append(f"stdout:\n{out}")
            if err:
                parts.append(f"stderr:\n{err}")
            if not parts:
                parts.append(f"(exit {result.returncode})")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"error: command timed out after {timeout}s"
        except Exception as e:
            return f"error: {e}"


# ── file read ─────────────────────────────────────────────────────────────────

class ReadFileTool:
    name = "read_file"
    description = "Read the contents of a file. Returns the text content."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or relative file path"},
                        "start_line": {"type": "integer", "description": "First line to read (1-indexed, optional)"},
                        "end_line":   {"type": "integer", "description": "Last line to read (inclusive, optional)"},
                    },
                    "required": ["path"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        path = Path(args["path"])
        if not path.is_absolute() and workdir:
            path = Path(workdir) / path
        try:
            lines = path.read_text(errors="replace").splitlines()
        except Exception as e:
            return f"error: {e}"

        start = args.get("start_line")
        end   = args.get("end_line")
        if start is not None:
            lines = lines[int(start) - 1:]
        if end is not None:
            lines = lines[:int(end) - (int(start) - 1 if start else 0)]

        numbered = "\n".join(f"{i+1:4d}  {l}" for i, l in enumerate(lines))
        return f"# {path}\n{numbered}"


# ── file write ────────────────────────────────────────────────────────────────

class WriteFileTool:
    name = "write_file"
    description = "Write or overwrite a file with the given content."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Full text content to write"},
                        "append":  {"type": "boolean", "description": "Append instead of overwrite (default false)"},
                    },
                    "required": ["path", "content"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        path = Path(args["path"])
        if not path.is_absolute() and workdir:
            path = Path(workdir) / path
        content = args["content"]
        mode = "a" if args.get("append") else "w"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.open(mode).write(content)
            return f"wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"error: {e}"


# ── grep ──────────────────────────────────────────────────────────────────────

class GrepTool:
    name = "grep"
    description = "Search for a pattern in files. Returns matching lines with filenames."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern":   {"type": "string",  "description": "Regex or literal pattern to search for"},
                        "path":      {"type": "string",  "description": "File or directory to search"},
                        "recursive": {"type": "boolean", "description": "Search recursively (default true)"},
                        "ignore_case": {"type": "boolean", "description": "Case-insensitive (default false)"},
                    },
                    "required": ["pattern", "path"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        pattern = args["pattern"]
        path = args.get("path", ".")
        if not Path(path).is_absolute() and workdir:
            path = str(Path(workdir) / path)
        flags = ["-n"]
        if args.get("recursive", True):
            flags.append("-r")
        if args.get("ignore_case", False):
            flags.append("-i")
        cmd = ["grep"] + flags + ["--", pattern, path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            out = result.stdout.strip()
            return out if out else "(no matches)"
        except Exception as e:
            return f"error: {e}"


# ── list directory ────────────────────────────────────────────────────────────

class ListDirTool:
    name = "list_dir"
    description = "List files and directories at a given path."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":      {"type": "string",  "description": "Directory to list (default: cwd)"},
                        "recursive": {"type": "boolean", "description": "List recursively (default false)"},
                        "show_hidden": {"type": "boolean", "description": "Include hidden files (default false)"},
                    },
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        path = Path(args.get("path", workdir or "."))
        if not path.is_absolute() and workdir:
            path = Path(workdir) / path
        recursive = args.get("recursive", False)
        show_hidden = args.get("show_hidden", False)
        try:
            if recursive:
                entries = sorted(path.rglob("*"))
            else:
                entries = sorted(path.iterdir())
            lines = []
            for e in entries:
                if not show_hidden and e.name.startswith("."):
                    continue
                indicator = "/" if e.is_dir() else ""
                size = ""
                if e.is_file():
                    try:
                        sz = e.stat().st_size
                        size = f"  ({_human_size(sz)})"
                    except Exception:
                        pass
                rel = e.relative_to(path) if not recursive else e.relative_to(path)
                lines.append(f"  {rel}{indicator}{size}")
            return f"{path}:\n" + ("\n".join(lines) if lines else "  (empty)")
        except Exception as e:
            return f"error: {e}"


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n}{unit}"
        n //= 1024
    return f"{n}TB"


# ── fetch URL (lightweight) ───────────────────────────────────────────────────

class FetchURLTool:
    name = "fetch_url"
    description = "Fetch the text content of a URL (GET request). Useful for reading docs or APIs."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url":       {"type": "string",  "description": "URL to fetch"},
                        "max_chars": {"type": "integer", "description": "Max characters to return (default 4000)"},
                    },
                    "required": ["url"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        import urllib.request
        url = args["url"]
        max_chars = int(args.get("max_chars", 4000))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ish-harness/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                content = r.read(max_chars * 2).decode(errors="replace")
            return content[:max_chars]
        except Exception as e:
            return f"error: {e}"


# ── registry ──────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    ShellTool(),
    ReadFileTool(),
    WriteFileTool(),
    GrepTool(),
    ListDirTool(),
    FetchURLTool(),
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def get_tool_schemas() -> list[dict]:
    return [t.schema() for t in ALL_TOOLS]


def dispatch_tool(name: str, args: dict, workdir: Optional[str] = None) -> str:
    tool = TOOL_MAP.get(name)
    if not tool:
        return f"unknown tool: {name}"
    return tool.run(args, workdir=workdir)

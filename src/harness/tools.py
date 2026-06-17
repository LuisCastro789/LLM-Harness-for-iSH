"""
Agent tools and skills available to LLMs inside ish-harness.
Compliant with the agentskills.io standard.
"""

import os
import subprocess
import shutil
import yaml
from pathlib import Path
from typing import Optional, Any, Dict, List


# ── skills discovery and parsing ──────────────────────────────────────────────

SKILLS_REGISTRY: Dict[str, Dict[str, Any]] = {}

def parse_skill_file(skill_md_path: Path) -> dict:
    content = skill_md_path.read_text(encoding="utf-8", errors="replace")
    if not content.startswith("---"):
        raise ValueError("Missing opening '---' for YAML frontmatter")
        
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Missing closing '---' for YAML frontmatter")
        
    frontmatter_str = parts[1]
    body = parts[2].strip()
    
    try:
        frontmatter = yaml.safe_load(frontmatter_str)
    except Exception as e:
        raise ValueError(f"Malformed YAML frontmatter: {e}")
        
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter is not a dictionary")
        
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    
    if not name or not isinstance(name, str):
        raise ValueError("Missing or invalid 'name' field in frontmatter")
    if not description or not isinstance(description, str):
        raise ValueError("Missing or invalid 'description' field in frontmatter")
        
    return {
        "name": name.strip(),
        "description": description.strip(),
        "frontmatter": frontmatter,
        "body": body,
        "location": skill_md_path,
        "dir": skill_md_path.parent
    }


def discover_skills(repo_dir: Path, workdir: Path) -> dict[str, dict]:
    skills = {}
    scopes = []
    
    # 1. Built-in / repo tools
    built_in_dir = repo_dir / "src" / "tools"
    if built_in_dir.exists():
        scopes.append(built_in_dir)
        
    # 2. User-level
    user_dir = Path.home() / ".agents" / "skills"
    if user_dir.exists():
        scopes.append(user_dir)
        
    # 3. Project-level
    project_dir = workdir / ".agents" / "skills"
    if project_dir.exists():
        scopes.append(project_dir)
        
    for scope in scopes:
        for path in scope.rglob("SKILL.md"):
            try:
                skill_info = parse_skill_file(path)
                name = skill_info["name"]
                skills[name] = skill_info
            except Exception:
                pass
                
    return skills


def refresh_skills(workdir: Optional[str] = None):
    global SKILLS_REGISTRY
    repo_dir = Path(__file__).resolve().parent.parent.parent
    if not workdir:
        workdir = os.getcwd()
    workdir_path = Path(workdir).resolve()
    SKILLS_REGISTRY = discover_skills(repo_dir, workdir_path)


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
    name = "read-file"
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
    name = "write-file"
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
    name = "list-dir"
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


# ── fetch URL (BeautifulSoup powered) ─────────────────────────────────────────

class FetchURLTool:
    name = "fetch-url"
    description = "Fetch the text content of a URL (GET request). Uses BeautifulSoup to clean up HTML."

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
                        "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)"},
                    },
                    "required": ["url"],
                },
            },
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        import urllib.request
        import urllib.error
        import urllib.parse
        from bs4 import BeautifulSoup

        url = args["url"]
        max_chars = int(args.get("max_chars", 8000))
        
        # Manual redirect handler to support 308 redirects
        current_url = url
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        html_content = ""
        final_url = url
        is_html = False
        
        try:
            for _ in range(5):
                req = urllib.request.Request(current_url, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=20) as response:
                        content_bytes = response.read()
                        charset = response.headers.get_content_charset() or 'utf-8'
                        html_content = content_bytes.decode(charset, errors='replace')
                        final_url = response.geturl()
                        
                        content_type = response.headers.get("Content-Type", "")
                        if "html" in content_type.lower() or html_content.strip().startswith("<"):
                            is_html = True
                        break
                except urllib.error.HTTPError as e:
                    if e.code in (301, 302, 303, 307, 308):
                        location = e.headers.get("Location")
                        if not location:
                            return f"error: HTTP {e.code} redirect without Location header"
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                    else:
                        return f"error: HTTP {e.code} {e.reason}"
            else:
                return "error: Too many redirects"
        except Exception as e:
            return f"error: {e}"

        if is_html:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove style, script, head, link, meta, noscript
                for element in soup(["script", "style", "head", "meta", "link", "noscript"]):
                    element.decompose()
                    
                # Process some basic tags to make them readable
                for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    level = int(header.name[1])
                    header.replace_with(f"\n\n{'#' * level} {header.get_text().strip()}\n")
                    
                for p in soup.find_all('p'):
                    p.replace_with(f"\n\n{p.get_text().strip()}\n")
                    
                for li in soup.find_all('li'):
                    li.replace_with(f"\n* {li.get_text().strip()}")
                    
                for a in soup.find_all('a'):
                    href = a.get('href', '')
                    text = a.get_text().strip()
                    if text and href and not href.startswith('#') and not href.startswith('javascript:'):
                        a.replace_with(f" [{text}]({href}) ")
                    elif text:
                        a.replace_with(f" {text} ")
                        
                text = soup.get_text()
                
                # Clean up multiple newlines and spaces
                lines = []
                for line in text.splitlines():
                    line_str = line.strip()
                    if line_str:
                        lines.append(line_str)
                    else:
                        if lines and lines[-1] != "":
                            lines.append("")
                            
                cleaned_text = "\n".join(lines).strip()
                return f"[Fetched from: {final_url}]\n\n" + cleaned_text[:max_chars]
            except Exception as e:
                return f"[Fetched from: {final_url} (BeautifulSoup cleanup failed: {e})]\n\n" + html_content[:max_chars]
        else:
            return f"[Fetched from: {final_url}]\n\n" + html_content[:max_chars]


# ── activate skill tool ───────────────────────────────────────────────────────

class ActivateSkillTool:
    name = "activate_skill"
    description = "Load the full instructions and list bundled resources for a specific skill from the catalog."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The name of the skill to activate",
                            "enum": list(SKILLS_REGISTRY.keys()) if SKILLS_REGISTRY else ["none"]
                        }
                    },
                    "required": ["name"]
                }
            }
        }

    def run(self, args: dict, workdir: Optional[str] = None) -> str:
        name = args.get("name")
        if not name or name not in SKILLS_REGISTRY:
            return f"error: skill '{name}' not found."
            
        skill = SKILLS_REGISTRY[name]
        body = skill["body"]
        skill_dir = skill["dir"]
        
        # Enumerate bundled resources
        resources = []
        for sub in ["scripts", "references", "assets"]:
            sub_dir = skill_dir / sub
            if sub_dir.exists() and sub_dir.is_dir():
                for p in sub_dir.rglob("*"):
                    if p.is_file():
                        rel = p.relative_to(skill_dir)
                        resources.append(f"  {sub}/{rel}")
                        
        res_block = ""
        if resources:
            res_block = "\n\n### Bundled Resources:\n" + "\n".join(resources)
            
        return f"""<skill_content name="{name}">
{body}{res_block}

Skill directory: {skill_dir}
Relative paths in this skill are relative to the skill directory.
</skill_content>"""


# ── registry ──────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    ShellTool(),
    ReadFileTool(),
    WriteFileTool(),
    GrepTool(),
    ListDirTool(),
    FetchURLTool(),
    ActivateSkillTool(),
]

TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def get_tool_schemas() -> list[dict]:
    # Refresh skills registry dynamically before returning schemas
    refresh_skills()
    return [t.schema() for t in ALL_TOOLS]


def dispatch_tool(name: str, args: dict, workdir: Optional[str] = None) -> str:
    # Refresh skills registry dynamically before dispatching
    refresh_skills(workdir)
    tool = TOOL_MAP.get(name)
    if not tool:
        return f"unknown tool: {name}"
    return tool.run(args, workdir=workdir)


def build_skills_catalog() -> str:
    refresh_skills()
    if not SKILLS_REGISTRY:
        return ""
        
    lines = [
        "\n=== AVAILABLE AGENT SKILLS ===",
        "The following skills provide specialized instructions for specific tasks.",
        "When a task matches a skill's description, call the activate_skill tool",
        "with the skill's name to load its full instructions.",
        ""
    ]
    for name, info in SKILLS_REGISTRY.items():
        desc = info["description"]
        lines.append(f"- {name}: {desc}")
        
    return "\n".join(lines)

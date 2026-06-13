"""
Configuration management for ish-harness.
Handles TOML config, provider profiles, and runtime settings.
"""

import os
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib          # type: ignore[no-redef]
    except ImportError:
        try:
            import tomli as tomllib   # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "Python 3.10 requires the 'tomli' package. "
                "Run: pip install tomli --break-system-packages"
            )
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


CONFIG_DIR = Path.home() / ".harness"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """\
# ish-harness configuration
# Full documentation: https://github.com/your-username/ish-harness

[ui]
theme = "dark"          # dark | light | monokai | solarized
show_tokens = true
show_timing = true
syntax_highlight = true
wrap_width = 0          # 0 = auto-detect terminal width
scroll_on_output = true

[session]
history_file = "~/.harness/history"
max_history = 1000
save_sessions = true
sessions_dir = "~/.harness/sessions"

[agent]
max_tool_calls = 20     # safety limit per turn
confirm_shell = true    # ask before executing shell commands
confirm_file_write = true
working_dir = "."       # default working directory for agent tasks
timeout = 120           # seconds per LLM call

[provider]
default = "google_ai_studio"

[provider.openai]
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
model = "gpt-4o"
max_tokens = 4096
temperature = 0.7
stream = true

[provider.anthropic]
api_key_env = "ANTHROPIC_API_KEY"
base_url = "https://api.anthropic.com"
model = "claude-3-5-sonnet-20241022"
max_tokens = 8096
temperature = 0.7
stream = true

[provider.gemma]
# Google Gemma via HuggingFace Inference API
api_key_env = "HF_TOKEN"
base_url = "https://api-inference.huggingface.co/models"
model = "google/gemma-3-27b-it"
max_tokens = 2048
temperature = 0.7
stream = false           # HF free tier may not support streaming

[provider.gemini]
api_key_env = "GEMINI_API_KEY"
base_url = "https://generativelanguage.googleapis.com/v1beta"
model = "gemini-2.0-flash"
max_tokens = 8096
temperature = 0.7
stream = true

[provider.ollama]
# Local Ollama instance
api_key_env = ""
base_url = "http://localhost:11434/v1"
model = "llama3.2"
max_tokens = 4096
temperature = 0.7
stream = true

[provider.groq]
api_key_env = "GROQ_API_KEY"
base_url = "https://api.groq.com/openai/v1"
model = "llama-3.3-70b-versatile"
max_tokens = 8192
temperature = 0.7
stream = false           # set true if you want streaming (may show blank on some models)

[provider.groq_compound]
# Groq Compound — built-in web search/code execution, no local tool calling
api_key_env = "GROQ_API_KEY"
base_url = "https://api.groq.com/openai/v1"
model = "groq/compound"
max_tokens = 8192
temperature = 0.7
stream = false
no_tools = true          # compound uses built-in tools only, not local tool calling

[provider.hf_harness]
# HuggingFace Inference API (generic, OpenAI-compatible endpoint)
api_key_env = "HF_TOKEN"
base_url = "https://api-inference.huggingface.co/v1"
model = "Qwen/Qwen2.5-72B-Instruct"
max_tokens = 2048
temperature = 0.7
stream = false

[provider.google_ai_studio]
# Google AI Studio — same Gemini API, separate key env var
api_key_env = "GOOGLE_AI_STUDIO_KEY"
base_url = "https://generativelanguage.googleapis.com/v1beta"
model = "gemini-2.5-flash"
max_tokens = 8096
temperature = 0.7
stream = true
"""


@dataclass
class UIConfig:
    theme: str = "dark"
    show_tokens: bool = True
    show_timing: bool = True
    syntax_highlight: bool = True
    wrap_width: int = 0
    scroll_on_output: bool = True


@dataclass
class SessionConfig:
    history_file: str = "~/.harness/history"
    max_history: int = 1000
    save_sessions: bool = True
    sessions_dir: str = "~/.harness/sessions"


@dataclass
class AgentConfig:
    max_tool_calls: int = 20
    confirm_shell: bool = True
    confirm_file_write: bool = True
    working_dir: str = "."
    timeout: int = 120


@dataclass
class ProviderConfig:
    api_key_env: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = True
    no_tools: bool = False      # set true to skip tool payload for models that don't support it

    def resolve_api_key(self) -> Optional[str]:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)


@dataclass
class Config:
    ui: UIConfig = field(default_factory=UIConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    providers: dict = field(default_factory=dict)
    default_provider: str = "openai"

    def get_provider(self, name: Optional[str] = None) -> ProviderConfig:
        key = name or self.default_provider
        raw = self.providers.get(key, {})
        return ProviderConfig(**{k: v for k, v in raw.items() if k in ProviderConfig.__dataclass_fields__})

    def list_providers(self) -> list[str]:
        return list(self.providers.keys())


def init_config_dir():
    """Create ~/.harness/ and write default config if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "sessions").mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG)
    return CONFIG_FILE


def load_config(path: Optional[Path] = None) -> Config:
    """Load and parse config.toml. Returns defaults if file is missing."""
    cfg_path = path or CONFIG_FILE
    if not cfg_path.exists():
        init_config_dir()
        # Return defaults on first run
        return _defaults()

    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        print(f"[harness] Warning: could not read config ({e}), using defaults.")
        return _defaults()

    ui = UIConfig(**{k: v for k, v in data.get("ui", {}).items() if k in UIConfig.__dataclass_fields__})
    session = SessionConfig(**{k: v for k, v in data.get("session", {}).items() if k in SessionConfig.__dataclass_fields__})
    agent = AgentConfig(**{k: v for k, v in data.get("agent", {}).items() if k in AgentConfig.__dataclass_fields__})

    provider_section = data.get("provider", {})
    default_provider = provider_section.pop("default", "openai")
    providers = {}
    for name, vals in provider_section.items():
        if isinstance(vals, dict):
            providers[name] = vals

    return Config(
        ui=ui,
        session=session,
        agent=agent,
        providers=providers,
        default_provider=default_provider,
    )


def _defaults() -> Config:
    """Return a Config with safe built-in defaults."""
    cfg = Config()
    # Populate built-in provider stubs so the UI can list them
    cfg.providers = {
        "openai":        {"api_key_env": "OPENAI_API_KEY",    "base_url": "https://api.openai.com/v1",                      "model": "gpt-4o",                        "max_tokens": 4096,  "temperature": 0.7, "stream": True,  "no_tools": False},
        "anthropic":     {"api_key_env": "ANTHROPIC_API_KEY", "base_url": "https://api.anthropic.com",                      "model": "claude-3-5-sonnet-20241022",     "max_tokens": 8096,  "temperature": 0.7, "stream": True,  "no_tools": False},
        "groq":          {"api_key_env": "GROQ_API_KEY",      "base_url": "https://api.groq.com/openai/v1",                 "model": "llama-3.3-70b-versatile",       "max_tokens": 8192,  "temperature": 0.7, "stream": False, "no_tools": False},
        "groq_compound": {"api_key_env": "GROQ_API_KEY",      "base_url": "https://api.groq.com/openai/v1",                 "model": "groq/compound",                 "max_tokens": 8192,  "temperature": 0.7, "stream": False, "no_tools": True},
        "gemma":         {"api_key_env": "HF_TOKEN",          "base_url": "https://api-inference.huggingface.co/models",    "model": "google/gemma-3-27b-it",         "max_tokens": 2048,  "temperature": 0.7, "stream": False, "no_tools": False},
        "gemini":        {"api_key_env": "GEMINI_API_KEY",    "base_url": "https://generativelanguage.googleapis.com/v1beta","model": "gemini-2.0-flash",             "max_tokens": 8096,  "temperature": 0.7, "stream": True,  "no_tools": False},
        "ollama":        {"api_key_env": "",                  "base_url": "http://localhost:11434/v1",                      "model": "llama3.2",                      "max_tokens": 4096,  "temperature": 0.7, "stream": True,  "no_tools": False},
        "hf_harness":    {"api_key_env": "HF_TOKEN",          "base_url": "https://api-inference.huggingface.co/v1",        "model": "Qwen/Qwen2.5-72B-Instruct",     "max_tokens": 2048,  "temperature": 0.7, "stream": False, "no_tools": False},
    }
    return cfg

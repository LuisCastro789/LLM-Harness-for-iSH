# ish-harness

**Agentic TUI LLM harness for iSH on iOS.**

A Gemini-CLI-style terminal application that runs natively inside the [iSH app](https://ish.app) (Alpine Linux on iOS). Chat with multiple LLM providers, automate tasks with an agentic tool loop, and keep a full session history — all from your iPhone or iPad.

```
╭─────────────────────────────────────────────────────────────╮
│                       ish-harness                           │
│               agentic LLM CLI for iSH                       │
╰─────────────────────────────────────────────────────────────╯

ℹ  ish-harness v0.1.0  |  provider: groq  |  model: llama-3.3-70b-versatile

❯ list my python files and summarise what each one does

╭─ You ─────────────────────────────────────────────────────────
│ list my python files and summarise what each one does
╰───────────────────────────────────────────────────────────────

╭─ groq · llama-3.3-70b-versatile ──────────────────────────────
│ I'll list the Python files in your working directory first.
│
  ⚙  tool: list-dir
     {
       "path": ".",
       "recursive": false
     }
  ↳  list-dir result:
     .:
       app.py   (4.2KB)
       utils.py (1.1KB)
│
│ Here's a summary of each file:
│ • app.py  — main Flask application, defines routes and startup
│ • utils.py — helper functions for input validation
╰──────────────────────────────── ↑312 ↓98 tok · 1.7s ─────────
```

---

## Features

- **Multi-provider** — OpenAI, Anthropic, Google Gemini, Google Gemma (HuggingFace), Groq, Ollama, any OpenAI-compatible endpoint
- **Agentic tool loop** — shell execution, file read/write, grep, directory listing, URL fetch; the LLM calls tools automatically until the task is done
- **Local-first Memory System (iSH-Memory)** — Hierarchical memory storage (wing/room/drawer) with SQLite + FTS5 full-text indexing, BM25 relevance ranking, and automatic context recall (the top 3 memories are automatically recalled and injected into the LLM prompt)
- **iSH-native** — pure Python stdlib, zero C extensions, zero external runtime deps; installs on Alpine i686 (musl libc) with a single command
- **Python 3.10+ compatible** — works on iSH's default Python (3.10)
- **Rich TUI** — box-drawing borders, streaming tokens, spinner, themes (dark / light / monokai / solarized), all via plain ANSI codes
- **Session persistence** — conversations saved as JSON, loadable by name
- **readline history** — persistent command history with Ctrl+R search
- **Confirmation gates** — asks before running shell commands or writing files
- **Auto tool-retry** — automatically retries without tools on models that don't support function calling

---

## Requirements

| Requirement | Notes |
|---|---|
| iSH app | [App Store](https://apps.apple.com/app/ish-shell/id1436902243) — free |
| Alpine Linux | Set up via iSH (default) |
| Python ≥ 3.10 | `apk add python3 py3-pip` |
| An API key | From your LLM provider |

No `pip` packages are required at runtime on Python 3.11+. On Python 3.10 (iSH default), `tomli` is installed automatically. The only other optional addition is `py3-readline` for shell history.

---

## Quick Start

### 1. Install iSH

Download [iSH](https://apps.apple.com/app/ish-shell/id1436902243) from the App Store and open it.

### 2. Clone and install

```sh
# Inside iSH:
apk add git python3 py3-pip py3-readline
git clone https://github.com/LuisCastro789/LLM-Harness-for-iSH.git
cd LLM-Harness-for-iSH
sh install.sh
```

### 3. Set your API key

```sh
# Groq (recommended for iSH — fast, free tier available)
export GROQ_API_KEY=gsk_...

# Or any other provider:
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GEMINI_API_KEY=AIza...
export HF_TOKEN=hf_...

# Make it permanent:
echo 'export GROQ_API_KEY=gsk_...' >> ~/.profile
```

### 4. Run

```sh
harness
❯ /provider groq
```

---

## Supported Providers

| Name | Env var | Model | Tool calling |
|---|---|---|---|
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | ✅ local |
| `groq_compound` | `GROQ_API_KEY` | `groq/compound` | ✅ built-in (web search, code) |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` | ✅ |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022` | ✅ |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.0-flash` | ✅ |
| `gemma` | `HF_TOKEN` | `google/gemma-3-27b-it` | ❌ |
| `hf_harness` | `HF_TOKEN` | `Qwen/Qwen2.5-72B-Instruct` | ✅ |
| `ollama` | — | `llama3.2` | ✅ |
| *(custom)* | *(any)* | any | depends on model |

### Groq model notes

Groq hosts several models with local tool calling support. Recommended for ish-harness:

| Model ID | Tool calling | Context | Notes |
|---|---|---|---|
| `llama-3.3-70b-versatile` | ✅ | 128k | Best quality, recommended default |
| `llama-3.1-8b-instant` | ✅ | 128k | Fastest, smallest — use with larger `max_tokens` limit |
| `meta-llama/llama-4-scout-17b-16e-instruct` | ✅ | 128k | Good balance |
| `qwen/qwen3-32b` | ✅ | 128k | Strong reasoning |
| `groq/compound` | built-in only | — | Web search + code execution, no local tools |
| `groq/compound-mini` | built-in only | — | Faster/cheaper compound variant |

> **Note:** `groq/compound` supports Groq's own built-in tools (web search, code execution) but does **not** support local tool calling via the `tools` parameter. Use the `groq_compound` provider which sets `no_tools = true` automatically.

---

## Usage

### Chat

Just type your message and press Enter. The agent responds and calls tools as needed.

### Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/exit` or `/quit` | Exit |
| `/clear` | Clear conversation history |
| `/reset` | Hard reset (history + state) |
| `/provider <name>` | Switch LLM provider |
| `/model <name>` | Override model for this session |
| `/theme <name>` | Switch theme (dark/light/monokai/solarized) |
| `/tools` | List available agent tools |
| `/status` | Show current provider, model, theme |
| `/save [name]` | Save session to disk |
| `/load <name>` | Load a saved session |
| `/sessions` | List all saved sessions |
| `/system <text>` | Override system prompt |
| `/multiline` | Multi-line input mode (end with `.`) |
| `/version` | Show version |

### Switching Providers

```
❯ /provider groq
✓  Switched to provider: groq  (model: llama-3.3-70b-versatile)

❯ /provider anthropic
✓  Switched to provider: anthropic  (model: claude-3-5-sonnet-20241022)
```

### Switching Models mid-session

```
❯ /model qwen/qwen3-32b
✓  Model overridden to: qwen/qwen3-32b
```

### Multi-line Input

```
❯ /multiline
  Multi-line mode. Enter '.' on a blank line to finish.
  … def add(a, b):
  …     return a + b
  … .
```

---

## Configuration

`~/.harness/config.toml` is created automatically on first run.

```toml
[ui]
theme = "dark"          # dark | light | monokai | solarized
show_tokens = true
show_timing = true

[agent]
max_tool_calls = 20     # safety limit per turn
confirm_shell = true    # ask before running shell commands
confirm_file_write = true
working_dir = "."

[provider]
default = "groq"

[provider.groq]
api_key_env = "GROQ_API_KEY"
base_url    = "https://api.groq.com/openai/v1"
model       = "llama-3.3-70b-versatile"
max_tokens  = 8192
temperature = 0.7
stream      = false     # recommended for Groq; streaming can produce blank output

[provider.groq_compound]
api_key_env = "GROQ_API_KEY"
base_url    = "https://api.groq.com/openai/v1"
model       = "groq/compound"
max_tokens  = 8192
stream      = false
no_tools    = true      # compound uses built-in tools, not local tool calling
```

### `no_tools` flag

Set `no_tools = true` for any model that doesn't support the OpenAI `tools` parameter (e.g. `groq/compound`, `groq/compound-mini`). The harness will skip sending the tool schema entirely. The model will still respond — it just won't be able to call ish-harness tools.

---

## Agent Tools & Skills

The harness supports both built-in core tools and dynamically discovered, modular **Agent Skills** (following the `agentskills.io` standard).

### Built-in Core Tools

| Tool | What it does |
|---|---|
| `shell` | Run any shell command; stdout + stderr returned to the LLM |
| `read-file` | Read a file (optionally with line range) |
| `write-file` | Write or append to a file |
| `grep` | Regex search across files or directories |
| `list-dir` | List directory contents with sizes |
| `fetch-url` | HTTP GET a URL and return clean text content |

Tools that modify the system (`shell`, `write-file`) show a confirmation prompt by default. Set `confirm_shell = false` in config to disable.

### Custom Agent Skills

Custom skills are dynamically loaded on-demand via the `activate_skill` tool, which exposes full instructions and bundled resources to the LLM as needed, conserving context window space.

| Skill | Description |
|---|---|
| `ish-memory` | Local-first hierarchical memory storage, search, and recall. |
| `pdf-creator` | Generate clean PDF documents from raw text content. |
| `pdf-manager` | Inspect, analyze, and split PDF documents. |

---

## iSH-Memory (Local-First AI Memory)

iSH-Memory is a highly optimized, resource-efficient local memory system designed specifically for the resource-constrained emulated environment of iSH. It runs entirely on device, requiring **zero** external vector databases, APIs, or heavy runtime dependencies.

### Architecture & Hierarchy
Memories are organized hierarchically (inspired by the MemPalace design) to allow highly targeted retrieval:
* **Wing**: High-level scope or context (e.g., `user`, `project`, `system`).
* **Room**: A specific topic, task, or area of interest (e.g., `git`, `python`, `deployment`).
* **Content (Drawer)**: The verbatim text snippet, conversation segment, or structured facts.

### Key Features
1. **SQLite + FTS5 Storage**: Uses native SQLite with Full-Text Search (FTS5) for fast keyword indexing. Database triggers automatically synchronize the FTS5 index on every insert, update, or delete.
2. **BM25 Relevance Ranking**: Uses a lightweight, pure-Python BM25 relevance ranking algorithm to sort matching memories by semantic relevance.
3. **Automatic Context Recall**: On every user input, the harness automatically queries the `MemoryStore` for the top 3 relevant memories and injects them directly into the dynamic system prompt.
4. **CLI Interface**: Perform manual memory management via the command line.

### CLI Usage
The memory CLI is located at `src/tools/custom_tools/ish-memory/scripts/memory_cli.py`.

* **Add a memory**:
  ```sh
  python3 src/tools/custom_tools/ish-memory/scripts/memory_cli.py add "SQLite triggers automatically sync FTS5 virtual tables." --wing development --room sqlite --metadata '{"author": "assistant"}'
  ```
* **Search memories**:
  ```sh
  python3 src/tools/custom_tools/ish-memory/scripts/memory_cli.py search "FTS5 triggers" --wing development
  ```
* **Get a memory by ID**:
  ```sh
  python3 src/tools/custom_tools/ish-memory/scripts/memory_cli.py get 1
  ```
* **Delete a memory by ID**:
  ```sh
  python3 src/tools/custom_tools/ish-memory/scripts/memory_cli.py delete 1
  ```

*Note: By default, the CLI uses the production database path `~/.harness/memory.db`. You can override this using the `--db <path>` option or the `HARNESS_MEMORY_DB` environment variable.*

---

## Project Structure

```
ish-harness/
├── src/harness/
│   ├── __init__.py       version
│   ├── __main__.py       entry point
│   ├── app.py            main REPL loop
│   ├── agent.py          agentic tool-call loop
│   ├── config.py         TOML config + defaults
│   ├── memory_store.py   SQLite + FTS5 database manager & BM25 ranker
│   ├── providers.py      OpenAI / Anthropic / Gemini / HF / Groq adapters
│   ├── tools.py          shell, file, grep, list, fetch tools, skill discovery
│   ├── renderer.py       ANSI TUI renderer
│   ├── themes.py         dark / light / monokai / solarized
│   ├── sessions.py       JSON session persistence
│   └── history.py        readline integration
├── src/tools/custom_tools/
│   ├── ish-memory/       iSH-Memory agentskills.io skill
│   │   ├── SKILL.md      Skill metadata and documentation
│   │   └── scripts/
│   │       └── memory_cli.py  Memory command line interface
│   ├── pdf_creator/      PDF Creator skill
│   └── pdf_manager/      PDF Manager skill
├── tests/
│   ├── test_harness.py
│   ├── test_memory_store.py
│   ├── test_memory_cli.py
│   └── test_memory_integration.py
├── install.sh            iSH bootstrap script
├── pyproject.toml
├── setup.py
└── README.md
```

---

## Troubleshooting

**`harness: command not found`**
```sh
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
```

**`ModuleNotFoundError: No module named 'tomli'`**
```sh
pip install tomli --break-system-packages
```

**Blank response after model switch**
Set `stream = false` in your provider config. Some models on Groq return empty content when streamed via raw SSE.

**HTTP 400 — tool calling not supported**
The harness auto-retries without tools on this error. If it persists, add `no_tools = true` to your provider config block.

**HTTP 413 — request too large**
Your model has a small context window. Switch to a model with a larger context (e.g. `llama-3.3-70b-versatile` on Groq has 128k tokens).

**HTTP 403 / Cloudflare 1010**
This was a missing `User-Agent` header — fixed in current version. Make sure you have the latest `providers.py`.

**`readline` not working / no history**
```sh
apk add py3-readline
```

**iSH is slow**
iSH emulates x86 on ARM. Python startup takes a few seconds — normal. Once running the harness is responsive.

---

## Extending

### Add a new tool

In `src/harness/tools.py`:

```python
class MyTool:
    name = "my_tool"
    description = "Does something useful."

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "..."},
                    },
                    "required": ["input"],
                },
            },
        }

    def run(self, args: dict, workdir=None) -> str:
        return f"result: {args['input']}"

ALL_TOOLS.append(MyTool())
TOOL_MAP["my_tool"] = ALL_TOOLS[-1]
```

### Add a custom provider

In `~/.harness/config.toml`:

```toml
[provider.my_provider]
api_key_env = "MY_API_KEY"
base_url    = "https://api.example.com/v1"
model       = "my-model"
max_tokens  = 4096
stream      = false
```

Any OpenAI-compatible endpoint works without code changes.

---

## License

MIT. See [LICENSE](LICENSE).

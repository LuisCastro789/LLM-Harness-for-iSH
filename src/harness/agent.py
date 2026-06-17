"""
Agent loop for ish-harness.

Drives the agentic tool-use cycle:
  user message → LLM → [tool calls → tool results → LLM] × N → final reply
"""

import os
import json
from typing import Callable, Optional

from .config import AgentConfig
from .providers import BaseProvider, Message, LLMResponse
from .tools import get_tool_schemas, dispatch_tool, TOOL_MAP, build_skills_catalog
from .memory_store import MemoryStore


SYSTEM_PROMPT = """\
You are a capable, concise agentic assistant running inside ish-harness on an iOS device via the iSH shell app.

Environment facts:
- OS: Alpine Linux (musl libc, i686) inside iSH on iOS
- You have access to a set of tools: shell, read-file, write-file, grep, list-dir, fetch-url, activate_skill
- When executing shell commands, prefer commands available in Alpine's busybox/apk ecosystem
- Be conservative with destructive actions; prefer dry-run flags when available
- Respond concisely; the terminal has limited screen space

Tool-use guidance:
- Use shell for multi-step system tasks (installing packages, running scripts, compiling)
- Chain tools logically; don't re-read files you already have in context
- After completing a task, summarise what was done in plain language
- If you are unsure about a destructive action, ask the user before proceeding
"""


class AgentSession:
    """Manages conversation history and context for a single session."""

    def __init__(self, provider: BaseProvider, cfg: AgentConfig):
        self.provider = provider
        self.cfg = cfg
        self.history: list[Message] = []
        self.tool_call_count: int = 0

    def reset(self):
        self.history.clear()
        self.tool_call_count = 0

    def append_user(self, content: str):
        self.history.append(Message(role="user", content=content))

    def append_assistant(self, content: str, tool_calls=None):
        self.history.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def append_tool_result(self, tool_name: str, result: str, call_id: str):
        self.history.append(Message(
            role="tool",
            content=result,
            tool_call_id=call_id,
            name=tool_name,
        ))


class AgentLoop:
    """
    Runs the agentic turn loop.

    Callbacks (all optional):
      on_llm_start(turn)          - called before each LLM call
      on_token(text)              - streaming token
      on_llm_end(response)        - called after each LLM call
      on_tool_call(name, args)    - before a tool is dispatched
      on_tool_result(name, out)   - after a tool returns
      on_confirm(name, args)      - must return True to allow execution
      on_error(msg)               - error notification
    """

    def __init__(
        self,
        session: AgentSession,
        *,
        on_llm_start: Optional[Callable] = None,
        on_token: Optional[Callable] = None,
        on_llm_end: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
        on_confirm: Optional[Callable] = None,   # (name, args) -> bool
        on_error: Optional[Callable] = None,
    ):
        self.session = session
        self.on_llm_start  = on_llm_start  or (lambda *a: None)
        self.on_token      = on_token      or (lambda *a: None)
        self.on_llm_end    = on_llm_end    or (lambda *a: None)
        self.on_tool_call  = on_tool_call  or (lambda *a: None)
        self.on_tool_result = on_tool_result or (lambda *a: None)
        self.on_confirm    = on_confirm    or (lambda name, args: True)
        self.on_error      = on_error      or (lambda *a: None)

    def run(self, user_input: str) -> str:
        """Run one user turn through the full agentic loop. Returns final assistant text."""
        sess = self.session
        cfg = sess.cfg

        sess.append_user(user_input)
        sess.tool_call_count = 0

        tools = get_tool_schemas()
        turn = 0

        # Automatic Memory Recall
        memories_text = ""
        try:
            db_path = os.environ.get("HARNESS_MEMORY_DB") or os.path.expanduser("~/.harness/memory.db")
            if os.path.exists(db_path):
                store = MemoryStore(db_path)
                try:
                    results = store.search_memories(user_input)
                    if results:
                        # Fetch top 3
                        top_results = results[:3]
                        memories_lines = ["\n### Relevant Memories:"]
                        for r in top_results:
                            memories_lines.append(f"- [{r['wing']}/{r['room']}]: {r['content']}")
                        memories_text = "\n".join(memories_lines) + "\n"
                finally:
                    store.close()
        except Exception:
            # Handle cases gracefully when the database does not exist, is empty, or fails
            pass

        while True:
            turn += 1
            self.on_llm_start(turn)

            # Build the dynamic system prompt with the available skills catalog
            skills_catalog = build_skills_catalog()
            dynamic_system_prompt = SYSTEM_PROMPT + memories_text + skills_catalog

            try:
                response: LLMResponse = sess.provider.chat(
                    messages=sess.history,
                    system=dynamic_system_prompt,
                    tools=tools if sess.cfg.max_tool_calls > 0 else None,
                    stream_cb=self.on_token,
                )
            except Exception as e:
                msg = f"LLM error: {e}"
                self.on_error(msg)
                sess.append_assistant(msg)
                return msg

            self.on_llm_end(response)

            # ── no tool calls → done ──────────────────────────────────────
            if not response.tool_calls:
                sess.append_assistant(response.content)
                return response.content

            # ── tool-call safety limit ────────────────────────────────────
            if sess.tool_call_count >= cfg.max_tool_calls:
                warn = "[harness] Tool call limit reached. Stopping agentic loop."
                self.on_error(warn)
                sess.append_assistant(response.content or warn)
                return response.content or warn

            # ── process each tool call ────────────────────────────────────
            sess.append_assistant(response.content or "", tool_calls=response.tool_calls)

            for tc in response.tool_calls:
                # Normalise across provider formats
                call_id, fn_name, fn_args = _parse_tool_call(tc)
                if fn_name is None:
                    continue

                self.on_tool_call(fn_name, fn_args)

                # Confirmation gate for destructive tools
                allowed = True
                if fn_name == "shell" and cfg.confirm_shell:
                    allowed = self.on_confirm(fn_name, fn_args)
                elif fn_name == "write-file" and cfg.confirm_file_write:
                    allowed = self.on_confirm(fn_name, fn_args)

                if not allowed:
                    result = "error: tool execution cancelled by user"
                else:
                    try:
                        result = dispatch_tool(fn_name, fn_args, workdir=cfg.working_dir)
                    except Exception as e:
                        result = f"error: {e}"

                self.on_tool_result(fn_name, result)
                sess.append_tool_result(fn_name, result, call_id)
                sess.tool_call_count += 1


def _parse_tool_call(tc) -> tuple[Optional[str], Optional[str], dict]:
    """Parse tool call into (call_id, name, args) across different providers."""
    # OpenAI / Groq / Gemini / Ollama format
    if hasattr(tc, "id") and hasattr(tc, "function"):
        call_id = tc.id
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
        except Exception:
            args = {}
        return call_id, name, args

    # Anthropic format
    if isinstance(tc, dict) and "id" in tc and "name" in tc:
        return tc["id"], tc["name"], tc.get("input", {})

    # Dictionary format fallback
    if isinstance(tc, dict) and "function" in tc:
        fn = tc["function"]
        call_id = tc.get("id")
        name = fn.get("name")
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        return call_id, name, args

    return None, None, {}

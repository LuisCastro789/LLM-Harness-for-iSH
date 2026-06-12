"""
Agent loop for ish-harness.

Drives the agentic tool-use cycle:
  user message → LLM → [tool calls → tool results → LLM] × N → final reply
"""

import json
from typing import Callable, Optional

from .config import AgentConfig
from .providers import BaseProvider, Message, LLMResponse
from .tools import get_tool_schemas, dispatch_tool, TOOL_MAP


SYSTEM_PROMPT = """\
You are a capable, concise agentic assistant running inside ish-harness on an iOS device via the iSH shell app.

Environment facts:
- OS: Alpine Linux (musl libc, i686) inside iSH on iOS
- You have access to a set of tools: shell, read_file, write_file, grep, list_dir, fetch_url
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

        while True:
            turn += 1
            self.on_llm_start(turn)

            try:
                response: LLMResponse = sess.provider.chat(
                    messages=sess.history,
                    system=SYSTEM_PROMPT,
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
                if fn_name in ("shell", "write_file"):
                    if cfg.confirm_shell and not self.on_confirm(fn_name, fn_args):
                        result = "[harness] user declined tool execution"
                        self.on_tool_result(fn_name, result)
                        sess.append_tool_result(fn_name, result, call_id)
                        continue

                sess.tool_call_count += 1
                result = dispatch_tool(fn_name, fn_args, workdir=cfg.working_dir)
                self.on_tool_result(fn_name, result)
                sess.append_tool_result(fn_name, result, call_id)

            # Loop back → LLM processes tool results


def _parse_tool_call(tc: dict) -> tuple:
    """Normalise a tool_call dict from OpenAI or Anthropic into (id, name, args)."""
    # OpenAI format: {"id": ..., "type": "function", "function": {"name": ..., "arguments": "..."}}
    if "function" in tc:
        fn = tc["function"]
        name = fn.get("name")
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {}
        return tc.get("id", ""), name, args

    # Anthropic format: {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
    if tc.get("type") == "tool_use":
        return tc.get("id", ""), tc.get("name"), tc.get("input", {})

    return "", None, {}

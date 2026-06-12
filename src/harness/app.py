"""
HarnessApp: main REPL loop for ish-harness.

Wires together config, provider, agent, renderer, sessions, and history.
"""

import sys
import os
import signal
from typing import Optional

from .config import load_config, init_config_dir, Config
from .providers import get_provider, BaseProvider, LLMResponse
from .agent import AgentSession, AgentLoop
from .renderer import Renderer
from .themes import THEMES
from .tools import TOOL_MAP
from .sessions import save_session, load_session, list_sessions, autosave
from .history import setup_readline, add_history
from . import __version__


class HarnessApp:
    def __init__(self, config_path=None):
        init_config_dir()
        self.cfg = load_config(config_path)
        self.renderer = Renderer(self.cfg.ui.theme)
        self._current_provider_name: str = self.cfg.default_provider
        self._current_model: Optional[str] = None
        self._custom_system: Optional[str] = None
        self._provider: Optional[BaseProvider] = None
        self._session: Optional[AgentSession] = None
        self._build_provider()

    # ── provider management ───────────────────────────────────────────────────

    def _build_provider(self):
        pcfg = self.cfg.get_provider(self._current_provider_name)
        if self._current_model:
            pcfg.model = self._current_model
        self._provider = get_provider(self._current_provider_name, pcfg)
        self._session = AgentSession(self._provider, self.cfg.agent)

    def _switch_provider(self, name: str):
        if name not in self.cfg.list_providers():
            self.renderer.error(f"Unknown provider '{name}'. Available: {', '.join(self.cfg.list_providers())}")
            return
        self._current_provider_name = name
        self._current_model = None
        self._build_provider()
        self.renderer.success(f"Switched to provider: {name}  (model: {self._provider.cfg.model})")

    # ── slash commands ────────────────────────────────────────────────────────

    def _handle_command(self, text: str) -> bool:
        """Process a /command. Returns True if handled (don't send to LLM)."""
        r = self.renderer
        parts = text.strip().split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            self._do_exit()

        elif cmd == "/help":
            r.help_text(self.cfg.list_providers())

        elif cmd == "/clear":
            self._session.reset()
            r.success("Conversation history cleared.")

        elif cmd == "/reset":
            self._session.reset()
            self._custom_system = None
            r.success("Session fully reset.")

        elif cmd == "/provider":
            if arg:
                self._switch_provider(arg)
            else:
                r.info(f"Current provider: {self._current_provider_name}")
                r.info(f"Available: {', '.join(self.cfg.list_providers())}")

        elif cmd == "/model":
            if arg:
                self._current_model = arg
                self._build_provider()
                r.success(f"Model overridden to: {arg}")
            else:
                r.info(f"Current model: {self._provider.cfg.model}")

        elif cmd == "/theme":
            if arg in THEMES:
                self.cfg.ui.theme = arg
                r.set_theme(arg)
                r.success(f"Theme: {arg}")
            else:
                r.error(f"Unknown theme '{arg}'. Available: {', '.join(THEMES)}")

        elif cmd == "/tools":
            r.tool_list(list(TOOL_MAP.keys()))

        elif cmd == "/status":
            r.status(
                provider_name=self._current_provider_name,
                model=self._provider.cfg.model,
                theme=self.cfg.ui.theme,
                history_len=len(self._session.history),
            )

        elif cmd == "/sessions":
            slist = list_sessions(self.cfg.session.sessions_dir)
            if not slist:
                r.info("No saved sessions.")
            else:
                r.rule("saved sessions")
                t = r.theme
                for s in slist:
                    r._wl(
                        r._styled(t.highlight, f"  {s['name']:<20}") +
                        r._styled(t.muted, f"{s['saved_at'][:16]}  {s['provider']}/{s['model']}  ({s['messages']} msgs)")
                    )
                r._wl()

        elif cmd == "/save":
            name = arg or None
            path = save_session(
                self._session.history,
                name,
                self._current_provider_name,
                self._provider.cfg.model,
                self.cfg.session.sessions_dir,
            )
            r.success(f"Session saved: {path}")

        elif cmd == "/load":
            if not arg:
                r.error("/load requires a session name")
            else:
                try:
                    msgs, meta = load_session(arg, self.cfg.session.sessions_dir)
                    self._session.history = msgs
                    r.success(f"Loaded session '{arg}' ({len(msgs)} messages)")
                    if meta.get("provider") and meta["provider"] != self._current_provider_name:
                        r.info(f"Session was saved with provider '{meta['provider']}'. Current: {self._current_provider_name}")
                except FileNotFoundError as e:
                    r.error(str(e))

        elif cmd == "/system":
            if arg:
                self._custom_system = arg
                r.success("Custom system prompt set for this session.")
            else:
                self._custom_system = None
                r.success("System prompt reset to default.")

        elif cmd == "/multiline":
            return False   # handled by caller

        elif cmd == "/version":
            r.info(f"ish-harness v{__version__}")

        else:
            r.warn(f"Unknown command: {cmd}  (type /help)")

        return True

    # ── agent callbacks ───────────────────────────────────────────────────────

    def _make_loop(self) -> AgentLoop:
        r = self.renderer
        turn_count = [0]
        response_buf = [None]

        def on_llm_start(turn):
            turn_count[0] = turn
            pname = self._current_provider_name
            if turn == 1:
                r.ai_turn_start(f"{pname} · {self._provider.cfg.model}")
            else:
                r.ai_turn_start(f"  ↻ turn {turn}")

        def on_token(text):
            r.stream_token(text)

        def on_llm_end(resp: LLMResponse):
            response_buf[0] = resp
            if not resp.tool_calls:
                r.ai_turn_end(resp if self.cfg.ui.show_tokens else None)

        def on_tool_call(name, args):
            # Close current ai box cleanly before tool output
            if self.cfg.ui.show_tokens:
                r._wl()
                r._wl(r._styled(r.theme.border, r.BL + r.H * (r.width - 2)))
            r.tool_call_display(name, args)

        def on_tool_result(name, result):
            r.tool_result_display(name, result)

        def on_confirm(name, args):
            return r.confirm(name, args)

        def on_error(msg):
            r.error(msg)

        return AgentLoop(
            self._session,
            on_llm_start=on_llm_start,
            on_token=on_token,
            on_llm_end=on_llm_end,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            on_confirm=on_confirm,
            on_error=on_error,
        )

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self):
        r = self.renderer
        cfg = self.cfg

        # Readline history
        setup_readline(cfg.session.history_file, cfg.session.max_history)

        # SIGINT handler — don't crash on Ctrl+C
        def _sigint(sig, frame):
            r._wl()
            r.warn("Interrupted (Ctrl+C). Type /exit to quit.")
        signal.signal(signal.SIGINT, _sigint)

        r.header()
        r.info(f"ish-harness v{__version__}  |  provider: {self._current_provider_name}  |  model: {self._provider.cfg.model}")
        r.info("Type /help for commands. Press Ctrl+C to interrupt a response.")

        # Check API key
        key = self._provider.cfg.resolve_api_key()
        if self._provider.cfg.api_key_env and not key:
            r.warn(f"API key not set. Expected env var: {self._provider.cfg.api_key_env}")

        agent_loop = self._make_loop()

        while True:
            try:
                user_input = r.prompt_input()
            except KeyboardInterrupt:
                r._wl()
                continue

            user_input = user_input.strip()
            if not user_input:
                continue

            add_history(user_input)

            # Multi-line mode
            if user_input in ("/multiline", "/ml"):
                user_input = r.multiline_prompt()
                if not user_input.strip():
                    continue

            # Slash commands
            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue

            # Rebuild loop in case provider changed
            agent_loop = self._make_loop()

            # Display user turn
            r.user_turn(user_input)

            # Run agent
            try:
                agent_loop.run(user_input)
            except KeyboardInterrupt:
                r._wl()
                r.warn("Response interrupted.")
            except Exception as e:
                r.error(f"Unexpected error: {e}")

            # Autosave
            if cfg.session.save_sessions:
                autosave(
                    self._session.history,
                    self._current_provider_name,
                    self._provider.cfg.model,
                    cfg.session.sessions_dir,
                )

    def _do_exit(self):
        self.renderer._wl()
        self.renderer.info("Goodbye.")
        sys.exit(0)

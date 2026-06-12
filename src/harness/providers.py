"""
Provider abstraction for ish-harness.

Supports:
  - OpenAI-compatible APIs  (OpenAI, Ollama, HF /v1 endpoints)
  - Anthropic Messages API
  - Google Gemini REST API
  - HuggingFace Inference API (Gemma and others, non-OpenAI path)
"""

import json
import time
import urllib.request
import urllib.error
from typing import Iterator, Optional
from dataclasses import dataclass

from .config import ProviderConfig


# ── shared types ─────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str   # "user" | "assistant" | "system" | "tool"
    content: str
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class LLMResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    elapsed: float = 0.0
    tool_calls: Optional[list] = None   # raw tool_calls block if any


@dataclass
class StreamChunk:
    delta: str
    done: bool = False
    tool_calls: Optional[list] = None


# ── helpers ───────────────────────────────────────────────────────────────────

class HTTPError(RuntimeError):
    """Wraps an HTTP error with the status code accessible."""
    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def _http_post(url: str, headers: dict, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        raise HTTPError(e.code, err_body) from e


def _http_stream(url: str, headers: dict, body: dict, timeout: int = 120) -> Iterator[str]:
    """Yield raw SSE lines from a streaming POST."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                yield raw.decode(errors="replace").rstrip("\n")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        raise HTTPError(e.code, err_body) from e


# ── base provider ─────────────────────────────────────────────────────────────

class BaseProvider:
    name: str = "base"

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.api_key = cfg.resolve_api_key() or ""

    def chat(
        self,
        messages: list[Message],
        system: Optional[str] = None,
        tools: Optional[list] = None,
        stream_cb=None,         # callable(str) -> None, called per token if streaming
    ) -> LLMResponse:
        raise NotImplementedError

    def _messages_to_dicts(self, messages: list[Message]) -> list[dict]:
        out = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            out.append(d)
        return out


# ── OpenAI-compatible (also covers Ollama, HF /v1) ───────────────────────────

class OpenAIProvider(BaseProvider):
    name = "openai"

    # Fragments that indicate the model doesn't support tool calling.
    # Matched case-insensitively against the 400 error body.
    _NO_TOOL_HINTS = (
        "tool calling",
        "tool_calling",
        "tools",
        "function calling",
        "function_call",
        "not supported",
    )

    def chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        # Honour explicit opt-out (e.g. compound-beta or other no-tool models)
        if self.cfg.no_tools:
            tools = None
        try:
            return self._do_chat(messages, system, tools, stream_cb)
        except HTTPError as e:
            if e.code == 400 and tools and self._is_tool_error(e.body):
                # Model doesn't support tool calling — retry without tools.
                # The agent loop will still work; it just won't call tools this turn.
                return self._do_chat(messages, system, tools=None, stream_cb=stream_cb)
            raise

    def _is_tool_error(self, body: str) -> bool:
        low = body.lower()
        return any(hint in low for hint in self._NO_TOOL_HINTS)

    def _do_chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(self._messages_to_dicts(messages))

        body: dict = {
            "model":      self.cfg.model,
            "messages":   msgs,
            "max_tokens": self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent":    "ish-harness/0.1.0",
        }

        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        use_stream = self.cfg.stream and stream_cb is not None

        t0 = time.time()

        if use_stream:
            body["stream"] = True
            collected = []
            tool_calls_buf = []
            for line in _http_stream(url, headers, body, self.cfg.__class__.__dict__.get("timeout", 120)):
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    collected.append(text)
                    stream_cb(text)
                if delta.get("tool_calls"):
                    tool_calls_buf.extend(delta["tool_calls"])

            content = "".join(collected)
            return LLMResponse(
                content=content,
                model=self.cfg.model,
                elapsed=time.time() - t0,
                tool_calls=tool_calls_buf or None,
            )
        else:
            body["stream"] = False
            resp = _http_post(url, headers, body)
            choice = resp.get("choices", [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content") or ""
            usage = resp.get("usage", {})
            return LLMResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model=resp.get("model", self.cfg.model),
                elapsed=time.time() - t0,
                tool_calls=msg.get("tool_calls"),
            )


# ── Anthropic Messages API ────────────────────────────────────────────────────

class AnthropicProvider(BaseProvider):
    name = "anthropic"
    API_VERSION = "2023-06-01"

    def chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        msgs = self._messages_to_dicts(messages)
        body: dict = {
            "model":      self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
            "messages":   msgs,
        }
        if system:
            body["system"] = system
        if tools:
            # Anthropic tool schema format
            body["tools"] = tools

        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         self.api_key,
            "anthropic-version": self.API_VERSION,
            "User-Agent":        "ish-harness/0.1.0",
        }

        url = self.cfg.base_url.rstrip("/") + "/v1/messages"
        use_stream = self.cfg.stream and stream_cb is not None

        t0 = time.time()

        if use_stream:
            body["stream"] = True
            collected = []
            for line in _http_stream(url, headers, body):
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event_type = obj.get("type", "")
                if event_type == "content_block_delta":
                    text = obj.get("delta", {}).get("text", "")
                    if text:
                        collected.append(text)
                        stream_cb(text)
            content = "".join(collected)
            return LLMResponse(content=content, model=self.cfg.model, elapsed=time.time() - t0)
        else:
            resp = _http_post(url, headers, body)
            parts = resp.get("content", [])
            content = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            usage = resp.get("usage", {})
            tool_use = [p for p in parts if p.get("type") == "tool_use"] or None
            return LLMResponse(
                content=content,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                model=resp.get("model", self.cfg.model),
                elapsed=time.time() - t0,
                tool_calls=tool_use,
            )


# ── Google Gemini REST API ────────────────────────────────────────────────────

class GeminiProvider(BaseProvider):
    name = "gemini"

    def chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        # Convert messages to Gemini format
        contents = []
        for m in messages:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.cfg.max_tokens,
                "temperature": self.cfg.temperature,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        model_id = self.cfg.model
        base = self.cfg.base_url.rstrip("/")
        url = f"{base}/models/{model_id}:generateContent?key={self.api_key}"

        t0 = time.time()
        headers = {"Content-Type": "application/json"}
        resp = _http_post(url, headers, body)

        candidates = resp.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

        usage = resp.get("usageMetadata", {})
        if stream_cb and text:
            stream_cb(text)

        return LLMResponse(
            content=text,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            model=model_id,
            elapsed=time.time() - t0,
        )


# ── HuggingFace Inference API (non-OpenAI path, e.g. raw model endpoints) ────

class HFProvider(BaseProvider):
    """
    Calls  POST /models/{model}  with the HF text-generation payload.
    Falls back to OpenAI-compat /v1 if base_url already ends in /v1.
    """
    name = "gemma"

    def chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        # Build a simple prompt from message history
        prompt = self._build_prompt(messages, system)

        base = self.cfg.base_url.rstrip("/")

        # If user pointed at the OpenAI-compat endpoint, delegate there
        if base.endswith("/v1"):
            oa = OpenAIProvider(self.cfg)
            return oa.chat(messages, system=system, tools=tools, stream_cb=stream_cb)

        url = f"{base}/{self.cfg.model}"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": self.cfg.max_tokens,
                "temperature":    self.cfg.temperature,
                "return_full_text": False,
            },
        }

        t0 = time.time()
        resp = _http_post(url, headers, body)

        if isinstance(resp, list) and resp:
            text = resp[0].get("generated_text", "")
        elif isinstance(resp, dict):
            text = resp.get("generated_text", "")
        else:
            text = str(resp)

        if stream_cb and text:
            stream_cb(text)

        return LLMResponse(content=text, model=self.cfg.model, elapsed=time.time() - t0)

    def _build_prompt(self, messages: list[Message], system: Optional[str]) -> str:
        """Build a chat-ML style prompt for HF models that don't get native chat."""
        parts = []
        if system:
            parts.append(f"<|system|>\n{system}\n")
        for m in messages:
            tag = "user" if m.role == "user" else "assistant"
            parts.append(f"<|{tag}|>\n{m.content}\n")
        parts.append("<|assistant|>\n")
        return "".join(parts)


# ── registry ──────────────────────────────────────────────────────────────────

_PROVIDER_MAP = {
    "openai":        OpenAIProvider,
    "anthropic":     AnthropicProvider,
    "gemini":        GeminiProvider,
    "gemma":         HFProvider,
    "groq":          OpenAIProvider,   # Groq is OpenAI-compatible
    "groq_compound": OpenAIProvider,   # Compound uses no_tools=True via config
    "hf_harness":    OpenAIProvider,   # HF /v1 is OpenAI-compat
    "ollama":        OpenAIProvider,   # Ollama speaks OpenAI-compat
}


def get_provider(name: str, cfg: ProviderConfig) -> BaseProvider:
    cls = _PROVIDER_MAP.get(name, OpenAIProvider)
    return cls(cfg)

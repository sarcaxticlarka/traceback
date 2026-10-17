"""Provider-agnostic LLM layer with automatic failover.

* ``AnthropicProvider``      - Claude via the Anthropic SDK.
* ``OpenAICompatProvider``   - any OpenAI-compatible Chat Completions API (OpenAI, Gemini, Groq, OpenRouter,
                               Mistral, DeepSeek, or a custom endpoint if explicitly allowed).
* ``FailoverClient``         - tries providers in priority order; on rate limit, quota, overload, timeout or an
                               invalid key it moves to the next one and records why.

Keys can come from the environment (server default) or from the user's request (frontend). User keys are held only
for the duration of the request, never logged, never persisted, and scrubbed from error messages.

Conversations use a small canonical format so a run can fail over mid-conversation:
    {"role": "user", "content": str}
    {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "input"}]}
    {"role": "tool", "tool_call_id": str, "content": str}
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

PRESETS: dict[str, dict[str, str]] = {
    "anthropic": {"label": "Anthropic (Claude)", "model": "claude-sonnet-5-5", "env": "ANTHROPIC_API_KEY", "base_url": ""},
    "openai": {"label": "OpenAI", "model": "gpt-4o-mini", "env": "OPENAI_API_KEY", "base_url": "https://api.openai.com/v1"},
    "gemini": {"label": "Google Gemini", "model": "gemini-2.0-flash", "env": "GEMINI_API_KEY",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    "groq": {"label": "Groq", "model": "llama-3.3-70b-versatile", "env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1"},
    "openrouter": {"label": "OpenRouter", "model": "openrouter/auto", "env": "OPENROUTER_API_KEY",
                   "base_url": "https://openrouter.ai/api/v1"},
    "mistral": {"label": "Mistral", "model": "mistral-small-latest", "env": "MISTRAL_API_KEY", "base_url": "https://api.mistral.ai/v1"},
    "deepseek": {"label": "DeepSeek", "model": "deepseek-chat", "env": "DEEPSEEK_API_KEY", "base_url": "https://api.deepseek.com/v1"},
    "custom": {"label": "Custom OpenAI-compatible", "model": "", "env": "", "base_url": ""},
}
FAILOVER_KINDS = {"rate_limit", "quota", "overloaded", "timeout", "auth", "network"}
REQUEST_TIMEOUT = 45.0


def allow_custom_base_url() -> bool:
    return os.getenv("TBK_ALLOW_CUSTOM_BASE_URL", "") == "1"


# ----------------------------------------------------------------------------------------------- types
@dataclass
class ProviderConfig:
    provider: str
    api_key: str
    model: str = ""
    base_url: str = ""

    def resolved(self) -> "ProviderConfig":
        if self.provider not in PRESETS:
            raise ValueError(f"unknown provider {self.provider!r}; choose from {sorted(PRESETS)}")
        p = PRESETS[self.provider]
        model = (self.model or p["model"]).strip()
        if self.provider == "custom":
            if not allow_custom_base_url():
                raise ValueError("custom base URLs are disabled on this server (set TBK_ALLOW_CUSTOM_BASE_URL=1)")
            base = self.base_url.strip()
            if not base.startswith(("http://", "https://")):
                raise ValueError("custom base_url must start with http:// or https://")
        else:
            base = p["base_url"]                      # presets ignore user-supplied URLs (no SSRF through the UI)
        if not model:
            raise ValueError(f"{self.provider}: a model name is required")
        return ProviderConfig(self.provider, self.api_key.strip(), model, base)

    @property
    def key_id(self) -> str:
        return hashlib.sha256(self.api_key.encode()).hexdigest()[:10]

    @staticmethod
    def from_dict(d: dict) -> "ProviderConfig":
        return ProviderConfig(str(d.get("provider", "")), str(d.get("api_key", "")), str(d.get("model", "") or ""),
                              str(d.get("base_url", "") or ""))


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    provider: str = ""
    model: str = ""


class ProviderError(Exception):
    def __init__(self, kind: str, message: str, provider: str = "", status: int | None = None, retry_after: float = 0.0):
        super().__init__(message)
        self.kind, self.provider, self.status, self.retry_after = kind, provider, status, retry_after


class Provider(Protocol):
    name: str
    model: str
    key_id: str

    def complete(self, system: str, messages: list[dict], tools: list[dict] | None, max_tokens: int) -> LLMResponse: ...


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


# ----------------------------------------------------------------------------------------------- anthropic
def _to_anthropic(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            blocks: list[dict] = []
            if m.get("text"):
                blocks.append({"type": "text", "text": m["text"]})
            for c in m.get("tool_calls", []):
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
        elif m["role"] == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)       # all results for one assistant turn go in one user message
            else:
                out.append({"role": "user", "content": [block]})
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, cfg: ProviderConfig, client: Any = None):
        self.cfg, self.model, self.key_id = cfg, cfg.model, cfg.key_id
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=cfg.api_key, timeout=REQUEST_TIMEOUT, max_retries=0)
        self.client = client

    def complete(self, system, messages, tools, max_tokens=1024) -> LLMResponse:
        kw: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": _to_anthropic(messages)}
        if system:
            kw["system"] = system
        if tools:
            kw["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools]
        try:
            resp = self.client.messages.create(**kw)
        except Exception as e:
            raise self._map(e) from None
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in resp.content if getattr(b, "type", "") == "tool_use"]
        return LLMResponse(text, calls, self.name, self.model)

    def _map(self, e: Exception) -> ProviderError:
        status = getattr(e, "status_code", None)
        msg = _scrub(str(e), self.cfg.api_key)[:300]
        cls = type(e).__name__
        kind = "other"
        if status == 429 or "RateLimit" in cls:
            kind = "rate_limit"
        elif status in (401, 403) or "Authentication" in cls or "PermissionDenied" in cls:
            kind = "auth"
        elif status == 402 or "credit balance" in msg.lower() or "quota" in msg.lower():
            kind = "quota"
        elif status in (500, 502, 503, 504, 529) or "Overloaded" in cls or "InternalServer" in cls:
            kind = "overloaded"
        elif "Timeout" in cls:
            kind = "timeout"
        elif "Connection" in cls:
            kind = "network"
        elif status == 400:
            kind = "bad_request"
        retry = 0.0
        headers = getattr(getattr(e, "response", None), "headers", None)
        if headers:
            try:
                retry = float(headers.get("retry-after", 0) or 0)
            except ValueError:
                pass
        return ProviderError(kind, f"{cls}: {msg}", self.name, status, retry)


# ----------------------------------------------------------------------------------------------- openai-compatible
def _to_openai(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("text") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c["name"], "arguments": json.dumps(c["input"])}}
                                     for c in m["tool_calls"]]
            out.append(msg)
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


class OpenAICompatProvider:
    def __init__(self, cfg: ProviderConfig, transport: httpx.BaseTransport | None = None):
        self.cfg, self.name, self.model, self.key_id = cfg, cfg.provider, cfg.model, cfg.key_id
        self.http = httpx.Client(base_url=cfg.base_url.rstrip("/"), timeout=REQUEST_TIMEOUT, transport=transport,
                                 headers={"Authorization": f"Bearer {cfg.api_key}"})

    def complete(self, system, messages, tools, max_tokens=1024) -> LLMResponse:
        body: dict[str, Any] = {"model": self.model, "messages": _to_openai(system, messages), "max_tokens": max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                                "parameters": t["input_schema"]}} for t in tools]
        try:
            r = self.http.post("/chat/completions", json=body)
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", f"timeout: {_scrub(str(e), self.cfg.api_key)}", self.name) from None
        except httpx.HTTPError as e:
            raise ProviderError("network", f"network: {_scrub(str(e), self.cfg.api_key)[:200]}", self.name) from None
        if r.status_code >= 400:
            raise self._map(r)
        data = r.json()
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(c.get("id") or f"call_{len(calls)}", fn.get("name", ""), args if isinstance(args, dict) else {}))
        return LLMResponse(msg.get("content") or "", calls, self.name, self.model)

    def _map(self, r: httpx.Response) -> ProviderError:
        text = _scrub(r.text, self.cfg.api_key)[:300]
        s = r.status_code
        low = text.lower()
        if s == 429 and ("insufficient_quota" in low or "quota" in low or "billing" in low):
            kind = "quota"
        elif s == 429:
            kind = "rate_limit"
        elif s in (401, 403):
            kind = "auth"
        elif s == 402:
            kind = "quota"
        elif s >= 500:
            kind = "overloaded"
        elif s == 400:
            kind = "bad_request"
        else:
            kind = "other"
        try:
            retry = float(r.headers.get("retry-after", 0) or 0)
        except ValueError:
            retry = 0.0
        return ProviderError(kind, f"HTTP {s}: {text}", self.name, s, retry)


def build_provider(cfg: ProviderConfig) -> Provider:
    cfg = cfg.resolved()
    if not cfg.api_key:
        raise ValueError(f"{cfg.provider}: API key is empty")
    return AnthropicProvider(cfg) if cfg.provider == "anthropic" else OpenAICompatProvider(cfg)


# ----------------------------------------------------------------------------------------------- failover
_COOLDOWN: dict[tuple[str, str], float] = {}
_COOLDOWN_LOCK = threading.Lock()
DEFAULT_COOLDOWN = {"rate_limit": 30.0, "quota": 600.0, "auth": 600.0, "overloaded": 15.0, "timeout": 10.0, "network": 10.0}


def _cooling(p: Provider) -> bool:
    with _COOLDOWN_LOCK:
        return _COOLDOWN.get((p.name, p.key_id), 0) > time.time()


def _cool(p: Provider, err: ProviderError) -> None:
    secs = max(err.retry_after, DEFAULT_COOLDOWN.get(err.kind, 10.0))
    with _COOLDOWN_LOCK:
        _COOLDOWN[(p.name, p.key_id)] = time.time() + min(secs, 900)


def reset_cooldowns() -> None:
    with _COOLDOWN_LOCK:
        _COOLDOWN.clear()


@dataclass
class FailoverClient:
    """Tries providers in order. ``events`` records every failover; ``used`` is the last provider that answered."""
    providers: list[Provider]
    events: list[dict] = field(default_factory=list)
    used: str = ""
    calls: int = 0

    def complete(self, system: str, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 1024) -> LLMResponse:
        ready = [p for p in self.providers if not _cooling(p)] or self.providers      # if all cooling, try anyway
        last: ProviderError | None = None
        for p in ready:
            try:
                resp = p.complete(system, messages, tools, max_tokens)
            except ProviderError as e:
                last = e
                self.events.append({"provider": p.name, "model": p.model, "kind": e.kind, "message": str(e)[:200]})
                if e.kind in FAILOVER_KINDS:
                    _cool(p, e)
                    continue
                raise
            self.used = f"{p.name}/{p.model}"
            self.calls += 1
            return resp
        raise last or ProviderError("other", "no LLM providers configured")

    def summary(self) -> dict:
        return {"used": self.used, "calls": self.calls, "failovers": self.events,
                "providers": [f"{p.name}/{p.model}" for p in self.providers]}


# ----------------------------------------------------------------------------------------------- resolution
_request_configs: ContextVar[list[ProviderConfig] | None] = ContextVar("tbk_llm_configs", default=None)


@contextmanager
def llm_scope(configs: list[ProviderConfig] | None):
    """Make the user's request-supplied providers visible to everything running inside this request."""
    token = _request_configs.set(configs)
    try:
        yield
    finally:
        _request_configs.reset(token)


def parse_user_configs(raw: list[dict] | None, limit: int = 6) -> list[ProviderConfig]:
    out = []
    for d in (raw or [])[:limit]:
        cfg = ProviderConfig.from_dict(d)
        if cfg.api_key:
            cfg.resolved()                               # validates provider / url / model, raises ValueError
            out.append(cfg)
    return out


def env_configs() -> list[ProviderConfig]:
    out = []
    for name, p in PRESETS.items():
        key = os.getenv(p["env"]) if p["env"] else None
        if key:
            out.append(ProviderConfig(name, key, os.getenv("TBK_LLM_MODEL", "") if name == "anthropic" else ""))
    return out


def configured_providers() -> list[ProviderConfig]:
    """User-supplied providers (priority) followed by server-default ones, de-duplicated by key."""
    seen, out = set(), []
    for c in (_request_configs.get() or []) + env_configs():
        k = (c.provider, c.key_id)
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def resolve_client(use_llm: bool | None = None) -> FailoverClient | None:
    """None when LLMs are disabled or no provider is configured (the offline planner then runs)."""
    if use_llm is False:
        return None
    providers = []
    for c in configured_providers():
        try:
            providers.append(build_provider(c))
        except ValueError:
            continue
    return FailoverClient(providers) if providers else None

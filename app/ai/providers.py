"""
ai/providers.py — Model providers behind the AI gateway.

* OpenAICompatibleProvider: any endpoint speaking the OpenAI chat-completions
  protocol (hosted gateways, vLLM, etc.). Configured by KYRO_LLM_BASE_URL,
  KYRO_LLM_API_KEY and KYRO_LLM_MODEL.
* MockProvider: deterministic local responses for tests, CI and demos; never
  makes a network call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx


class AIProviderError(RuntimeError):
    """Provider call failed. Messages never include the API key or request body."""


@dataclass
class ProviderResult:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int = 30):
        if not base_url or not api_key:
            raise AIProviderError("KYRO_LLM_BASE_URL and KYRO_LLM_API_KEY must be set when KYRO_LLM_MOCK=false")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._timeout = timeout_seconds

    def complete(self, system: str, user: str, *, max_tokens: int, temperature: float = 0.0) -> ProviderResult:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        try:
            response = httpx.post(self.url, headers=self._headers, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise AIProviderError(f"LLM request failed: {type(exc).__name__}") from None

        if response.status_code >= 400:
            # Keep only a short, sanitised snippet of the provider's error
            detail = re.sub(r"sk-[A-Za-z0-9]{8,}", "sk-***", response.text[:300])
            raise AIProviderError(f"LLM returned HTTP {response.status_code}: {detail}")

        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIProviderError("LLM response was not in chat-completions format") from None

        usage = body.get("usage") or {}
        return ProviderResult(
            text=text,
            model=body.get("model") or self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock"):
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int, temperature: float = 0.0) -> ProviderResult:
        # Echo back any {"echo": "..."} request so the connectivity check round-trips
        echo = re.search(r'"echo":\s*"([^"]*)"', user)
        if echo:
            text = json.dumps({"status": "ok", "echo": echo.group(1), "mock": True})
        elif "JSON" in system or "json" in system:
            text = json.dumps({"mock": True, "summary": "Mock response: AI provider is in mock mode."})
        else:
            text = "Mock response: AI provider is in mock mode."
        return ProviderResult(text=text, model=f"mock:{self.model}", prompt_tokens=0, completion_tokens=0)

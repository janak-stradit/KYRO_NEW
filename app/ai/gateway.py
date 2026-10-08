"""
ai/gateway.py — The single entry point for AI calls in KYRO (Phase 11.0).

    result = AIGateway(db).run(
        "system.connectivity_check", {"nonce": "abc"},
        sensitive={"John James": "PERSON"}, entity_type="ALERT", entity_id=alert.id,
        requested_by=user.id,
    )

For every call it: checks the kill switch, renders a versioned prompt,
redacts personal data, calls the provider (or the mock), parses JSON when the
prompt asks for it, restores the redacted values for display, and writes an
`ai_interactions` row — including for failures and disabled calls.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.ai.prompts import get_prompt
from app.ai.providers import AIProviderError, MockProvider, OpenAICompatibleProvider
from app.ai.redaction import Redactor
from app.config import Settings, get_settings
from app.models.ai_interaction import AIInteraction


class AIDisabledError(RuntimeError):
    """AI features are switched off (KYRO_AI_ENABLED=false)."""


@dataclass
class AIResult:
    interaction_id: uuid.UUID
    text: str
    data: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""
    prompt_id: str = ""
    prompt_version: int = 0
    latency_ms: int = 0
    redaction_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _parse_json(text: str) -> dict[str, Any] | None:
    """Accept plain JSON or JSON wrapped in a ```json fence / surrounding prose."""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        candidates.append(fenced.group(1))
    braces = re.search(r"\{.*\}", text, re.S)
    if braces:
        candidates.append(braces.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    return None


def _restore_json(value: Any, redactor: Redactor) -> Any:
    if isinstance(value, str):
        return redactor.restore(value)
    if isinstance(value, list):
        return [_restore_json(v, redactor) for v in value]
    if isinstance(value, dict):
        return {k: _restore_json(v, redactor) for k, v in value.items()}
    return value


class AIGateway:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    # ── configuration ────────────────────────────────────────────
    def _provider(self):
        s = self.settings
        if s.kyro_llm_mock:
            return MockProvider(s.kyro_llm_model)
        return OpenAICompatibleProvider(
            base_url=s.kyro_llm_base_url,
            api_key=s.kyro_llm_api_key.get_secret_value(),
            model=s.kyro_llm_model,
            timeout_seconds=s.kyro_llm_timeout_seconds,
        )

    def status(self) -> dict[str, Any]:
        """Configuration summary safe to show to admins (never the key)."""
        s = self.settings
        return {
            "enabled": s.kyro_ai_enabled,
            "mock": s.kyro_llm_mock,
            "provider": "mock" if s.kyro_llm_mock else OpenAICompatibleProvider.name,
            "model": s.kyro_llm_model,
            "endpoint_host": urlparse(s.kyro_llm_base_url).hostname if s.kyro_llm_base_url else None,
            "api_key_configured": bool(s.kyro_llm_api_key.get_secret_value()),
        }

    # ── main entry point ─────────────────────────────────────────
    def run(
        self,
        prompt_id: str,
        variables: dict[str, Any],
        *,
        sensitive: dict[str, str] | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        requested_by: uuid.UUID | None = None,
    ) -> AIResult:
        prompt = get_prompt(prompt_id)
        redactor = Redactor(known=dict(sensitive or {}))
        system, user = prompt.render({k: redactor.redact(str(v)) for k, v in variables.items()})
        system, user = redactor.redact(system), redactor.redact(user)

        log = AIInteraction(
            feature=prompt.feature,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            provider="mock" if self.settings.kyro_llm_mock else OpenAICompatibleProvider.name,
            model=self.settings.kyro_llm_model,
            input_redacted=(f"[system]\n{system}\n\n" if system else "") + f"[user]\n{user}",
            redaction_count=redactor.count,
            entity_type=entity_type,
            entity_id=entity_id,
            requested_by=requested_by,
        )

        if not self.settings.kyro_ai_enabled:
            log.status = "DISABLED"
            log.error = "AI features are disabled (KYRO_AI_ENABLED=false)"
            self._save(log)
            raise AIDisabledError(log.error)

        started = time.perf_counter()
        try:
            provider = self._provider()
            result = provider.complete(system, user, max_tokens=prompt.max_tokens)
        except AIProviderError as exc:
            log.status = "ERROR"
            log.error = str(exc)
            log.latency_ms = int((time.perf_counter() - started) * 1000)
            self._save(log)
            raise

        log.latency_ms = int((time.perf_counter() - started) * 1000)
        log.status = "SUCCESS"
        log.model = result.model
        log.prompt_tokens = result.prompt_tokens
        log.completion_tokens = result.completion_tokens
        log.output_text = result.text  # stored still redacted

        warnings: list[str] = []
        data = None
        if prompt.response_format == "json":
            data = _parse_json(result.text)
            if data is None:
                warnings.append("Model did not return valid JSON")
            log.output_json = data
        self._save(log)

        return AIResult(
            interaction_id=log.id,
            text=redactor.restore(result.text),
            data=_restore_json(data, redactor) if data is not None else None,
            provider=log.provider,
            model=log.model,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            latency_ms=log.latency_ms,
            redaction_count=redactor.count,
            warnings=warnings,
        )

    def _save(self, log: AIInteraction) -> None:
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

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


_MOCK_DEADLINE = re.compile(
    r"(within \d+ (?:calendar |business )?days[^,.;]*|no later than [^,.;]*|for (?:a period of )?\w+ years)", re.I
)
_MOCK_CATEGORIES = (
    ("REPORTING", r"\b(report|file|filing|notif)"),
    ("RECORDKEEPING", r"\b(record|retain|maintain a copy)"),
    ("CUSTOMER_IDENTIFICATION", r"\b(identif|verif)"),
    ("PROGRAM", r"\b(program|polic|procedure|training|independent testing)"),
    ("MONITORING", r"\b(monitor|due diligence)"),
)


def _mock_obligations(text: str, limit: int = 8) -> list[dict]:
    """
    Rule-of-thumb stand-in for the model: every sentence saying someone
    "shall" or "must" do something becomes a proposed obligation. Good enough
    to exercise the review workflow without a provider; not a substitute for it.
    """
    obligations = []
    for sentence in re.split(r"(?<=[.;:])\s+", text):
        sentence = sentence.strip()
        match = re.match(r"^(?:\([A-Za-z0-9]+\)\s*)*(?:[A-Z][\w ]{2,40}\.\s+)?(.*?)\b(shall|must)\b\s+(.+)$", sentence, re.S)
        if not match or re.match(r"(not be construed|mean)\b", match.group(3)):
            continue
        party = re.sub(r"^(?:\([A-Za-z0-9]+\)\s*)+", "", match.group(1)).strip(" ,") or "Covered institution"
        deadline = _MOCK_DEADLINE.search(sentence)
        category = next((c for c, pattern in _MOCK_CATEGORIES if re.search(pattern, sentence, re.I)), "OTHER")
        obligations.append(
            {
                "obligated_party": party[:200],
                "action": match.group(3).rstrip(".;:")[:400],
                "deadline": deadline.group(1) if deadline else None,
                "condition": None,
                "category": category,
                "source_quote": sentence,
            }
        )
        if len(obligations) >= limit:
            break
    return obligations


_MOCK_CONTROL_KEYWORDS = (
    ("R001", r"currency|\$10,000"),
    ("CASE_DISPOSITION", r"suspicious|\bSAR\b"),
    ("SCREENING", r"sanction|OFAC|government list|designated"),
    ("UBO_REGISTER", r"beneficial owner"),
    ("CUSTOMER_ONBOARDING", r"identity of|identif\w+ (?:of|number|information)|customer identification"),
    ("KYC_REVIEW", r"ongoing|periodic|update customer information"),
    ("AUDIT_LOG", r"\bretain|\brecords?\b"),
)


def _mock_mappings(obligation_text: str) -> list[dict]:
    """Keyword stand-in for the model; an obligation with no keyword hit is a gap."""
    return [
        {"control_code": code, "rationale": "Mock mapping: the obligation mentions terms this control deals with."}
        for code, pattern in _MOCK_CONTROL_KEYWORDS
        if re.search(pattern, obligation_text, re.I)
    ][:3]


_MOCK_DOCUMENT_LABELS = (
    ("full_name", r"(?:full )?name|surname and given names|account holder|customer"),
    ("company_name", r"company name|registered name|legal name|entity name"),
    ("date_of_birth", r"date of birth|dob|born"),
    ("nationality", r"nationality|citizenship"),
    ("id_number", r"(?:passport|document|id|identity card|licen[cs]e) (?:number|no\.?)"),
    ("issue_date", r"(?:date of issue|issue date|issued(?: on)?|statement date|date)"),
    ("expiry_date", r"(?:date of expiry|expiry date|expires(?: on)?|valid until)"),
    ("registration_number", r"(?:company|registration|registered) (?:number|no\.?)"),
    ("incorporation_date", r"(?:date of incorporation|incorporated(?: on)?)"),
    ("address", r"(?:registered |residential )?address"),
    ("country", r"country(?: of (?:residence|incorporation))?"),
    ("director", r"director"),
    ("beneficial_owner", r"(?:ultimate )?beneficial owner|shareholder|ubo"),
    ("period_end", r"period end(?:ing)?|year end(?:ed)?"),
    ("total_assets", r"total assets"),
    ("revenue", r"revenue|turnover"),
    ("net_income", r"net (?:income|profit)"),
    ("source_of_funds", r"source of (?:funds|wealth)"),
    ("amount", r"amount"),
)


def _mock_document_fields(user: str) -> list[dict]:
    """
    Stand-in for the model on documents: reads "Label: value" lines. It only
    finds fields a document labels explicitly, which is enough to exercise
    the review workflow without a provider.
    """
    wanted = set(re.findall(r"[a-z_]+", user.split("Fields to extract:", 1)[1].split("\n", 1)[0]))
    fields, page = [], 1
    for line in user.split("Document text:", 1)[1].splitlines():
        marker = re.fullmatch(r"\s*\[Page (\d+)\]\s*", line)
        if marker:
            page = int(marker.group(1))
            continue
        for field, labels in _MOCK_DOCUMENT_LABELS:
            match = re.match(rf"\s*(?:{labels})\s*[:\-]\s*(.+?)\s*$", line, re.I)
            if match and field in wanted:
                fields.append({"field": field, "value": match.group(1), "page": page, "source_quote": line.strip(), "confidence": 0.6})
                break
    return fields[:40]


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock"):
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int, temperature: float = 0.0) -> ProviderResult:
        # Echo back any {"echo": "..."} request so the connectivity check round-trips
        echo = re.search(r'"echo":\s*"([^"]*)"', user)
        if echo:
            text = json.dumps({"status": "ok", "echo": echo.group(1), "mock": True})
        elif "obligations" in system and "Section text:" in user:
            text = json.dumps({"obligations": _mock_obligations(user.split("Section text:", 1)[1])})
        elif "Document text:" in user and "Fields to extract:" in user:
            text = json.dumps({"fields": _mock_document_fields(user)})
        elif "Control catalogue:" in user:
            text = json.dumps({"mappings": _mock_mappings(user.split("Control catalogue:", 1)[0])})
        elif "JSON" in system or "json" in system:
            text = json.dumps({"mock": True, "summary": "Mock response: AI provider is in mock mode."})
        else:
            text = "Mock response: AI provider is in mock mode."
        return ProviderResult(text=text, model=f"mock:{self.model}", prompt_tokens=0, completion_tokens=0)

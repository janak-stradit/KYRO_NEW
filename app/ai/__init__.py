"""
ai — Compliance AI foundation (Phase 11.0, docs/plans/COMPLIANCE_AI_PLAN.md).

All AI calls go through AIGateway: kill switch, versioned prompts, PII
redaction, provider abstraction and an audit row per call.
"""
from app.ai.gateway import AIDisabledError, AIGateway, AIResult
from app.ai.prompts import PromptError, get_prompt
from app.ai.providers import AIProviderError

__all__ = ["AIGateway", "AIResult", "AIDisabledError", "AIProviderError", "PromptError", "get_prompt"]

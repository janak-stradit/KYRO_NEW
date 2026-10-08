"""
ai/prompts.py — Versioned prompt registry.

Each prompt is a Markdown file in app/ai/prompt_templates/ with a small header:

    ---
    id: system.connectivity_check
    version: 1
    feature: system
    response_format: json        # or: text
    max_tokens: 200
    ---
    ## system
    You are ...
    ## user
    Reply with {{thing}} ...

Variables use {{name}}. Changing a prompt means bumping its version, so every
logged AI output can be traced to the exact prompt text that produced it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompt_templates"
_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    id: str
    version: int
    feature: str
    response_format: str  # "json" or "text"
    max_tokens: int
    system: str
    user: str

    def variables(self) -> set[str]:
        return set(_VAR.findall(self.system)) | set(_VAR.findall(self.user))

    def render(self, variables: dict[str, str]) -> tuple[str, str]:
        missing = self.variables() - set(variables)
        if missing:
            raise PromptError(f"Prompt {self.id} is missing variables: {', '.join(sorted(missing))}")

        def fill(template: str) -> str:
            return _VAR.sub(lambda m: str(variables[m.group(1)]), template)

        return fill(self.system), fill(self.user)


def _parse(path: Path) -> Prompt:
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not match:
        raise PromptError(f"{path.name}: missing '---' header")
    header: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()

    sections = re.split(r"^##\s*(system|user)\s*$", match.group(2), flags=re.M)
    parts = {sections[i]: sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    if "user" not in parts:
        raise PromptError(f"{path.name}: needs a '## user' section")

    try:
        return Prompt(
            id=header["id"],
            version=int(header["version"]),
            feature=header.get("feature", "general"),
            response_format=header.get("response_format", "text"),
            max_tokens=int(header.get("max_tokens", 800)),
            system=parts.get("system", ""),
            user=parts["user"],
        )
    except (KeyError, ValueError) as exc:
        raise PromptError(f"{path.name}: bad header ({exc})") from exc


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, Prompt]:
    prompts: dict[str, Prompt] = {}
    for path in sorted(PROMPT_DIR.glob("*.md")):
        prompt = _parse(path)
        if prompt.id in prompts:
            raise PromptError(f"Duplicate prompt id {prompt.id} in {path.name}")
        prompts[prompt.id] = prompt
    return prompts


def get_prompt(prompt_id: str) -> Prompt:
    try:
        return load_prompts()[prompt_id]
    except KeyError:
        raise PromptError(f"Unknown prompt: {prompt_id}") from None

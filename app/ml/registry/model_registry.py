"""
ml/registry/model_registry.py — Pickle-based model storage with versioning
and a lightweight active/candidate pointer per model name (enough for a real
A/B rollout: route a traffic percentage to a candidate version and compare
outcomes before promoting it).

Chosen over MLflow for Phase 2: no extra service to run, and version/rollback
semantics are simple enough that a JSON pointer file covers it.
"""
from __future__ import annotations

import json
import os
import pickle
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

POINTERS_FILE = "registry.json"


def _make_world_writable(path: Path) -> None:
    """models/ is typically a host bind-mount, and the container's non-root
    user's UID rarely matches the host user's — whichever side writes a file
    first otherwise locks the other side out of ever updating it. Chmod'ing
    to 666 right after a write we own keeps it writable from both sides."""
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


class ModelNotFoundError(RuntimeError):
    pass


class ModelRegistry:
    def __init__(self, models_dir: Path | str | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else Path(get_settings().model_registry_path)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._pointers_path = self.models_dir / POINTERS_FILE

    # ── Pointer file (active/candidate per model name) ──────────
    def _read_pointers(self) -> dict[str, Any]:
        if not self._pointers_path.exists():
            return {}
        with self._pointers_path.open("r") as f:
            return json.load(f)

    def _write_pointers(self, pointers: dict[str, Any]) -> None:
        with self._pointers_path.open("w") as f:
            json.dump(pointers, f, indent=2)
        _make_world_writable(self._pointers_path)

    # ── Save / load model artifacts ──────────────────────────────
    def save_model(self, model: Any, name: str, version: int, metrics: dict) -> str:
        path = self.models_dir / f"{name}_v{version}.pkl"
        artifact = {
            "model": model,
            "name": name,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "feature_names": getattr(model, "feature_names", None),
        }
        with path.open("wb") as f:
            pickle.dump(artifact, f)
        _make_world_writable(path)
        return str(path)

    def list_versions(self, name: str) -> list[int]:
        versions = []
        for p in self.models_dir.glob(f"{name}_v*.pkl"):
            try:
                versions.append(int(p.stem.rsplit("_v", 1)[1]))
            except (IndexError, ValueError):
                continue
        return sorted(versions)

    def next_version(self, name: str) -> int:
        existing = self.list_versions(name)
        return (existing[-1] + 1) if existing else 1

    def load_model(self, name: str, version: int | None = None) -> dict:
        if version is None:
            versions = self.list_versions(name)
            if not versions:
                raise ModelNotFoundError(f"No versions found for model '{name}'")
            version = versions[-1]
        path = self.models_dir / f"{name}_v{version}.pkl"
        if not path.exists():
            raise ModelNotFoundError(f"Model '{name}' version {version} not found at {path}")
        with path.open("rb") as f:
            return pickle.load(f)

    # ── Active / candidate routing (basic A/B) ───────────────────
    def set_active(self, name: str, version: int) -> None:
        pointers = self._read_pointers()
        entry = pointers.setdefault(name, {})
        entry["active"] = version
        self._write_pointers(pointers)

    def set_candidate(self, name: str, version: int, traffic_pct: float) -> None:
        pointers = self._read_pointers()
        entry = pointers.setdefault(name, {})
        entry["candidate"] = version
        entry["candidate_traffic_pct"] = traffic_pct
        self._write_pointers(pointers)

    def promote_candidate(self, name: str) -> int:
        pointers = self._read_pointers()
        entry = pointers.get(name, {})
        candidate = entry.get("candidate")
        if candidate is None:
            raise ModelNotFoundError(f"No candidate set for model '{name}'")
        entry["active"] = candidate
        entry["candidate"] = None
        entry["candidate_traffic_pct"] = 0
        self._write_pointers(pointers)
        return candidate

    def get_routing(self, name: str) -> dict:
        pointers = self._read_pointers()
        entry = pointers.get(name)
        if entry is None or entry.get("active") is None:
            versions = self.list_versions(name)
            if not versions:
                raise ModelNotFoundError(f"No versions found for model '{name}'")
            entry = {"active": versions[-1], "candidate": None, "candidate_traffic_pct": 0}
            self._write_pointers({**pointers, name: entry})
        return entry

    def resolve_serving_version(self, name: str) -> tuple[int, bool]:
        """Returns (version, is_candidate) — randomly routes to the
        candidate at its configured traffic percentage, active otherwise."""
        entry = self.get_routing(name)
        candidate = entry.get("candidate")
        traffic_pct = entry.get("candidate_traffic_pct", 0) or 0
        if candidate is not None and random.random() * 100 < traffic_pct:
            return candidate, True
        return entry["active"], False

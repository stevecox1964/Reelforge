"""Per-stage model registry and resolution.

A global catalog seeds .studio/models.json on first use. Per-project overrides
live in Projects/<name>/project.json under a "models" block. Stage scripts call
resolve_model(stage, project) instead of hardcoding an endpoint, so the model a
stage runs with is driven by the studio UI / project config.

Only model IDs confirmed working in this project belong in DEFAULT_REGISTRY —
FAL returns opaque 404s for invalid IDs, so never add an unverified endpoint.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import REPO_ROOT, project_paths


REGISTRY_PATH = REPO_ROOT / ".studio" / "models.json"


# Catalog of stages -> {default key, models{key -> spec}}. `label` is for UI
# display; `endpoint` is the FAL model id passed to the runner.
DEFAULT_REGISTRY: dict = {
    "stages": {
        "storyboards": {
            "default": "flux-schnell",
            "models": {
                "flux-schnell": {
                    "label": "Flux Schnell",
                    "provider": "fal",
                    "endpoint": "fal-ai/flux/schnell",
                    "notes": "Fast & cheap. Default. Hallucinates in-frame text.",
                },
                "gpt-image-2": {
                    "label": "GPT Image 2",
                    "provider": "fal",
                    "endpoint": "openai/gpt-image-2",
                    "notes": "BYOK OpenAI (needs OPENAI_API_KEY). Renders in-frame text cleanly.",
                },
            },
        },
        "clips": {
            "default": "kling-v3",
            "models": {
                "kling-v3": {
                    "label": "Kling V3",
                    "provider": "fal",
                    "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
                    "notes": "Image-to-video. Default.",
                },
            },
        },
        "voiceover": {
            "default": "xai-tts-v1",
            "models": {
                "xai-tts-v1": {
                    "label": "xAI TTS v1",
                    "provider": "fal",
                    "endpoint": "xai/tts/v1",
                    "notes": "xAI text-to-speech. Default.",
                },
            },
        },
    }
}


def seed_registry() -> Path:
    """Write the default registry to .studio/models.json if it doesn't exist yet."""
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(json.dumps(DEFAULT_REGISTRY, indent=2) + "\n", encoding="utf-8")
    return REGISTRY_PATH


def load_registry() -> dict:
    """Return the registry, seeding the default catalog on first call."""
    seed_registry()
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _stage_entry(registry: dict, stage: str) -> dict:
    entry = registry.get("stages", {}).get(stage)
    if not entry:
        known = ", ".join(registry.get("stages", {}))
        raise KeyError(f"Unknown stage '{stage}'. Known stages: {known}")
    return entry


def project_models(project: str) -> dict:
    """Return the per-project model override block (key per stage), or {}."""
    pp = project_paths(project)
    if not pp.config.exists():
        return {}
    cfg = json.loads(pp.config.read_text(encoding="utf-8"))
    return cfg.get("models") or {}


def resolve_model(stage: str, project: str | None = None) -> str:
    """Resolve a stage's FAL endpoint, honoring a per-project override.

    Precedence: project.json models[stage] key -> stage default key. The chosen
    key is looked up in the registry to get its endpoint. Fails loud (KeyError)
    if the key is unknown so a bad override surfaces in the job output instead
    of silently falling back.
    """
    registry = load_registry()
    entry = _stage_entry(registry, stage)
    models = entry.get("models", {})
    key = entry.get("default")
    if project:
        override = project_models(project).get(stage)
        if override:
            key = override
    spec = models.get(key)
    if not spec:
        known = ", ".join(models)
        raise KeyError(f"Model '{key}' not in registry for stage '{stage}'. Known: {known}")
    return spec["endpoint"]

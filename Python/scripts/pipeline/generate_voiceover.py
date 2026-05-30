"""Generate voiceover audio for a project (paid FAL TTS stage)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import project_paths, rel_to_repo
from fal_runner import run_fal
from status import load_manifest, save_manifest, upsert_generation, update_stage, print_stage_card, update_project_stage


DEFAULT_MODEL = "xai/tts/v1"


def generate(project: str, *, model: str = DEFAULT_MODEL) -> dict:
    pp = project_paths(project)
    if not pp.voiceover_recipe.exists():
        raise FileNotFoundError(f"Voiceover recipe missing: {pp.voiceover_recipe}")
    pp.ensure_dirs()
    print(f"\nGenerating voiceover with {model}", flush=True)
    out = run_fal(
        model=model, recipe=pp.voiceover_recipe,
        media_dst=pp.voiceover_audio(".mp3"),
        fal_results_dir=pp.fal_results_dir,
        fallback_ext=".mp3",
    )

    manifest = load_manifest(pp.manifest)
    upsert_generation(
        manifest, scene_id="voiceover", mode="text_to_speech",
        model=model, recipe=rel_to_repo(pp.voiceover_recipe),
        output_json=rel_to_repo(out.result_json_path),
        media_files=[rel_to_repo(out.media_path)] if out.media_path else [],
        notes="Voiceover audio generated.",
        decision="pending_review",
    )
    update_stage(manifest,
                 approval_status="voiceover_pending_approval",
                 completed_labels=["Voiceover generated"])
    save_manifest(pp.manifest, manifest)
    update_project_stage(pp.config, "voiceover")
    return {"project": project, "media_path": rel_to_repo(out.media_path) if out.media_path else None}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Generate voiceover audio.")
    parser.add_argument("project")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    out = generate(args.project, model=args.model)
    pp = project_paths(args.project)
    print_stage_card(
        title="VIDEO PIPELINE: VOICEOVER COMPLETE",
        project=args.project,
        status="Voiceover generated. Awaiting approval before assembly.",
        artifacts=[pp.audio_dir],
        next_steps=["Listen to the voiceover.",
                    "Approve to assemble the review cut."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

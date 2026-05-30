"""Generate storyboard stills for a project (paid FAL stage)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import project_paths, rel_to_repo
from fal_runner import run_fal
from status import load_manifest, save_manifest, upsert_generation, update_stage, print_stage_card, update_project_stage


DEFAULT_MODEL = "fal-ai/flux/schnell"


def generate(project: str, *, model: str = DEFAULT_MODEL,
             only: list[str] | None = None) -> dict:
    pp = project_paths(project)
    if not pp.scene_plan.exists():
        raise FileNotFoundError(f"Scene plan missing: {pp.scene_plan}")
    plan = json.loads(pp.scene_plan.read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    if only:
        scenes = [s for s in scenes if s.get("id") in set(only)]

    pp.ensure_dirs()
    manifest = load_manifest(pp.manifest)
    results = []

    for scene in scenes:
        sid = scene["id"]
        recipe_path = pp.storyboard_recipe(sid)
        if not recipe_path.exists():
            raise FileNotFoundError(f"Storyboard recipe missing: {recipe_path}")
        print(f"\nGenerating storyboard for {sid}", flush=True)
        out = run_fal(
            model=model, recipe=recipe_path,
            media_dst=pp.still_for(sid, ".png"),
            fal_results_dir=pp.fal_results_dir,
            fallback_ext=".png",
        )
        if out.media_path:
            results.append({"scene_id": sid, "media_path": rel_to_repo(out.media_path)})
        upsert_generation(
            manifest, scene_id=sid, mode="text_to_image",
            model=model, recipe=rel_to_repo(recipe_path),
            output_json=rel_to_repo(out.result_json_path),
            media_files=[rel_to_repo(out.media_path)] if out.media_path else [],
            notes="Storyboard still generated; awaiting review before image-to-video.",
            decision="pending_review",
        )

    update_stage(manifest,
                 approval_status="storyboard_stills_pending_approval",
                 completed_labels=["Storyboard stills generated"])
    save_manifest(pp.manifest, manifest)
    update_project_stage(pp.config, "storyboards")
    return {"project": project, "scenes": results}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Generate storyboard stills for a project.")
    parser.add_argument("project")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--scene", action="append", help="Limit to specific scene id(s).")
    args = parser.parse_args()
    out = generate(args.project, model=args.model, only=args.scene)
    pp = project_paths(args.project)
    print_stage_card(
        title="VIDEO PIPELINE: STORYBOARDS COMPLETE",
        project=args.project,
        status=f"Generated {len(out['scenes'])} still(s). Awaiting approval.",
        artifacts=[pp.stills_dir],
        next_steps=["Review the stills in the studio UI.",
                    "Approve to start clip animation (paid)."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

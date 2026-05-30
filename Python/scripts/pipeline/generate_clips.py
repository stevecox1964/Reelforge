"""Animate storyboard stills into image-to-video clips (paid FAL stage)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import project_paths, rel_to_repo
from fal_runner import run_fal
from status import load_manifest, save_manifest, upsert_generation, update_stage, print_stage_card, update_project_stage


DEFAULT_MODEL = "fal-ai/kling-video/v3/standard/image-to-video"


def generate(project: str, *, model: str = DEFAULT_MODEL,
             only: list[str] | None = None) -> dict:
    pp = project_paths(project)
    plan = json.loads(pp.scene_plan.read_text(encoding="utf-8"))
    scenes = plan.get("scenes", [])
    if only:
        scenes = [s for s in scenes if s.get("id") in set(only)]

    pp.ensure_dirs()
    manifest = load_manifest(pp.manifest)
    results = []

    for scene in scenes:
        sid = scene["id"]
        recipe_path = pp.clip_recipe(sid)
        if not recipe_path.exists():
            raise FileNotFoundError(f"Clip recipe missing: {recipe_path}")
        still = pp.existing_still(sid)
        if still is None:
            raise FileNotFoundError(f"No storyboard still found for {sid} in {pp.stills_dir}")
        print(f"\nAnimating {sid} from {still.name}", flush=True)
        out = run_fal(
            model=model, recipe=recipe_path,
            media_dst=pp.clip_for(sid, ".mp4"),
            fal_results_dir=pp.fal_results_dir,
            upload_files={"start_image_url": still},
            fallback_ext=".mp4",
        )
        if out.media_path:
            results.append({"scene_id": sid, "media_path": rel_to_repo(out.media_path)})
        upsert_generation(
            manifest, scene_id=sid, mode="image_to_video",
            model=model, recipe=rel_to_repo(recipe_path),
            output_json=rel_to_repo(out.result_json_path),
            media_files=[rel_to_repo(out.media_path)] if out.media_path else [],
            source_image=rel_to_repo(still),
            notes="Animated clip generated from approved still.",
            decision="pending_review",
        )

    update_stage(manifest,
                 approval_status="video_clips_pending_approval",
                 completed_labels=["Video clips generated"])
    save_manifest(pp.manifest, manifest)
    update_project_stage(pp.config, "clips")
    return {"project": project, "scenes": results}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Animate stills into clips.")
    parser.add_argument("project")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--scene", action="append")
    args = parser.parse_args()
    out = generate(args.project, model=args.model, only=args.scene)
    pp = project_paths(args.project)
    print_stage_card(
        title="VIDEO PIPELINE: CLIPS COMPLETE",
        project=args.project,
        status=f"Generated {len(out['scenes'])} clip(s). Awaiting approval.",
        artifacts=[pp.clips_dir],
        next_steps=["Review the clips in the studio UI.",
                    "Approve to generate voiceover (paid)."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

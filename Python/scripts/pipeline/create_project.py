"""Create a new project under Projects/<name>/ from one idea."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import REPO_ROOT, project_paths, slugify
from status import print_stage_card


VIDEO_TYPES = ("animated_story", "product_promo", "app_demo", "explainer", "logo_reveal")


def infer_project_name(idea: str) -> str:
    import re
    words = re.findall(r"[a-zA-Z0-9]+", idea.lower())
    stop = {"a","an","and","about","for","make","new","the","to","video"}
    useful = [w for w in words if w not in stop]
    return slugify("_".join(useful[:5]) or idea)


def infer_video_type(idea: str) -> str:
    lo = idea.lower()
    if "logo" in lo: return "logo_reveal"
    if "app" in lo or "software" in lo or "screen" in lo: return "app_demo"
    if "explain" in lo or "how " in lo or "why " in lo: return "explainer"
    if "company" in lo or "service" in lo or "product" in lo: return "product_promo"
    return "animated_story"


def scene_count(duration: int) -> int:
    if duration <= 8: return 2
    if duration <= 15: return 3
    if duration <= 25: return 5
    return 6


def scene_purposes(count: int) -> list[str]:
    return {
        2: ["hook", "payoff"],
        3: ["hook", "development", "payoff"],
        5: ["hook", "setup", "turn", "resolution", "ending"],
        6: ["hook", "setup", "development", "turn", "resolution", "ending"],
    }[count]


def build_scene_plan(project: str, idea: str, video_type: str, duration: int,
                     aspect_ratio: str, voiceover: bool) -> dict:
    count = scene_count(duration)
    base = max(3, round(duration / count))
    style = "cinematic, polished, coherent visual continuity, no text, no logos, no watermark"
    type_visual = {
        "animated_story": lambda p: f"{idea}. Show the {p} moment clearly with expressive action and a readable composition.",
        "product_promo":  lambda p: f"A polished service promo scene for {idea}, focused on the {p} moment and the customer benefit.",
        "app_demo":       lambda p: f"A clean app demo style scene for {idea}, showing the {p} workflow moment on modern screens.",
        "logo_reveal":    lambda p: f"A polished logo reveal scene for {idea}, emphasizing the {p} moment with elegant motion.",
        "explainer":      lambda p: f"A clear explainer visual for {idea}, focused on the {p} point with simple cinematic composition.",
    }[video_type]
    scenes = []
    for i, purpose in enumerate(scene_purposes(count), 1):
        sid = f"scene_{i:03d}"
        scenes.append({
            "id": sid,
            "duration_seconds": base,
            "purpose": purpose,
            "story_beat": f"{purpose.title()} beat for: {idea}",
            "visual": type_visual(purpose),
            "camera_motion": "slow controlled push in",
            "style_notes": style,
            "voiceover": f"{purpose.title()}: {idea}." if voiceover else "",
            "on_screen_text": "",
            "generation_mode": "text_to_image_then_image_to_video",
            "status": "planned",
        })
    return {
        "project": project, "idea": idea, "video_type": video_type,
        "aspect_ratio": aspect_ratio, "target_duration_seconds": duration,
        "scenes": scenes,
    }


def image_size_for_aspect(aspect_ratio: str) -> dict | str:
    if aspect_ratio == "9:16":
        return {"width": 1024, "height": 1536}
    if aspect_ratio == "1:1":
        return {"width": 1024, "height": 1024}
    return "landscape_16_9"


def default_checklist() -> list[dict]:
    return [{"label": label, "done": False} for label in [
        "Scene plan created", "Scene plan approved",
        "Storyboard stills generated", "Stills approved",
        "Video clips generated", "Clips approved",
        "Voiceover generated", "Voiceover approved",
        "Review cut assembled", "Final cut approved",
    ]]


def create_project(*, idea: str, project: str | None, video_type: str | None,
                   duration: int, aspect_ratio: str, voiceover: bool) -> dict:
    name = slugify(project) if project else infer_project_name(idea)
    vtype = video_type or infer_video_type(idea)
    pp = project_paths(name)
    if pp.root.exists() and any(pp.root.iterdir()):
        raise FileExistsError(f"Projects/{name}/ already exists and is not empty.")
    pp.ensure_dirs()

    plan = build_scene_plan(name, idea, vtype, duration, aspect_ratio, voiceover)
    pp.scene_plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    title = name.replace('_', ' ').title()
    brief_lines = [
        f"# {title}", "",
        f"**Idea:** {idea}", f"**Type:** {vtype}",
        f"**Duration:** {duration} seconds", f"**Aspect ratio:** {aspect_ratio}",
        f"**Voiceover:** {'yes' if voiceover else 'no'}", "",
        "## Scenes",
    ]
    for s in plan["scenes"]:
        brief_lines.append(f"- {s['id']}: {s['purpose']} - {s['visual']}")
    pp.brief.write_text("\n".join(brief_lines) + "\n", encoding="utf-8")

    image_size = image_size_for_aspect(aspect_ratio)
    for s in plan["scenes"]:
        recipe = {
            "prompt": f"{s['visual']} {s['style_notes']}",
            "image_size": image_size,
            "num_images": 1,
        }
        pp.storyboard_recipe(s["id"]).write_text(
            json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
        clip_recipe = {
            "prompt": ("Preserve the input image and design. "
                       f"{s['camera_motion']}. Animate this beat: {s['story_beat']}. "
                       "Stable composition, coherent motion, no text, no logos, no watermark."),
            "duration": str(s["duration_seconds"]),
            "aspect_ratio": aspect_ratio,
            "generate_audio": False,
            "negative_prompt": "blur, distortion, warped subjects, unreadable text, logos, watermark, flicker, low quality",
        }
        pp.clip_recipe(s["id"]).write_text(
            json.dumps(clip_recipe, indent=2) + "\n", encoding="utf-8")

    if voiceover:
        text = " ".join(s["voiceover"] for s in plan["scenes"] if s["voiceover"])
        pp.voiceover_recipe.write_text(
            json.dumps({"text": text}, indent=2) + "\n", encoding="utf-8")

    now = datetime.now(timezone.utc).isoformat()
    pp.manifest.write_text(json.dumps({
        "project": name, "created_at": now, "video_type": vtype,
        "aspect_ratio": aspect_ratio, "target_duration_seconds": duration,
        "approval_status": "scene_plan_pending_approval",
        "idea": idea,
        "checklist": default_checklist(),
        "review_outputs": [],
        "generations": [],
    }, indent=2) + "\n", encoding="utf-8")

    pp.config.write_text(json.dumps({
        "project": name, "video_type": vtype, "aspect_ratio": aspect_ratio,
        "target_duration_seconds": duration, "voiceover": voiceover,
        "created_at": now, "current_stage": "scene_plan",
    }, indent=2) + "\n", encoding="utf-8")

    return {"project": name, "paths": pp}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Create a Projects/<name>/ video project.")
    parser.add_argument("--idea", required=True)
    parser.add_argument("--project")
    parser.add_argument("--type", choices=VIDEO_TYPES)
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--aspect", choices=["16:9", "9:16", "1:1"], default="16:9")
    parser.add_argument("--voiceover", choices=["yes", "no"], default="yes")
    args = parser.parse_args()

    out = create_project(
        idea=args.idea, project=args.project, video_type=args.type,
        duration=args.duration, aspect_ratio=args.aspect,
        voiceover=(args.voiceover == "yes"),
    )
    pp = out["paths"]
    print_stage_card(
        title="VIDEO PIPELINE: PROJECT CREATED",
        project=out["project"],
        status="Scene plan written. No paid FAL calls yet.",
        artifacts=[pp.brief, pp.scene_plan, pp.manifest, pp.config],
        next_steps=[
            "Review the scene plan in the studio UI.",
            "Approve to generate storyboard stills (first paid stage).",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

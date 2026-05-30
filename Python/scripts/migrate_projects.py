"""One-shot migration: Docs/MediaGeneration/* -> Projects/<name>/

For each manifest in Docs/MediaGeneration/manifests/, this script:
  - Creates Projects/<name>/ with subdirs (recipes/, outputs/, fal_results/)
  - Copies brief, scene plan, recipes, generated media, fal results, review cuts
  - Writes a new manifest.json with canonical Projects/<name>/... paths
  - Writes a project.json with the canonical config

The script is idempotent (uses copy2 + exist_ok) and never deletes anything
from the old location. Originals are deleted by hand after smoke test.

Missing source files are reported in the migration summary, not raised.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_ROOT = REPO_ROOT / "Docs" / "MediaGeneration"
NEW_ROOT = REPO_ROOT / "Projects"


def _resolve_old(path_str: str) -> Path:
    """Manifest paths are relative to repo root; tolerate forward/backslashes."""
    p = Path(path_str.replace("\\", "/"))
    return (REPO_ROOT / p).resolve()


def _copy_if_exists(src: Path, dst: Path, missing: list[str]) -> Path | None:
    if not src.exists():
        missing.append(str(src.relative_to(REPO_ROOT)) if src.is_absolute() else str(src))
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _new_rel(path: Path) -> str:
    """Path relative to repo root in forward-slash form for manifests."""
    return path.relative_to(REPO_ROOT).as_posix()


def _strip_project_prefix(name: str, project: str) -> str:
    if name.startswith(project + "_"):
        return name[len(project) + 1 :]
    return name


def _canonical_review_name(orig: Path, project: str) -> str:
    """smart_websites_for_small_companies_with_fal_voiceover.mp4 -> with_fal_voiceover.mp4"""
    return _strip_project_prefix(orig.name, project)


def migrate_project(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    project = manifest["project"]
    project_dir = NEW_ROOT / project
    missing: list[str] = []

    for sub in ("recipes/storyboards", "recipes/image_to_video", "outputs/stills",
                "outputs/clips", "outputs/audio", "outputs/review", "fal_results"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    new_manifest: dict[str, Any] = {
        "project": project,
        "created_at": manifest.get("created_at"),
        "video_type": manifest.get("video_type"),
        "aspect_ratio": manifest.get("aspect_ratio"),
        "target_duration_seconds": manifest.get("target_duration_seconds"),
        "platforms": manifest.get("platforms"),
        "approval_status": manifest.get("approval_status"),
        "voiceover_script": manifest.get("voiceover_script"),
        "checklist": manifest.get("checklist", []),
        "review_outputs": [],
        "generations": [],
    }

    if brief_str := manifest.get("brief"):
        _copy_if_exists(_resolve_old(brief_str), project_dir / "brief.md", missing)
    if plan_str := manifest.get("scene_plan"):
        _copy_if_exists(_resolve_old(plan_str), project_dir / "scene_plan.json", missing)

    for review in manifest.get("review_outputs", []):
        src = _resolve_old(review["path"])
        new_name = _canonical_review_name(src, project)
        new_path = project_dir / "outputs" / "review" / new_name
        copied = _copy_if_exists(src, new_path, missing)
        entry = dict(review)
        if copied:
            entry["path"] = _new_rel(copied)
        if audio_str := review.get("audio"):
            audio_src = _resolve_old(audio_str)
            audio_dst = project_dir / "outputs" / "audio" / f"voiceover{audio_src.suffix}"
            audio_copied = _copy_if_exists(audio_src, audio_dst, missing)
            if audio_copied:
                entry["audio"] = _new_rel(audio_copied)
        new_manifest["review_outputs"].append(entry)

    for gen in manifest.get("generations", []):
        mode = gen.get("mode")
        scene_id = gen.get("scene_id", "")
        new_gen = dict(gen)

        if recipe_str := gen.get("recipe"):
            recipe_src = _resolve_old(recipe_str)
            if mode == "text_to_image":
                recipe_dst = project_dir / "recipes" / "storyboards" / f"{scene_id}.json"
            elif mode == "image_to_video":
                recipe_dst = project_dir / "recipes" / "image_to_video" / f"{scene_id}.json"
            elif mode == "text_to_speech":
                recipe_dst = project_dir / "recipes" / "voiceover.json"
            else:
                recipe_dst = project_dir / "recipes" / recipe_src.name
            copied = _copy_if_exists(recipe_src, recipe_dst, missing)
            if copied:
                new_gen["recipe"] = _new_rel(copied)

        if output_json_str := gen.get("output_json"):
            json_src = _resolve_old(output_json_str)
            json_dst = project_dir / "fal_results" / json_src.name
            copied = _copy_if_exists(json_src, json_dst, missing)
            if copied:
                new_gen["output_json"] = _new_rel(copied)

        if source_image_str := gen.get("source_image"):
            new_gen["source_image"] = _rewrite_source_image(
                _resolve_old(source_image_str), project_dir, new_manifest, project, missing
            )

        new_media: list[str] = []
        for idx, media_str in enumerate(gen.get("media_files", [])):
            media_src = _resolve_old(media_str)
            media_dst = _canonical_media_path(media_src, mode, scene_id, idx, project_dir)
            copied = _copy_if_exists(media_src, media_dst, missing)
            if copied:
                new_media.append(_new_rel(copied))
        new_gen["media_files"] = new_media

        new_manifest["generations"].append(new_gen)

    project_dir.joinpath("manifest.json").write_text(
        json.dumps(new_manifest, indent=2), encoding="utf-8"
    )

    project_config = {
        "project": project,
        "video_type": manifest.get("video_type"),
        "aspect_ratio": manifest.get("aspect_ratio", "16:9"),
        "target_duration_seconds": manifest.get("target_duration_seconds", 20),
        "platforms": manifest.get("platforms", []),
        "created_at": manifest.get("created_at"),
        "current_stage": _infer_current_stage(new_manifest),
    }
    project_dir.joinpath("project.json").write_text(
        json.dumps(project_config, indent=2), encoding="utf-8"
    )

    return {"project": project, "missing": missing}


def _canonical_media_path(src: Path, mode: str, scene_id: str, idx: int, project_dir: Path) -> Path:
    ext = src.suffix
    if mode == "text_to_image":
        return project_dir / "outputs" / "stills" / f"{scene_id}{ext}"
    if mode == "image_to_video":
        return project_dir / "outputs" / "clips" / f"{scene_id}{ext}"
    if mode == "text_to_speech":
        suffix = "_matched" if "matched" in src.stem else ("" if idx == 0 else f"_{idx}")
        return project_dir / "outputs" / "audio" / f"voiceover{suffix}{ext}"
    return project_dir / "outputs" / src.name


def _rewrite_source_image(src: Path, project_dir: Path,
                          new_manifest: dict, project: str, missing: list[str]) -> str:
    """source_image typically references a still already copied to outputs/stills/.
    Look it up; if not found in the new manifest yet, copy under its old name."""
    for gen in new_manifest.get("generations", []):
        if gen.get("mode") != "text_to_image":
            continue
        for m in gen.get("media_files", []):
            if Path(m).name == src.name:
                return m
            new_path = (REPO_ROOT / m).resolve()
            if new_path.exists() and new_path.stat().st_size == _safe_size(src):
                return m
    dst = project_dir / "outputs" / "stills" / src.name
    copied = _copy_if_exists(src, dst, missing)
    return _new_rel(copied) if copied else src.name


def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return -1


def _infer_current_stage(manifest: dict[str, Any]) -> str:
    status = (manifest.get("approval_status") or "").lower()
    if "review_cut" in status or "voiceover" in status:
        return "complete"
    has_clips = any(g.get("mode") == "image_to_video" and g.get("media_files")
                    for g in manifest.get("generations", []))
    has_stills = any(g.get("mode") == "text_to_image" and g.get("media_files")
                     for g in manifest.get("generations", []))
    if has_clips:
        return "voiceover"
    if has_stills:
        return "clips"
    if manifest.get("generations"):
        return "storyboards"
    return "scene_plan"


def main() -> int:
    if not OLD_ROOT.exists():
        print(f"ERROR: {OLD_ROOT} does not exist", file=sys.stderr)
        return 1

    manifests = sorted((OLD_ROOT / "manifests").glob("*_manifest.json"))
    if not manifests:
        print(f"ERROR: no manifests found in {OLD_ROOT / 'manifests'}", file=sys.stderr)
        return 1

    NEW_ROOT.mkdir(parents=True, exist_ok=True)
    results = [migrate_project(m) for m in manifests]

    print(f"\nMigrated {len(results)} project(s) to {NEW_ROOT.relative_to(REPO_ROOT)}/\n")
    for r in results:
        print(f"  {r['project']}: {len(r['missing'])} missing file(s)")
        for m in r["missing"][:5]:
            print(f"      - {m}")
        if len(r["missing"]) > 5:
            print(f"      ... and {len(r['missing']) - 5} more")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

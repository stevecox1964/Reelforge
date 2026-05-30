"""Canonical filesystem layout for a Projects/<name>/ project."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECTS_ROOT = REPO_ROOT / "Projects"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug[:64] or "new_video"


@dataclass(frozen=True)
class ProjectPaths:
    name: str
    root: Path

    @property
    def brief(self) -> Path: return self.root / "brief.md"
    @property
    def scene_plan(self) -> Path: return self.root / "scene_plan.json"
    @property
    def manifest(self) -> Path: return self.root / "manifest.json"
    @property
    def config(self) -> Path: return self.root / "project.json"
    @property
    def storyboards_dir(self) -> Path: return self.root / "recipes" / "storyboards"
    @property
    def clips_recipes_dir(self) -> Path: return self.root / "recipes" / "image_to_video"
    @property
    def voiceover_recipe(self) -> Path: return self.root / "recipes" / "voiceover.json"
    @property
    def stills_dir(self) -> Path: return self.root / "outputs" / "stills"
    @property
    def clips_dir(self) -> Path: return self.root / "outputs" / "clips"
    @property
    def audio_dir(self) -> Path: return self.root / "outputs" / "audio"
    @property
    def review_dir(self) -> Path: return self.root / "outputs" / "review"
    @property
    def fal_results_dir(self) -> Path: return self.root / "fal_results"

    def storyboard_recipe(self, scene_id: str) -> Path:
        return self.storyboards_dir / f"{scene_id}.json"

    def clip_recipe(self, scene_id: str) -> Path:
        return self.clips_recipes_dir / f"{scene_id}.json"

    def still_for(self, scene_id: str, ext: str = ".png") -> Path:
        return self.stills_dir / f"{scene_id}{ext}"

    def clip_for(self, scene_id: str, ext: str = ".mp4") -> Path:
        return self.clips_dir / f"{scene_id}{ext}"

    def voiceover_audio(self, ext: str = ".mp3") -> Path:
        return self.audio_dir / f"voiceover{ext}"

    def review_cut(self) -> Path:
        return self.review_dir / "review_cut.mp4"

    def existing_still(self, scene_id: str) -> Path | None:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = self.still_for(scene_id, ext)
            if p.exists():
                return p
        return None

    def existing_clip(self, scene_id: str) -> Path | None:
        for ext in (".mp4", ".mov", ".webm"):
            p = self.clip_for(scene_id, ext)
            if p.exists():
                return p
        return None

    def ensure_dirs(self) -> None:
        for d in (self.storyboards_dir, self.clips_recipes_dir, self.stills_dir,
                  self.clips_dir, self.audio_dir, self.review_dir, self.fal_results_dir):
            d.mkdir(parents=True, exist_ok=True)


def project_paths(name: str) -> ProjectPaths:
    slug = slugify(name)
    return ProjectPaths(name=slug, root=PROJECTS_ROOT / slug)


def list_projects() -> list[str]:
    if not PROJECTS_ROOT.exists():
        return []
    return sorted(p.name for p in PROJECTS_ROOT.iterdir()
                  if p.is_dir() and (p / "project.json").exists())


def rel_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()

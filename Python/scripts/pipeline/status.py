"""Stage cards and manifest helpers (project-folder aware)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def print_stage_card(*, title: str, project: str, status: str,
                     artifacts: list[Path | str] | None = None,
                     next_steps: list[str] | None = None) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f"Project: {project}")
    print(f"Status: {status}")
    if artifacts:
        print("\nWhere to look:")
        for a in artifacts:
            print(f"  - {a}")
    if next_steps:
        print("\nWhat to do next:")
        for i, step in enumerate(next_steps, 1):
            print(f"  {i}. {step}")
    print("=" * 72)


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def upsert_generation(manifest: dict[str, Any], *, scene_id: str, mode: str,
                      model: str | None = None, recipe: str | None = None,
                      output_json: str | None = None, media_files: list[str] | None = None,
                      source_image: str | None = None, notes: str = "",
                      decision: str = "pending_review") -> dict[str, Any]:
    gens = manifest.setdefault("generations", [])
    record = next((g for g in gens if g.get("scene_id") == scene_id and g.get("mode") == mode), None)
    if record is None:
        record = {"scene_id": scene_id, "mode": mode}
        gens.append(record)
    if model is not None: record["model"] = model
    if recipe is not None: record["recipe"] = recipe
    if output_json is not None: record["output_json"] = output_json
    if media_files is not None: record["media_files"] = media_files
    if source_image is not None: record["source_image"] = source_image
    record["notes"] = notes
    record["decision"] = decision
    return record


def update_stage(manifest: dict[str, Any], *, approval_status: str,
                 completed_labels: list[str] | None = None) -> None:
    manifest["approval_status"] = approval_status
    if completed_labels:
        for item in manifest.get("checklist", []):
            if item.get("label") in completed_labels:
                item["done"] = True


def update_project_stage(config_path: Path, stage: str) -> None:
    if not config_path.exists():
        return
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["current_stage"] = stage
    config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

"""FAL Video Studio backend (Projects/<name>/ layout)."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECTS_ROOT = PROJECT_ROOT / "Projects"
WEB_ROOT = PROJECT_ROOT / "web" / "studio"
STUDIO_DIR = PROJECT_ROOT / ".studio"
DB_PATH = STUDIO_DIR / "studio.sqlite3"
PIPELINE_DIR = PROJECT_ROOT / "Python" / "scripts" / "pipeline"

sys.path.insert(0, str(PIPELINE_DIR))
from paths import project_paths, list_projects, slugify  # noqa: E402
from create_project import create_project as pipeline_create_project, VIDEO_TYPES  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

STUDIO_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FAL Video Studio")
app.mount("/studio", StaticFiles(directory=WEB_ROOT, html=True), name="studio")
app.mount("/projects", StaticFiles(directory=PROJECTS_ROOT), name="projects")


STAGES = ("storyboards", "clips", "voiceover", "review")

STAGE_SCRIPTS = {
    "storyboards": PIPELINE_DIR / "generate_storyboards.py",
    "clips":       PIPELINE_DIR / "generate_clips.py",
    "voiceover":   PIPELINE_DIR / "generate_voiceover.py",
    "review":      PIPELINE_DIR / "assemble_review.py",
}


class ProjectCreate(BaseModel):
    idea: str = Field(min_length=1)
    project: str | None = None
    video_type: str | None = None
    aspect_ratio: str = "16:9"
    target_duration_seconds: int = 20
    voiceover: bool = True


class ScenePlanRequest(BaseModel):
    scenes: list[dict[str, Any]]


class CloneRequest(BaseModel):
    new_name: str = Field(min_length=1)


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _proj_url(path: Path) -> str:
    return "/projects/" + path.relative_to(PROJECTS_ROOT).as_posix()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.executescript("""
            create table if not exists jobs (
              id text primary key,
              project text not null,
              stage text not null,
              command_json text not null,
              status text not null,
              created_at real not null,
              started_at real,
              finished_at real,
              returncode integer,
              output text not null default ''
            );
        """)


def _read_json(p: Path, default: Any) -> Any:
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _project_summary(name: str) -> dict[str, Any]:
    pp = project_paths(name)
    cfg = _read_json(pp.config, {})
    manifest = _read_json(pp.manifest, {})
    mtime = max((p.stat().st_mtime for p in (pp.manifest, pp.config) if p.exists()), default=0)
    return {
        "project": name,
        "video_type": cfg.get("video_type") or manifest.get("video_type"),
        "aspect_ratio": cfg.get("aspect_ratio") or manifest.get("aspect_ratio"),
        "target_duration_seconds": cfg.get("target_duration_seconds") or manifest.get("target_duration_seconds"),
        "current_stage": cfg.get("current_stage"),
        "approval_status": manifest.get("approval_status"),
        "created_at": cfg.get("created_at") or manifest.get("created_at"),
        "updated_at": mtime,
    }


def _files_in(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    out = []
    for p in sorted(directory.iterdir(), key=lambda x: x.name):
        if p.is_file():
            out.append({
                "name": p.name,
                "url": _proj_url(p),
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
    return out


def _project_detail(name: str) -> dict[str, Any]:
    pp = project_paths(name)
    if not pp.config.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        **_project_summary(name),
        "brief": pp.brief.read_text(encoding="utf-8") if pp.brief.exists() else "",
        "scene_plan": _read_json(pp.scene_plan, {}),
        "manifest": _read_json(pp.manifest, {}),
        "outputs": {
            "stills": _files_in(pp.stills_dir),
            "clips": _files_in(pp.clips_dir),
            "audio": _files_in(pp.audio_dir),
            "review": _files_in(pp.review_dir),
        },
    }


def _stage_command(project: str, stage: str) -> list[str]:
    if stage not in STAGE_SCRIPTS:
        raise HTTPException(status_code=400, detail=f"Unknown stage. Use one of: {', '.join(STAGES)}")
    return [sys.executable, str(STAGE_SCRIPTS[stage]), project]


def _enqueue(project: str, stage: str, command: list[str]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    with _db() as conn:
        conn.execute(
            "insert into jobs (id, project, stage, command_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
            (job_id, project, stage, json.dumps(command), "queued", time.time()),
        )
    return {"job_id": job_id, "status": "queued", "stage": stage, "project": project}


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["command"] = json.loads(d.pop("command_json"))
    return d


def claim_next_job() -> dict[str, Any] | None:
    with _db() as conn:
        conn.isolation_level = None
        conn.execute("begin immediate")
        row = conn.execute(
            "select * from jobs where status='queued' order by created_at asc limit 1"
        ).fetchone()
        if row is None:
            conn.execute("commit")
            return None
        conn.execute("update jobs set status='running', started_at=? where id=?",
                     (time.time(), row["id"]))
        conn.execute("commit")
    return _row_to_job(row)


def _append_output(job_id: str, text: str) -> None:
    with _db() as conn:
        row = conn.execute("select output from jobs where id=?", (job_id,)).fetchone()
        existing = row["output"] if row else ""
        conn.execute("update jobs set output=? where id=?", ((existing + text)[-30000:], job_id))


def _finish(job_id: str, status: str, returncode: int) -> None:
    with _db() as conn:
        conn.execute(
            "update jobs set status=?, finished_at=?, returncode=? where id=?",
            (status, time.time(), returncode, job_id),
        )


def run_claimed_job(job: dict[str, Any]) -> None:
    job_id = job["id"]
    try:
        process = subprocess.Popen(
            job["command"], cwd=PROJECT_ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for line in process.stdout:
            _append_output(job_id, line)
        rc = process.wait()
        _finish(job_id, "completed" if rc == 0 else "failed", rc)
    except Exception as exc:
        _append_output(job_id, f"\n{type(exc).__name__}: {exc}\n")
        _finish(job_id, "failed", -1)


def job_worker_loop() -> None:
    while True:
        job = claim_next_job()
        if job is None:
            time.sleep(2)
            continue
        run_claimed_job(job)


def mark_interrupted_jobs() -> None:
    msg = "\nServer restarted while this job was running. Review outputs, then requeue if needed.\n"
    with _db() as conn:
        rows = conn.execute("select id, output from jobs where status='running'").fetchall()
        for row in rows:
            conn.execute(
                "update jobs set status='interrupted', finished_at=?, returncode=?, output=? where id=?",
                (time.time(), -1, ((row["output"] or "") + msg)[-30000:], row["id"]),
            )


init_db()


# ---- Routes ----------------------------------------------------------------

@app.get("/")
def root() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "database": str(DB_PATH),
        "fal_key_set": bool(os.environ.get("FAL_KEY")),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "video_types": list(VIDEO_TYPES),
        "stages": list(STAGES),
    }


@app.get("/api/projects")
def projects() -> list[dict[str, Any]]:
    summaries = [_project_summary(n) for n in list_projects()]
    summaries.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
    return summaries


@app.post("/api/projects")
def create_project(data: ProjectCreate) -> dict[str, Any]:
    try:
        result = pipeline_create_project(
            idea=data.idea, project=data.project, video_type=data.video_type,
            duration=data.target_duration_seconds, aspect_ratio=data.aspect_ratio,
            voiceover=data.voiceover,
        )
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _project_detail(result["project"])


@app.get("/api/projects/{project}")
def project_detail(project: str) -> dict[str, Any]:
    return _project_detail(slugify(project))


@app.post("/api/projects/{project}/clone")
def clone_project(project: str, data: CloneRequest) -> dict[str, Any]:
    import json as _json
    import shutil as _shutil
    from datetime import datetime, timezone
    src = project_paths(project)
    if not src.config.exists():
        raise HTTPException(status_code=404, detail="Source project not found")
    dst = project_paths(data.new_name)
    if dst.root.exists() and any(dst.root.iterdir()):
        raise HTTPException(status_code=409, detail=f"Project '{dst.name}' already exists")
    dst.ensure_dirs()
    # Copy brief, scene plan, recipes (everything except outputs/fal_results/manifest).
    if src.brief.exists():      _shutil.copy2(src.brief, dst.brief)
    if src.scene_plan.exists(): _shutil.copy2(src.scene_plan, dst.scene_plan)
    for sub in ("storyboards", "image_to_video"):
        for r in (src.root / "recipes" / sub).glob("*.json"):
            _shutil.copy2(r, dst.root / "recipes" / sub / r.name)
    if src.voiceover_recipe.exists():
        _shutil.copy2(src.voiceover_recipe, dst.voiceover_recipe)
    # Fresh project.json + manifest.json with the new name and current stage reset.
    src_cfg = _read_json(src.config, {})
    src_cfg.update({"project": dst.name, "current_stage": "scene_plan",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "cloned_from": src.name})
    _write_json(dst.config, src_cfg)
    src_manifest = _read_json(src.manifest, {})
    new_manifest = {
        "project": dst.name,
        "created_at": src_cfg["created_at"],
        "video_type": src_manifest.get("video_type"),
        "aspect_ratio": src_manifest.get("aspect_ratio"),
        "target_duration_seconds": src_manifest.get("target_duration_seconds"),
        "approval_status": "scene_plan_pending_approval",
        "idea": src_manifest.get("idea"),
        "checklist": [{"label": item.get("label"), "done": False}
                      for item in src_manifest.get("checklist", [])],
        "review_outputs": [],
        "generations": [],
        "cloned_from": src.name,
    }
    _write_json(dst.manifest, new_manifest)
    # Rewrite the scene plan's "project" field so downstream tooling references the clone.
    if dst.scene_plan.exists():
        plan = _read_json(dst.scene_plan, {})
        plan["project"] = dst.name
        _write_json(dst.scene_plan, plan)
    return _project_detail(dst.name)


@app.put("/api/projects/{project}/scene-plan")
def save_scene_plan(project: str, data: ScenePlanRequest) -> dict[str, Any]:
    pp = project_paths(project)
    if not pp.scene_plan.exists():
        raise HTTPException(status_code=404, detail="Scene plan not found")
    plan = _read_json(pp.scene_plan, {})
    plan["scenes"] = data.scenes
    _write_json(pp.scene_plan, plan)
    return {"ok": True, "scene_plan": _rel(pp.scene_plan)}


@app.post("/api/projects/{project}/stages/{stage}/run")
def run_stage(project: str, stage: str) -> dict[str, Any]:
    pp = project_paths(project)
    if not pp.config.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return _enqueue(pp.name, stage, _stage_command(pp.name, stage))


@app.post("/api/projects/{project}/stages/{stage}/approve")
def approve_stage(project: str, stage: str) -> dict[str, Any]:
    pp = project_paths(project)
    if not pp.manifest.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    manifest = _read_json(pp.manifest, {})
    if stage == "scene_plan":
        next_status = "scene_plan_approved"
        label = "Scene plan approved"
    elif stage == "storyboards":
        next_status = "stills_approved"; label = "Stills approved"
    elif stage == "clips":
        next_status = "clips_approved"; label = "Clips approved"
    elif stage == "voiceover":
        next_status = "voiceover_approved"; label = "Voiceover approved"
    elif stage == "review":
        next_status = "final_approved"; label = "Final cut approved"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown stage to approve: {stage}")
    manifest["approval_status"] = next_status
    for item in manifest.get("checklist", []):
        if item.get("label") == label:
            item["done"] = True
    _write_json(pp.manifest, manifest)
    return {"ok": True, "approval_status": next_status}


@app.get("/api/projects/{project}/jobs")
def project_jobs(project: str) -> list[dict[str, Any]]:
    pp = project_paths(project)
    with _db() as conn:
        rows = conn.execute(
            "select * from jobs where project=? order by created_at desc limit 50",
            (pp.name,),
        ).fetchall()
    return [_row_to_job(r) for r in rows]


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    with _db() as conn:
        rows = conn.execute("select * from jobs order by created_at desc limit 100").fetchall()
    return [_row_to_job(r) for r in rows]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("select * from jobs where id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_job(row)

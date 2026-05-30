"""Assemble the review cut: concat clips, mix voiceover (atempo-matched)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import project_paths, rel_to_repo
from status import load_manifest, save_manifest, update_stage, print_stage_card, update_project_stage


def _ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _write_concat_list(items: list[Path], dst: Path) -> None:
    # BOM-free utf-8; ffmpeg concat demuxer chokes on BOM.
    lines = "\n".join(f"file '{p.as_posix()}'" for p in items) + "\n"
    dst.write_bytes(lines.encode("utf-8"))


def assemble(project: str) -> dict:
    pp = project_paths(project)
    plan = json.loads(pp.scene_plan.read_text(encoding="utf-8"))
    clips = []
    for scene in plan.get("scenes", []):
        clip = pp.existing_clip(scene["id"])
        if clip is None:
            raise FileNotFoundError(f"Clip missing for {scene['id']} in {pp.clips_dir}")
        clips.append(clip)
    if not clips:
        raise RuntimeError("No clips found.")

    pp.ensure_dirs()
    concat_list = pp.review_dir / "concat_list.txt"
    _write_concat_list(clips, concat_list)

    bare_cut = pp.review_dir / "concat_no_audio.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(bare_cut),
    ], check=True)

    final = pp.review_cut()
    audio_path = pp.voiceover_audio(".mp3")
    if not audio_path.exists():
        # No voiceover available - just re-encode the concat as the review cut.
        subprocess.run([
            "ffmpeg", "-y", "-i", str(bare_cut),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(final),
        ], check=True)
        notes = "Review cut without voiceover."
        speed = None
    else:
        video_dur = _ffprobe_duration(bare_cut)
        audio_dur = _ffprobe_duration(audio_path)
        speed = audio_dur / video_dur if video_dur > 0 else 1.0
        # atempo is limited to 0.5-2.0 per filter; chain if needed.
        filters = []
        s = speed
        while s > 2.0:
            filters.append("atempo=2.0"); s /= 2.0
        while s < 0.5:
            filters.append("atempo=0.5"); s /= 0.5
        filters.append(f"atempo={s:.4f}")
        chain = ",".join(filters)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(bare_cut), "-i", str(audio_path),
            "-filter_complex", f"[1:a]{chain}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(final),
        ], check=True)
        notes = f"Review cut with voiceover at speed {speed:.4f}x."

    final_dur = _ffprobe_duration(final)

    manifest = load_manifest(pp.manifest)
    manifest["review_outputs"] = [{
        "type": "review_cut",
        "path": rel_to_repo(final),
        "duration_seconds": final_dur,
        "audio": rel_to_repo(audio_path) if audio_path.exists() else None,
        "voiceover_speed": speed,
        "notes": notes,
    }]
    update_stage(manifest,
                 approval_status="review_cut_complete",
                 completed_labels=["Review cut assembled"])
    save_manifest(pp.manifest, manifest)
    update_project_stage(pp.config, "complete")

    return {"project": project, "review_cut": rel_to_repo(final),
            "duration_seconds": final_dur, "voiceover_speed": speed}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Assemble the review cut.")
    parser.add_argument("project")
    args = parser.parse_args()
    out = assemble(args.project)
    pp = project_paths(args.project)
    print_stage_card(
        title="VIDEO PIPELINE: REVIEW CUT ASSEMBLED",
        project=args.project,
        status=f"Final {out['duration_seconds']:.2f}s cut written.",
        artifacts=[pp.review_cut()],
        next_steps=["Watch the review cut in the studio UI.",
                    "Approve as final or revise upstream and re-run."],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

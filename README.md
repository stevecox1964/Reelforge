# Reelforge

A FAL-powered orchestration engine for short (20–30s) videos, with a local web studio. Each project lives in its own folder under `Projects/<name>/` and walks through the same 5-step pipeline:

```
idea → scene plan → storyboards → clips → review cut
```

Paid stages are gated behind explicit approval in the UI.

## Quick start

```powershell
.\run.bat
```

Opens the studio on http://127.0.0.1:8765/ and runs the durable worker in the background. Press Ctrl+C to stop both.

Set your `FAL_KEY` in `.env` first:

```
FAL_KEY=your_key
OPENAI_API_KEY=your_key   # only needed for openai/gpt-image-2 (text-in-image)
```

## Project layout

```
Projects/<name>/
  project.json           # type, duration, aspect_ratio, current_stage
  brief.md
  scene_plan.json
  recipes/
    storyboards/scene_001.json ...
    image_to_video/scene_001.json ...
    voiceover.json
  outputs/
    stills/, clips/, audio/, review/
  fal_results/           # raw FAL responses
  manifest.json          # artifact index + cost estimate
```

## Repo layout

```
Projects/                # one folder per video project
Python/scripts/
  pipeline/              # stage scripts (create_project, generate_*, assemble_review, cost_report)
  studio/                # FastAPI server + durable worker
  migrate_projects.py    # one-shot Docs/MediaGeneration → Projects migration
web/studio/              # vanilla JS frontend
.studio/                 # SQLite job queue (gitignored)
run.bat
```

## Workflow

1. Click **New Project** in the studio, describe the video idea, pick duration + aspect ratio.
2. **Review the scene plan**, edit any scene (edits auto-save on blur, so regeneration always uses your latest text), click **Approve Plan**.
3. **Generate Storyboards** — paid stills (Flux Schnell by default; use gpt-image-2 if text must appear in-frame).
4. **Approve Storyboards** to unlock clip animation.
5. **Generate Clips** — paid image-to-video (Kling V3 by default).
6. **Approve Clips**, then generate voiceover (FAL TTS).
7. **Assemble Review Cut** — local ffmpeg concat with atempo-matched voiceover.

The current stage and approval status live in `project.json` and `manifest.json`. Job queue state survives server/worker/browser restarts (SQLite at `.studio/studio.sqlite3`).

## CLI fallback

Every stage works headless too:

```powershell
python Python/scripts/pipeline/create_project.py --idea "tiny otter making toast" --aspect 9:16
python Python/scripts/pipeline/generate_storyboards.py tiny_otter_making_toast
python Python/scripts/pipeline/generate_clips.py tiny_otter_making_toast
python Python/scripts/pipeline/generate_voiceover.py tiny_otter_making_toast
python Python/scripts/pipeline/assemble_review.py tiny_otter_making_toast
python Python/scripts/pipeline/cost_report.py tiny_otter_making_toast
```

## Setup

```powershell
uv sync
```

Pre-requisites: Python 3.11+, ffmpeg on PATH, a FAL key.

## Migration from the old layout

The old `Docs/MediaGeneration/{briefs,manifests,recipes,outputs,storyboards}/` tree has been migrated into `Projects/<name>/`. To re-run the migration on a fresh checkout that still has the old tree:

```powershell
python Python/scripts/migrate_projects.py
```

The migration is idempotent; missing source files (e.g., deleted older outputs) are reported but don't fail the run.

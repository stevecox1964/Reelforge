# Current Plan — Studio v2 Feature Work

Captures the four feature requests from the post-refactor UX review (2026-05-28). Tackled in order; each one ships in its own commit on a single feature branch.

---

## 1. Sidebar reorder — New Project above project list

**Why:** New users couldn't find the "+ New Project" button at the bottom of the sidebar.

**Scope:**
- `web/studio/index.html`: move the `<button id="btn-new-project">` block above `<div class="project-list">`.
- `web/studio/styles.css`: rename / drop `.sidebar-footer`; restyle the new-project button as the primary sidebar CTA.

**Effort:** ~10 min. Should ship first as a quick win.

---

## 2. Per-stage model config — global registry + per-project overrides

**Why:** Today every stage script has a hardcoded `DEFAULT_MODEL`. Users want to pick models per stage, including swapping in alternatives like `openai/gpt-image-2` for stills with in-frame text.

**Decisions:**
- **Storage:** Global registry + per-project overrides (chosen 2026-05-28).
- Global registry lives at `.studio/models.json`, seeded by the server on first start.
- Per-project override lives in `Projects/<name>/project.json` under a new `models` block. Omitted keys fall back to global default.

**Files to add/change:**
- New: `Python/scripts/pipeline/models.py` — `resolve_model(stage, project_name) → ModelSpec`. Stage scripts call this instead of hardcoded `DEFAULT_MODEL`.
- Update: `generate_storyboards.py`, `generate_clips.py`, `generate_voiceover.py`, `cost_report.py` — drop hardcoded `DEFAULT_MODEL`, call `resolve_model()`.
- Update: `server.py` — new endpoints `GET/PUT /api/models`, `PUT /api/projects/{name}/models`.
- Update: `web/studio/app.js` + `index.html` — new "Models" view (top-nav button) and a small "Model:" dropdown on each stage card.

**Registry shape (`.studio/models.json`):**
```json
{
  "stages": {
    "storyboards": {
      "default": "flux-schnell",
      "models": {
        "flux-schnell": { "provider": "fal", "endpoint": "fal-ai/flux/schnell",
                          "notes": "Fast & cheap" },
        "gpt-image-2":  { "provider": "fal", "endpoint": "openai/gpt-image-2",
                          "notes": "BYOK OpenAI; renders in-image text cleanly" },
        "flux-dev":     { "provider": "replicate", "endpoint": "black-forest-labs/flux-dev",
                          "notes": "Higher quality, slower" }
      }
    },
    "clips":     { "default": "kling-v3",      "models": { "kling-v3":     {...},
                                                            "kling-v1.6":  {...} } },
    "voiceover": { "default": "xai-tts-v1",    "models": { "xai-tts-v1":   {...} } }
  }
}
```

**Per-project override (in `project.json`):**
```json
"models": { "storyboards": "gpt-image-2" }
```

---

## 3. Provider adapter layer — FAL + Replicate

**Why:** `fal_runner.py` calls `fal_client.subscribe()` directly. Adding other providers (Replicate first, others later) requires an adapter shape.

**Decisions:**
- **Scope this round:** Adapter layer + FAL today, Replicate next (chosen 2026-05-28).
- Recipe format and Replicate auth handling — still open, see "Open questions" below.

**Files to add:**
```
Python/scripts/pipeline/providers/
  __init__.py        # get_provider(name) → Provider
  base.py            # abstract Provider with run() → RunResult
  fal.py             # existing fal_client logic, lifted out of fal_runner.py
  replicate.py       # NEW: replicate.run() adapter
```

**Files to change:**
- `fal_runner.py` → renamed to `runner.py`. Looks up provider from the resolved model spec and delegates to the adapter.
- `pyproject.toml` — add `replicate` package dependency.
- `.env` — document new optional `REPLICATE_API_TOKEN`.

**Validation:** Smoke test by setting a project's `models.storyboards = "flux-dev"` (Replicate) and running the storyboards stage. If a PNG lands in `outputs/stills/`, the adapter shape is right.

---

## 4. Usage view — cross-project, local-only

**Why:** No way today to see total spend across projects.

**Decisions:**
- **First cut:** Cross-project estimates only, from local manifests (chosen 2026-05-28). No live provider billing API calls.
- Refresh behaviour — still open, see "Open questions" below.

**Files to add/change:**
- New endpoint `GET /api/usage` in `server.py`:
  - Walk every `Projects/*/manifest.json`
  - Sum `cost_estimate` by project / stage / model / provider
  - Optionally re-run `cost_report.report()` for projects with stale/missing estimates
- New UI page in `web/studio/`: top-nav "Usage" button alongside "Models". Three tables (by project, by stage, by provider) and one top-line total.

---

## Open questions (still need decisions)

1. **Replicate auth UX** — when `REPLICATE_API_TOKEN` isn't set, do we (a) hide Replicate models from the UI until the token is present, or (b) show them and fail at run time with a clear error?
2. **Recipe format** — keep recipes in a normalized "intent" shape and let each provider adapter translate to its wire format, OR write provider-native recipes that get regenerated whenever the project's model changes? Trade-off: portability vs. full provider expressiveness.
3. **Usage page refresh** — recompute cost on demand (fast load, manual "Refresh" button), OR auto-recompute on every page load (always live, slower for many projects)?

---

## Execution order

1. Sidebar reorder (quick win).
2. `pipeline/models.py` + `.studio/models.json` seeding + stage scripts use `resolve_model()`.
3. Adapter layer refactor: `fal_runner.py` → `providers/fal.py` + `runner.py`. **No behavior change in this commit.**
4. Add `providers/replicate.py` + `replicate` dep. Smoke test with one model.
5. Model registry endpoints + per-project override endpoint.
6. UI: "Models" view + per-card dropdown.
7. Usage endpoint + "Usage" UI page.
8. README update.

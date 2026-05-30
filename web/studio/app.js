// ── api ──────────────────────────────────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = body;
    try { msg = JSON.parse(body).detail || body; } catch (_) {}
    throw new Error(msg || res.statusText);
  }
  return res.json();
}

const get  = (path)       => api(path);
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
const put  = (path, body) => api(path, { method: "PUT",  body: JSON.stringify(body) });

// ── state ────────────────────────────────────────────────────────────────────

const S = {
  project:    null,
  manifest:   null,
  scenePlan:  [],
  step:       1,
  jobs:       {},      // stage -> jobId
};

const sceneId = (sc, i) => sc.id || sc.scene_id || `scene_${String(i + 1).padStart(3, "0")}`;

// ── step machine ─────────────────────────────────────────────────────────────

function setDot(step, mode) {
  const dot = document.getElementById(`dot-${step}`);
  if (!dot) return;
  dot.classList.remove("is-active", "is-done");
  if (mode === "active") dot.classList.add("is-active");
  if (mode === "done")   dot.classList.add("is-done");
}

function setConnector(step, done) {
  const c = document.getElementById(`conn-${step}`);
  if (c) c.classList.toggle("is-done", done);
}

function setCardState(n, state) {
  const card = document.getElementById(`card-${n}`);
  if (card) card.dataset.state = state;
  if (state === "active") setDot(n, "active");
  if (state === "completed") { setDot(n, "done"); setConnector(n, true); }
  if (state === "locked")  setDot(n, "");
}

function setSummary(n, text) {
  const el = document.getElementById(`card-${n}-summary`);
  if (el) el.textContent = text;
}

function advanceTo(n) {
  if (n > 1) setCardState(n - 1, "completed");
  setCardState(n, "active");
  S.step = n;
  setTimeout(() => {
    document.getElementById(`card-${n}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 80);
}

// ── start over ───────────────────────────────────────────────────────────────

function resetAll() {
  Object.assign(S, { project: null, manifest: null, scenePlan: [], step: 1, jobs: {} });

  for (let i = 1; i <= 5; i++) setCardState(i, i === 1 ? "active" : "locked");
  for (let i = 1; i <= 4; i++) setConnector(i, false);

  setConceptMode("create");
  document.getElementById("thought-input").value = "";
  document.querySelectorAll(".type-tile.selected").forEach(t => t.classList.remove("selected"));
  resetGroup("duration-group", "30");
  resetGroup("aspect-group",   "16:9");
  document.getElementById("concept-msg").textContent = "";

  document.getElementById("scenes-list").innerHTML = "";
  document.getElementById("plan-msg").textContent = "";

  clearEl("storyboard-gate");
  clearEl("storyboard-media");
  clearEl("clips-gate");
  clearEl("clips-media");
  clearEl("complete-content");
  hide("storyboard-progress");
  hide("clips-progress");

  resetStoryboardActions();
  resetClipsActions();

  for (let i = 1; i <= 5; i++) setSummary(i, "");
  document.getElementById("card-1").scrollIntoView({ behavior: "smooth", block: "start" });
  refreshProjectList();
}

function resetGroup(groupId, defaultValue) {
  document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(b => {
    b.classList.toggle("selected", b.dataset.value === defaultValue);
  });
}

function clearEl(id)  { const e = document.getElementById(id); if (e) e.innerHTML = ""; }
function hide(id)     { const e = document.getElementById(id); if (e) e.style.display = "none"; }
function show(id)     { const e = document.getElementById(id); if (e) e.style.display = ""; }
function esc(v)       { return String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function resetStoryboardActions() {
  const el = document.getElementById("storyboard-actions");
  el.style.display = "";
  el.innerHTML = `
    <button class="btn-primary" id="btn-gen-storyboards">Generate Storyboards →</button>
    <span class="cost-note">Text-to-image · paid FAL call</span>
  `;
  document.getElementById("btn-gen-storyboards").addEventListener("click", generateStoryboards);
}

function resetClipsActions() {
  const el = document.getElementById("clips-actions");
  el.style.display = "";
  el.innerHTML = `
    <button class="btn-primary btn-paid" id="btn-gen-clips">Generate Clips →</button>
    <span class="cost-note">Image-to-video · most expensive stage</span>
  `;
  document.getElementById("btn-gen-clips").addEventListener("click", generateClips);
}

// ── card 1: concept ──────────────────────────────────────────────────────────

function setConceptMode(mode) {
  // mode: "create" or "view"
  document.getElementById("concept-create").style.display = mode === "create" ? "" : "none";
  document.getElementById("concept-view").style.display   = mode === "view"   ? "" : "none";
}

function renderConceptView(detail) {
  const set = (id, val, fallback = "—") => {
    const el = document.getElementById(id);
    el.textContent = val || fallback;
    el.classList.toggle("empty", !val);
  };
  const idea = detail.manifest?.idea || detail.brief?.split("\n").find(l => l.startsWith("**Idea:**"))?.replace("**Idea:**", "").trim() || "—";
  set("cv-idea", idea);
  set("cv-type", (detail.video_type || "").replace(/_/g, " "));
  set("cv-duration", detail.target_duration_seconds ? `${detail.target_duration_seconds}s` : "");
  set("cv-aspect", detail.aspect_ratio);
  set("cv-created", (detail.created_at || "").slice(0, 10));
  setConceptMode("view");
}

function initConceptCard() {
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.getElementById("thought-input").value = chip.dataset.thought;
      if (chip.dataset.type) selectType(chip.dataset.type);
    });
  });

  document.getElementById("btn-clone-project").addEventListener("click", cloneCurrentProject);

  document.querySelectorAll(".type-tile").forEach(tile => {
    tile.addEventListener("click", () => selectType(tile.dataset.type));
  });

  for (const groupId of ["duration-group", "aspect-group"]) {
    document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(`#${groupId} .btn-toggle`).forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
      });
    });
  }

  document.getElementById("btn-create-project").addEventListener("click", submitConcept);
}

function selectType(type) {
  document.querySelectorAll(".type-tile").forEach(t => t.classList.remove("selected"));
  document.querySelector(`.type-tile[data-type="${type}"]`)?.classList.add("selected");
}

async function cloneCurrentProject() {
  if (!S.project) return;
  const suggested = S.project + "_clone";
  const newName = window.prompt(`Clone "${S.project}" as:`, suggested);
  if (!newName || !newName.trim()) return;
  const btn = document.getElementById("btn-clone-project");
  btn.textContent = "Cloning…"; btn.disabled = true;
  try {
    const detail = await post(`/api/projects/${S.project}/clone`, { new_name: newName.trim() });
    refreshProjectList();
    loadExistingProject(detail.project);
  } catch (err) {
    alert(`Clone failed: ${err.message}`);
  } finally {
    btn.textContent = "Clone Project →"; btn.disabled = false;
  }
}

async function submitConcept() {
  const idea = document.getElementById("thought-input").value.trim();
  if (!idea) {
    document.getElementById("concept-msg").textContent = "Please describe your video idea.";
    return;
  }

  const videoType   = document.querySelector(".type-tile.selected")?.dataset.type || null;
  const duration    = parseInt(document.querySelector("#duration-group .btn-toggle.selected")?.dataset.value || "20");
  const aspectRatio = document.querySelector("#aspect-group .btn-toggle.selected")?.dataset.value || "16:9";

  const btn = document.getElementById("btn-create-project");
  btn.textContent = "Creating…";
  btn.disabled = true;
  document.getElementById("concept-msg").textContent = "";

  try {
    const detail = await post("/api/projects", {
      idea, video_type: videoType, aspect_ratio: aspectRatio,
      target_duration_seconds: duration, voiceover: true,
    });

    S.project   = detail.project;
    S.manifest  = detail.manifest || {};
    S.scenePlan = detail.scene_plan?.scenes || [];

    setSummary(1, `${idea.slice(0, 52)}${idea.length > 52 ? "…" : ""} · ${duration}s · ${aspectRatio}`);
    advanceTo(2);
    renderScenePlan(S.scenePlan);
    refreshProjectList();
  } catch (err) {
    document.getElementById("concept-msg").textContent = `Error: ${err.message}`;
  } finally {
    btn.textContent = "Create Project →";
    btn.disabled = false;
  }
}

// ── card 2: scene plan ───────────────────────────────────────────────────────

const PURPOSE_CLASS = {
  hook: "purpose-hook", setup: "purpose-setup", turn: "purpose-turn",
  resolution: "purpose-resolution", ending: "purpose-ending",
  development: "purpose-setup", payoff: "purpose-ending",
};

function renderScenePlan(scenes) {
  const list = document.getElementById("scenes-list");
  list.innerHTML = "";
  jsonEditorOpen = false;
  document.getElementById("btn-edit-json").textContent = "Edit as JSON";

  scenes.forEach((sc, i) => {
    const cls = PURPOSE_CLASS[sc.purpose] || "purpose-default";
    const card = document.createElement("div");
    card.className = "scene-card";
    card.dataset.sceneId = sceneId(sc, i);
    card.dataset.purpose = sc.purpose || "scene";
    card.dataset.styleNotes = sc.style_notes || "";
    card.innerHTML = `
      <div class="scene-left">
        <div class="scene-num">${i + 1}</div>
        <div class="scene-purpose ${cls}">${esc(sc.purpose || "scene")}</div>
      </div>
      <div class="scene-right">
        <div class="scene-field">
          <label class="scene-lbl">Visual</label>
          <textarea class="scene-visual scene-input" rows="2">${esc(sc.visual || "")}</textarea>
        </div>
        <div class="scene-row">
          <div class="scene-field">
            <label class="scene-lbl">Camera motion</label>
            <input class="scene-camera scene-input" type="text" value="${esc(sc.camera_motion || "")}">
          </div>
          <div class="scene-field field-duration">
            <label class="scene-lbl">Duration</label>
            <div class="dur-wrap">
              <input class="scene-dur scene-input" type="number" value="${sc.duration_seconds || 4}" min="2" max="10">
              <span class="dur-unit">s</span>
            </div>
          </div>
        </div>
        <div class="scene-field">
          <label class="scene-lbl">Voiceover</label>
          <textarea class="scene-voiceover scene-input" rows="2">${esc(sc.voiceover || "")}</textarea>
        </div>
      </div>
    `;
    list.appendChild(card);
  });
}

function collectScenes() {
  return Array.from(document.querySelectorAll(".scene-card")).map(card => ({
    id:               card.dataset.sceneId,
    purpose:          card.dataset.purpose,
    visual:           card.querySelector(".scene-visual").value,
    camera_motion:    card.querySelector(".scene-camera").value,
    voiceover:        card.querySelector(".scene-voiceover").value,
    duration_seconds: parseInt(card.querySelector(".scene-dur").value) || 4,
    style_notes:      card.dataset.styleNotes || "",
  }));
}

let jsonEditorOpen = false;

function initScenePlanCard() {
  document.getElementById("btn-approve-plan").addEventListener("click", approvePlan);
  document.getElementById("btn-edit-json").addEventListener("click", toggleJson);
}

function toggleJson() {
  const list = document.getElementById("scenes-list");
  const btn  = document.getElementById("btn-edit-json");

  if (!jsonEditorOpen) {
    const scenes = collectScenes();
    const ta = document.createElement("textarea");
    ta.id = "json-editor";
    ta.className = "json-editor";
    ta.value = JSON.stringify(scenes, null, 2);
    ta.rows = 22;
    list.innerHTML = "";
    list.appendChild(ta);
    btn.textContent = "Back to Visual Editor";
    jsonEditorOpen = true;
  } else {
    try {
      const raw = document.getElementById("json-editor").value;
      const parsed = JSON.parse(raw);
      const scenes = Array.isArray(parsed) ? parsed : (parsed.scenes || []);
      S.scenePlan = scenes;
      renderScenePlan(scenes);
      btn.textContent = "Edit as JSON";
      jsonEditorOpen = false;
    } catch (e) {
      alert("Invalid JSON — fix it before switching back.");
    }
  }
}

async function approvePlan() {
  const scenes = jsonEditorOpen
    ? (() => {
        const raw = document.getElementById("json-editor")?.value || "[]";
        const p = JSON.parse(raw);
        return Array.isArray(p) ? p : (p.scenes || []);
      })()
    : collectScenes();

  const btn = document.getElementById("btn-approve-plan");
  btn.textContent = "Saving…";
  btn.disabled = true;
  document.getElementById("plan-msg").textContent = "";

  try {
    await put(`/api/projects/${S.project}/scene-plan`, { scenes });
    await post(`/api/projects/${S.project}/stages/scene_plan/approve`, {});
    S.scenePlan = scenes;

    const totalSec = scenes.reduce((s, sc) => s + (sc.duration_seconds || 4), 0);
    setSummary(2, `${scenes.length} scenes · ${totalSec}s total`);

    advanceTo(3);
    renderStoryboardGate();
  } catch (err) {
    document.getElementById("plan-msg").textContent = `Error: ${err.message}`;
  } finally {
    btn.textContent = "Approve Plan →";
    btn.disabled = false;
  }
}

// ── card 3: storyboards ──────────────────────────────────────────────────────

function renderStoryboardGate() {
  const aspect = S.manifest?.aspect_ratio || "16:9";
  const count  = S.scenePlan.length;
  document.getElementById("storyboard-gate").innerHTML = `
    <div class="gate-item"><div class="gate-lbl">Model</div><div class="gate-val">Flux Schnell</div></div>
    <div class="gate-item"><div class="gate-lbl">Type</div><div class="gate-val">Text → Image</div></div>
    <div class="gate-item"><div class="gate-lbl">Count</div><div class="gate-val">${count} stills</div></div>
    <div class="gate-item"><div class="gate-lbl">Aspect</div><div class="gate-val">${aspect}</div></div>
    <p class="gate-note" style="grid-column:span 4">Cheap stills first; approve before paying for clips.</p>
  `;
}

async function generateStoryboards() {
  const btn = document.getElementById("btn-gen-storyboards");
  btn.textContent = "Queuing…";
  btn.disabled = true;

  try {
    const job = await post(`/api/projects/${S.project}/stages/storyboards/run`, {});
    S.jobs.storyboards = job.job_id;
    document.getElementById("storyboard-actions").style.display = "none";
    showJobProgress("storyboard", job, "Generating storyboards");
    pollJob("storyboard", job.job_id, onStoryboardsDone);
  } catch (err) {
    alert(`Could not queue storyboards: ${err.message}`);
    btn.textContent = "Generate Storyboards →";
    btn.disabled = false;
  }
}

async function onStoryboardsDone() {
  const detail = await get(`/api/projects/${S.project}`);
  const files  = detail.outputs?.stills || [];
  if (files.length) renderMedia("storyboard-media", files);

  const actions = document.getElementById("storyboard-actions");
  actions.style.display = "";
  actions.innerHTML = `
    <button class="btn-primary" id="btn-approve-sb">Approve Storyboards →</button>
    <button class="btn-ghost"   id="btn-regen-sb">Regenerate</button>
  `;
  document.getElementById("btn-approve-sb").addEventListener("click", approveStoryboards);
  document.getElementById("btn-regen-sb").addEventListener("click", regenStoryboards);

  setSummary(3, `${files.length} storyboards ready`);
}

async function approveStoryboards() {
  await post(`/api/projects/${S.project}/stages/storyboards/approve`, {});
  const count = document.querySelectorAll("#storyboard-media .media-card").length;
  setSummary(3, `${count} storyboards approved`);
  advanceTo(4);
  renderClipsGate();
}

function regenStoryboards() {
  clearEl("storyboard-media");
  hide("storyboard-progress");
  resetStoryboardActions();
}

// ── card 4: clips ────────────────────────────────────────────────────────────

function renderClipsGate() {
  const aspect   = S.manifest?.aspect_ratio || "16:9";
  const count    = S.scenePlan.length;
  const totalSec = S.scenePlan.reduce((s, sc) => s + (sc.duration_seconds || 4), 0);
  document.getElementById("clips-gate").innerHTML = `
    <div class="gate-item"><div class="gate-lbl">Model</div><div class="gate-val">Kling V3</div></div>
    <div class="gate-item"><div class="gate-lbl">Type</div><div class="gate-val">Image → Video</div></div>
    <div class="gate-item"><div class="gate-lbl">Clips</div><div class="gate-val">${count} clips</div></div>
    <div class="gate-item"><div class="gate-lbl">Total</div><div class="gate-val">~${totalSec}s</div></div>
    <p class="gate-note gate-note-paid" style="grid-column:span 4">Most expensive stage. Approve storyboards above first.</p>
  `;
}

async function generateClips() {
  if (!window.confirm(`Queue paid clip generation for "${S.project}"?`)) return;

  const btn = document.getElementById("btn-gen-clips");
  btn.textContent = "Queuing…";
  btn.disabled = true;

  try {
    const job = await post(`/api/projects/${S.project}/stages/clips/run`, {});
    S.jobs.clips = job.job_id;
    document.getElementById("clips-actions").style.display = "none";
    showJobProgress("clips", job, "Animating clips");
    pollJob("clips", job.job_id, onClipsDone);
  } catch (err) {
    alert(`Could not queue clips: ${err.message}`);
    btn.textContent = "Generate Clips →";
    btn.disabled = false;
  }
}

async function onClipsDone() {
  const detail = await get(`/api/projects/${S.project}`);
  const files  = detail.outputs?.clips || [];
  if (files.length) renderMedia("clips-media", files);

  const actions = document.getElementById("clips-actions");
  actions.style.display = "";
  actions.innerHTML = `
    <button class="btn-primary" id="btn-approve-clips">Approve Clips →</button>
    <button class="btn-ghost"   id="btn-regen-clips">Regenerate</button>
  `;
  document.getElementById("btn-approve-clips").addEventListener("click", approveClips);
  document.getElementById("btn-regen-clips").addEventListener("click", () => {
    clearEl("clips-media"); hide("clips-progress"); resetClipsActions();
  });
  setSummary(4, `${files.length} clips ready`);
}

async function approveClips() {
  await post(`/api/projects/${S.project}/stages/clips/approve`, {});
  const count = document.querySelectorAll("#clips-media .media-card").length;
  setSummary(4, `${count} clips approved`);
  advanceTo(5);
  renderComplete();
}

// ── card 5: voiceover + review ───────────────────────────────────────────────

async function renderComplete() {
  const detail = await get(`/api/projects/${S.project}`);
  const audio  = detail.outputs?.audio  || [];
  const review = detail.outputs?.review || [];
  const name   = (S.project || "").replace(/_/g, " ");

  document.getElementById("complete-content").innerHTML = `
    <div class="complete-stage">
      <h3 class="complete-stage-title">Voiceover</h3>
      <div class="job-progress" id="vo-progress" style="display:none"></div>
      <div id="vo-media" class="media-grid"></div>
      <div class="card-actions" id="vo-actions"></div>
    </div>
    <div class="complete-stage">
      <h3 class="complete-stage-title">Review Cut</h3>
      <div class="job-progress" id="rv-progress" style="display:none"></div>
      <div id="rv-media" class="media-grid"></div>
      <div class="card-actions" id="rv-actions"></div>
    </div>
    <div class="complete-actions">
      <button class="btn-ghost" id="btn-refresh-complete">↻ Refresh</button>
    </div>
  `;
  document.getElementById("btn-refresh-complete").addEventListener("click", () => renderComplete());

  renderMedia("vo-media", audio);
  renderMedia("rv-media", review);
  resetVoiceoverActions(audio.length > 0);
  resetReviewActions(review.length > 0, audio.length > 0);
  await reattachRunningJobs();

  if (review.length) setSummary(5, "Review cut ready");
  else if (audio.length) setSummary(5, "Voiceover ready");
  else setSummary(5, "Voiceover & review pending");
}

function resetVoiceoverActions(hasAudio) {
  const el = document.getElementById("vo-actions");
  if (hasAudio) {
    el.innerHTML = `
      <button class="btn-primary" id="btn-approve-vo">Approve Voiceover →</button>
      <button class="btn-ghost"   id="btn-regen-vo">Regenerate</button>
    `;
    document.getElementById("btn-approve-vo").addEventListener("click", approveVoiceover);
    document.getElementById("btn-regen-vo").addEventListener("click", generateVoiceover);
  } else {
    el.innerHTML = `
      <button class="btn-primary btn-paid" id="btn-gen-vo">Generate Voiceover →</button>
      <span class="cost-note">Text-to-speech · paid FAL call</span>
    `;
    document.getElementById("btn-gen-vo").addEventListener("click", generateVoiceover);
  }
}

function resetReviewActions(hasReview, hasAudio) {
  const el = document.getElementById("rv-actions");
  if (hasReview) {
    el.innerHTML = `
      <button class="btn-ghost" id="btn-rebuild-rv">Reassemble</button>
      <span class="cost-note">Local FFmpeg assembly · no FAL cost</span>
    `;
    document.getElementById("btn-rebuild-rv").addEventListener("click", assembleReview);
  } else {
    el.innerHTML = `
      <button class="btn-primary" id="btn-build-rv" ${hasAudio ? "" : "disabled"}>Assemble Review Cut →</button>
      <span class="cost-note">Local FFmpeg · approve voiceover first</span>
    `;
    document.getElementById("btn-build-rv").addEventListener("click", assembleReview);
  }
}

async function generateVoiceover() {
  try {
    const job = await post(`/api/projects/${S.project}/stages/voiceover/run`, {});
    S.jobs.voiceover = job.job_id;
    clearEl("vo-actions");
    showJobProgress("vo", job, "Generating voiceover");
    pollJob("vo", job.job_id, async () => {
      const detail = await get(`/api/projects/${S.project}`);
      renderMedia("vo-media", detail.outputs?.audio || []);
      resetVoiceoverActions(true);
    });
  } catch (err) {
    alert(`Could not queue voiceover: ${err.message}`);
    resetVoiceoverActions(false);
  }
}

async function approveVoiceover() {
  await post(`/api/projects/${S.project}/stages/voiceover/approve`, {});
  resetReviewActions(false, true);
}

async function assembleReview() {
  try {
    const job = await post(`/api/projects/${S.project}/stages/review/run`, {});
    S.jobs.review = job.job_id;
    clearEl("rv-actions");
    showJobProgress("rv", job, "Assembling review cut");
    pollJob("rv", job.job_id, async () => {
      const detail = await get(`/api/projects/${S.project}`);
      renderMedia("rv-media", detail.outputs?.review || []);
      resetReviewActions(true, true);
      setSummary(5, "Review cut ready");
    });
  } catch (err) {
    alert(`Could not assemble review: ${err.message}`);
    resetReviewActions(false, true);
  }
}

// ── job progress & polling ───────────────────────────────────────────────────

function showJobProgress(stage, job, label) {
  const el = document.getElementById(`${stage}-progress`);
  el.style.display = "";
  el.innerHTML = `
    <div class="job-bar">
      <div class="spinner"></div>
      <div class="job-info">
        <div class="job-lbl">${esc(label)}</div>
        <div class="job-id">Job ${(job.job_id || "").slice(0, 8)}…</div>
      </div>
      <div class="job-badge" id="${stage}-badge" data-status="queued">queued</div>
    </div>
    <div class="job-out-wrap">
      <details><summary>Show output</summary>
        <pre class="job-out" id="${stage}-out"></pre>
      </details>
    </div>
  `;
}

function updateJobProgress(stage, job) {
  const badge = document.getElementById(`${stage}-badge`);
  const out   = document.getElementById(`${stage}-out`);
  if (badge) { badge.textContent = job.status; badge.dataset.status = job.status; }
  if (out && job.output) out.textContent = job.output.slice(-2000);
}

function pollJob(stage, jobId, onDone) {
  const timer = setInterval(async () => {
    try {
      const job = await get(`/api/jobs/${jobId}`);
      updateJobProgress(stage, job);
      if (job.status === "completed") {
        clearInterval(timer);
        onDone();
      } else if (job.status === "failed" || job.status === "interrupted") {
        clearInterval(timer);
        const el = document.getElementById(`${stage}-progress`);
        if (el) el.insertAdjacentHTML("beforeend",
          `<div class="job-error">Job ${job.status}. Check output above.</div>`);
      }
    } catch (e) { console.error("poll error", e); }
  }, 2000);
}

const STAGE_TO_UI = {
  voiceover: { uiStage: "vo", label: "Generating voiceover",   onDone: onVoiceoverPolled },
  review:    { uiStage: "rv", label: "Assembling review cut",  onDone: onReviewPolled },
};

async function onVoiceoverPolled() {
  const detail = await get(`/api/projects/${S.project}`);
  renderMedia("vo-media", detail.outputs?.audio || []);
  resetVoiceoverActions((detail.outputs?.audio || []).length > 0);
}

async function onReviewPolled() {
  const detail = await get(`/api/projects/${S.project}`);
  renderMedia("rv-media", detail.outputs?.review || []);
  resetReviewActions((detail.outputs?.review || []).length > 0, (detail.outputs?.audio || []).length > 0);
  setSummary(5, "Review cut ready");
}

async function reattachRunningJobs() {
  // After a page reload or project switch, scan the server for any queued/running
  // jobs for this project and re-attach the poller so the UI catches completion.
  try {
    const jobs = await get(`/api/projects/${S.project}/jobs`);
    for (const job of jobs) {
      if (job.status !== "queued" && job.status !== "running") continue;
      const map = STAGE_TO_UI[job.stage];
      if (!map) continue;
      showJobProgress(map.uiStage, { job_id: job.id }, map.label);
      pollJob(map.uiStage, job.id, map.onDone);
    }
  } catch (e) { console.error("reattachRunningJobs", e); }
}

// ── media rendering ──────────────────────────────────────────────────────────

function renderMedia(containerId, files) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  files.forEach(f => {
    const url  = f.url  || f;
    const name = f.name || url;
    const isVideo = /\.(mp4|webm|mov)$/i.test(name);
    const isAudio = /\.(mp3|wav|aac|m4a)$/i.test(name);
    const card = document.createElement("div");
    card.className = "media-card";
    if (isVideo)      card.innerHTML = `<video src="${url}" controls preload="metadata"></video>`;
    else if (isAudio) card.innerHTML = `<div class="audio-card"><audio src="${url}" controls></audio><div class="audio-name">${esc(name)}</div></div>`;
    else              card.innerHTML = `<img src="${url}" alt="${esc(name)}" loading="lazy">`;
    container.appendChild(card);
  });
}

// ── sidebar ──────────────────────────────────────────────────────────────────

async function refreshProjectList() {
  try {
    const projects = await get("/api/projects");
    const list = document.getElementById("project-list");
    if (!projects.length) {
      list.innerHTML = `<div class="project-empty">No projects yet</div>`;
      return;
    }
    list.innerHTML = projects.map(p => `
      <button class="project-item${p.project === S.project ? " active" : ""}" data-project="${esc(p.project)}">
        <div class="project-item-name">${esc((p.project || "").replace(/_/g, " "))}</div>
        <div class="project-item-meta">${esc((p.video_type || "").replace(/_/g, " "))} · ${esc(p.current_stage || "")}</div>
      </button>
    `).join("");
    list.querySelectorAll(".project-item").forEach(btn => {
      btn.addEventListener("click", () => loadExistingProject(btn.dataset.project));
    });
  } catch (e) { console.error("refreshProjectList", e); }
}

async function loadExistingProject(slug) {
  try {
    const detail = await get(`/api/projects/${slug}`);
    S.project   = slug;
    S.manifest  = detail.manifest || {};
    S.scenePlan = detail.scene_plan?.scenes || [];

    for (let i = 1; i <= 5; i++) setCardState(i, "locked");
    for (let i = 1; i <= 4; i++) setConnector(i, false);
    clearEl("storyboard-media"); clearEl("clips-media");
    hide("storyboard-progress"); hide("clips-progress");
    resetStoryboardActions(); resetClipsActions();

    const dur    = detail.target_duration_seconds || S.manifest.target_duration_seconds || 20;
    const aspect = detail.aspect_ratio || S.manifest.aspect_ratio || "16:9";
    const idea   = S.manifest.idea || slug.replace(/_/g, " ");
    setSummary(1, `${idea.slice(0, 52)} · ${dur}s · ${aspect}`);
    setCardState(1, "completed");
    renderConceptView(detail);

    const totalSec = S.scenePlan.reduce((s, sc) => s + (sc.duration_seconds || 4), 0);
    setSummary(2, `${S.scenePlan.length} scenes · ${totalSec}s total`);
    setCardState(2, "completed");
    renderScenePlan(S.scenePlan);

    const outputs  = detail.outputs || {};
    const hasSb    = (outputs.stills || []).length > 0;
    const hasClips = (outputs.clips  || []).length > 0;
    const hasAudio = (outputs.audio  || []).length > 0;
    const hasReview= (outputs.review || []).length > 0;

    if (hasReview || hasAudio) {
      setSummary(3, `${outputs.stills?.length || 0} storyboards`);
      setCardState(3, "completed");
      renderMedia("storyboard-media", outputs.stills || []);
      setSummary(4, `${outputs.clips?.length || 0} clips`);
      setCardState(4, "completed");
      renderMedia("clips-media", outputs.clips || []);
      advanceTo(5);
      await renderComplete();
    } else if (hasClips) {
      setSummary(3, `${outputs.stills.length} storyboards`);
      setCardState(3, "completed");
      renderMedia("storyboard-media", outputs.stills);
      renderClipsGate();
      renderMedia("clips-media", outputs.clips);
      const actions = document.getElementById("clips-actions");
      actions.innerHTML = `
        <button class="btn-primary" id="btn-approve-clips">Approve Clips →</button>
        <button class="btn-ghost"   id="btn-regen-clips">Regenerate</button>
      `;
      document.getElementById("btn-approve-clips").addEventListener("click", approveClips);
      document.getElementById("btn-regen-clips").addEventListener("click", () => {
        clearEl("clips-media"); resetClipsActions();
      });
      setSummary(4, `${outputs.clips.length} clips ready`);
      advanceTo(4);
    } else if (hasSb) {
      renderStoryboardGate();
      renderMedia("storyboard-media", outputs.stills);
      const actions = document.getElementById("storyboard-actions");
      actions.innerHTML = `
        <button class="btn-primary" id="btn-approve-sb">Approve Storyboards →</button>
        <button class="btn-ghost"   id="btn-regen-sb">Regenerate</button>
      `;
      document.getElementById("btn-approve-sb").addEventListener("click", approveStoryboards);
      document.getElementById("btn-regen-sb").addEventListener("click", regenStoryboards);
      setSummary(3, `${outputs.stills.length} storyboards ready`);
      advanceTo(3);
    } else {
      renderStoryboardGate();
      advanceTo(3);
    }

    document.querySelectorAll(".project-item").forEach(b => {
      b.classList.toggle("active", b.dataset.project === slug);
    });
  } catch (err) {
    alert(`Failed to load project: ${err.message}`);
  }
}

// ── health ───────────────────────────────────────────────────────────────────

async function checkHealth() {
  try {
    const h = await get("/api/health");
    const dot = document.getElementById("health-dot");
    const lbl = document.getElementById("health-label");
    if (h.fal_key_set) {
      dot.dataset.status = "ok";
      lbl.textContent = "FAL connected";
    } else {
      dot.dataset.status = "warn";
      lbl.textContent = "FAL key missing";
    }
  } catch {
    document.getElementById("health-dot").dataset.status = "error";
    document.getElementById("health-label").textContent = "Server offline";
  }
}

// ── card collapse ────────────────────────────────────────────────────────────

function initCardToggles() {
  for (let i = 1; i <= 5; i++) {
    const header = document.getElementById(`card-${i}-header`);
    const body   = document.getElementById(`card-${i}-body`);
    if (!header || !body) continue;
    header.addEventListener("click", () => {
      const card = header.closest(".card");
      if (card.dataset.state === "completed") body.classList.toggle("expanded");
    });
  }
}

// ── init ─────────────────────────────────────────────────────────────────────

function initProgressTrack() {
  document.querySelectorAll(".progress-step").forEach(step => {
    step.addEventListener("click", () => {
      const n = parseInt(step.dataset.step);
      if (!n) return;
      const card = document.getElementById(`card-${n}`);
      if (!card) return;
      // If the target card is collapsed (completed), expand it so the user sees content.
      const body = document.getElementById(`card-${n}-body`);
      if (card.dataset.state === "completed" && body && !body.classList.contains("expanded")) {
        body.classList.add("expanded");
      }
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function init() {
  checkHealth();
  refreshProjectList();
  initConceptCard();
  initScenePlanCard();
  initCardToggles();
  initProgressTrack();
  resetStoryboardActions();
  resetClipsActions();

  document.getElementById("btn-start-over").addEventListener("click", () => {
    if (S.project && !window.confirm("Start over? Your project remains saved.")) return;
    resetAll();
  });
  document.getElementById("btn-new-project").addEventListener("click", () => {
    if (S.project && !window.confirm("Start a new project? Your current project remains saved.")) return;
    resetAll();
  });
  document.getElementById("btn-refresh-projects").addEventListener("click", refreshProjectList);
}

document.addEventListener("DOMContentLoaded", init);

"""Estimate FAL generation costs for a project (Projects/<name>/ layout)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import REPO_ROOT, project_paths


DEFAULT_MODELS = {
    "text_to_image": "fal-ai/flux/schnell",
    "image_to_video": "fal-ai/kling-video/v3/standard/image-to-video",
    "text_to_speech": "xai/tts/v1",
}

TTS_PER_1000_CHARS_FALLBACK = 0.0042


def _resolve(value: str) -> Path:
    p = Path(value.replace("\\", "/"))
    return p if p.is_absolute() else REPO_ROOT / p


def _pricing(model: str, cache: dict) -> dict | None:
    if model in cache: return cache[model]
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        cache[model] = None
        return None
    try:
        resp = requests.get(
            "https://api.fal.ai/v1/models/pricing?" + urlencode({"endpoint_id": model}),
            headers={"Authorization": f"Key {fal_key}"}, timeout=30)
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
        cache[model] = prices[0] if prices else None
    except Exception:
        cache[model] = None
    return cache[model]


def _ffprobe_dur(path: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            check=True, capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return None


def _estimate(record: dict, cache: dict) -> dict:
    mode = record.get("mode", "")
    model = record.get("model") or DEFAULT_MODELS.get(mode, "")
    price = _pricing(model, cache) if model else None
    unit_price = float(price.get("unit_price", 0)) if price else 0.0
    price_unit = price.get("unit") if price else "unknown"
    note = ""
    qty, qty_unit, fallback_cost = 0.0, "unknown", None

    result: dict = {}
    if record.get("output_json"):
        oj = _resolve(record["output_json"])
        if oj.exists():
            result = json.loads(oj.read_text(encoding="utf-8"))

    if mode == "text_to_image":
        for img in result.get("images", []):
            qty += (float(img.get("width", 0)) * float(img.get("height", 0))) / 1_000_000
        qty_unit = "megapixels"
    elif mode == "image_to_video":
        for m in record.get("media_files", []):
            d = _ffprobe_dur(_resolve(m))
            if d: qty += d
        if qty == 0 and record.get("recipe"):
            qty = float(json.loads(_resolve(record["recipe"]).read_text()).get("duration", 0))
        qty_unit = "seconds"
    elif mode == "text_to_speech":
        if record.get("recipe"):
            chars = len(json.loads(_resolve(record["recipe"]).read_text()).get("text", ""))
            qty = chars / 1000
            qty_unit = "thousand characters"
            fallback_cost = qty * TTS_PER_1000_CHARS_FALLBACK
            if price_unit == "compute seconds":
                note = "fallback: model page per-character pricing (compute seconds not in result JSON)"

    cost = fallback_cost if fallback_cost is not None else qty * unit_price
    return {"scene_id": record.get("scene_id", ""), "mode": mode, "model": model,
            "quantity": qty, "quantity_unit": qty_unit,
            "unit_price": unit_price, "price_unit": price_unit,
            "estimated_cost_usd": cost, "note": note}


def report(project: str) -> dict:
    load_dotenv(REPO_ROOT / ".env", override=False)
    pp = project_paths(project)
    if not pp.manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {pp.manifest}")
    manifest = json.loads(pp.manifest.read_text(encoding="utf-8"))
    cache: dict = {}
    rows = [_estimate(g, cache) for g in manifest.get("generations", [])]
    rows = [r for r in rows if r["estimated_cost_usd"] or r["quantity"]]
    total = sum(r["estimated_cost_usd"] for r in rows)
    manifest["cost_estimate"] = {
        "currency": "USD", "provider": "fal",
        "total_estimated_cost_usd": round(total, 6), "items": rows,
    }
    pp.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"project": project, "total_usd": total, "items": rows}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Cost report for a project.")
    parser.add_argument("project")
    args = parser.parse_args()
    out = report(args.project)
    print(f"Cost report: {args.project}")
    print("-" * 72)
    for r in out["items"]:
        print(f"  {r['scene_id']:>10}  {r['mode']:<15}  {r['quantity']:.4f} {r['quantity_unit']:<22}  ${r['estimated_cost_usd']:.4f}")
        if r["note"]: print(f"             {r['note']}")
    print("-" * 72)
    print(f"  Total: ${out['total_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

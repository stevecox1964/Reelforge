"""Run a single FAL request and write media to a known destination path.

Unlike the old fal_generate.py (which dropped timestamped files into a folder),
this runner writes the first downloaded media file to a caller-specified path,
making downstream code path-deterministic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from paths import REPO_ROOT, rel_to_repo


@dataclass
class FalRunResult:
    media_path: Path | None
    result_json_path: Path
    request_id: str
    raw_result: dict[str, Any]


def _find_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        urls.append(value)
    elif isinstance(value, dict):
        for v in value.values(): urls.extend(_find_urls(v))
    elif isinstance(value, list):
        for v in value: urls.extend(_find_urls(v))
    return urls


def _safe_suffix(url: str, fallback: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", suffix or ""):
        return suffix
    return fallback


def _download(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    dst.write_bytes(response.content)
    return dst


def run_fal(*, model: str, recipe: Path, media_dst: Path,
            fal_results_dir: Path, upload_files: dict[str, Path] | None = None,
            fallback_ext: str = ".bin") -> FalRunResult:
    """Run a fal model, save full JSON result, download first media to media_dst.

    media_dst is treated as a *stem hint*: its parent and filename stem are kept,
    but the actual extension is taken from the URL so we don't pretend a .mp4
    is a .png. The actual media path is returned in the result.
    """
    load_dotenv(REPO_ROOT / ".env", override=False)
    if not os.environ.get("FAL_KEY"):
        raise RuntimeError("FAL_KEY is not set in environment.")
    try:
        import fal_client
    except ImportError as e:
        raise RuntimeError("Missing fal-client. pip install fal-client") from e

    arguments: dict[str, Any] = json.loads(recipe.read_text(encoding="utf-8"))
    if upload_files:
        for key, path in upload_files.items():
            if not path.exists():
                raise FileNotFoundError(f"Upload file does not exist: {path}")
            arguments[key] = fal_client.upload_file(str(path))

    request_id_holder = {"id": ""}
    def _on_enqueue(rid: str) -> None:
        request_id_holder["id"] = rid
        print(f"  queued FAL request: {rid}", flush=True)

    fal_results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    result_json_path = fal_results_dir / f"fal_result_{timestamp}.json"

    try:
        result = fal_client.subscribe(model, arguments=arguments, with_logs=True,
                                       on_enqueue=_on_enqueue)
    except Exception as exc:
        error_path = fal_results_dir / f"fal_error_{timestamp}.json"
        error_path.write_text(json.dumps({
            "model": model, "request_id": request_id_holder["id"],
            "arguments": arguments, "error_type": type(exc).__name__,
            "error": str(exc),
        }, indent=2), encoding="utf-8")
        raise

    result_json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    urls = list(dict.fromkeys(_find_urls(result)))
    media_path: Path | None = None
    if urls:
        url = urls[0]
        ext = _safe_suffix(url, fallback_ext)
        media_path = media_dst.with_suffix(ext)
        _download(url, media_path)

    return FalRunResult(
        media_path=media_path,
        result_json_path=result_json_path,
        request_id=request_id_holder["id"],
        raw_result=result,
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run one FAL request to a known destination.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--recipe", required=True, help="Path to a JSON recipe file.")
    parser.add_argument("--media-dst", required=True, help="Destination path stem for the first downloaded media.")
    parser.add_argument("--fal-results-dir", required=True)
    parser.add_argument("--upload-file", action="append", default=[],
                        help="key=path - upload local file, replace arg key with returned URL.")
    args = parser.parse_args()

    uploads = {}
    for item in args.upload_file:
        if "=" not in item: raise ValueError(f"--upload-file must be key=path, got {item}")
        k, v = item.split("=", 1)
        uploads[k] = Path(v) if Path(v).is_absolute() else REPO_ROOT / v

    out = run_fal(
        model=args.model,
        recipe=Path(args.recipe) if Path(args.recipe).is_absolute() else REPO_ROOT / args.recipe,
        media_dst=Path(args.media_dst) if Path(args.media_dst).is_absolute() else REPO_ROOT / args.media_dst,
        fal_results_dir=Path(args.fal_results_dir) if Path(args.fal_results_dir).is_absolute() else REPO_ROOT / args.fal_results_dir,
        upload_files=uploads,
    )
    print(json.dumps({
        "media_path": rel_to_repo(out.media_path) if out.media_path else None,
        "result_json_path": rel_to_repo(out.result_json_path),
        "request_id": out.request_id,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(_cli())

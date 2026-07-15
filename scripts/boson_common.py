#!/usr/bin/env python3
"""Shared helpers for Boson AI skill scripts.

Uses the `requests` library (Boson's official examples all use it).
Covers: API client (Bearer auth), config loading, doc-cache, and the
official-docs sync check reused from the mimo skill pattern.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    raise ImportError(
        "This skill requires the 'requests' library. Install it with: pip install requests"
    )

DEFAULT_BASE_URL = "https://api.boson.ai"
SKILL_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path.cwd()  # User's current working directory — outputs land here
DEFAULT_CONFIG = SKILL_ROOT / "templates" / "config.example.json"
DEFAULT_KNOWN_RULES = SKILL_ROOT / "templates" / "known_rules.json"
DEFAULT_DOC_CACHE_DIR = "output/.doc_cache"


def resolve_output_dir(path: str | Path) -> Path:
    """Resolve an output path: relative paths are based on CWD (project root), not skill root.

    This ensures generated artifacts land in the user's project output/ directory,
    not inside the skill package. Skill-internal resources (config, known_rules,
    examples) are still read from SKILL_ROOT.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load config JSON. Priority: explicit path > CWD/config.json > skill template."""
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.append(PROJECT_ROOT / "boson_config.json")  # project-local override
    candidates.append(DEFAULT_CONFIG)  # skill template (always exists)
    for p in candidates:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def resolve_api_key(args: Any, config: Dict[str, Any]) -> Optional[str]:
    env_name = str(config.get("api_key_env", "BOSON_API_KEY"))
    return getattr(args, "api_key", None) or os.getenv(env_name) or config.get("api_key")


def resolve_base_url(args: Any, config: Dict[str, Any]) -> str:
    env_name = str(config.get("base_url_env", "BOSON_BASE_URL"))
    url = (
        getattr(args, "base_url", None)
        or os.getenv(env_name)
        or config.get("default_base_url")
        or DEFAULT_BASE_URL
    )
    return str(url).rstrip("/")


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class BosonAPIError(RuntimeError):
    """Preserves HTTP status code and parsed error body."""

    def __init__(self, status_code: int, body: str, retry_after: Optional[float] = None):
        super().__init__(f"HTTP {status_code}: {body[:500]}")
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after


def _parse_retry_after(resp: "requests.Response") -> Optional[float]:
    val = resp.headers.get("Retry-After")
    if not val:
        return None
    try:
        return max(0.0, float(val))
    except ValueError:
        return None


def _parse_error_body(resp: "requests.Response") -> str:
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return err.get("message", json.dumps(err))
        return str(err)
    except Exception:
        return resp.text[:500]


class BosonClient:
    """Thin wrapper over the Boson REST API."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 120):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    # ---- low-level ----

    def _post(self, path: str, *, json_body: Any = None, stream: bool = False):
        url = self.base_url + path
        try:
            resp = self.session.post(url, json=json_body, timeout=self.timeout, stream=stream)
        except requests.RequestException as exc:
            raise RuntimeError(f"network error: {exc}") from exc
        if not resp.ok:
            raise BosonAPIError(resp.status_code, _parse_error_body(resp), _parse_retry_after(resp))
        return resp

    def _get(self, path: str, *, stream: bool = False):
        url = self.base_url + path
        try:
            resp = self.session.get(url, timeout=self.timeout, stream=stream)
        except requests.RequestException as exc:
            raise RuntimeError(f"network error: {exc}") from exc
        if not resp.ok:
            raise BosonAPIError(resp.status_code, _parse_error_body(resp), _parse_retry_after(resp))
        return resp

    # ---- TTS ----

    def create_speech(
        self,
        *,
        text: str,
        model: str = "higgs-tts-3",
        voice: Optional[str] = None,
        response_format: str = "mp3",
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        stream: bool = False,
    ):
        """POST /v1/audio/speech. Returns a requests.Response (binary audio or PCM stream)."""
        body: Dict[str, Any] = {"input": text, "model": model, "response_format": response_format}
        if voice:
            body["voice"] = voice
        if ref_audio:
            body["ref_audio"] = ref_audio
        if ref_text:
            body["ref_text"] = ref_text
        if stream:
            body["stream"] = True
            body["response_format"] = "pcm"  # streaming requires pcm
        return self._post("/v1/audio/speech", json_body=body, stream=stream)

    # ---- Voice management ----

    def create_voice(self, *, ref_audio: str, ref_text: str, description: Optional[str] = None) -> Dict[str, Any]:
        """POST /v1/audio/voices — register a reusable cloned voice."""
        body: Dict[str, Any] = {"ref_audio": ref_audio, "ref_text": ref_text}
        if description:
            body["description"] = description
        resp = self._post("/v1/audio/voices", json_body=body)
        return resp.json()

    def get_voice(self, voice_id: str) -> Dict[str, Any]:
        """GET /v1/audio/voices/{voice_id}."""
        resp = self._get(f"/v1/audio/voices/{voice_id}")
        return resp.json()

    def list_voices(self, limit: int = 100) -> Dict[str, Any]:
        """GET /v1/audio/voices — list registered voices."""
        resp = self._get(f"/v1/audio/voices?limit={limit}")
        return resp.json()

    # ---- Avatar video ----

    def create_video(self, *, ref_image: str, model: str = "higgs-avatar",
                     input_audio: Optional[str] = None, input_tts: Optional[Dict[str, Any]] = None,
                     size: str = "640x640") -> Dict[str, Any]:
        """POST /v1/videos — create avatar video (async). Returns Video object."""
        if bool(input_audio) == bool(input_tts):
            raise ValueError("Provide exactly one of input_audio or input_tts")
        body: Dict[str, Any] = {"model": model, "ref_image": ref_image, "size": size}
        if input_audio:
            body["input"] = input_audio
        if input_tts:
            body["input_tts"] = input_tts
        resp = self._post("/v1/videos", json_body=body)
        return resp.json()

    def create_video_stream(self, *, ref_image: str, model: str = "higgs-avatar",
                            input_audio: Optional[str] = None, input_tts: Optional[Dict[str, Any]] = None,
                            size: str = "640x640"):
        """POST /v1/videos/stream — streaming fMP4. Returns (video_id, response_stream)."""
        if bool(input_audio) == bool(input_tts):
            raise ValueError("Provide exactly one of input_audio or input_tts")
        body: Dict[str, Any] = {"model": model, "ref_image": ref_image, "size": size}
        if input_audio:
            body["input"] = input_audio
        if input_tts:
            body["input_tts"] = input_tts
        resp = self._post("/v1/videos/stream", json_body=body, stream=True)
        video_id = resp.headers.get("X-Video-Id")
        return video_id, resp

    def get_video(self, video_id: str) -> Dict[str, Any]:
        """GET /v1/videos/{video_id} — poll status."""
        resp = self._get(f"/v1/videos/{video_id}")
        return resp.json()

    def download_video(self, video_id: str) -> "requests.Response":
        """GET /v1/videos/{video_id}/content — download rendered MP4."""
        return self._get(f"/v1/videos/{video_id}/content", stream=True)

    def wait_for_video(self, video_id: str, poll_interval: float = 2.0, max_wait: float = 300.0) -> Dict[str, Any]:
        """Poll until video is completed or failed. Returns final Video object."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            v = self.get_video(video_id)
            status = v.get("status", "")
            if status == "completed":
                return v
            if status == "failed":
                raise RuntimeError(f"video {video_id} failed: {v.get('error', 'unknown')}")
            time.sleep(poll_interval)
        raise TimeoutError(f"video {video_id} did not complete within {max_wait}s")


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def file_to_data_uri(path: Path, *, max_bytes: int = 10 * 1024 * 1024) -> str:
    """Read a file and return a data URI (base64). Raises if over max_bytes."""
    import base64
    import mimetypes
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ValueError(f"file {path} is {len(raw)} bytes; max is {max_bytes}")
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def with_retries(fn, *, retries: int = 2, sleep_cap: float = 30.0, verbose: bool = False):
    """Retry fn() on BosonAPIError (429/5xx) with exponential backoff."""
    last_exc = None
    for attempt in range(1, retries + 2):
        try:
            return fn()
        except BosonAPIError as exc:
            last_exc = exc
            if attempt > retries:
                break
            if exc.retry_after is not None:
                wait = exc.retry_after
            elif exc.status_code >= 500 or exc.status_code == 429:
                wait = min(2 ** attempt, sleep_cap)
            else:
                break  # non-retryable
            if verbose:
                print(f"[WARN] attempt {attempt} failed (HTTP {exc.status_code}); retrying in {wait:.1f}s")
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Doc cache (reused pattern from mimo skill)
# ---------------------------------------------------------------------------

class DocCache:
    """File-based cache for fetched doc text. Lives in the project's output dir."""

    def __init__(self, cache_dir: str = DEFAULT_DOC_CACHE_DIR):
        self.dir = resolve_output_dir(cache_dir)

    def _path_for(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.dir / f"{h}.txt"

    def get(self, url: str, ttl_hours: float = 24.0) -> Optional[str]:
        p = self._path_for(url)
        if not p.exists():
            return None
        age = time.time() - p.stat().st_mtime
        if age > ttl_hours * 3600:
            return None
        return p.read_text(encoding="utf-8")

    def set(self, url: str, content: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path_for(url).write_text(content, encoding="utf-8")


def fetch_text(url: str, timeout: int = 30) -> str:
    """Fetch a URL as text."""
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "boson-skill-selfcheck/1.0"})
    resp.raise_for_status()
    return resp.text

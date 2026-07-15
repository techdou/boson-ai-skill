#!/usr/bin/env python3
"""Boson AI Avatar Video — talking-head video from a still image + driving audio/text.

Higgs Avatar generates lip-synced, head-moving avatar video from:
  - ref_image: a still photo (PNG/JPEG/WEBP)
  - input: driving audio (audio-to-video, max 60s)
  - input_tts: text request (text-to-video, gateway synthesizes voice first)

Two modes:
  1. Async (default): POST → poll → download MP4
  2. Streaming (--stream): live fMP4 byte stream, playback starts immediately

Usage:
  # Audio-to-video (async)
  python scripts/boson_avatar_video.py --ref-image face.jpg --input speech.mp3 --output out.mp4

  # Text-to-video (async)
  python scripts/boson_avatar_video.py --ref-image face.jpg --tts-text "Hello world" --tts-voice chloe --output out.mp4

  # Streaming (live fMP4)
  python scripts/boson_avatar_video.py --ref-image face.jpg --tts-text "Hello" --stream --output out.mp4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boson_common import (  # noqa: E402
    BosonClient,
    PROJECT_ROOT,
    file_to_data_uri,
    load_config,
    resolve_api_key,
    resolve_base_url,
    resolve_output_dir,
    write_bytes,
)

# Known Boson server-side bug (public preview): text-to-video (input_tts) fails
# with an ascii encoding error. When detected, we auto-fallback to TTS→audio→video.
_T2V_BUG_SIGNATURE = "codec can't encode"


def _resolve_ref_image(ref_image_arg: str) -> str:
    """Resolve ref_image: local file → data URI; else pass through as URL."""
    p = Path(ref_image_arg)
    if p.exists():
        return file_to_data_uri(p)
    return ref_image_arg


def _resolve_input_audio(input_arg: str) -> str:
    """Resolve driving audio: local file → data URI; else pass through as URL."""
    p = Path(input_arg)
    if p.exists():
        return file_to_data_uri(p)
    return input_arg


def _build_tts_body(args: argparse.Namespace, config: dict) -> Dict[str, Any]:
    """Build the input_tts speech request from CLI args."""
    tts_body: Dict[str, Any] = {
        "model": args.tts_model or config.get("default_tts_model", "higgs-tts-3"),
        "input": args.tts_text,
    }
    if args.tts_voice:
        tts_body["voice"] = args.tts_voice
    if args.tts_ref_audio:
        tts_body["ref_audio"] = _resolve_input_audio(args.tts_ref_audio)
    if args.tts_ref_text:
        tts_body["ref_text"] = args.tts_ref_text
    return tts_body


def _do_tts_then_video(client: BosonClient, *, ref_image: str, model: str, size: str,
                       tts_body: Dict[str, Any], poll_interval: float, max_wait: float,
                       out_path: Path) -> int:
    """Fallback: synthesize audio via TTS, then use audio-to-video."""
    print("[FALLBACK] Text-to-video hit a known Boson server bug.")
    print("[FALLBACK] Switching to TTS → audio → video (two-step)...")

    # Step 1: TTS
    voice = tts_body.get("voice")
    tts_text = tts_body["input"]
    print(f"  [1/4] Synthesizing audio ({len(tts_text)} chars, voice={voice})...")
    tts_resp = client.create_speech(text=tts_text, model=tts_body.get("model", "higgs-tts-3"),
                                     voice=voice, response_format="wav")
    audio_dir = resolve_output_dir("output/video/_tts_temp")
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"tts_{int(time.time())}.wav"
    write_bytes(audio_path, tts_resp.content)
    print(f"        {len(tts_resp.content)} bytes -> {audio_path}")

    # Step 2: audio-to-video
    print(f"  [2/4] Creating video (audio-to-video)...")
    video = client.create_video(ref_image=ref_image, model=model,
                                 input_audio=file_to_data_uri(audio_path), size=size)
    video_id = video["id"]
    print(f"        video_id={video_id}")

    print(f"  [3/4] Polling until completed...")
    client.wait_for_video(video_id, poll_interval=poll_interval, max_wait=max_wait)

    print(f"  [4/4] Downloading MP4...")
    resp = client.download_video(video_id)
    write_bytes(out_path, resp.content)
    print(f"        {len(resp.content)} bytes -> {out_path}")

    # Cleanup temp audio
    audio_path.unlink(missing_ok=True)
    print("[FALLBACK] Done. (temp audio cleaned up)")
    return 0


def run_async(args: argparse.Namespace, config: dict, client: BosonClient) -> int:
    """Create video → poll → download. Auto-fallbacks text-to-video on known bug."""
    ref_image = _resolve_ref_image(args.ref_image)
    model = args.model or config.get("default_avatar_model", "higgs-avatar")
    size = args.size or config.get("default_video_size", "640x640")
    out_path = resolve_output_dir(args.output or "output/video/avatar.mp4")

    input_audio = None
    input_tts = None

    if args.input:
        input_audio = _resolve_input_audio(args.input)
    elif args.tts_text:
        input_tts = _build_tts_body(args, config)

    if args.dry_run:
        print(f"[DRY] model={model}, ref_image={'file' if Path(args.ref_image).exists() else 'url'}, size={size}")
        if input_audio:
            print(f"[DRY] mode=audio-to-video, input={'file' if Path(args.input).exists() else 'url'}")
        else:
            print(f"[DRY] mode=text-to-video, tts_text={len(args.tts_text)} chars, voice={args.tts_voice}")
        return 0

    poll_interval = float(args.poll_interval or config.get("video_poll_interval", 2.0))
    max_wait = float(args.max_wait or config.get("video_max_wait", 300.0))

    # If text-to-video mode, try it first but catch the known server bug
    if input_tts and not args.no_fallback:
        print("[1/3] Creating video job (text-to-video)...")
        video = client.create_video(ref_image=ref_image, model=model,
                                     input_audio=None, input_tts=input_tts, size=size)
        video_id = video["id"]
        print(f"      video_id={video_id}, status={video.get('status', 'queued')}")

        if args.create_only:
            print(json.dumps(video, ensure_ascii=False, indent=2))
            return 0

        print("[2/3] Polling until completed...")
        try:
            video = client.wait_for_video(video_id, poll_interval=poll_interval, max_wait=max_wait)
        except RuntimeError as exc:
            if _T2V_BUG_SIGNATURE in str(exc):
                # Known server bug — auto-fallback to TTS→audio→video
                return _do_tts_then_video(client, ref_image=ref_image, model=model, size=size,
                                           tts_body=input_tts, poll_interval=poll_interval,
                                           max_wait=max_wait, out_path=out_path)
            raise  # Different error, re-raise

        print(f"      status=completed, progress={video.get('progress', 100)}")
        print("[3/3] Downloading MP4...")
        resp = client.download_video(video_id)
        write_bytes(out_path, resp.content)
        print(f"      {len(resp.content)} bytes -> {out_path}")
        return 0

    # Audio-to-video mode (or --no-fallback with input_tts)
    print("[1/3] Creating video job...")
    video = client.create_video(
        ref_image=ref_image, model=model,
        input_audio=input_audio, input_tts=input_tts, size=size,
    )
    video_id = video["id"]
    print(f"      video_id={video_id}, status={video.get('status', 'queued')}")

    if args.create_only:
        print(json.dumps(video, ensure_ascii=False, indent=2))
        return 0

    print("[2/3] Polling until completed...")
    video = client.wait_for_video(video_id, poll_interval=poll_interval, max_wait=max_wait)
    print(f"      status=completed, progress={video.get('progress', 100)}")

    print("[3/3] Downloading MP4...")
    resp = client.download_video(video_id)
    write_bytes(out_path, resp.content)
    print(f"      {len(resp.content)} bytes -> {out_path}")
    return 0


def run_stream(args: argparse.Namespace, config: dict, client: BosonClient) -> int:
    """Streaming mode — receive live fMP4."""
    ref_image = _resolve_ref_image(args.ref_image)
    model = args.model or config.get("default_avatar_model", "higgs-avatar")
    size = args.size or config.get("default_video_size", "640x640")

    input_audio = None
    input_tts = None
    if args.input:
        input_audio = _resolve_input_audio(args.input)
    elif args.tts_text:
        tts_body: Dict[str, Any] = {
            "model": args.tts_model or config.get("default_tts_model", "higgs-tts-3"),
            "input": args.tts_text,
        }
        if args.tts_voice:
            tts_body["voice"] = args.tts_voice
        input_tts = tts_body

    if args.dry_run:
        print(f"[DRY] streaming mode, model={model}, size={size}")
        return 0

    out_path = resolve_output_dir(args.output or "output/video/stream.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("[STREAM] Starting...")
    video_id, resp = client.create_video_stream(
        ref_image=ref_image, model=model,
        input_audio=input_audio, input_tts=input_tts, size=size,
    )
    print(f"[STREAM] video_id={video_id}")

    total = 0
    with out_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    print(f"[STREAM] {total} bytes -> {out_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Boson AI Avatar Video — talking-head video generation")
    # Image (required)
    p.add_argument("--ref-image", required=True, help="Reference image (face to animate): local path or URL")
    # Driving input — exactly one required
    p.add_argument("--input", default=None, help="Driving audio (audio-to-video): local path or URL, max 60s")
    p.add_argument("--tts-text", default=None, help="Text for text-to-video mode")
    p.add_argument("--tts-voice", default=None, help="Voice for text-to-video (preset or custom ID)")
    p.add_argument("--tts-model", default=None, help="TTS model for text-to-video; default higgs-tts-3")
    p.add_argument("--tts-ref-audio", default=None, help="Clone ref for text-to-video voice")
    p.add_argument("--tts-ref-text", default=None, help="Transcript of tts-ref-audio")
    # Video params
    p.add_argument("--model", default=None, help="Avatar model; default higgs-avatar")
    p.add_argument("--size", default=None, choices=["640x640", "640x480", "480x640"], help="Output video size")
    p.add_argument("--output", "-o", default=None, help="Output MP4 path")
    # Execution
    p.add_argument("--stream", action="store_true", help="Streaming fMP4 mode (instead of async poll)")
    p.add_argument("--create-only", action="store_true", help="Only create the job, print video_id and exit")
    p.add_argument("--no-fallback", action="store_true", help="Disable auto-fallback from text-to-video to TTS+audio-to-video")
    p.add_argument("--poll-interval", type=float, default=None, help="Seconds between status polls")
    p.add_argument("--max-wait", type=float, default=None, help="Max seconds to wait for completion")
    p.add_argument("--config", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)
    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)

    if not args.dry_run and not api_key:
        print("[ERROR] BOSON_API_KEY is required", file=sys.stderr)
        return 1

    # Validate: exactly one driving input
    has_input = bool(args.input)
    has_tts = bool(args.tts_text)
    if has_input == has_tts:
        print("[ERROR] provide exactly one of --input (audio) or --tts-text (text-to-video)", file=sys.stderr)
        return 1

    client = BosonClient(api_key or "dry-run-key", base_url, timeout=args.timeout)

    if args.stream:
        return run_stream(args, config, client)
    else:
        return run_async(args, config, client)


if __name__ == "__main__":
    raise SystemExit(main())

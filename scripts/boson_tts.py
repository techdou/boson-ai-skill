#!/usr/bin/env python3
"""Boson AI TTS — text-to-speech synthesis with Higgs TTS 3.

Supports: preset voices, voice cloning (inline ref_audio), streaming PCM,
batch synthesis from a segments JSON file, and inline emotion/style tags.

Usage examples:
  # Single text to MP3
  python scripts/boson_tts.py --text "Hello world" --voice chloe --output out.mp3

  # Clone a voice from reference audio
  python scripts/boson_tts.py --text "Hello" --ref-audio sample.wav --ref-text "sample transcript" --output cloned.mp3

  # Batch from segments
  python scripts/boson_tts.py --segments segments.json --out-dir output/audio

  # Stream PCM (low latency)
  python scripts/boson_tts.py --text "Hello" --stream --output stream.wav
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boson_common import (  # noqa: E402
    BosonAPIError,
    BosonClient,
    DocCache,
    PROJECT_ROOT,
    file_to_data_uri,
    load_config,
    resolve_api_key,
    resolve_base_url,
    resolve_output_dir,
    with_retries,
    write_bytes,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

# Format → file extension map. PCM streaming is written to .wav container.
FORMAT_EXT = {"mp3": ".mp3", "wav": ".wav", "pcm": ".wav", "opus": ".opus", "aac": ".aac", "flac": ".flac"}


def _run_doc_check(config: Dict[str, Any], args: Any, *, api_key: Optional[str], base_url: str) -> None:
    """Lightweight non-blocking doc check (advisory only, never raises except on --check-docs)."""
    if not config.get("doc_check_enabled", True):
        return
    if getattr(args, "skip_check", False):
        return
    try:
        import check_official_docs as _cod
        issues = _cod.run_check(config, args, api_key_override=api_key, base_url_override=base_url)
        critical = [i for i in issues if i["severity"] == _cod.CRITICAL]
        warnings = [i for i in issues if i["severity"] == _cod.WARNING]
        if critical:
            print(f"[DOC-CHECK] {len(critical)} CRITICAL issue(s):")
            for i in critical:
                print(f"  [CRITICAL] ({i['section']}) {i['message']}")
            if getattr(args, "check_docs", False):
                raise RuntimeError("Official-doc check found CRITICAL issues. Use --skip-check to override.")
        elif warnings:
            mode = "blocking" if getattr(args, "check_docs", False) else "non-blocking"
            print(f"[DOC-CHECK] {len(warnings)} WARNING(s) ({mode}).")
            if getattr(args, "check_docs", False):
                raise RuntimeError("Official-doc check found warnings and --check-docs is enabled.")
    except RuntimeError:
        raise
    except Exception as exc:
        if getattr(args, "verbose", False):
            print(f"[DOC-CHECK] Skipped: {exc}")


def synthesize_single(client: BosonClient, *, text: str, model: str, voice: Optional[str],
                      response_format: str, ref_audio: Optional[str], ref_text: Optional[str],
                      stream: bool, retries: int, verbose: bool) -> bytes:
    """Synthesize a single text and return audio bytes."""
    resp = with_retries(
        lambda: client.create_speech(
            text=text, model=model, voice=voice, response_format=response_format,
            ref_audio=ref_audio, ref_text=ref_text, stream=stream,
        ),
        retries=retries, verbose=verbose,
    )
    if stream:
        # Collect PCM chunks
        chunks: List[bytes] = []
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)
    return resp.content


def _safe_filename(text: str, max_len: int = 40) -> str:
    """Generate a safe filename from text prefix."""
    import re
    clean = re.sub(r'[\\/:*?"<>|]', "_", text[:max_len]).strip()
    return clean or "output"


def _resolve_ref_audio(ref_audio_arg: Optional[str]) -> Optional[str]:
    """Resolve ref_audio: if it's a local file path, convert to data URI; else pass through (URL)."""
    if not ref_audio_arg:
        return None
    p = Path(ref_audio_arg)
    if p.exists():
        return file_to_data_uri(p)
    return ref_audio_arg  # assume it's a URL or already-encoded data URI


def run_single(args: argparse.Namespace, config: Dict[str, Any], client: BosonClient) -> int:
    """Synthesize a single text string to a file."""
    fmt = args.response_format or config.get("default_tts_format", "mp3")
    if args.stream:
        fmt = "pcm"
    ref_audio = _resolve_ref_audio(args.ref_audio)
    voice = args.voice or config.get("default_voice")
    model = args.model or config.get("default_tts_model", "higgs-tts-3")

    if args.dry_run:
        print(f"[DRY] model={model}, voice={voice}, format={fmt}, ref_audio={'yes' if ref_audio else 'no'}")
        print(f"[DRY] text ({len(args.text)} chars): {args.text[:80]}...")
        return 0

    audio_bytes = synthesize_single(
        client, text=args.text, model=model, voice=voice,
        response_format=fmt, ref_audio=ref_audio, ref_text=args.ref_text,
        stream=args.stream, retries=int(args.retries or config.get("retries", 2)),
        verbose=args.verbose,
    )
    out_path = resolve_output_dir(args.output or f"output/audio/{_safe_filename(args.text)}.{FORMAT_EXT.get(fmt, '.mp3')}")
    write_bytes(out_path, audio_bytes)
    print(f"[OK] {len(audio_bytes)} bytes -> {out_path}")
    return 0


def run_batch(args: argparse.Namespace, config: Dict[str, Any], client: BosonClient) -> int:
    """Batch synthesize from a segments JSON file."""
    segments_path = Path(args.segments)
    if not segments_path.exists():
        print(f"[ERROR] segments file not found: {segments_path}", file=sys.stderr)
        return 1
    segments = json.loads(segments_path.read_text(encoding="utf-8"))
    if not isinstance(segments, list):
        print("[ERROR] segments file must contain a JSON array", file=sys.stderr)
        return 1

    out_dir = resolve_output_dir(args.out_dir or config.get("default_tts_output_dir", "output/audio"))
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = resolve_output_dir(args.manifest or config.get("default_tts_manifest", "output/audio_manifest.json"))
    model_default = args.model or config.get("default_tts_model", "higgs-tts-3")
    voice_default = args.voice or config.get("default_voice")
    fmt_default = args.response_format or config.get("default_tts_format", "mp3")
    sleep_between = float(args.sleep_between if args.sleep_between is not None else config.get("sleep_between", 0.0))
    retries = int(args.retries or config.get("retries", 2))

    results: List[Dict[str, Any]] = []
    for i, seg in enumerate(segments, start=1):
        text = str(seg.get("text") or seg.get("input") or "").strip()
        if not text:
            results.append({"index": i, "status": "skipped", "reason": "empty text"})
            continue
        title = str(seg.get("title") or seg.get("name") or f"segment_{i:03d}")
        voice = seg.get("voice") or voice_default
        model = seg.get("model") or model_default
        fmt = seg.get("format") or fmt_default
        ref_audio = _resolve_ref_audio(seg.get("ref_audio"))
        ref_text = seg.get("ref_text")
        out_file = out_dir / f"{i:03d}_{_safe_filename(title, 30)}.{FORMAT_EXT.get(fmt, '.mp3')}"

        if out_file.exists() and not args.overwrite:
            print(f"[SKIP] {out_file.name} (exists; use --overwrite)")
            results.append({"index": i, "title": title, "status": "skipped", "audio_path": str(out_file)})
            continue

        if args.dry_run:
            print(f"[DRY] {i:03d} {out_file.name}: {len(text)} chars, model={model}, voice={voice}")
            results.append({"index": i, "title": title, "status": "dry_run", "text_len": len(text)})
            continue

        try:
            audio_bytes = synthesize_single(
                client, text=text, model=model, voice=voice, response_format=fmt,
                ref_audio=ref_audio, ref_text=ref_text, stream=False,
                retries=retries, verbose=args.verbose,
            )
            write_bytes(out_file, audio_bytes)
            print(f"[OK] {i:03d} {out_file.name}: {len(audio_bytes)} bytes")
            results.append({"index": i, "title": title, "status": "success", "audio_path": str(out_file), "bytes": len(audio_bytes)})
        except Exception as exc:
            print(f"[FAIL] {i:03d} {title}: {exc}", file=sys.stderr)
            results.append({"index": i, "title": title, "status": "failed", "error": str(exc)})
            if args.stop_on_error:
                break

        if sleep_between > 0:
            time.sleep(sleep_between)

    manifest = {"summary": {"total": len(results), "success": sum(1 for r in results if r["status"] == "success")},
                "segments": results}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] manifest: {manifest_path}")
    return 1 if any(r["status"] == "failed" for r in results) else 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Boson AI TTS — synthesize speech with Higgs TTS 3")
    # Input (mutually exclusive groups handled in main)
    p.add_argument("--text", help="Text to synthesize (single mode)")
    p.add_argument("--segments", help="Path to segments JSON for batch mode")
    # Output
    p.add_argument("--output", "-o", help="Output file path (single mode)")
    p.add_argument("--out-dir", help="Output directory (batch mode)")
    p.add_argument("--manifest", help="Manifest output path (batch mode)")
    # TTS params
    p.add_argument("--model", default=None, help="TTS model; default higgs-tts-3")
    p.add_argument("--voice", default=None, help="Preset voice (chloe/eleanor/jake/marcus/nora/oliver/default) or custom voice ID")
    p.add_argument("--response-format", default=None, choices=["mp3", "wav", "pcm", "opus", "aac", "flac"])
    p.add_argument("--ref-audio", help="Reference audio for cloning: local path, URL, or data URI")
    p.add_argument("--ref-text", help="Transcript of ref_audio")
    # Streaming
    p.add_argument("--stream", action="store_true", help="Stream PCM (low latency); implies format=pcm")
    # Execution
    p.add_argument("--config", default=None, help="Config JSON path")
    p.add_argument("--api-key", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--retries", type=int, default=None)
    p.add_argument("--sleep-between", type=float, default=None)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--stop-on-error", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Plan without API calls")
    # Doc check
    p.add_argument("--check-docs", action="store_true", help="Blocking official-doc check")
    p.add_argument("--skip-check", action="store_true", help="Skip doc check entirely")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)

    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)

    if not args.dry_run and not api_key:
        print("[ERROR] BOSON_API_KEY is required (set env var or use --api-key)", file=sys.stderr)
        return 1

    # Doc check (advisory unless --check-docs)
    if api_key:
        _run_doc_check(config, args, api_key=api_key, base_url=base_url)

    client = BosonClient(api_key or "dry-run-key", base_url, timeout=args.timeout)

    if args.segments:
        return run_batch(args, config, client)
    elif args.text:
        return run_single(args, config, client)
    else:
        print("[ERROR] provide --text (single) or --segments (batch)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

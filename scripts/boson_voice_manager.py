#!/usr/bin/env python3
"""Boson AI Voice Manager — register, list, and inspect reusable cloned voices.

Registering a voice from reference audio gives you a stable voice_<sha256> ID
that you can pass to the `voice` field of boson_tts.py, instead of sending
ref_audio on every request.

Usage:
  # Register a voice
  python scripts/boson_voice_manager.py create --ref-audio sample.wav --ref-text "transcript"

  # List all registered voices
  python scripts/boson_voice_manager.py list

  # Get details of one voice
  python scripts/boson_voice_manager.py get --voice-id voice_abc123
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boson_common import (  # noqa: E402
    BosonClient,
    file_to_data_uri,
    load_config,
    resolve_api_key,
    resolve_base_url,
)


def cmd_create(args: argparse.Namespace, config: dict, client: BosonClient) -> int:
    ref_audio_path = Path(args.ref_audio)
    if not ref_audio_path.exists():
        # Maybe it's a URL
        ref_audio_val = args.ref_audio
    else:
        ref_audio_val = file_to_data_uri(ref_audio_path)

    if args.dry_run:
        print(f"[DRY] ref_audio: {'file' if ref_audio_path.exists() else 'url'}, ref_text: {len(args.ref_text)} chars")
        return 0

    result = client.create_voice(ref_audio=ref_audio_val, ref_text=args.ref_text, description=args.description)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace, config: dict, client: BosonClient) -> int:
    if args.dry_run:
        print("[DRY] would list voices")
        return 0
    result = client.list_voices(limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_get(args: argparse.Namespace, config: dict, client: BosonClient) -> int:
    if args.dry_run:
        print(f"[DRY] would get voice {args.voice_id}")
        return 0
    result = client.get_voice(args.voice_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Boson AI Voice Manager — register/list/get cloned voices")
    sub = p.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Register a reusable voice from reference audio")
    p_create.add_argument("--ref-audio", required=True, help="Reference audio: local path or URL")
    p_create.add_argument("--ref-text", required=True, help="Transcript of the reference audio")
    p_create.add_argument("--description", default=None, help="Optional description")

    p_list = sub.add_parser("list", help="List all registered voices")
    p_list.add_argument("--limit", type=int, default=100)

    p_get = sub.add_parser("get", help="Get a single voice by ID")
    p_get.add_argument("--voice-id", required=True, help="Voice ID (voice_xxx)")

    # Common
    for sp in [p_create, p_list, p_get]:
        sp.add_argument("--config", default=None)
        sp.add_argument("--api-key", default=None)
        sp.add_argument("--base-url", default=None)
        sp.add_argument("--timeout", type=int, default=30)
        sp.add_argument("--dry-run", action="store_true")
        sp.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)
    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)

    if not args.dry_run and not api_key:
        print("[ERROR] BOSON_API_KEY is required", file=sys.stderr)
        return 1

    client = BosonClient(api_key or "dry-run-key", base_url, timeout=args.timeout)

    if args.command == "create":
        return cmd_create(args, config, client)
    elif args.command == "list":
        return cmd_list(args, config, client)
    elif args.command == "get":
        return cmd_get(args, config, client)
    else:
        print(f"[ERROR] unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

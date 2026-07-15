#!/usr/bin/env python3
"""Check whether local Boson AI rules are in sync with official docs.

Uses Boson's llms.txt → .md sources and openapi.json to verify:
  1. TTS preset voices list
  2. TTS / Avatar model IDs
  3. Response format options
  4. Video size options

Exit codes: 0=no issues, 1=WARNING/CRITICAL (with --fail-on), 2=couldn't complete.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boson_common import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_CONFIG,
    DEFAULT_DOC_CACHE_DIR,
    DEFAULT_KNOWN_RULES,
    DocCache,
    PROJECT_ROOT,
    SKILL_ROOT,
    fetch_text,
    load_config,
    resolve_api_key,
    resolve_base_url,
)

CRITICAL = "CRITICAL"
WARNING = "WARNING"
INFO = "INFO"
_SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}


def extract_tts_rules(md_text: str) -> Dict[str, Any]:
    """Extract preset voices from TTS voices doc."""
    # Preset voices appear as `voice_name` in the voice table.
    # Known stable set — avoids false positives from table headers.
    voice_pattern = re.compile(r"`(chloe|eleanor|jake|marcus|nora|oliver|default|berlinda)`")
    voices = sorted(set(m.group(1) for m in voice_pattern.finditer(md_text)))
    return {"preset_voices": voices}


def extract_openapi_rules(openapi_text: str) -> Dict[str, Any]:
    """Extract model IDs, formats, sizes from openapi.json text."""
    data = json.loads(openapi_text)
    schemas = data.get("components", {}).get("schemas", {})

    # TTS model enum
    speech_schema = schemas.get("CreateSpeechRequest", {})
    model_prop = speech_schema.get("properties", {}).get("model", {})
    tts_models = model_prop.get("enum", ["higgs-tts-3"]) if isinstance(model_prop, dict) else ["higgs-tts-3"]

    # Response format enum
    fmt_prop = speech_schema.get("properties", {}).get("response_format", {})
    formats = fmt_prop.get("enum", []) if isinstance(fmt_prop, dict) else []

    # Video model enum + sizes
    video_schema = schemas.get("CreateVideoRequest", {})
    video_model_prop = video_schema.get("properties", {}).get("model", {})
    avatar_models = video_model_prop.get("enum", ["higgs-avatar"]) if isinstance(video_model_prop, dict) else ["higgs-avatar"]
    size_prop = video_schema.get("properties", {}).get("size", {})
    sizes = size_prop.get("enum", []) if isinstance(size_prop, dict) else []

    return {
        "tts_models": tts_models,
        "tts_formats": formats,
        "avatar_models": avatar_models,
        "video_sizes": sizes,
    }


def _diff_lists(name: str, local: list, remote: list, section: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    local_set, remote_set = set(local), set(remote)
    for item in sorted(local_set - remote_set):
        issues.append({"severity": WARNING, "section": section,
                        "message": f"{name} '{item}' in local rules but NOT in official docs. May be removed/renamed."})
    for item in sorted(remote_set - local_set):
        issues.append({"severity": INFO, "section": section,
                        "message": f"{name} '{item}' in official docs but not in local rules. Consider adding."})
    return issues


def check_docs(known_rules: Dict[str, Any], cache: DocCache, ttl_hours: float, force_refresh: bool) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    issues: List[Dict[str, str]] = []
    extracted: Dict[str, Any] = {}
    urls = known_rules.get("source_urls", {})

    # OpenAPI spec (authoritative for model IDs, formats, sizes)
    openapi_url = urls.get("openapi_json")
    if openapi_url:
        text = cache.get(openapi_url, ttl_hours) if not force_refresh else None
        if text is None:
            try:
                text = fetch_text(openapi_url)
                cache.set(openapi_url, text)
            except Exception as exc:
                issues.append({"severity": WARNING, "section": "openapi", "message": f"Could not fetch openapi.json: {exc}"})
                text = ""
        if text:
            try:
                remote = extract_openapi_rules(text)
                extracted.update(remote)
                local = known_rules.get("tts", {})
                issues += _diff_lists("TTS model", local.get("models", []), remote.get("tts_models", []), "tts")
                issues += _diff_lists("TTS format", local.get("formats", []), remote.get("tts_formats", []), "tts")
                local_avatar = known_rules.get("avatar", {})
                issues += _diff_lists("Avatar model", local_avatar.get("models", []), remote.get("avatar_models", []), "avatar")
                issues += _diff_lists("Video size", local_avatar.get("sizes", []), remote.get("video_sizes", []), "avatar")
            except Exception as exc:
                issues.append({"severity": WARNING, "section": "openapi", "message": f"Could not parse openapi.json: {exc}"})

    # Voices doc (preset voice names)
    voices_url = urls.get("voices_md")
    if voices_url:
        text = cache.get(voices_url, ttl_hours) if not force_refresh else None
        if text is None:
            try:
                text = fetch_text(voices_url)
                cache.set(voices_url, text)
            except Exception as exc:
                issues.append({"severity": WARNING, "section": "voices", "message": f"Could not fetch voices doc: {exc}"})
                text = ""
        if text:
            remote = extract_tts_rules(text)
            extracted["preset_voices"] = remote.get("preset_voices", [])
            local = known_rules.get("tts", {})
            issues += _diff_lists("Preset voice", local.get("preset_voices", []), remote.get("preset_voices", []), "tts")

    return issues, extracted


def run_check(
    config: Dict[str, Any],
    args: Any,
    *,
    known_rules_path: Optional[Path] = None,
    api_key_override: Optional[str] = None,
    base_url_override: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Run the full doc check. Returns list of issues."""
    rules_path = known_rules_path or Path(config.get("known_rules_path") or DEFAULT_KNOWN_RULES)
    if not rules_path.is_absolute():
        rules_path = SKILL_ROOT / rules_path
    known_rules = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path.exists() else {}

    ttl = float(config.get("doc_check_ttl_hours", 24))
    cache_dir = config.get("doc_check_cache_dir", DEFAULT_DOC_CACHE_DIR)
    # Doc cache follows the project (CWD), not the skill package.
    if not Path(cache_dir).is_absolute():
        cache_dir = str(PROJECT_ROOT / cache_dir)
    cache = DocCache(cache_dir)
    force_refresh = bool(getattr(args, "force_refresh", False))

    issues, _ = check_docs(known_rules, cache, ttl, force_refresh)
    return issues


def has_blocking_issue(issues: List[Dict[str, str]], fail_on: str = WARNING) -> bool:
    threshold = _SEVERITY_ORDER.get(fail_on, _SEVERITY_ORDER[WARNING])
    return any(_SEVERITY_ORDER.get(i["severity"], 9) <= threshold for i in issues)


def format_text(issues: List[Dict[str, str]]) -> str:
    if not issues:
        return "[OK] Local rules match official Boson docs. No issues found."
    lines = [f"[CHECK] {len(issues)} issue(s):"]
    for issue in sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i["severity"], 9)):
        lines.append(f"  [{issue['severity']}] ({issue['section']}) {issue['message']}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check Boson AI local rules vs official docs")
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--known-rules", default=str(DEFAULT_KNOWN_RULES))
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument("--format", default="text", choices=["text", "json"])
    p.add_argument("--fail-on", default="warning", choices=["critical", "warning"])
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    config = load_config(args.config)
    rules_path = Path(args.known_rules) if args.known_rules else DEFAULT_KNOWN_RULES
    issues = run_check(config, args, known_rules_path=rules_path)

    if args.format == "json":
        print(json.dumps({"issues": issues, "counts": {
            "critical": sum(1 for i in issues if i["severity"] == CRITICAL),
            "warning": sum(1 for i in issues if i["severity"] == WARNING),
            "info": sum(1 for i in issues if i["severity"] == INFO),
        }}, ensure_ascii=False, indent=2))
    else:
        print(format_text(issues))

    fail_on = "critical" if args.fail_on == "critical" else "warning"
    return 1 if has_blocking_issue(issues, fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())

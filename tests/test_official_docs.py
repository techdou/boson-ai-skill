import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import boson_common as common
import check_official_docs as checker


class BosonDocCheckTests(unittest.TestCase):
    def test_cli_fail_on_critical(self):
        for severity, expected in (("WARNING", 0), ("critical", 1)):
            with self.subTest(severity=severity), patch.object(
                checker, "run_check", return_value=[{
                    "severity": severity, "section": "docs", "message": "test issue",
                }],
            ), patch.object(checker, "load_config", return_value={}), patch.object(
                sys, "argv", ["check_official_docs.py", "--fail-on", "critical"],
            ), redirect_stdout(io.StringIO()):
                self.assertEqual(checker.main(), expected)

    def test_missing_model_enum_is_not_backfilled(self):
        rules = {
            "source_urls": {"openapi_json": "https://example.invalid/openapi.json"},
            "tts": {"models": ["higgs-tts-3"], "formats": ["mp3"]},
            "avatar": {"models": ["higgs-avatar"], "sizes": ["640x640"]},
        }
        for model_prop in ({}, {"enum": []}, {"enum": "higgs-tts-3"}, {"enum": [None]}):
            spec = {"components": {"schemas": {
                "CreateSpeechRequest": {"properties": {
                    "model": model_prop, "response_format": {"enum": ["mp3"]},
                }},
                "CreateVideoRequest": {"properties": {
                    "model": {"default": "higgs-avatar"}, "size": {"enum": ["640x640"]},
                }},
            }}}
            with self.subTest(model_prop=model_prop), patch.object(
                checker, "fetch_text", return_value=json.dumps(spec),
            ):
                issues, extracted = checker.check_docs(rules, Mock(), 24, True)
                self.assertEqual(extracted["tts_models"], [])
                self.assertEqual(extracted["avatar_models"], [])
                self.assertEqual([issue["severity"] for issue in issues], ["WARNING", "WARNING"])
                self.assertTrue(all("Could not verify" in issue["message"] for issue in issues))
                self.assertFalse(checker.has_blocking_issue(issues, "critical"))
                self.assertTrue(checker.has_blocking_issue(issues, "warning"))

    def test_extracts_presets_from_samples_and_model_note_not_examples(self):
        doc = '''## Preset voices
zoe
<audio src="https://docs.boson.ai/public/audio/higgs-audio-tts-voices/v3.1/zoe_intro.mp3" />
> `adam`, `alex`, and `chloe` are built into Higgs TTS 3.1 and work only with `higgs-tts-3.1`.
    "voice": "example"
## Reference voice
<audio src="https://docs.boson.ai/public/audio/sample_intro.mp3" />
'''
        self.assertEqual(checker.extract_tts_rules(doc)["preset_voices"], ["adam", "alex", "chloe", "zoe"])

    def test_missing_dotenv_loader_is_not_silent(self):
        with patch.dict(sys.modules, {"dotenv": None}), patch.object(
            Path, "is_file", return_value=True,
        ), self.assertWarnsRegex(RuntimeWarning, "python-dotenv.*not installed"):
            common._load_skill_env()

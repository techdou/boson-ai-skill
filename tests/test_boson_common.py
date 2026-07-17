#!/usr/bin/env python3
"""Unit tests for boson-ai-skill.

Covers the pure (non-network) helpers in boson_common.py and
boson_avatar_video.py: path resolution, data-URI encoding, retry
behavior, doc cache, file safety, and the text-to-video fallback
signature matcher.

Run: python -m unittest discover -s tests -v
"""
import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Make scripts importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import boson_common as bc  # noqa: E402
import boson_avatar_video as bav  # noqa: E402


class TestResolveOutputDir(unittest.TestCase):
    """resolve_output_dir must send relative paths to CWD, not SKILL_ROOT."""

    def test_relative_path_goes_to_cwd(self):
        result = bc.resolve_output_dir("output/audio/x.mp3")
        self.assertEqual(result, bc.PROJECT_ROOT / "output" / "audio" / "x.mp3")

    def test_absolute_path_passes_through(self):
        abs_path = os.path.abspath("/tmp/some/abs/path.mp3") if os.name != "nt" else "C:/tmp/abs.mp3"
        result = bc.resolve_output_dir(abs_path)
        self.assertEqual(result, Path(abs_path))

    def test_does_not_use_skill_root_for_relative(self):
        """Regression guard: relative paths must NOT land inside the skill package."""
        result = bc.resolve_output_dir("output/audio/x.mp3")
        self.assertNotIn(".agents/skills/boson-ai-skill", str(result))


class TestFileToDataUri(unittest.TestCase):
    """file_to_data_uri must base64-encode with a MIME prefix and reject oversize."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.tmp.write(b"fake-audio-bytes")
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_basic_encoding(self):
        uri = bc.file_to_data_uri(Path(self.tmp.name))
        self.assertTrue(uri.startswith("data:audio/wav;base64,"))
        # Decodable
        import base64
        encoded = uri.split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), b"fake-audio-bytes")

    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):
            bc.file_to_data_uri(Path(self.tmp.name), max_bytes=4)  # payload is 16 bytes


class TestWriteBytes(unittest.TestCase):
    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "deep" / "nested" / "f.bin"
            bc.write_bytes(out, b"hello")
            self.assertEqual(out.read_bytes(), b"hello")


class TestBosonAPIError(unittest.TestCase):
    def test_preserves_status_and_retry_after(self):
        err = bc.BosonAPIError(429, "rate limited", retry_after=1.5)
        self.assertEqual(err.status_code, 429)
        self.assertEqual(err.retry_after, 1.5)
        self.assertIn("429", str(err))


class TestWithRetries(unittest.TestCase):
    """with_retries should retry on 429/5xx and give up on 4xx non-retryable."""

    def test_success_first_try(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        self.assertEqual(bc.with_retries(fn, retries=2), "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_on_429(self):
        # Avoid real sleep
        with patch("boson_common.time.sleep"):
            calls = []
            def fn():
                calls.append(1)
                if len(calls) < 2:
                    raise bc.BosonAPIError(429, "busy")
                return "ok"
            self.assertEqual(bc.with_retries(fn, retries=2), "ok")
            self.assertEqual(len(calls), 2)

    def test_does_not_retry_on_400(self):
        with patch("boson_common.time.sleep"):
            calls = []
            def fn():
                calls.append(1)
                raise bc.BosonAPIError(400, "bad request")
            with self.assertRaises(bc.BosonAPIError):
                bc.with_retries(fn, retries=3)
            self.assertEqual(len(calls), 1)  # not retried


class TestDocCache(unittest.TestCase):
    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as d:
            cache = bc.DocCache(d)
            cache.set("https://example.com/a", "hello world")
            self.assertEqual(cache.get("https://example.com/a"), "hello world")

    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            cache = bc.DocCache(d)
            self.assertIsNone(cache.get("https://example.com/never-set"))

    def test_ttl_expires(self):
        with tempfile.TemporaryDirectory() as d:
            cache = bc.DocCache(d)
            cache.set("https://example.com/a", "hello")
            # Backdate the file so it's older than the TTL.
            p = cache._path_for("https://example.com/a")
            old_mtime = time.time() - 3600 * 48  # 48h ago
            os.utime(p, (old_mtime, old_mtime))
            self.assertIsNone(cache.get("https://example.com/a", ttl_hours=24))


class TestIsT2VServerBug(unittest.TestCase):
    """The fallback signature matcher must catch the known Boson bug wording
    variants but not flag unrelated errors."""

    def test_observed_wording(self):
        self.assertTrue(bav.is_t2v_server_bug(
            "video failed: internal error: 'ascii' codec can't encode character '\\u201c'"
        ))

    def test_case_insensitive(self):
        self.assertTrue(bav.is_t2v_server_bug("Codec Can't Encode something"))
        self.assertTrue(bav.is_t2v_server_bug("UNICODEDECODEERROR while parsing"))

    def test_input_tts_field_mentioned(self):
        # Last-resort signature: any error mentioning the t2v field itself.
        self.assertTrue(bav.is_t2v_server_bug("input_tts field rejected by gateway"))

    def test_unrelated_error_not_matched(self):
        self.assertFalse(bav.is_t2v_server_bug("ref_image too large"))
        self.assertFalse(bav.is_t2v_server_bug("audio_too_long"))
        self.assertFalse(bav.is_t2v_server_bug(""))

    def test_empty_returns_false(self):
        self.assertFalse(bav.is_t2v_server_bug(""))


class TestResolveRefImageAndAudio(unittest.TestCase):
    """_resolve_ref_image / _resolve_input_audio must turn local files into
    data URIs and pass URLs through unchanged."""

    def test_url_passes_through(self):
        url = "https://example.com/face.jpg"
        self.assertEqual(bav._resolve_ref_image(url), url)
        self.assertEqual(bav._resolve_input_audio(url), url)

    def test_local_file_becomes_data_uri(self):
        # On Windows, NamedTemporaryFile keeps a handle open until GC. Write to a
        # manually-managed path instead so we can reliably close+unlink.
        tmpdir = tempfile.mkdtemp()
        try:
            p = Path(tmpdir) / "ref.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\nfakepng")
            uri = bav._resolve_ref_image(str(p))
            self.assertTrue(uri.startswith("data:"))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

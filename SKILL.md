---
name: boson-ai-skill
version: 1.1.0
description: Generate speech audio and talking-head avatar videos with Boson AI (Higgs TTS 3 + Higgs Avatar). Use whenever the user wants text-to-speech in 100+ languages, voice cloning, emotion/style-controlled narration, avatar/digital-human video, or anything involving the Boson AI API — even if they don't say "Boson" explicitly. Covers preset voices (chloe/eleanor/jake/marcus/nora/oliver), inline emotion tags, reference-audio cloning, reusable voice registration, audio-to-video, text-to-video, and streaming fMP4.
---

# Boson AI Skill

Use this Skill when the user wants to generate **audio** (text-to-speech, voice cloning, narration) or **video** (talking-head avatar / digital human) using the Boson AI API. The core models are:

- **Higgs TTS 3** — chat-native TTS with 102 languages, instant voice cloning, inline emotion/style/sound-effect tags.
- **Higgs Avatar** — talking-head video from a single still photo + driving audio or text.

## Progressive disclosure rule

Do not run the full pipeline by default. Choose the smallest script for the task:

- **Synthesize speech from text**: `scripts/boson_tts.py` (single text or batch segments)
- **Clone a voice from reference audio** (one-off): `scripts/boson_tts.py --ref-audio <file> --ref-text <transcript>`
- **Register a reusable cloned voice**: `scripts/boson_voice_manager.py create`
- **List or inspect saved voices**: `scripts/boson_voice_manager.py list` / `get`
- **Generate avatar video**: `scripts/boson_avatar_video.py` (audio-driven or text-driven)
- **Check if local rules match official docs**: `scripts/check_official_docs.py`

## Quick setup

```bash
export BOSON_API_KEY="bai-你的key"
```

Windows PowerShell:

```powershell
$env:BOSON_API_KEY="bai-你的key"
```

## Output directory policy

Generated audio, video, manifests, and doc-cache are written to **the current project's `output/` directory** (i.e. `$CWD/output/`), not inside the skill package. This means each project session gets its own isolated output. Skill-internal resources (config templates, known_rules, examples) are still read from the skill directory. To override, pass an absolute path with `--output` / `--out-dir`.

## Core capability 1: TTS (text-to-speech)

### Single text → audio file

```bash
python scripts/boson_tts.py \
  --text "Hello, welcome to the course." \
  --voice chloe \
  --output output/audio/welcome.mp3
```

### Batch from segments JSON

```bash
python scripts/boson_tts.py \
  --segments output/segments.json \
  --out-dir output/audio \
  --manifest output/audio_manifest.json
```

Segments JSON format:

```json
[
  {"text": "First segment text.", "voice": "chloe", "title": "intro"},
  {"text": "Second segment text.", "voice": "oliver", "title": "body"}
]
```

### Voice cloning (one-off, inline)

```bash
python scripts/boson_tts.py \
  --text "This will sound like the reference speaker." \
  --ref-audio sample.wav \
  --ref-text "Transcript of sample.wav" \
  --output output/audio/cloned.mp3
```

### Streaming PCM (low latency)

```bash
python scripts/boson_tts.py --text "Hello" --voice chloe --stream --output output/audio/stream.wav
```

### Preset voices

| Voice | Style | Gender |
|---|---|---|
| `chloe` | Friendly, clear, engaging, American | Female |
| `eleanor` | Calm, articulate, professional, educational | Female |
| `jake` | Energetic, dramatic, passionate | Male |
| `marcus` | Enthusiastic, confident, professorial | Male |
| `nora` | Calm, clear, narrative | Female |
| `oliver` | Calm, articulate, thoughtful, reflective | Male |
| `default` | Platform default voice | — |

### Inline tags (emotion / style / sfx / prosody)

Tags go **inside** the `--text` value. Lead with delivery tags; positional tags (pause, sfx) go where they should occur.

```bash
# Emotion + sound effect
python scripts/boson_tts.py \
  --text "<|emotion:enthusiasm|>Welcome to the show! <|sfx:laughter|>Haha, let's go!" \
  --voice jake --output excited.mp3

# Speed control + pause
python scripts/boson_tts.py \
  --text "<|prosody:speed_slow|>Let me explain slowly.<|prosody:pause|> One step at a time." \
  --voice eleanor --output slow.mp3
```

Tag categories:
- **emotion**: elation, amusement, enthusiasm, determination, pride, contentment, affection, relief, contemplation, confusion, surprise, awe, longing, anger, fear, disgust, bitterness, sadness, shame, helplessness, arousal
- **style**: singing, shouting, whispering
- **sfx**: cough, laughter, crying, screaming, burping, humming, sigh, sniff, sneeze
- **prosody**: speed_very_slow (~0.65×), speed_slow (~0.85×), speed_fast (~1.2×), speed_very_fast (~1.4×), pitch_low (~−3st), pitch_high (~+2.5st), pause (~400-700ms), long_pause (~700-1500ms), expressive_high, expressive_low

Full tag reference: load `docs/tts_tags.md` when you need the complete list with examples.

## Core capability 2: Voice management (reusable cloning)

Register a reference voice once, get a stable `voice_<sha256>` ID, reuse it across requests without re-uploading audio.

```bash
# Register
python scripts/boson_voice_manager.py create \
  --ref-audio sample.wav \
  --ref-text "Transcript of the sample audio" \
  --description "My custom voice"

# List all registered voices
python scripts/boson_voice_manager.py list

# Get one voice's details
python scripts/boson_voice_manager.py get --voice-id voice_abc123
```

Then use the returned voice ID with TTS:

```bash
python scripts/boson_tts.py --text "Hello" --voice voice_abc123 --output out.mp3
```

## Core capability 3: Avatar video (talking-head)

### Audio-to-video (animate a photo with driving audio)

```bash
python scripts/boson_avatar_video.py \
  --ref-image face.jpg \
  --input speech.mp3 \
  --output output/video/avatar.mp4
```

### Text-to-video (synthesize voice + animate in one request)

```bash
python scripts/boson_avatar_video.py \
  --ref-image face.jpg \
  --tts-text "Hello, I'm a digital avatar." \
  --tts-voice chloe \
  --output output/video/avatar.mp4
```

### Streaming (live fMP4, playback starts immediately)

```bash
python scripts/boson_avatar_video.py \
  --ref-image face.jpg \
  --tts-text "Hello world" \
  --stream \
  --output output/video/stream.mp4
```

### Video params

- **size**: `640x640` (square, default), `640x480` (landscape), `480x640` (portrait)
- **input audio**: max 60 seconds (sets video length)
- **ref_image**: PNG/JPEG/WEBP, max 10 MB
- **--create-only**: just submit the job and print video_id without waiting
- **--no-fallback**: disable auto-fallback from text-to-video to TTS+audio-to-video

### Text-to-video auto-fallback

Boson's Higgs Avatar is in public preview. The `input_tts` (text-to-video) mode has a known server-side encoding bug that causes failures. When detected, this skill **automatically falls back** to a two-step approach: TTS synthesizes audio first, then audio-to-video generates the video. You see `[FALLBACK]` messages in the log when this happens. Use `--no-fallback` to disable.

## Self-update guard

This skill checks itself against official Boson AI docs (`openapi.json` + `.md` sources) before synthesis. Default non-blocking; use `--check-docs` to enforce, `--skip-check` to bypass.

```bash
# Manual check
python scripts/check_official_docs.py

# Force refresh cache
python scripts/check_official_docs.py --force-refresh
```

## Languages

Higgs TTS 3 auto-detects language from input text — **no language parameter needed**. Supports 102 languages including Chinese, English, Japanese, Korean, French, German, Spanish, Arabic, Hindi, Vietnamese, Thai, and more. For accents, use a reference clip with the target accent.

## Details

Load deeper docs only when needed:

- `docs/tts_tags.md` — complete inline tag reference (emotions, styles, sfx, prosody)
- `docs/api_rules.md` — model IDs, endpoints, format limits, error codes
- `docs/self_update.md` — how the official-doc sync mechanism works
- `docs/troubleshooting.md` — common errors and fixes

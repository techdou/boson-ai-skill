# Boson AI Skill

A [ZCode](https://zcode.ai) / Claude Code / OpenCode agent skill for [Boson AI](https://boson.ai)'s **Higgs TTS 3** and **Higgs Avatar** models. Generate speech in 102 languages, clone voices, create talking-head avatar videos — all from the command line.

## Features

**Higgs TTS 3 — Text-to-Speech**
- 102 languages with single-digit WER/CER (Chinese, English, Japanese, Korean, Thai, Vietnamese, French, German, Spanish, Arabic, Hindi, and more)
- 6 preset voices + instant voice cloning from reference audio
- Inline emotion / style / sound-effect / prosody tags for fine-grained control
- Streaming PCM for low-latency output
- Batch synthesis from segments JSON

**Higgs Avatar — Talking-Head Video**
- Animate a still photo with driving audio (audio-to-video)
- Or synthesize voice + animate in one request (text-to-video)
- Streaming fMP4 for real-time playback
- Auto-fallback when text-to-video hits the known server-side bug

**Self-Update Guard**
- Runtime check against Boson's official `openapi.json` and `.md` docs
- Detects model deprecation, voice list changes, and parameter drift
- 24h cache, non-blocking by default

## Quick Start

### Prerequisites

- Python 3.9+
- `requests` library: `pip install requests`
- A Boson AI API key (`bai-...`) from [boson.ai](https://boson.ai)

### Install

Clone this repo into your agent skills directory:

```bash
# For ZCode / Claude Code / OpenCode
git clone https://github.com/techdou/boson-ai-skill.git ~/.agents/skills/boson-ai-skill
```

### Set API Key

```bash
export BOSON_API_KEY="bai-your-key-here"
```

Windows PowerShell:

```powershell
$env:BOSON_API_KEY="bai-your-key-here"
```

### Generate Your First Speech

```bash
cd ~/.agents/skills/boson-ai-skill

python scripts/boson_tts.py \
  --text "Hello, welcome to Boson AI." \
  --voice chloe \
  --output output/welcome.mp3
```

Audio is saved to the **current project's** `output/` directory.

## Usage

### Text-to-Speech

```bash
# Single text
python scripts/boson_tts.py --text "你好世界" --voice chloe --output hello.mp3

# Batch from segments JSON
python scripts/boson_tts.py --segments examples/segments.sample.json --out-dir output/audio

# Voice cloning (one-off)
python scripts/boson_tts.py --text "Hello" --ref-audio sample.wav --ref-text "transcript" --output cloned.mp3

# Streaming PCM
python scripts/boson_tts.py --text "Hello" --stream --output stream.wav
```

### Preset Voices

| Voice | Style | Gender |
|---|---|---|
| `chloe` | Friendly, clear, engaging | Female |
| `eleanor` | Calm, articulate, educational | Female |
| `jake` | Energetic, dramatic, passionate | Male |
| `marcus` | Enthusiastic, confident, professorial | Male |
| `nora` | Calm, narrative | Female |
| `oliver` | Thoughtful, reflective | Male |

### Inline Tags

Control emotion, style, sound effects, and prosody directly in the text:

```bash
python scripts/boson_tts.py \
  --text "<|emotion:enthusiasm|>Welcome! <|sfx:laughter|>Haha, let's go! <|prosody:speed_slow|>One step at a time." \
  --voice jake --output tagged.mp3
```

Full tag reference: [`docs/tts_tags.md`](docs/tts_tags.md)

### Voice Management

Register a reusable cloned voice to avoid re-uploading reference audio:

```bash
python scripts/boson_voice_manager.py create --ref-audio sample.wav --ref-text "transcript"
python scripts/boson_voice_manager.py list
python scripts/boson_voice_manager.py get --voice-id voice_abc123
```

### Avatar Video

```bash
# Audio-to-video: animate a photo with driving audio
python scripts/boson_avatar_video.py --ref-image face.jpg --input speech.wav --output avatar.mp4

# Text-to-video: synthesize voice + animate (auto-fallback if server bug hit)
python scripts/boson_avatar_video.py --ref-image face.jpg --tts-text "Hello world" --tts-voice chloe --output avatar.mp4

# Streaming
python scripts/boson_avatar_video.py --ref-image face.jpg --tts-text "Hello" --stream --output stream.mp4
```

## Output Directory Policy

Generated files (audio, video, manifests) are written to **the current project's `output/` directory** (`$CWD/output/`), not inside the skill package. Each project session gets isolated outputs. Override with `--output` / `--out-dir` using an absolute path.

## Project Structure

```
boson-ai-skill/
├── SKILL.md                         # Agent routing + quick reference
├── README.md                        # This file
├── scripts/
│   ├── boson_common.py              # API client, config, doc cache
│   ├── boson_tts.py                 # TTS synthesis (single/batch/stream/clone)
│   ├── boson_voice_manager.py       # Voice registration/list/get
│   ├── boson_avatar_video.py        # Avatar video (async/stream/fallback)
│   └── check_official_docs.py       # Self-update doc sync check
├── templates/
│   ├── config.example.json          # Default configuration
│   └── known_rules.json             # Official rules snapshot (diff baseline)
├── examples/
│   └── segments.sample.json         # Batch TTS example
└── docs/
    ├── api_rules.md                 # API endpoints, params, error codes
    ├── tts_tags.md                  # Inline tag reference
    ├── self_update.md               # Self-update mechanism design
    └── troubleshooting.md           # Common errors and fixes
```

## Configuration

Copy `templates/config.example.json` to your project root as `boson_config.json` to override defaults:

```json
{
  "default_voice": "chloe",
  "default_tts_format": "mp3",
  "doc_check_enabled": true,
  "doc_check_ttl_hours": 24
}
```

Config priority: `--config` flag > `$CWD/boson_config.json` > skill template.

## Self-Update Guard

The skill checks itself against Boson's official documentation before synthesis:

```bash
# Manual check
python scripts/check_official_docs.py

# Force refresh
python scripts/check_official_docs.py --force-refresh
```

Default behavior is non-blocking (advisory only). See [`docs/self_update.md`](docs/self_update.md) for details.

## Requirements

- Python ≥ 3.9
- [requests](https://pypi.org/project/requests/) (`pip install requests`)
- [Boson AI API key](https://boson.ai)

## License

MIT

## Acknowledgments

- [Boson AI](https://boson.ai) for the Higgs TTS 3 and Higgs Avatar models
- API docs: [https://docs.boson.ai](https://docs.boson.ai)

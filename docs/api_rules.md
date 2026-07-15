# Boson AI API Rules (snapshot 2026-07-15)

> **官方文档**: https://docs.boson.ai/api-reference/
> **OpenAPI Spec**: https://docs.boson.ai/openapi.json
> **LLM index**: https://docs.boson.ai/llms.txt
>
> 运行 `python scripts/check_official_docs.py` 可自动对比本地规则与官方文档。

## 认证

- Header: `Authorization: Bearer $BOSON_API_KEY`
- Key 格式: `bai-...`

## TTS: POST /v1/audio/speech

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `input` | string (必填) | — | 要合成的文本,可含 inline tags,最长 5000 字符 |
| `model` | enum | `higgs-tts-3` | TTS 模型 ID |
| `voice` | string | `default` | 预设音色名或自定义 voice ID;与 ref_audio/ref_text 互斥 |
| `response_format` | enum | `mp3` | `mp3`/`wav`/`pcm`/`opus`/`aac`/`flac`;流式必须是 `pcm` |
| `stream` | boolean | `false` | 流式返回 PCM chunk |
| `ref_audio` | string\|null | — | 一次性克隆:URL / data URI / base64;≤10MB |
| `ref_text` | string\|null | — | ref_audio 的推荐转写文本 |

## Voice 管理

### POST /v1/audio/voices — 注册可复用音色

| 参数 | 必填 | 说明 |
|---|---|---|
| `ref_audio` | 是 | 参考音频:URL/data URI/base64,≤10MB,≥3.0s |
| `ref_text` | 是 | 参考音频转写文本 |
| `description` | 否 | 描述 |

返回 `VoiceObject`:`{voice: "voice_<sha256>", ref_text, description?, created_at?}`。相同音频 + 相同 key 注册返回同一 ID。

### GET /v1/audio/voices — 列出音色

返回当前 API key 下所有注册的音色。

### GET /v1/audio/voices/{voice_id} — 获取单个音色

## Avatar Video

### POST /v1/videos — 创建数字人视频(异步)

| 参数 | 必填 | 说明 |
|---|---|---|
| `ref_image` | 是 | 人脸照片:URL/data URI/base64;PNG/JPEG/WEBP,≤10MB |
| `input` | 二选一 | audio-to-video:驱动音频,≤60s |
| `input_tts` | 二选一 | text-to-video:speech request JSON(同 TTS body,不支持 stream) |
| `model` | — | `higgs-avatar`(默认) |
| `size` | — | `640x640`(默认)/ `640x480` / `480x640` |

返回 `VideoObject`:`{id, object: "video", model, status, progress, size, created_at, error?}`。

状态流转:`queued → in_progress → completed | failed`

### GET /v1/videos/{video_id} — 轮询状态

### GET /v1/videos/{video_id}/content — 下载 MP4

`status=completed` 后可下载,否则 404。

### POST /v1/videos/stream — 流式视频

同 `/v1/videos` body,但响应体是 live fMP4 字节流。video_id 在 `X-Video-Id` 响应头里。

## 错误码

| HTTP | type | 含义 |
|---|---|---|
| 400 | `input_too_long` | TTS 输入超 5000 字符 |
| 400 | `invalid_image_format` / `invalid_size` / `audio_too_long` / `empty_input` | 视频参数错误 |
| 401 | — | API key 缺失/无效 |
| 404 | `model_not_found` | 未知模型 ID |
| 413 | `payload_too_large` | inline 数据超 10MB |
| 422 | — | body 格式错误(如 input/input_tts 都传或都不传) |
| 429 | `all_replicas_busy` | 限流或服务繁忙;看 `Retry-After` 头 |

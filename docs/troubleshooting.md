# Troubleshooting

## `BOSON_API_KEY is required`

设置环境变量:

```bash
export BOSON_API_KEY="bai-你的key"
```

或传参:`--api-key "bai-xxx"`。

## `400 input_too_long`

TTS `input` 超过 5000 字符。拆分成多段,用 `--segments` 批量模式。

## `422` (video: neither or both of input / input_tts)

Avatar video 必须提供**恰好一个**驱动输入:
- `--input`(audio-to-video)或
- `--tts-text`(text-to-video)

不能两个都传,也不能都不传。

## `413 payload_too_large`

inline 的 `ref_image` 或 `ref_audio` base64 后超 10MB。用 URL 传入代替 inline base64,或压缩文件。

## `429 all_replicas_busy`

服务繁忙。脚本会读 `Retry-After` 头自动重试。如仍频繁触发,增大 `--sleep-between`。

## Text-to-video 报 `codec can't encode` 错误

这是 Boson Higgs Avatar public preview 的**已知服务端 bug**——`input_tts`（text-to-video）模式处理文本时触发 ascii 编码错误。连官方示例图 + 纯英文文本也会复现。

**我们的 skill 已内置自动 fallback**：检测到这个错误后，自动转成"TTS 生成音频 → audio-to-video 生成视频"两步走。你会在日志里看到 `[FALLBACK]` 标记。

如果你想手动控制：
- 直接用 audio-to-video 模式：`--input audio.wav`（绕过 bug）
- 禁用自动 fallback：`--no-fallback`（失败就报错，不自动转）

## Video 一直 `queued` 不变

检查:
- `ref_image` 是清晰的人脸正面照
- `input` 音频不超过 60 秒
- `--max-wait` 是否太短(默认 300s,复杂视频可能需要更久)

## Cloned voice 效果差

- `ref_audio` 至少 3 秒,清晰无背景噪音
- `ref_text` 必须是 `ref_audio` 的准确转写
- 频繁使用建议先 `boson_voice_manager.py create` 注册,拿稳定 voice ID 复用

## TTS 输出有杂音或断续

- 非 streaming 模式更稳定,优先用默认模式
- streaming 模式输出 PCM,脚本写入 WAV 容器;如果手动处理注意是 24kHz 16-bit mono
- 某些 tag 组合可能产生不自然效果,简化 tag 试试

## `RequestsDependencyWarning`

Python 环境的 `urllib3` / `charset_normalizer` 版本跟 `requests` 不完全匹配。这只是警告,不影响功能。要消除:

```bash
pip install --upgrade requests urllib3 charset-normalizer
```

# TTS Inline Tags Reference

Higgs TTS 3 的 inline tag 系统让你在 `input` 文本里直接控制情感、风格、音效和韵律。tag 格式统一为 `<|category:value|>`。

## 使用原则

- **delivery tag 放开头**:emotion/style/speed/pitch/expressiveness 影响整段,放在文本起始处。
- **positional tag 放具体位置**:`<|prosody:pause|>` 和 `<|sfx:...|>` 放在应该生效的位置。
- **sfx 配合拟声词**:`<|sfx:laughter|>Haha` 效果比单独 `<|sfx:laughter|>` 好。

## Emotion `<|emotion:...|>`

| Tag | 效果 |
|---|---|
| `<\|emotion:elation\|>` | 狂喜 |
| `<\|emotion:amusement\|>` | 觉得好笑 |
| `<\|emotion:enthusiasm\|>` | 热情兴奋 |
| `<\|emotion:determination\|>` | 坚定 |
| `<\|emotion:pride\|>` | 自豪自信 |
| `<\|emotion:contentment\|>` | 平静满足 |
| `<\|emotion:affection\|>` | 温暖关爱 |
| `<\|emotion:relief\|>` | 如释重负 |
| `<\|emotion:contemplation\|>` | 沉思 |
| `<\|emotion:confusion\|>` | 困惑 |
| `<\|emotion:surprise\|>` | 惊讶 |
| `<\|emotion:awe\|>` | 敬畏 |
| `<\|emotion:longing\|>` | 渴望 |
| `<\|emotion:arousal\|>` | 兴奋渴望 |
| `<\|emotion:anger\|>` | 愤怒 |
| `<\|emotion:fear\|>` | 恐惧 |
| `<\|emotion:disgust\|>` | 厌恶 |
| `<\|emotion:bitterness\|>` | 苦涩 |
| `<\|emotion:sadness\|>` | 悲伤 |
| `<\|emotion:shame\|>` | 羞愧 |
| `<\|emotion:helplessness\|>` | 无助 |

## Style `<|style:...|>`

| Tag | 效果 |
|---|---|
| `<\|style:singing\|>` | 唱歌 |
| `<\|style:shouting\|>` | 大喊 |
| `<\|style:whispering\|>` | 耳语 |

## Sound Effects `<|sfx:...|>`

音效是人声发出的(不是混入的音频素材)。

| Tag | 效果 | 配合拟声词 |
|---|---|---|
| `<\|sfx:cough\|>` | 咳嗽 | Ahem |
| `<\|sfx:laughter\|>` | 笑 | Haha |
| `<\|sfx:crying\|>` | 哭 | — |
| `<\|sfx:screaming\|>` | 尖叫 | Ah |
| `<\|sfx:burping\|>` | 打嗝 | Burp |
| `<\|sfx:humming\|>` | 哼 | Hmm |
| `<\|sfx:sigh\|>` | 叹气 | Ahh / Uh |
| `<\|sfx:sniff\|>` | 吸鼻子 | Sff |
| `<\|sfx:sneeze\|>` | 打喷嚏 | Achoo |

## Prosody `<|prosody:...|>`

| Tag | 效果 |
|---|---|
| `<\|prosody:speed_very_slow\|>` | ~0.65× 语速 |
| `<\|prosody:speed_slow\|>` | ~0.85× 语速 |
| `<\|prosody:speed_fast\|>` | ~1.2× 语速 |
| `<\|prosody:speed_very_fast\|>` | ~1.4× 语速 |
| `<\|prosody:pitch_low\|>` | ~−3 半音 |
| `<\|prosody:pitch_high\|>` | ~+2.5 半音 |
| `<\|prosody:pause\|>` | ~400-700ms 停顿(positional) |
| `<\|prosody:long_pause\|>` | ~700-1500ms 停顿(positional) |
| `<\|prosody:expressive_high\|>` | 更富表现力 |
| `<\|prosody:expressive_low\|>` | 更平淡 |

## 组合示例

```
<|emotion:enthusiasm|>Welcome everyone! <|sfx:laughter|>Haha, today is going to be amazing. <|prosody:speed_slow|>But first, let me explain the basics <|prosody:pause|> step by step.
```

```
<|emotion:sadness|><|sfx:crying|>I... I'm sorry. <|prosody:long_pause|> I tried my best, but it wasn't enough.
```

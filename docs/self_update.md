# Self-Update Guard Design

本 skill 内置运行时官方文档同步校验,防止 Boson AI API 迭代(模型下线、参数变更、音色增减)后 skill 静默失效。

## 检测原理

Boson AI 提供两个机器可读文档源:

1. **`openapi.json`** (https://docs.boson.ai/openapi.json) — OpenAPI 3.0 规范,包含所有模型的 enum 定义(模型 ID、格式、尺寸)。这是**权威来源**。
2. **`.md` 文档源** (通过 `llms.txt` 发现) — 预置音色表、tag 参考、语言列表。

`check_official_docs.py` 做两件事:

- fetch `openapi.json` → 解析 `CreateSpeechRequest.model.enum`、`response_format.enum`、`CreateVideoRequest.model.enum`、`size.enum`
- fetch voices.md → 用已知音色名正则提取音色集合
- 跟 `templates/known_rules.json` 做 diff

## 差异分级

| 级别 | 含义 | 示例 |
|---|---|---|
| CRITICAL | 本地规则里有但官方已删除 | 模型被下线 |
| WARNING | 本地规则里有但官方文档没找到 | 音色可能改名 |
| INFO | 官方有但本地没有 | 新增能力,建议跟进 |

## 运行时行为

跟 mimo skill 一致——**默认非阻断**:

| 场景 | 默认 | 可控 |
|---|---|---|
| 缓存未过期(24h TTL) | 零网络开销静默通过 | — |
| 缓存过期 | 后台刷新不阻断 | `--check-docs` 同步阻断 |
| 发现差异 | 提示但继续执行 | `--check-docs` 升级阻断 |
| check 自身出错 | 静默降级 | `--verbose` 看 |

## 怎么更新 known_rules.json

1. `python scripts/check_official_docs.py --force-refresh --format json`
2. 对照差异,确认官方文档变化
3. 编辑 `templates/known_rules.json`
4. 更新 `snapshot_date`
5. 再跑一次 check 确认零 issue

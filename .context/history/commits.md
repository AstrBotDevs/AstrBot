# Commit Decision History

> 此文件是 `commits.jsonl` 的人类可读视图，可由工具重生成。
> Canonical store: `commits.jsonl` (JSONL, append-only)

| Date | Context-Id | Commit | Summary | Decisions | Bugs | Risk |
|------|-----------|--------|---------|-----------|------|------|
| 2026-04-28 | `096607b7` | TBD | fix(provider): 修复 DeepSeek reasoning_effort 被已有值覆盖的问题并缓存配置 | reasoning_effort 直接赋值替代 setdefault；引入缓存避免重复解析和警告 | setdefault 导致 provider 配置无法覆盖已有值 | low |

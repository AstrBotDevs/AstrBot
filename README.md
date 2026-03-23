# AstrBot SDK

AstrBot 插件开发 SDK，提供 v4 runtime、worker protocol 和插件工具链。

## 安装

```bash
pip install astrbot-sdk
```

## 开发安装

```bash
# 克隆仓库后
pip install -e .

# 或使用 uv
uv sync
```

## 初始化插件

```bash
astr init demo-plugin
astr init demo-plugin --agents claude,codex,opencode
```

`astr init <name>` 会继续按原样生成插件骨架。传入 `--agents` 时，会在新插件目录下额外生成对应的项目级 agent 目录：

- Claude Code: `.claude/skills/astrbot-plugin-dev/`
- Codex: `.agents/skills/astrbot-plugin-dev/`
- OpenCode: `.opencode/skills/astrbot-plugin-dev/`

`--agents` 仅支持 `claude`、`codex`、`opencode`，使用逗号分隔；重复值会去重，非法值会直接报错。

## 目录结构

```
astrbot-sdk/
├── src/
│   └── astrbot_sdk/      # SDK 主包
├── pyproject.toml
└── README.md
```

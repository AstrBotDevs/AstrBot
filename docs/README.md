
# AstrBot
_✨ 易上手的多平台 LLM 聊天机器人及开发框架（的官方文档） ✨_

[查看文档](https://docs.astrbot.app/) ｜ [问题提交](https://github.com/AstrBotDevs/AstrBot/issues)

[AstrBot](https://github.com/AstrBotDevs/AstrBot) 是一个松耦合、异步、支持多消息平台部署、具有易用的插件系统和完善的大语言模型（LLM）接入功能的聊天机器人及开发框架。

![image](https://github.com/user-attachments/assets/48f72a71-9456-4166-bbd2-f2a6c8cd740f)

## AI Agent 文档

文档构建会自动生成以下文件，不需要手动编辑或提交：

- `/llms.txt`：面向 AI Agent 的文档索引。
- `/llms-full.txt`：中英文完整文档。
- `/llms-zh.txt`、`/llms-en.txt`：按语言拆分的完整文档。
- `/raw/zh/...md`、`/raw/en/...md`：单篇 Markdown 原文。

本地生成和测试：

```bash
pnpm run docs:generate
pnpm run docs:test
```


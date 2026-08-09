---
outline: deep
---

# 👋 I'm AstrBot

## Introduction

AstrBot is an open-source, all-in-one Agentic assistant for personal and group chats. It can be deployed across dozens of mainstream instant messaging platforms, such as QQ, Telegram, WeCom, Lark, DingTalk, and Slack. It also includes a lightweight built-in ChatUI (similar to OpenWebUI), providing reliable and extensible conversational AI infrastructure for individuals, developers, and teams. Whether you are building a personal AI companion, an intelligent customer service assistant, an automation bot, or an enterprise knowledge base, AstrBot helps you build AI applications directly inside your IM workflows.

This documentation tracks the current fork branch. When this fork diverges from upstream, the behavior documented here follows this repository.

The current branch targets Python 3.14+, uses a FastAPI Dashboard backend, and organizes platforms, providers, plugins, and Agents through explicit runtime services, lifecycle ownership, an event bus, and an ordered pipeline. Text-to-image rendering is local through Playwright Chromium rather than the removed remote rendering path.

## Documentation Overview

This documentation is divided into the following sections:

- **Deployment**: multiple ways to quickly deploy AstrBot on local machines or cloud servers.
- **Messaging Platform Integration**: integration guides for 18+ mainstream instant messaging platforms.
- **AI Provider Integration**: connect to model providers, use AstrBot's built-in Agent Runner, or integrate third-party Agent Runner services such as Dify, Coze, Alibaba Bailian, and DeerFlow.
- **Usage Guides**: practical guides for features such as plugins, tool calling, knowledge base, MCP, Skills, and Agent sandbox.

## Quick Start

- Deploy AstrBot: Start with [source deployment](/en/deploy/astrbot/cli), or use the [Docker](/en/deploy/astrbot/docker) path that builds this checkout locally.
- Connect to IM platforms: Follow the instructions to connect AstrBot to your preferred IM platforms such as Discord, Telegram, Slack, etc.
- Configure AI models: AstrBot supports various AI models. See [Connecting Model Services](/en/providers/start)

## Distribution Boundary

This fork currently publishes no independent PyPI package, GitHub release assets, desktop build, or container image. The following install sources belong to upstream AstrBot or third parties and are not builds of this branch:

- `uv tool install astrbot` and `uv tool upgrade astrbot`;
- AUR packages named after AstrBot;
- images such as `soulter/astrbot`;
- Dashboard assets from upstream releases; startup entry points neither download nor use them.

Use the current checkout for source deployments, or build the root `Dockerfile` through `compose.yml` or `compose-with-napcat.yml`. Source deployments bind the WebUI to `127.0.0.1:6185` by default. The Compose files explicitly set the container listener to `0.0.0.0` while keeping host ports on loopback; remote publishing requires `ASTRBOT_BIND_ADDRESS` plus firewall and reverse-proxy protection.

## How It Works

Platform adapters normalize inbound messages into `AstrMessageEvent`. `EventBus` selects a Pipeline from the matching config profile, then executes wake, whitelist, session-state, rate-limit, safety, preprocessing, plugin/Agent, result-decoration, and response stages in order. See [Project Architecture](/en/dev/architecture) for the startup flow, ownership boundaries, and change map.

## Notice

1. AstrBot is licensed under [AGPL-3.0-or-later](https://github.com/Xero-Team/AstrBot/blob/master/LICENSE). If you provide a modified version to users over a network, make sure you satisfy the license obligations.
2. Before using this project, please read the End User License Agreement (EULA): [End User License Agreement](https://github.com/Xero-Team/AstrBot/blob/master/EULA.md). If you do not agree to any terms of the agreement, do not use this project.

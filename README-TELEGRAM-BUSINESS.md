# Telegram Business 个人账号托管

本分支在 AstrBot `v4.30.0-beta.2`（base commit `ccd78fc5b`）基础上，新增 Telegram Business 能力：让 AI 以你的 Telegram 个人账号身份接管私聊，自动读取并回复客户消息。

## 改了什么

- 新增 Business 事件处理：
  - `business_connection`：记录连接 / 授权 / 停用状态
  - `business_message`：作为普通消息接入 AI 管线
  - `edited_business_message`：不当作新消息处理
  - `deleted_business_messages`：记录删除日志
- 复用原有消息管线（AI、人格、上下文记忆、插件、过滤器、命令），没有另起一套。
- 回复携带 `business_connection_id`，真正以个人账号身份发出。
- 会话隔离：`biz:{chat_id}:{business_connection_id}`，不同客户、不同连接互不串。
- Update 去重；连接状态持久化到 `data/telegram_business_connections.json`；失效连接自动停止回复。
- 新增配置开关 `telegram_business_enabled`（默认 `true`）。

### 改动文件

- `astrbot/core/platform/sources/telegram/tg_adapter.py`
- `astrbot/core/platform/sources/telegram/tg_event.py`
- `astrbot/core/platform/astrbot_message.py`
- `astrbot/core/config/default.py`
- `tests/fixtures/mocks/telegram.py`
- `tests/test_telegram_business.py`（新增）

## 最快部署（从拉代码到启动）

环境要求：Ubuntu 22.04+，Python 3.12，能访问 GitHub。

### 1. 拉取代码

```bash
git clone --branch feat/telegram-business git@github.com:gonglchuangl/AstrBot.git
cd AstrBot
```

已有仓库则用：

```bash
cd /path/to/AstrBot
git remote add fork git@github.com:gonglchuangl/AstrBot.git
git fetch fork feat/telegram-business
git checkout -b feat/telegram-business fork/feat/telegram-business
```

### 2. 安装环境（uv，最快）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### 3. 配置 Telegram Bot Token

启动后进 WebUI（默认 http://localhost:6185）→ 平台配置 → Telegram，填入 `telegram_token`。
（或直接编辑 `data/cmd_config.json` 中 Telegram 平台的 `telegram_token`。）

### 4. 连接你的个人账号（Business 授权，必须做）

Telegram 客户端 → 设置 → Telegram Business → 聊天机器人 → 添加你的 Bot，并授权“回复 / 读取消息”。

### 5. 启动

开发 / 前台：

```bash
uv run python main.py
```

生产 / 守护（nohup）：

```bash
cd /path/to/AstrBot
nohup .venv/bin/python -u main.py >> astrbot.log 2>&1 &
```

宝塔（Python 项目）：
项目命令填 `/path/to/AstrBot/.venv/bin/python -u /path/to/AstrBot/main.py`。

### 6. 验证

```bash
# 看日志确认适配器已启动
tail -f astrbot.log   # 前台启动时直接看输出
# 期望看到：Telegram Platform Adapter is running.

# 让别人给你的个人账号发一句“你好”，应由个人账号身份自动回复。
# 连接状态文件生成即说明已接管：
ls -l data/telegram_business_connections.json
```

## 回滚

```bash
git checkout master
# 或删除本分支： git branch -D feat/telegram-business
```

## 测试

```bash
uv run pytest tests/test_telegram_business.py tests/test_telegram_adapter.py -q
```

## 注意

- 需要 python-telegram-bot 22.8+（`uv sync` 会自动安装）。
- `data/telegram_business_connections.json` 是运行时状态，重启后 Telegram 会重新推送连接更新，无需手动迁移。

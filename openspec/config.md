# 配置规范

## 概述

AstrBot 配置系统遵循以下原则：

| 原则 | 说明 |
|------|------|
| **分离关注点** | 按功能域分离配置 |
| **敏感信息隔离** | 密钥、密码存储在独立的安全文件中 |
| **环境变量优先** | 密钥通过环境变量注入，不写入配置文件 |
| **分层配置** | 系统配置 → 平台配置 → 插件配置 |

> 相关: [env.md](env.md)（环境变量）, [path.md](path.md)（路径规范）, [api.md](api.md)（HTTP API）

### 配置域

| 域 | 配置文件 | 说明 |
|---|----------|------|
| **安全配置** | `secrets.yaml` | API keys、密码、JWT secrets、GPG 密钥 |
| **平台配置** | `platform.yaml` | 平台适配器设置 |
| **提供商配置** | `providers.yaml` | LLM 提供商设置（不含密钥） |
| **Agent 配置** | `agent.yaml` | Agent 行为参数 |
| **系统配置** | `system.yaml` | 日志、调试、代理、API 服务器等 |
| **GPG 配置** | `gpg.yaml` | GPG 安全配置（可选） |
| **插件配置** | `plugins/` | 各插件独立配置 |

## GPG 安全配置（可选）

### 概述

AstrBot 提供可选的 GPG 安全功能，用于配置文件的签名与验签，防止配置被篡改。

| 功能 | 说明 |
|------|------|
| **配置签名** | 对配置文件进行签名，确保完整性 |
| **配置验签** | 启动时验证配置文件签名，检测篡改 |
| **插件签名** | 验证插件包的 GPG 签名 |

### gpg.yaml（GPG 配置）

```yaml
# GPG 安全配置
# 可选功能，不启用时不影响正常功能

security:
  # GPG 功能开关
  enable: false

  # 验签模式
  # - none: 不验签
  # - warn: 验签失败仅警告
  # - enforce: 验签失败阻止启动
  verify_mode: "warn"

  # 信任的公钥指纹列表
  trusted_keys:
    - "ABCDEF1234567890..."
    - "FEDCBA0987654321..."

  # 签名的配置文件模式
  signed_configs:
    - "secrets.yaml"
    - "agent.yaml"
    - "platform.yaml"

  # 签名文件后缀
  signature_suffix: ".sig"

  # GPG 主目录（默认使用系统配置）
  gnupg_home: ""
```

### secrets.yaml 中的 GPG 密钥

```yaml
# GPG 密钥配置
gpg:
  # 私钥（用于签名）
  # 使用空字符串表示不配置
  private_key: ""
  passphrase: ""

  # 或使用 GPG Keybox 格式
  # keybox: "/path/to/s.gpg-keybox"

  # 公钥指纹（用于验签）
  fingerprint: "ABCDEF1234567890..."
```

### 配置签名与验签流程

#### 签名流程

```bash
# 1. 首次签名
astrbot gpg sign --config secrets.yaml
astrbot gpg sign --config agent.yaml

# 2. 生成签名文件
# secrets.yaml.sig
# agent.yaml.sig

# 3. 签名文件内容（JSON 格式）
{
  "config_file": "secrets.yaml",
  "signature": "-----BEGIN PGP SIGNATURE-----...",
  "signed_at": "2026-03-26T10:00:00Z",
  "issuer": "AstrBot/1.0"
}
```

#### 验签流程

```
启动时：
1. 检查 gpg.yaml 中 verify_mode
2. 对 signed_configs 中的每个文件：
   a. 读取配置文件
   b. 读取对应的 .sig 签名文件
   c. 使用 trusted_keys 中的公钥验签
3. 根据 verify_mode 处理结果：
   - none: 跳过验签
   - warn: 验签失败记录警告日志
   - enforce: 验签失败阻止启动并报错
```

### 目录结构

```
$XDG_CONFIG_HOME/astrbot/
├── gpg.yaml                    # GPG 安全配置
├── secrets.yaml                # 包含 GPG 密钥
├── secrets.yaml.sig            # 配置文件签名
├── agent.yaml
├── agent.yaml.sig
└── ...
```

### 命令行接口

```bash
# 签名配置文件
astrbot gpg sign --config <file> [--output <dir>]

# 验签配置文件
astrbot gpg verify --config <file>

# 验签所有已签名配置
astrbot gpg verify --all

# 导出公钥
astrbot gpg export --keyring <fingerprint> [--output <file>]

# 生成新密钥对
astrbot gpg generate --name "AstrBot" --email "astrbot@example.com"
```

### 安全原则

| 原则 | 说明 |
|------|------|
| **私钥保护** | 私钥仅存储在 secrets.yaml 中，不提交到版本控制 |
| **密钥分离** | GPG 签名密钥与 API 密钥分离存储 |
| **验签优先** | 生产环境建议使用 `verify_mode: enforce` |
| **密钥轮换** | 定期更换签名密钥并重新签名配置文件 |

## 敏感信息隔离

### 原则

| 原则 | 说明 |
|------|------|
| **密钥不上传** | `secrets.yaml` 必须在 `.gitignore` 中 |
| **环境变量注入** | 生产环境通过环境变量注入密钥 |
| **不记录日志** | 配置值不写入日志 |

### secrets.yaml

```yaml
# 安全配置 - 请勿提交到版本控制
# Security config - DO NOT commit to version control

# Dashboard 凭证
dashboard:
  password: "your-hashed-password"
  jwt_secret: "your-jwt-secret"

# LLM Provider API Keys
providers:
  openai:
    api_key: "sk-..."
  anthropic:
    api_key: "sk-ant-..."
  dashscope:
    api_key: "..."

# 平台凭证
platforms:
  telegram:
    bot_token: "12345:ABC..."
  discord:
    bot_token: "..."

# 第三方服务
third_party:
  baidu_aip:
    app_id: ""
    api_key: ""
    secret_key: ""
  moonshotai:
    api_key: ""
  coze:
    api_key: ""
    bot_id: ""

# API Keys（HTTP API 服务认证）
api:
  keys:
    - id: "my-app"
      key: "sk-xxxxxxxxxxxx"
      name: "My Application"
      permissions:
        - "chat"
        - "file"
        - "message"
      rate_limit:
        requests: 100
        period: 60
```

### 环境变量注入

敏感配置通过环境变量覆盖：

```bash
# .env 或系统环境变量
ASTRBOT_DASHBOARD_PASSWORD=xxx
ASTRBOT_DASHBOARD_JWT_SECRET=xxx
ASTRBOT_PROVIDER_OPENAI_API_KEY=sk-xxx
ASTRBOT_PROVIDER_ANTHROPIC_API_KEY=sk-ant-xxx
ASTRBOT_PLATFORM_TELEGRAM_BOT_TOKEN=xxx
```

## 配置文件结构

### 1. system.yaml（系统配置）

```yaml
# 系统配置

log:
  level: INFO                    # DEBUG, INFO, WARNING, ERROR
  file_enable: false
  file_path: logs/astrbot.log
  file_max_mb: 20
  disable_access_log: true

proxy:
  http_proxy: ""
  https_proxy: ""
  no_proxy:
    - localhost
    - 127.0.0.1

trace:
  enable: false
  log_enable: false
  log_path: logs/astrbot.trace.log

temp:
  dir_max_size: 1024            # MB

timezone: Asia/Shanghai

pypi_index_url: https://mirrors.aliyun.com/pypi/simple/
pip_install_arg: ""

# 回调配置
callback_api_base: ""

# API 服务器配置
api:
  host: "0.0.0.0"
  port: 6185
  timeout: 60
  max_body_size: 100
  rate_limit:
    default:
      requests: 100
      period: 60
    high:
      requests: 1000
      period: 60
```

### 2. platform.yaml（平台配置）

```yaml
# 平台配置

# 通用平台设置
platform_settings:
  unique_session: false
  rate_limit:
    time: 60
    count: 30
    strategy: "stall"           # stall, reject
  reply_prefix: ""
  forward_threshold: 1500
  enable_id_white_list: true
  id_whitelist: []
  id_whitelist_log: true
  wl_ignore_admin_on_group: true
  wl_ignore_admin_on_friend: true
  reply_with_mention: false
  reply_with_quote: false
  path_mapping: []
  segmented_reply:
    enable: false
    only_llm_result: true
    interval_method: "random"
    interval: "1.5,3.5"
    words_count_threshold: 150
    split_mode: "regex"
    regex: ".*?[。？！~…]+|.+$"
    split_words: ["。", "？", "！", "~", "…"]
  no_permission_reply: true
  empty_mention_waiting: true
  empty_mention_waiting_need_reply: true
  friend_message_needs_wake_prefix: false
  ignore_bot_self_message: false
  ignore_at_all: false

# 平台列表
platforms: []

# 平台特定配置
platform_specific:
  lark:
    pre_ack_emoji:
      enable: false
      emojis: ["Typing"]
  telegram:
    pre_ack_emoji:
      enable: false
      emojis: ["✍️"]
  discord:
    pre_ack_emoji:
      enable: false
      emojis: ["🤔"]
```

### 3. providers.yaml（提供商配置）

```yaml
# LLM 提供商配置

provider_settings:
  enable: true
  default_provider_id: ""
  fallback_chat_models: []
  default_image_caption_provider_id: ""
  image_caption_prompt: "Please describe the image using Chinese."
  provider_pool: ["*"]

# API Keys 在 secrets.yaml 中配置
# providers:
#   openai:
#     api_key: "sk-..."        # 在 secrets.yaml 中
#     model: "gpt-4"
#     base_url: ""              # 可选，自定义 endpoint
```

### 4. agent.yaml（Agent 配置）

```yaml
# Agent 配置

agent_settings:
  wake_prefix: ["/"]
  default_personality: "default"
  persona_pool: ["*"]
  prompt_prefix: "{{prompt}}"

  # 上下文配置
  context_limit_reached_strategy: "truncate_by_turns"
  llm_compress_instruction: "..."
  llm_compress_keep_recent: 6
  llm_compress_provider_id: ""
  max_context_length: -1
  dequeue_context_length: 1

  # 输出配置
  streaming_response: false
  show_tool_use_status: false
  show_tool_call_result: false
  sanitize_context_by_modalities: false
  max_quoted_fallback_images: 20

  # Web Search
  web_search: false
  websearch_provider: "default"
  # websearch_tavily_key: 在 secrets.yaml 中
  # websearch_bocha_key: 在 secrets.yaml 中
  web_search_link: false

  # 标识
  identifier: false
  group_name_display: false
  datetime_system_prompt: true

  # Agent Runner
  agent_runner_type: "local"    # local, dify, coze, dashscope, deerflow
  dify_agent_runner_provider_id: ""
  coze_agent_runner_provider_id: ""
  dashscope_agent_runner_provider_id: ""
  deerflow_agent_runner_provider_id: ""

  # 工具配置
  unsupported_streaming_strategy: "realtime_segmenting"
  reachability_check: false
  max_agent_step: 30
  tool_call_timeout: 60
  tool_schema_mode: "full"

  # 安全模式
  llm_safety_mode: true
  safety_mode_strategy: "system_prompt"

  # 主动能力
  proactive_capability:
    add_cron_tools: true

  # Computer Use
  computer_use_runtime: "none"
  computer_use_require_admin: true

  # 图片压缩
  image_compress_enabled: true
  image_compress_options:
    max_size: 1024
    quality: 95

# 子 Agent 编排
subagent_orchestrator:
  main_enable: false
  remove_main_duplicate_tools: false
  router_system_prompt: "..."
  agents: []

# STT/TTS
provider_stt_settings:
  enable: false
  provider_id: ""

provider_tts_settings:
  enable: false
  provider_id: ""
  dual_output: false
  use_file_service: false
  trigger_probability: 1.0

# LTM
provider_ltm_settings:
  group_icl_enable: false
  group_message_max_cnt: 300
  image_caption: false
  image_caption_provider_id: ""
  active_reply:
    enable: false
    method: "possibility_reply"
    possibility_reply: 0.1
    whitelist: []
```

### 5. plugins/（插件配置）

各插件配置在 `plugins/` 目录下，文件名与插件名对应：

```
plugins/
├── _conf_schema.json           # 插件配置 schema
├── my_plugin.yaml             # my_plugin 插件配置
└── another_plugin.yaml         # another_plugin 插件配置
```

## 目录结构

```
$XDG_CONFIG_HOME/astrbot/
├── config.yaml                  # 主配置入口
├── secrets.yaml                 # 安全配置（不提交）
├── system.yaml                  # 系统配置
├── platform.yaml                # 平台配置
├── providers.yaml               # 提供商配置
├── agent.yaml                   # Agent 配置
├── gpg.yaml                    # GPG 安全配置（可选）
├── plugins/                     # 插件配置
│   ├── _conf_schema.json        # 插件 schema
│   └── *.yaml                   # 各插件配置
└── mcp_servers.json             # MCP 服务器配置
```

## 配置加载优先级

```
环境变量 > secrets.yaml > config.yaml > 默认值
```

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 最高 | 环境变量 | `ASTRBOT_*` 前缀 |
| 高 | secrets.yaml | 敏感信息 |
| 中 | config.yaml | 用户配置 |
| 低 | 默认值 | 代码中的默认值 |

## 配置迁移

旧版 `cmd_config.json` 迁移到新版：

| 旧字段 | 新配置文件 | 说明 |
|--------|------------|------|
| `dashboard.*` | `secrets.yaml` | 密码、JWT secret |
| `provider_settings.websearch_*_key` | `secrets.yaml` | API keys |
| `platform_settings.*` | `platform.yaml` | 平台设置 |
| `provider_settings.*` | `providers.yaml` + `agent.yaml` | 提供商和 Agent |
| `provider_stt/tts_settings.*` | `agent.yaml` | STT/TTS |
| `content_safety.baidu_aip.*` | `secrets.yaml` | 安全密钥 |
| `log_level`, `http_proxy` | `system.yaml` | 系统配置 |
| `plugin_set`, `kb_*` | `plugins/` | 插件配置 |

## 不规范示例

❌ **旧方式** - 所有配置混在一起：

```json
{
  "dashboard": {
    "password": "plain-text-or-hashed",
    "jwt_secret": "secret-in-config"
  },
  "provider_settings": {
    "openai_api_key": "sk-xxx"
  }
}
```

✅ **新方式** - 分离关注点：

```
config/
├── secrets.yaml      # 密码、密钥
├── system.yaml       # 日志、代理
├── platform.yaml     # 平台设置
├── providers.yaml    # 提供商配置
└── agent.yaml        # Agent 配置
```

## 实施建议

1. **新增配置**：新功能应按域分类到对应文件
2. **敏感信息**：绝不写入 `config.yaml`，使用 `secrets.yaml` 或环境变量
3. **默认值**：在代码中设置默认值，配置文件仅覆盖需要修改的项
4. **Schema 验证**：使用 JSON Schema 验证配置文件格式

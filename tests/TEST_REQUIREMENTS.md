# AstrBot 测试需求清单

本文档详细列出 AstrBot 项目所有需要添加测试的功能模块。

## 测试架构

### 目录结构

```
tests/
├── conftest.py              # 共享 fixtures 和配置
├── （使用 pyproject.toml 中的 [tool.pytest.ini_options]）
├── TEST_REQUIREMENTS.md     # 测试需求清单（本文档）
├── __init__.py              # 包初始化
│
├── unit/                    # 单元测试
│   ├── __init__.py
│   ├── test_core_lifecycle.py
│   ├── test_conversation_mgr.py
│   └── ...
│
├── integration/             # 集成测试
│   ├── __init__.py
│   ├── conftest.py          # 集成测试专用 fixtures
│   ├── test_pipeline_integration.py
│   └── ...
│
├── agent/                   # Agent 相关测试
│   ├── test_context_manager.py
│   └── test_truncator.py
│
├── fixtures/                # 测试数据和 fixtures
│   ├── __init__.py
│   ├── configs/             # 测试配置文件
│   ├── messages/            # 测试消息数据
│   ├── plugins/             # 测试插件
│   └── knowledge_base/      # 测试知识库数据
│
└── test_*.py                # 根级别测试文件
```

### 运行测试

```bash
# 运行所有测试
make test
# 或
uv run pytest tests/ -v

# 运行单元测试
make test-unit
# 或
uv run pytest tests/ -v -m "unit and not integration"

# 运行集成测试
make test-integration
# 或
uv run pytest tests/integration/ -v -m integration

# 运行测试并生成覆盖率报告
make test-cov
# 或
uv run pytest tests/ --cov=astrbot --cov-report=term-missing --cov-report=html -v

# 快速测试（跳过慢速测试）
make test-quick
# 或
uv run pytest tests/ -v -m "not slow and not integration" --tb=short

# 运行特定测试文件
uv run pytest tests/test_main.py -v

# 运行特定测试类
uv run pytest tests/test_main.py::TestCheckEnv -v

# 运行特定测试方法
uv run pytest tests/test_main.py::TestCheckEnv::test_check_env -v
```

### 测试标记

| 标记 | 说明 | 示例 |
|------|------|------|
| `@pytest.mark.unit` | 单元测试 | `-m unit` |
| `@pytest.mark.integration` | 集成测试 | `-m integration` |
| `@pytest.mark.slow` | 慢速测试（>1秒） | `-m "not slow"` |
| `@pytest.mark.platform` | 平台适配器测试 | `-m platform` |
| `@pytest.mark.provider` | LLM Provider 测试 | `-m provider` |
| `@pytest.mark.db` | 数据库相关测试 | `-m db` |
| `@pytest.mark.asyncio` | 异步测试 | 自动添加 |

说明:
- `tests/conftest.py` 会根据目录自动补充标记：`tests/integration/**` 自动标记为 `integration`，其余测试默认标记为 `unit`。
- `tests/fixtures/**` 是测试数据目录，已在 pytest 配置中排除，不参与测试收集。

### 可用 Fixtures

共享 fixtures（`tests/conftest.py`）:

| Fixture | 说明 | 作用域 |
|---------|------|--------|
| `event_loop` | 会话级事件循环 | session |
| `temp_dir` | 临时目录 | function |
| `temp_data_dir` | 模拟 data 目录结构 | function |
| `temp_config_file` | 临时配置文件 | function |
| `temp_db_file` | 临时数据库文件路径 | function |
| `temp_db` | 临时数据库实例 | function |
| `mock_provider` | 模拟 Provider | function |
| `mock_platform` | 模拟 Platform | function |
| `mock_conversation` | 模拟 Conversation | function |
| `mock_event` | 模拟 AstrMessageEvent | function |
| `mock_context` | 模拟插件上下文 | function |
| `astrbot_config` | AstrBotConfig 实例 | function |
| `main_agent_build_config` | MainAgentBuildConfig 实例 | function |
| `provider_request` | ProviderRequest 实例 | function |

集成测试 fixtures（`tests/integration/conftest.py`）:

| Fixture | 说明 | 作用域 |
|---------|------|--------|
| `integration_context` | 集成测试完整 Context | function |
| `mock_llm_provider_for_integration` | 集成测试 LLM Provider | function |
| `mock_platform_for_integration` | 集成测试 Platform | function |
| `mock_pipeline_context` | 模拟 PipelineContext | function |
| `populated_test_db` | 预置数据数据库 | function |

### 测试数据

测试数据位于 `tests/fixtures/` 目录：

```python
from tests.fixtures import load_fixture, get_fixture_path

# 加载 JSON 测试数据
messages = load_fixture("messages/test_messages.json")

# 获取测试数据文件路径
config_path = get_fixture_path("configs/test_cmd_config.json")
```

---

## 目录

- [现有测试分析](#现有测试分析)
- [测试优先级说明](#测试优先级说明)
- [1. 核心模块 (astrbot/core)](#1-核心模块-astrbotcore)
- [2. 平台适配器 (astrbot/core/platform)](#2-平台适配器-astrbotcoreplatform)
- [3. LLM Provider (astrbot/core/provider)](#3-llm-provider-astrbotcoreprovider)
- [4. Agent 系统 (astrbot/core/agent)](#4-agent-系统-astrbotcoreagent)
- [5. Pipeline 消息处理 (astrbot/core/pipeline)](#5-pipeline-消息处理-astrbotcorepipeline)
- [6. 插件系统 (astrbot/core/star)](#6-插件系统-astrbotcorestar)
- [7. 知识库系统 (astrbot/core/knowledge_base)](#7-知识库系统-astrbotcoreknowledge_base)
- [8. 数据库层 (astrbot/core/db)](#8-数据库层-astrbotcoredb)
- [9. API 层 (astrbot/api)](#9-api-层-astrbotapi)
- [10. Dashboard 后端 (astrbot/dashboard)](#10-dashboard-后端-astrbotdashboard)
- [11. CLI 模块 (astrbot/cli)](#11-cli-模块-astrbotcli)
- [12. 内置插件 (astrbot/builtin_stars)](#12-内置插件-astrbotbuiltin_stars)
- [13. 工具类 (astrbot/core/utils)](#13-工具类-astrbotcoreutils)
- [14. 其他模块](#14-其他模块)

---

## 现有测试分析

### 已有测试文件

| 文件 | 测试内容 | 覆盖范围 |
|------|----------|----------|
| `test_main.py` | 主入口环境检查、Dashboard 文件下载 | `main.py` 基础功能 |
| `test_plugin_manager.py` | 插件管理器初始化、安装、更新、卸载 | `PluginManager` |
| `test_openai_source.py` | OpenAI Provider 错误处理、图片处理 | `ProviderOpenAIOfficial` |
| `test_backup.py` | 备份导出/导入、数据迁移 | 备份系统 |
| `test_dashboard.py` | Dashboard 路由、API | 部分 Dashboard 功能 |
| `test_kb_import.py` | 知识库导入 | 知识库导入功能 |
| `test_quoted_message_parser.py` | 引用消息解析 | 引用消息提取 |
| `test_security_fixes.py` | 安全修复测试 | 安全相关功能 |
| `test_temp_dir_cleaner.py` | 临时目录清理 | `TempDirCleaner` |
| `test_tool_loop_agent_runner.py` | Tool Loop Agent Runner | `ToolLoopAgentRunner` |
| `test_context_manager.py` | Context Manager | 上下文管理器 |
| `test_truncator.py` | Truncator | 截断器 |

### 测试覆盖率分析

- **覆盖较好的模块**: 备份系统、Plugin Manager、OpenAI Source、Context Manager
- **需要加强的模块**: 平台适配器、其他 Provider、Pipeline、大部分工具类

---

## 测试优先级说明

| 优先级 | 说明 |
|--------|------|
| **P0** | 核心功能，影响系统稳定性，必须测试 |
| **P1** | 重要功能，影响用户体验，应该测试 |
| **P2** | 辅助功能，建议测试 |
| **P3** | 边缘场景，可选测试 |

---

## 1. 核心模块 (astrbot/core)

### 1.1 core_lifecycle.py - 核心生命周期 [P0]

- [ ] `AstrBotCoreLifecycle.__init__()` 初始化
- [ ] `AstrBotCoreLifecycle.start()` 启动流程
- [ ] `AstrBotCoreLifecycle.stop()` 停止流程
- [ ] 组件初始化顺序正确性
- [ ] 异常处理和恢复机制

### 1.2 astr_main_agent.py - 主 Agent [P0]

- [ ] `build_main_agent()` 构建流程
- [ ] `_select_provider()` Provider 选择逻辑
- [ ] `_get_session_conv()` 会话获取/创建
- [ ] `_apply_kb()` 知识库应用
- [ ] `_apply_file_extract()` 文件提取
- [ ] `_ensure_persona_and_skills()` 人设和技能应用
- [ ] `_decorate_llm_request()` LLM 请求装饰
- [ ] `_modalities_fix()` 模态修复
- [ ] `_sanitize_context_by_modalities()` 按模态清理上下文
- [ ] `_plugin_tool_fix()` 插件工具过滤
- [ ] `_handle_webchat()` Webchat 标题生成
- [ ] `_apply_llm_safety_mode()` LLM 安全模式
- [ ] `_apply_sandbox_tools()` 沙箱工具应用
- [ ] `MainAgentBuildConfig` 配置验证

### 1.3 conversation_mgr.py - 会话管理 [P0]

- [ ] `ConversationManager.new_conversation()` 新建会话
- [ ] `ConversationManager.get_conversation()` 获取会话
- [ ] `ConversationManager.get_curr_conversation_id()` 获取当前会话 ID
- [ ] `ConversationManager.delete_conversation()` 删除会话
- [ ] `ConversationManager.update_conversation()` 更新会话
- [ ] 会话历史管理
- [ ] 并发访问处理

### 1.4 persona_mgr.py - 人设管理 [P1]

- [ ] `PersonaManager.load_personas()` 加载人设
- [ ] `PersonaManager.get_persona()` 获取人设
- [ ] 人设验证
- [ ] 人设热重载

### 1.5 event_bus.py - 事件总线 [P1]

- [ ] 事件发布
- [ ] 事件订阅
- [ ] 事件过滤
- [ ] 异步事件处理

### 1.6 backup/ - 备份系统 [P1]

- [ ] `AstrBotExporter.export()` 导出功能
- [ ] `AstrBotImporter.import_()` 导入功能
- [ ] `ImportPreCheckResult` 预检查
- [ ] 版本迁移
- [ ] 数据完整性验证

### 1.7 cron/ - 定时任务 [P2]

- [ ] `CronManager.add_job()` 添加任务
- [ ] `CronManager.remove_job()` 删除任务
- [ ] `CronManager.list_jobs()` 列出任务
- [ ] 任务执行
- [ ] 任务持久化

### 1.8 config/ - 配置管理 [P0]

- [ ] `AstrBotConfig` 配置加载
- [ ] 配置验证
- [ ] 配置热重载
- [ ] i18n 工具函数

### 1.9 computer/ - 计算机使用 [P2]

- [ ] `ComputerClient` 初始化
- [ ] `Booter` 实现 (local, shipyard, boxlite)
- [ ] 文件系统操作层
- [ ] Python 执行层
- [ ] Shell 执行层
- [ ] 安全限制

---

## 2. 平台适配器 (astrbot/core/platform)

### 2.1 Platform 基类 [P0]

- [ ] `Platform` 抽象类
- [ ] `AstrMessageEvent` 事件类
- [ ] `AstrBotMessage` 消息类
- [ ] `MessageMember` 成员类
- [ ] `PlatformMetadata` 元数据

### 2.2 aiocqhttp (QQ) [P1]

- [ ] `aiocqhttpPlatform` 初始化
- [ ] 消息接收和解析
- [ ] 消息发送
- [ ] 群消息处理
- [ ] 私聊消息处理
- [ ] OneBot API 调用

### 2.3 telegram [P1]

- [ ] `TelegramPlatform` 初始化
- [ ] Webhook 设置
- [ ] 消息解析
- [ ] 消息发送
- [ ] 内联查询
- [ ] 回调查询

### 2.4 discord [P1]

- [ ] `DiscordPlatform` 初始化
- [ ] 消息监听
- [ ] 消息发送
- [ ] Slash 命令
- [ ] 组件交互

### 2.5 slack [P1]

- [ ] `SlackPlatform` 初始化
- [ ] Socket Mode
- [ ] 消息解析
- [ ] 消息发送
- [ ] 事件处理

### 2.6 wecom (企业微信) [P1]

- [ ] `WecomPlatform` 初始化
- [ ] 回调验证
- [ ] 消息加解密
- [ ] 消息发送

### 2.7 wecom_ai_bot [P1]

- [ ] AI Bot 特定功能
- [ ] 消息格式转换

### 2.8 feishu (飞书) [P1]

- [ ] `LarkPlatform` 初始化
- [ ] 事件订阅
- [ ] 消息发送
- [ ] 卡片消息

### 2.9 dingtalk (钉钉) [P1]

- [ ] `DingTalkPlatform` 初始化
- [ ] 回调处理
- [ ] 消息发送

### 2.10 qqofficial [P2]

- [ ] QQ 官方 API 集成
- [ ] 消息解析和发送

### 2.11 qqofficial_webhook [P2]

- [ ] Webhook 模式
- [ ] 消息处理

### 2.12 weixin_official_account (微信公众号) [P2]

- [ ] 公众号消息处理
- [ ] 被动回复
- [ ] 模板消息

### 2.13 webchat [P1]

- [ ] WebSocket 连接
- [ ] 消息传输
- [ ] 会话管理

### 2.14 satori [P2]

- [ ] Satori 协议适配
- [ ] 消息格式转换

### 2.15 line [P2]

- [ ] LINE 平台适配
- [ ] 消息处理

### 2.16 misskey [P2]

- [ ] Misskey 平台适配
- [ ] 消息处理

---

## 3. LLM Provider (astrbot/core/provider)

### 3.1 Provider 基类 [P0]

- [ ] `Provider` 抽象类
- [ ] `ProviderRequest` 请求类
- [ ] `LLMResponse` 响应类
- [ ] `TokenUsage` Token 统计
- [ ] `ProviderMetaData` 元数据

### 3.2 ProviderManager [P0]

- [ ] `ProviderManager` 初始化
- [ ] Provider 注册
- [ ] Provider 选择
- [ ] Fallback 机制
- [ ] API Key 轮换

### 3.3 OpenAI Source [P0]

- [ ] `ProviderOpenAIOfficial` 基础功能
- [ ] 文本对话
- [ ] 流式响应
- [ ] 图片处理
- [ ] 工具调用
- [ ] 错误处理
- [ ] API Key 轮换
- [ ] 模态检查

### 3.4 Anthropic Source [P1]

- [ ] `ProviderAnthropic` 基础功能
- [ ] Claude API 调用
- [ ] 流式响应
- [ ] 工具调用
- [ ] 图片处理

### 3.5 Gemini Source [P1]

- [ ] `ProviderGemini` 基础功能
- [ ] Google AI API 调用
- [ ] 流式响应
- [ ] 工具调用
- [ ] 安全设置

### 3.6 Groq Source [P1]

- [ ] `ProviderGroq` 基础功能
- [ ] 快速推理

### 3.7 xAI Source [P1]

- [ ] `ProviderXAI` 基础功能
- [ ] Grok API

### 3.8 Zhipu Source [P1]

- [ ] `ProviderZhipu` 基础功能
- [ ] 智谱 API

### 3.9 DashScope Source [P1]

- [ ] 阿里云灵积 API

### 3.10 oai_aihubmix_source [P2]

- [ ] AIHubMix 适配

### 3.11 gsv_selfhosted_source [P2]

- [ ] 自托管模型适配

### 3.12 TTS Providers [P2]

- [ ] `openai_tts_api_source` OpenAI TTS
- [ ] `azure_tts_source` Azure TTS
- [ ] `edge_tts_source` Edge TTS
- [ ] `dashscope_tts` 阿里云 TTS
- [ ] `fishaudio_tts_api_source` FishAudio TTS
- [ ] `gemini_tts_source` Gemini TTS
- [ ] `genie_tts` Genie TTS
- [ ] `gsvi_tts_source` GSVI TTS
- [ ] `minimax_tts_api_source` Minimax TTS
- [ ] `volcengine_tts` 火山引擎 TTS

### 3.13 STT Providers [P2]

- [ ] `whisper_api_source` Whisper API
- [ ] `whisper_selfhosted_source` 自托管 Whisper
- [ ] `sensevoice_selfhosted_source` 自托管 SenseVoice

### 3.14 Embedding Providers [P1]

- [ ] `openai_embedding_source` OpenAI Embedding
- [ ] `gemini_embedding_source` Gemini Embedding

### 3.15 Rerank Providers [P2]

- [ ] `bailian_rerank_source` 百炼 Rerank
- [ ] `vllm_rerank_source` vLLM Rerank
- [ ] `xinference_rerank_source` Xinference Rerank

---

## 4. Agent 系统 (astrbot/core/agent)

### 4.1 Agent 基础 [P0]

- [ ] `Agent` 基类
- [ ] `AgentRunner` 运行器基类
- [ ] `RunContext` 运行上下文

### 4.2 ToolLoopAgentRunner [P0]

- [ ] `run()` 执行流程
- [ ] `reset()` 重置
- [ ] 工具调用循环
- [ ] 流式响应处理
- [ ] 错误处理
- [ ] Fallback Provider 支持

### 4.3 Context Manager [P0]

- [ ] `ContextManager.process()` 上下文处理
- [ ] Token 计数
- [ ] 上下文截断
- [ ] LLM 压缩
- [ ] Enforce Max Turns

### 4.4 Truncator [P1]

- [ ] `truncate_by_turns()` 按轮次截断
- [ ] `truncate_by_halving()` 半截断

### 4.5 Compressor [P1]

- [ ] `TruncateByTurnsCompressor` 截断压缩器
- [ ] `LLMSummaryCompressor` LLM 压缩器
- [ ] `split_history()` 历史分割

### 4.6 Token Counter [P1]

- [ ] `count_tokens()` Token 计数
- [ ] 多语言支持

### 4.7 Tool [P0]

- [ ] `FunctionTool` 函数工具
- [ ] `ToolSet` 工具集
- [ ] `HandoffTool` 移交工具
- [ ] `MCPTool` MCP 工具

### 4.8 Tool Executor [P0]

- [ ] `FunctionToolExecutor` 工具执行器
- [ ] 并发执行
- [ ] 超时处理

### 4.9 Agent Runners - 第三方 [P2]

- [ ] `coze_agent_runner` Coze Agent
- [ ] `coze_api_client` Coze API
- [ ] `dashscope_agent_runner` DashScope Agent
- [ ] `dify_agent_runner` Dify Agent
- [ ] `dify_api_client` Dify API

### 4.10 Agent Message [P1]

- [ ] `Message` 消息类
- [ ] `TextPart` 文本部分
- [ ] `ImagePart` 图片部分
- [ ] `ToolCall` 工具调用

### 4.11 Agent Hooks [P1]

- [ ] `BaseAgentRunHooks` 钩子基类
- [ ] `MAIN_AGENT_HOOKS` 主 Agent 钩子

### 4.12 Agent Response [P1]

- [ ] `AgentResponse` 响应类
- [ ] 响应类型处理

### 4.13 Subagent Orchestrator [P2]

- [ ] `SubagentOrchestrator` 子代理编排
- [ ] 任务分发
- [ ] 结果聚合

---

## 5. Pipeline 消息处理 (astrbot/core/pipeline)

### 5.1 Scheduler [P0]

- [ ] `PipelineScheduler` 调度器
- [ ] Stage 注册
- [ ] 执行顺序
- [ ] 异常处理

### 5.2 Stage 基类 [P1]

- [ ] `Stage` 抽象类
- [ ] `process()` 处理方法

### 5.3 Preprocess Stage [P1]

- [ ] 消息预处理
- [ ] 消息格式化

### 5.4 Process Stage [P0]

- [ ] `agent_request` Agent 请求处理
- [ ] `star_request` 插件请求处理
- [ ] `internal` 内部处理
- [ ] `third_party` 第三方处理

### 5.5 Content Safety Check [P1]

- [ ] 内容安全检查 Stage
- [ ] `baidu_aip` 百度内容审核
- [ ] `keywords` 关键词过滤

### 5.6 Rate Limit Check [P1]

- [ ] 速率限制检查
- [ ] 令牌桶算法

### 5.7 Session Status Check [P1]

- [ ] 会话状态检查
- [ ] 会话锁定

### 5.8 Waking Check [P1]

- [ ] 唤醒词检查

### 5.9 Whitelist Check [P1]

- [ ] 白名单检查
- [ ] 权限验证

### 5.10 Respond Stage [P1]

- [ ] 响应发送
- [ ] 消息队列

### 5.11 Result Decorate [P2]

- [ ] 结果装饰
- [ ] 消息格式化

### 5.12 Context [P1]

- [ ] `PipelineContext` 上下文
- [ ] `context_utils` 上下文工具

---

## 6. 插件系统 (astrbot/core/star)

### 6.1 StarManager [P0]

- [ ] `PluginManager` 插件管理器
- [ ] 插件加载
- [ ] 插件卸载
- [ ] 插件重载
- [ ] 依赖解析

### 6.2 Star 基类 [P0]

- [ ] `Star` 插件类
- [ ] 生命周期方法
- [ ] 元数据

### 6.3 Star Handler [P0]

- [ ] `star_handlers_registry` 处理器注册表
- [ ] 处理器执行
- [ ] 异常处理

### 6.4 Register [P0]

- [ ] `register_star` 插件注册
- [ ] `register_command` 命令注册
- [ ] `register_llm_tool` LLM 工具注册
- [ ] `register_regex` 正则注册
- [ ] `register_on_llm_request/response` LLM 钩子

### 6.5 Filters [P1]

- [ ] `command` 命令过滤器
- [ ] `command_group` 命令组过滤器
- [ ] `regex` 正则过滤器
- [ ] `permission` 权限过滤器
- [ ] `event_message_type` 消息类型过滤器
- [ ] `platform_adapter_type` 平台类型过滤器
- [ ] `custom_filter` 自定义过滤器

### 6.6 Context [P0]

- [ ] `Context` 插件上下文
- [ ] 服务访问

### 6.7 Command Management [P1]

- [ ] 命令注册
- [ ] 命令解析
- [ ] 命令路由

### 6.8 Config [P1]

- [ ] 插件配置
- [ ] 配置验证

### 6.9 Session Managers [P1]

- [ ] `session_llm_manager` 会话 LLM 管理
- [ ] `session_plugin_manager` 会话插件管理

### 6.10 Star Tools [P1]

- [ ] `star_tools` 插件工具

### 6.11 Updator [P1]

- [ ] 插件更新器

---

## 7. 知识库系统 (astrbot/core/knowledge_base)

### 7.1 KB Manager [P0]

- [ ] `KnowledgeBaseManager` 知识库管理器
- [ ] 知识库创建
- [ ] 知识库删除
- [ ] 知识库查询

### 7.2 KB Database [P1]

- [ ] `kb_db_sqlite` SQLite 存储
- [ ] 向量存储
- [ ] 元数据管理

### 7.3 Chunking [P1]

- [ ] `base` 分块基类
- [ ] `fixed_size` 固定大小分块
- [ ] `recursive` 递归分块

### 7.4 Parsers [P1]

- [ ] `base` 解析器基类
- [ ] `pdf_parser` PDF 解析
- [ ] `text_parser` 文本解析
- [ ] `markitdown_parser` Markdown 解析
- [ ] `url_parser` URL 解析

### 7.5 Retrieval [P0]

- [ ] `manager` 检索管理器
- [ ] `sparse_retriever` 稀疏检索
- [ ] `rank_fusion` 排序融合

### 7.6 Models [P1]

- [ ] 数据模型
- [ ] 向量模型

### 7.7 Prompts [P2]

- [ ] 提示词模板

---

## 8. 数据库层 (astrbot/core/db)

### 8.1 SQLite [P0]

- [ ] `SQLiteDatabase` 数据库连接
- [ ] 查询执行
- [ ] 事务处理
- [ ] 连接池

### 8.2 PO (Persistent Objects) [P1]

- [ ] `ConversationV2` 会话模型
- [ ] `PlatformSession` 平台会话
- [ ] `Personality` 人设模型
- [ ] 其他数据模型

### 8.3 Migration [P1]

- [ ] `helper` 迁移助手
- [ ] `migra_3_to_4` 版本迁移
- [ ] `migra_45_to_46` 版本迁移
- [ ] `migra_token_usage` Token 使用迁移
- `migra_webchat_session` Webchat 会话迁移
- [ ] `shared_preferences_v3` 偏好设置迁移

### 8.4 VecDB [P1]

- [ ] `base` 向量数据库基类
- [ ] `faiss_impl` FAISS 实现
  - [ ] `vec_db` 向量数据库
  - [ ] `document_storage` 文档存储
  - [ ] `embedding_storage` 嵌入存储

---

## 9. API 层 (astrbot/api)

### 9.1 Exports [P0]

- [ ] `all.py` 导出正确性
- [ ] 导入路径验证

### 9.2 Message Components [P1]

- [ ] `message_components.py` 消息组件
- [ ] 组件类型
- [ ] 序列化/反序列化

### 9.3 Event [P1]

- [ ] `event/__init__` 事件定义
- [ ] `event/filter` 事件过滤器

### 9.4 Platform [P1]

- [ ] `platform/__init__` 平台接口

### 9.5 Provider [P1]

- [ ] `provider/__init__` Provider 接口

### 9.6 Star [P1]

- [ ] `star/__init__` 插件接口

### 9.7 Util [P2]

- [ ] `util/__init__` 工具函数

---

## 10. Dashboard 后端 (astrbot/dashboard)

### 10.1 Server [P0]

- [ ] `server.py` 服务器初始化
- [ ] 路由注册
- [ ] 中间件
- [ ] 静态文件服务

### 10.2 Routes [P0]

- [ ] `auth` 认证路由
- [ ] `backup` 备份路由
- [ ] `chat` 聊天路由
- [ ] `chatui_project` ChatUI 项目路由
- [ ] `command` 命令路由
- [ ] `config` 配置路由
- [ ] `conversation` 会话路由
- [ ] `cron` 定时任务路由
- [ ] `file` 文件路由
- [ ] `knowledge_base` 知识库路由
- [ ] `live_chat` 实时聊天路由
- [ ] `log` 日志路由
- [ ] `persona` 人设路由
- [ ] `platform` 平台路由
- [ ] `plugin` 插件路由
- [ ] `session_management` 会话管理路由
- [ ] `skills` 技能路由
- [ ] `stat` 统计路由
- [ ] `static_file` 静态文件路由
- [ ] `subagent` 子代理路由
- [ ] `t2i` 文字转图片路由
- [ ] `tools` 工具路由
- [ ] `update` 更新路由
- [ ] `util` 工具路由

### 10.3 Utils [P1]

- [ ] `utils.py` Dashboard 工具函数

---

## 11. CLI 模块 (astrbot/cli)

### 11.1 Main [P1]

- [ ] `__main__.py` CLI 入口
- [ ] 命令解析

### 11.2 Commands [P1]

- [ ] `cmd_conf` 配置命令
- [ ] `cmd_init` 初始化命令
- [ ] `cmd_plug` 插件命令
- [ ] `cmd_run` 运行命令

### 11.3 Utils [P2]

- [ ] `basic` 基础工具
- [ ] `plugin` 插件工具
- [ ] `version_comparator` 版本比较

---

## 12. 内置插件 (astrbot/builtin_stars)

### 12.1 builtin_commands [P1]

- [ ] `main.py` 插件入口
- [ ] `admin` 管理命令
- [ ] `alter_cmd` 备用命令
- [ ] `conversation` 会话命令
- [ ] `help` 帮助命令
- [ ] `llm` LLM 命令
- [ ] `persona` 人设命令
- [ ] `plugin` 插件命令
- [ ] `provider` Provider 命令
- [ ] `setunset` 设置命令
- [ ] `sid` SID 命令
- [ ] `t2i` 文字转图片命令
- [ ] `tts` TTS 命令
- [ ] `utils/rst_scene` 场景重置

### 12.2 session_controller [P1]

- [ ] `main.py` 会话控制器
- [ ] 会话锁定
- [ ] 会话解锁

### 12.3 web_searcher [P2]

- [ ] `main.py` 网页搜索
- [ ] `engines/bing` Bing 搜索
- [ ] `engines/sogo` 搜狗搜索

### 12.4 astrbot [P1]

- [ ] `main.py` AstrBot 内置功能
- [ ] `long_term_memory` 长期记忆

---

## 13. 工具类 (astrbot/core/utils)

### 13.1 Path Utils [P1]

- [ ] `astrbot_path.py` 路径工具
  - [ ] `get_astrbot_root()`
  - [ ] `get_astrbot_data_path()`
  - [ ] `get_astrbot_config_path()`
  - [ ] `get_astrbot_plugin_path()`
  - [ ] `get_astrbot_temp_path()`
- [ ] `path_util.py` 路径工具

### 13.2 IO Utils [P1]

- [ ] `io.py` IO 工具
  - [ ] 文件下载
  - [ ] 图片下载
- [ ] `file_extract.py` 文件提取

### 13.3 Network Utils [P1]

- [ ] `network_utils.py` 网络工具
- [ ] `http_ssl.py` SSL 工具
- [ ] `webhook_utils.py` Webhook 工具

### 13.4 String Utils [P2]

- [ ] `string_utils.py` 字符串工具
- [ ] `command_parser.py` 命令解析

### 13.5 T2I Utils [P2]

- [ ] `t2i/local_strategy.py` 本地策略
- [ ] `t2i/network_strategy.py` 网络策略
- [ ] `t2i/renderer.py` 渲染器
- [ ] `t2i/template_manager.py` 模板管理

### 13.6 Quoted Message Utils [P1]

- [ ] `quoted_message_parser.py` 引用消息解析
- [ ] `quoted_message/chain_parser.py` 链解析
- [ ] `quoted_message/extractor.py` 提取器
- [ ] `quoted_message/image_refs.py` 图片引用
- [ ] `quoted_message/image_resolver.py` 图片解析
- [ ] `quoted_message/onebot_client.py` OneBot 客户端
- [ ] `quoted_message/settings.py` 设置

### 13.7 Other Utils [P2]

- [ ] `active_event_registry.py` 活动事件注册
- [ ] `history_saver.py` 历史保存
- [ ] `log_pipe.py` 日志管道
- [ ] `media_utils.py` 媒体工具
- [ ] `metrics.py` 指标
- [ ] `migra_helper.py` 迁移助手
- [ ] `pip_installer.py` Pip 安装器
- [ ] `plugin_kv_store.py` 插件 KV 存储
- [ ] `runtime_env.py` 运行环境
- [ ] `session_lock.py` 会话锁
- [ ] `session_waiter.py` 会话等待
- [ ] `shared_preferences.py` 共享偏好
- [ ] `temp_dir_cleaner.py` 临时目录清理
- [ ] `tencent_record_helper.py` 腾讯记录助手
- [ ] `trace.py` 追踪
- [ ] `version_comparator.py` 版本比较
- [ ] `llm_metadata.py` LLM 元数据

---

## 14. 其他模块

### 14.1 skills/ [P2]

- [ ] `skill_manager.py` 技能管理器
- [ ] 技能加载
- [ ] 技能执行

### 14.2 tools/ [P1]

- [ ] `cron_tools.py` Cron 工具

### 14.3 message/ [P0]

- [ ] `components.py` 消息组件
  - [ ] `Plain` 纯文本
  - [ ] `Image` 图片
  - [ ] `At` @ 提及
  - [ ] `Reply` 回复
  - [ ] `File` 文件
  - [ ] 其他组件
- [ ] `message_event_result.py` 消息事件结果
  - [ ] `MessageEventResult`
  - [ ] `MessageChain`
  - [ ] `CommandResult`

### 14.4 Root Files [P1]

- [ ] `main.py` 主入口
  - [ ] 环境检查
  - [ ] Dashboard 下载
  - [ ] 服务启动
- [ ] `runtime_bootstrap.py` 运行时引导

---

## 测试编写建议

### 测试命名规范

```python
# 文件命名: test_<module_name>.py
# 类命名: Test<FeatureName>
# 方法命名: test_<scenario>_<expected_result>
```

### 测试结构

```python
import pytest

class TestFeatureName:
    """功能描述"""

    @pytest.fixture
    def setup(self):
        """测试前置"""
        pass

    def test_normal_case(self, setup):
        """测试正常情况"""
        pass

    def test_edge_case(self, setup):
        """测试边界情况"""
        pass

    def test_error_handling(self, setup):
        """测试错误处理"""
        pass
```

### Mock 使用建议

- 对外部 API 调用使用 `unittest.mock`
- 对异步函数使用 `AsyncMock`
- 对文件系统操作使用 `tmp_path` fixture

### 异步测试

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

---

## 进度追踪

口径说明:
- 下表统计的是“需求条目完成度”，不是 pytest 已有用例数量。
- 当前 pytest 测试基线（`uv run pytest tests/ --collect-only`）：`204` 条已收集用例。

| 模块 | 总计 | 已完成 | 进度 |
|------|------|--------|------|
| 核心模块 | 50 | 0 | 0% |
| 平台适配器 | 40 | 0 | 0% |
| LLM Provider | 45 | 0 | 0% |
| Agent 系统 | 40 | 0 | 0% |
| Pipeline | 25 | 0 | 0% |
| 插件系统 | 30 | 0 | 0% |
| 知识库 | 25 | 0 | 0% |
| 数据库 | 20 | 0 | 0% |
| API 层 | 15 | 0 | 0% |
| Dashboard | 30 | 0 | 0% |
| CLI | 10 | 0 | 0% |
| 内置插件 | 25 | 0 | 0% |
| 工具类 | 40 | 0 | 0% |
| 其他 | 20 | 0 | 0% |
| **总计** | **415** | **0** | **0%** |

---

## 注意事项

1. **测试隔离**: 每个测试应该独立运行，不依赖其他测试
2. **数据隔离**: 使用临时目录和数据库，不要污染真实数据
3. **异步测试**: 记得使用 `@pytest.mark.asyncio` 装饰器
4. **Mock 外部依赖**: 不要依赖真实的 API 调用
5. **测试覆盖**: 关注边界条件和错误处理
6. **测试速度**: 保持测试快速执行，避免长时间等待

---

*最后更新: 2026-02-20*
*生成工具: Claude Code*

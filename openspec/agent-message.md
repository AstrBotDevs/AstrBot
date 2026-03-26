# Agent 消息处理流程规范

## 概述

AstrBot Agent 采用**双缓冲区 + 流控**的消息处理模型，实现消息的削峰填谷、限流保护和安全处理。

**核心设计**：
- **输入缓冲区**：用户消息暂存，按频率控制消费
- **输出缓冲区**：回复消息暂存，按策略分发
- **流控引擎**：根据 API 限制自动调节消费速率
- **安全层**：防注入、防泄密、防误触

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Platform Adapter                          │
│  (QQ / Telegram / Discord / ...)                                │
└────────────────────────────┬────────────────────────────────────┘
                             │ commit_event()
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Input Message Buffer                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ UserQueue (per user/conversation)                       │    │
│  │ - metadata: user_id, platform, timestamp, session_id   │    │
│  │ - messages: [msg1, msg2, ...]                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                     FlowControl                                  │
│                    (rate limiter)                                │
└───────────────────────────┼─────────────────────────────────────┘
                            │ pull_messages()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Core                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Context     │───▶│  LLM Loop    │───▶│  Tool Call   │      │
│  │  Manager     │    │  (step loop) │    │  Executor    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ produce_result()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Output Buffer                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ ResultQueue (per session)                               │    │
│  │ - content: string / stream                              │    │
│  │ - format: plain / markdown / html                       │    │
│  │ - strategy: streaming / segmented / full                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                   DispatchStrategy                                │
│                  (streaming / segmented / full)                  │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Platform Adapter                              │
│  (SendResult)                                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 工具、技能与 Agent 协作体系

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Core (LLM Loop)                         │
│                                                                  │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│   │  Internal   │    │    MCP     │    │   Skills    │       │
│   │   Tools     │    │   Tools    │    │             │       │
│   │ (Function   │    │  (MCP      │    │  (Pre-built │       │
│   │   Tool)     │    │  Client)   │    │   Agent     │       │
│   │             │    │             │    │   Flows)    │       │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘       │
│          │                   │                   │              │
│          └───────────────────┴───────────────────┘              │
│                              │                                  │
│                      Tool Executor                               │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 协作层                                 │
│                                                                  │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│   │    本地     │    │   远程      │    │   子 Agent  │       │
│   │   Subagent  │    │  A2A Agent │    │   (MCP/A2A) │       │
│   │             │    │             │    │             │       │
│   └─────────────┘    └─────────────┘    └─────────────┘       │
│                                                                  │
│   ┌─────────────────────────────────────────────────────┐        │
│   │              ACP 协议 (Agent 通信)                    │        │
│   └─────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 工具来源

| 来源 | 协议 | 说明 |
|------|------|------|
| **Internal Tools** | 自定义 Python | `FunctionTool`/`ToolSet`，Star 插件注册 |
| **MCP Tools** | MCP JSON-RPC 2.0 | 外部 MCP 服务器提供的工具 |
| **Skills** | 自定义协议 | 预构建的 Agent 执行流程模板 |

### 1.3 工具调用决策

```rust
pub struct ToolRouter {
    internal: ToolSet,
    mcp: HashMap<String, Box<dyn MCPClient>>,
    skills: HashMap<String, Box<dyn SkillExecutor>>,
}

impl ToolRouter {
    pub fn new(
        internal: ToolSet,
        mcp: HashMap<String, Box<dyn MCPClient>>,
        skills: HashMap<String, Box<dyn SkillExecutor>>,
    ) -> Self {
        Self { internal, mcp, skills }
    }

    /// 路由工具调用
    pub async fn route_tool_call(
        &self,
        tool_name: &str,
        arguments: Value,
        context: &mut AgentContext,
    ) -> Result<ToolResult> {
        // 1. 检查内部工具
        if let Some(internal_tool) = self.internal.get_tool(tool_name) {
            return self.call_internal(internal_tool, arguments, context).await;
        }

        // 2. 检查 MCP 工具
        for (_, client) in &self.mcp {
            if client.has_tool(tool_name) {
                return client.call_tool(tool_name, arguments).await;
            }
        }

        // 3. 检查 Skills
        if let Some(skill) = self.skills.get(tool_name) {
            return skill.execute(tool_name, arguments, context).await;
        }

        Err(ToolError::NotFound(format!("Tool not found: {}", tool_name)).into())
    }
}
```

### 1.4 Agent 协作（ACP 协议）

```rust
pub struct ACPAgentClient {
    connection: ACPConnection,
}

impl ACPAgentClient {
    /// 调用远程 Agent
    pub async fn call_agent(
        &self,
        agent_name: &str,
        action: &str,
        args: Value,
        stream: bool,
    ) -> Result<AgentResult> {
        let request = ACPRequest {
            method: "agent/call".to_string(),
            params: json!({
                "agent": agent_name,
                "action": action,
                "args": args,
            }),
        };

        if stream {
            Ok(AgentResult::Stream(self.connection.stream_request(request).await?))
        } else {
            self.send_request(request).await
        }
    }

    /// 列出可用 Agent
    pub async fn list_agents(&self) -> Result<Vec<AgentCard>> {
        let response = self.send_request(ACPRequest {
            method: "agent/list".to_string(),
            params: json!({}),
        }).await?;

        let agents = response.result["agents"]
            .as_array()
            .ok_or_else(|| ACPError::InvalidResponse("agents".to_string()))?;

        agents.iter()
            .map(|a| serde_json::from_value(a.clone()).map_err(|e| e.into()))
            .collect()
    }
}
```

### 1.5 Skills 执行

```rust
pub struct SkillExecutor {
    registry: SkillRegistry,
}

impl SkillExecutor {
    pub fn new(registry: SkillRegistry) -> Self {
        Self { registry }
    }

    /// 执行 Skill
    pub async fn execute(
        &self,
        skill_name: &str,
        input_data: Value,
        context: &mut AgentContext,
    ) -> Result<SkillResult> {
        let skill = self.registry.get(skill_name)
            .ok_or_else(|| SkillError::NotFound(format!("Skill not found: {}", skill_name)))?;

        // Skill 可以包含多个步骤
        let steps = skill.get_steps();
        let mut results = Vec::new();

        for step in steps {
            // 每个步骤可以是工具调用或 Agent 调用
            let result = match step.step_type.as_str() {
                "tool" => self.call_tool(&step.tool, &step.args).await,
                "agent" => self.call_agent(&step.agent, &step.action, &step.args).await,
                "llm" => self.call_llm(&step.prompt, context).await,
                _ => Err(SkillError::InvalidStep(step.step_type.clone()).into()),
            }?;

            results.push(result);

            // 检查是否需要停止
            if step.on_result == "stop_if_success" && results.last().map(|r| r.success).unwrap_or(false) {
                break;
            }
        }

        Ok(SkillResult {
            skill_name: skill_name.to_string(),
            steps: results.clone(),
            final_output: results.last().cloned(),
        })
    }
}
```

### 1.6 配置

```yaml
# agent.yaml

# 工具配置
tools:
  # 内部工具
  internal:
    enabled: true
    max_per_request: 128

  # MCP 工具
  mcp:
    enabled: true
    servers: []  # MCP 服务器配置

  # Skills
  skills:
    enabled: true
    registry_path: "$XDG_DATA_HOME/astrbot/skills/"

# Agent 协作配置
agent_collaboration:
  # ACP 配置
  acp:
    enabled: true
    endpoints:
      - name: "local"
        type: "unix"
        path: "/run/astrbot/acp.sock"

  # 子 Agent 配置
  subagents:
    enabled: true
    max_parallel: 3
    timeout: 300

  # Agent 发现
  discovery:
    # 自动发现同进程内的 Subagent
    auto_discover_internal: true

    # 定期刷新远程 Agent 列表
    refresh_interval: 60
```

---

## 2. 输入缓冲区（Input Buffer）

### 2.1 队列结构

```rust
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::Arc;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputMessage {
    /// 全局唯一 ID
    pub message_id: String,
    /// 平台标识
    pub platform: String,
    /// 用户 ID
    pub user_id: String,
    /// 会话 ID
    pub conversation_id: String,
    /// 消息内容
    pub content: MessageContent,
    /// 到达时间
    pub timestamp: f64,
    /// 扩展元数据
    pub metadata: HashMap<String, String>,
    /// 优先级（越高越先处理）
    #[serde(default)]
    pub priority: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MessageContent {
    Plain(String),
    Chain(Vec<MessageSegment>),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageSegment {
    pub segment_type: String,
    pub content: String,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

pub struct UserMessageQueue {
    pub user_id: String,
    pub session_id: String,
    messages: VecDeque<InputMessage>,
    metadata: HashMap<String, String>,
    pub created_at: f64,
    pub updated_at: f64,
    pub max_size: usize,
    pub max_age: f64,
}

impl UserMessageQueue {
    pub fn new(user_id: String, session_id: String) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();

        Self {
            user_id,
            session_id,
            messages: VecDeque::new(),
            metadata: HashMap::new(),
            created_at: now,
            updated_at: now,
            max_size: 1000,
            max_age: 3600.0,
        }
    }

    pub fn push(&mut self, msg: InputMessage) {
        self.messages.push_back(msg);
        self.updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
    }

    pub fn pop(&mut self) -> Option<InputMessage> {
        self.messages.pop_front()
    }

    pub fn len(&self) -> usize {
        self.messages.len()
    }

    pub fn is_empty(&self) -> bool {
        self.messages.is_empty()
    }
}
```

### 2.2 缓冲区配置

```yaml
# agent.yaml
input_buffer:
  # 单用户队列最大消息数
  max_queue_size: 1000

  # 消息最大存活时间（秒）
  max_message_age: 3600

  # 超出限制时的处理策略
  overflow_strategy: "drop_oldest"  # drop_oldest | drop_newest | block

  # 丢弃消息时的提示前缀
  overflow_hint: "[消息过多，部分早期消息已丢弃]"

  # 是否按用户隔离队列
  per_user_queue: true

  # 是否按会话隔离队列
  per_conversation_queue: true
```

### 2.3 溢出保护策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `drop_oldest` | 丢弃最旧的消息，保留最新的 | 高频聊天，侧重时效性 |
| `drop_newest` | 丢弃最新的消息，保留旧的 | 重要指令，不容丢失 |
| `block` | 阻塞输入，直到队列有空位 | 重要对话，不容任何丢弃 |

**溢出时的处理**：

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowStrategy {
    DropOldest,
    DropNewest,
    Block,
}

pub struct InputBuffer {
    queues: HashMap<String, Arc<tokio::sync::Mutex<UserMessageQueue>>>,
    overflow_strategy: OverflowStrategy,
    overflow_hint: String,
}

impl InputBuffer {
    /// 添加消息到队列
    pub async fn add_message(&self, queue_id: &str, message: InputMessage) -> Result<(), BufferError> {
        let queue = self.queues.get(queue_id)
            .ok_or(BufferError::QueueNotFound)?;

        let mut queue = queue.lock().await;

        if queue.messages.len() >= queue.max_size {
            match self.overflow_strategy {
                OverflowStrategy::DropOldest => {
                    if let Some(old_msg) = queue.messages.pop_front() {
                        // 在丢弃的消息前插入提示
                        let hint = InputMessage {
                            message_id: "system_hint".into(),
                            content: MessageContent::Plain(format!(
                                "[{} 丢弃于 {}]",
                                self.overflow_hint,
                                old_msg.timestamp
                            )),
                            ..message.clone()
                        };
                        queue.messages.push_front(hint);
                    }
                    queue.messages.push_back(message);
                }
                OverflowStrategy::DropNewest => {
                    // 丢弃新消息，不插入
                }
                OverflowStrategy::Block => {
                    // 等待直到队列有空位
                    while queue.messages.len() >= queue.max_size {
                        let queue_clone = queue.clone();
                        drop(queue);
                        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                        queue = queue_clone.lock().await;
                    }
                    queue.messages.push_back(message);
                }
            }
        } else {
            queue.messages.push_back(message);
        }

        Ok(())
    }
}
```

---

## 3. 流控引擎（Flow Control）

### 3.1 速率限制配置

```yaml
# agent.yaml
flow_control:
  # 消费速率模式
  mode: "auto"  # auto | manual

  # 手动模式：每秒处理消息数
  manual_rate: 10

  # 自动模式：基于 LLM API 限制计算
  auto:
    # LLM API 每分钟请求限制
    api_rpm_limit: 60

    # 每次请求预计处理消息数
    messages_per_request: 5

    # 安全系数（留一定余量）
    safety_margin: 0.8

    # 最小消费间隔（秒）
    min_interval: 0.5

    # 最大消费间隔（秒）
    max_interval: 10
```

### 3.2 速率计算公式

```
effective_rate = min(api_rpm_limit * messages_per_request * safety_margin, 1/min_interval)
consume_interval = 1 / effective_rate
```

**示例**：
- API RPM = 60
- 每请求处理 5 条消息
- 安全系数 = 0.8
- 有效速率 = 60 * 5 * 0.8 = 240 消息/分钟 = 4 消息/秒
- 消费间隔 = 0.25 秒

### 3.3 令牌桶实现

```rust
use std::sync::atomic::{AtomicFloat, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub struct TokenBucket {
    rate: f64,           // 每秒令牌数
    capacity: f64,        // 桶容量
    tokens: AtomicFloat,
    last_update: std::sync::Mutex<Instant>,
}

impl TokenBucket {
    pub fn new(rate: f64, capacity: f64) -> Self {
        Self {
            rate,
            capacity,
            tokens: AtomicFloat::new(capacity),
            last_update: std::sync::Mutex::new(Instant::now()),
        }
    }

    /// 获取令牌，返回需要等待的秒数
    pub fn acquire(&self, tokens: f64) -> f64 {
        let mut last_update = self.last_update.lock().unwrap();
        let elapsed = last_update.elapsed().as_secs_f64();
        let current_tokens = self.tokens.load(Ordering::SeqCst);

        let new_tokens = (current_tokens + elapsed * self.rate).min(self.capacity);
        self.tokens.store(new_tokens, Ordering::SeqCst);
        *last_update = Instant::now();

        if new_tokens >= tokens {
            self.tokens.fetch_sub(tokens as f32, Ordering::SeqCst);
            0.0
        } else {
            (tokens - new_tokens) / self.rate
        }
    }

    /// 等待直到获取令牌
    pub async fn wait_and_acquire(&self, tokens: f64) {
        let wait = self.acquire(tokens);
        if wait > 0.0 {
            tokio::time::sleep(Duration::from_secs_f64(wait)).await;
        }
    }
}
```

### 3.4 优先级调度

```rust
use std::collections::HashMap;
use std::sync::Arc;

pub struct PriorityScheduler {
    buckets: HashMap<String, Arc<TokenBucket>>,
    queues: HashMap<String, Arc<tokio::sync::Mutex<UserMessageQueue>>>,
}

impl PriorityScheduler {
    pub fn new() -> Self {
        Self {
            buckets: HashMap::new(),
            queues: HashMap::new(),
        }
    }

    /// 获取下一条待处理消息（按优先级）
    pub async fn next_message(&self) -> Option<InputMessage> {
        let mut candidates = Vec::new();

        // 1. 收集所有非空队列
        for (user_id, queue) in &self.queues {
            let queue = queue.lock().await;
            if queue.is_empty() {
                continue;
            }

            // 2. 计算该用户的可用速率
            let Some(bucket) = self.buckets.get(user_id) else {
                continue;
            };

            // 3. 获取队首消息（peek，不移除）
            let msg = queue.messages.front()?.clone();
            candidates.push((msg, Arc::clone(bucket), user_id.clone()));
        }

        if candidates.is_empty() {
            return None;
        }

        // 4. 按优先级 + 可用性排序
        // 优先级相同时，优先处理令牌充足的
        candidates.sort_by(|a, b| {
            let a_priority = a.0.priority;
            let b_priority = b.0.priority;
            let a_tokens = a.1.tokens.load(Ordering::SeqCst);
            let b_tokens = b.1.tokens.load(Ordering::SeqCst);
            let a_score = (a_priority as f64, a_tokens);
            let b_score = (b_priority as f64, b_tokens);
            b_score.partial_cmp(&a_score).unwrap_or(std::cmp::Ordering::Equal)
        });

        // 5. 等待最紧急消息的令牌
        let (_msg, bucket, user_id) = &candidates[0];
        bucket.wait_and_acquire(1.0).await;

        // 6. 移除并返回
        let queue = self.queues.get(user_id)?;
        let mut queue = queue.lock().await;
        queue.pop()
    }
}
```

---

## 4. Agent 核心（Agent Core）

### 4.1 上下文管理（Context Manager）

```rust
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentContext {
    /// 消息历史
    pub messages: Vec<Message>,
    /// 系统提示
    pub system_prompt: String,
    /// 可用工具
    pub tools: Vec<ToolDefinition>,
    /// 记忆存储
    pub memory: Arc<dyn MemoryStore>,
    /// 扩展元数据
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct ContextConfig {
    pub max_context_tokens: usize,
    pub compress_threshold: f64,
    pub keep_recent_messages: usize,
}

pub struct ContextManager {
    config: ContextConfig,
    tool_registry: Arc<dyn ToolRegistry>,
}

impl ContextManager {
    pub fn new(config: ContextConfig, tool_registry: Arc<dyn ToolRegistry>) -> Self {
        Self { config, tool_registry }
    }

    /// 构建 Agent 执行上下文
    pub async fn build_context(
        &self,
        queue: &UserMessageQueue,
        memory: Arc<dyn MemoryStore>,
    ) -> Result<AgentContext, ContextError> {
        // 1. 从队列获取消息
        let raw_messages: Vec<InputMessage> = queue.messages.iter().cloned().collect();

        // 2. 应用安全过滤
        let filtered_messages = self.apply_security_filters(raw_messages)?;

        // 3. 构建消息列表
        let messages = self.build_message_list(filtered_messages)?;

        // 4. 检查是否需要压缩
        let total_tokens = self.estimate_tokens(&messages);
        let messages = if total_tokens > self.config.max_context_tokens {
            self.compress_context(messages, memory.clone()).await?
        } else {
            messages
        };

        // 5. 添加系统提示
        let system_prompt = self.build_system_prompt()?;

        // 6. 获取可用工具
        let tools = self.tool_registry.list_tools().await?;

        Ok(AgentContext {
            messages,
            system_prompt,
            tools,
            memory,
            metadata: HashMap::new(),
        })
    }

    /// 压缩上下文
    async fn compress_context(
        &self,
        messages: Vec<Message>,
        memory: Arc<dyn MemoryStore>,
    ) -> Result<Vec<Message>, ContextError> {
        let keep = self.config.keep_recent_messages;

        // 保留最近 N 条消息
        let recent: Vec<Message> = messages.into_iter().rev().take(keep).collect();
        let history: Vec<Message> = messages.into_iter().rev().skip(keep).collect();

        // 摘要历史消息并存入记忆
        if !history.is_empty() {
            let summary = self.summarize(&history)?;
            memory.add(Message {
                role: "system".into(),
                content: format!("[历史摘要] {}", summary),
                metadata: HashMap::from([("type".into(), "summary".into())]),
            }).await?;
        }

        Ok(recent)
    }
}
```

### 4.2 上下文配置

```yaml
# agent.yaml
context:
  # 最大上下文 token 数
  max_context_tokens: 128000

  # 触发压缩的阈值（比例）
  compress_threshold: 0.85

  # 压缩后保留的最近消息数
  keep_recent_messages: 6

  # 压缩提供者（为空则使用主 Provider）
  compress_provider_id: ""

  # 压缩提示词
  compress_instruction: |
    请简洁地总结对话要点，保留关键信息如：
    - 用户的主要需求或问题
    - 已确定的方案或结论
    - 未完成的任务

  # 消息保留策略
  retention:
    # 保留最近 N 小时内的原始消息
    recent_hours: 24

    # 超出后转为摘要存储
    summarize_after: true
```

---

## 5. 工具调用策略（Tool Calling Strategy）

### 5.1 工具调用最佳实践

```yaml
# agent.yaml
tool_calling:
  # 工具调用策略
  strategy: "smart"  # eager | sequential | smart

  # 每次请求最大工具调用数
  max_calls_per_request: 128

  # 工具调用超时（秒）
  timeout: 60

  # 工具调用失败重试次数
  max_retries: 3

  # 是否并行调用独立工具
  parallel_calls: true

  # 并行调用最大数量
  max_parallel_calls: 5

  # 工具结果的最大 token 数（截断）
  max_result_tokens: 4096

  # 是否在工具调用后立即返回中间结果
  stream_intermediate: true
```

### 5.2 工具调用流程

```rust
use async_trait::async_trait;

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: HashMap<String, serde_json::Value>,
}

#[derive(Debug)]
pub struct ToolResult {
    pub id: String,
    pub name: String,
    pub result: Result<String, ToolError>,
}

#[derive(Debug, thiserror::Error)]
pub enum ToolError {
    #[error("Tool not found: {0}")]
    NotFound(String),
    #[error("Execution failed: {0}")]
    ExecutionFailed(String),
    #[error("Timeout")]
    Timeout,
}

pub struct ToolCallingPolicy {
    config: ToolCallingConfig,
    tool_executor: Arc<dyn ToolExecutor>,
}

impl ToolCallingPolicy {
    /// 执行工具调用
    pub async fn execute_tools(
        &self,
        llm_response: &LLMResponse,
        context: &AgentContext,
    ) -> Result<Vec<ToolResult>, ToolError> {
        // 1. 解析工具调用请求
        let tool_calls = &llm_response.tool_calls;

        if tool_calls.is_empty() {
            return Ok(Vec::new());
        }

        // 2. 按策略分组
        let groups = self.group_by_dependency(tool_calls);

        let mut results = Vec::new();

        // 3. 按组执行
        for group in groups {
            letannels = if self.can_parallel(&group) {
                // 并行执行
                self.execute_parallel(group, context).await?
            } else {
                // 串行执行
                self.execute_sequential(group, context).await?
            };

            results.extend(group_results);

            // 4. 检查是否超过限制
            if results.len() >= self.config.max_calls_per_request {
                break;
            }
        }

        Ok(results)
    }

    /// 按依赖关系分组
    fn group_by_dependency(&self, tool_calls: &[ToolCall]) -> Vec<Vec<ToolCall>> {
        let mut groups = Vec::new();
        let mut current_group = Vec::new();

        for call in tool_calls {
            // 检查是否依赖前一个工具的结果
            if !current_group.is_empty() && call.depends_on_previous {
                current_group.push(call.clone());
            } else {
                if !current_group.is_empty() {
                    groups.push(current_group);
                }
                current_group = vec![call.clone()];
            }
        }

        if !current_group.is_empty() {
            groups.push(current_group);
        }

        groups
    }

    /// 检查是否可以并行执行
    fn can_parallel(&self, group: &[ToolCall]) -> bool {
        self.config.parallel_calls && group.iter().all(|c| !c.depends_on_previous)
    }

    /// 并行执行
    async fn execute_parallel(
        &self,
        calls: Vec<ToolCall>,
        context: &AgentContext,
    ) -> Result<Vec<ToolResult>, ToolError> {
        let futures = calls.into_iter().map(|call| {
            self.execute_single(call, context)
        });

        let results = futures::future::join_all(futures).await;

        Ok(results.into_iter().map(|r| r.unwrap()).collect())
    }

    /// 串行执行
    async fn execute_sequential(
        &self,
        calls: Vec<ToolCall>,
        context: &AgentContext,
    ) -> Result<Vec<ToolResult>, ToolError> {
        let mut results = Vec::new();

        for call in calls {
            let result = self.execute_single(call, context).await?;
            results.push(result);
        }

        Ok(results)
    }
}
```

### 5.3 工具选择策略

```rust
pub struct ToolSelector {
    max_tools_per_request: usize,
    prefer_recent: bool,
}

impl ToolSelector {
    pub fn new(max_tools_per_request: usize, prefer_recent: bool) -> Self {
        Self {
            max_tools_per_request,
            prefer_recent,
        }
    }

    /// 选择最相关的工具
    pub fn select_tools(
        &self,
        available_tools: &[Tool],
        query: &str,
        context: &AgentContext,
    ) -> Vec<Tool> {
        // 1. 计算工具与查询的相关性
        let mut scored: Vec<(f64, Tool)> = available_tools
            .iter()
            .map(|tool| (self.calculate_relevance(tool, query, context), tool.clone()))
            .collect();

        // 2. 排序并截取
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
        let selected: Vec<Tool> = scored.into_iter().take(self.max_tools_per_request).map(|(_, t)| t).collect();

        // 3. 如果启用了最近使用优先
        if self.prefer_recent {
            self.boost_recent(selected, context)
        } else {
            selected
        }
    }

    /// 计算相关性分数
    fn calculate_relevance(&self, tool: &Tool, query: &str, context: &AgentContext) -> f64 {
        let mut score = 0.0;

        // 工具名称匹配
        if query.to_lowercase().split_whitespace().any(|w| tool.name.to_lowercase().contains(w)) {
            score += 0.3;
        }

        // 工具描述匹配
        if !tool.description.is_empty() {
            let query_words: std::collections::HashSet<&str> =
                query.to_lowercase().split_whitespace().collect();
            let desc_words: std::collections::HashSet<&str> =
                tool.description.to_lowercase().split_whitespace().collect();
            let overlap = query_words.intersection(&desc_words).count();
            score += overlap as f64 * 0.1;
        }

        // 最近使用过的工具加权
        if let Some(recent_tools) = context.metadata.get("recent_tools") {
            if recent_tools.contains(&tool.name) {
                score += 0.2;
            }
        }

        score
    }

    /// 最近使用优先
    fn boost_recent(&self, mut tools: Vec<Tool>, context: &AgentContext) -> Vec<Tool> {
        let recent_tools = context.metadata.get("recent_tools");
        tools.sort_by(|a, b| {
            let a_recent = recent_tools.map(|r| r.contains(&a.name)).unwrap_or(false);
            let b_recent = recent_tools.map(|r| r.contains(&b.name)).unwrap_or(false);
            b_recent.cmp(&a_recent)
        });
        tools
    }
}
```

---

## 6. 安全层（Security Layer）

### 6.1 安全配置

```yaml
# agent.yaml
security:
  # 防注入配置
  injection:
    # 启用防注入
    enable: true

    # 检测模式
    mode: "strict"  # strict | moderate | permissive

    # 注入模式识别
    patterns:
      - name: "role_play_injection"
        regex: "(?i)(you are now|forget previous|ignore all)"
        severity: "high"

      - name: "system_prompt_leak"
        regex: "(?i)(repeat your? (system|initial) (prompt|instructions))"
        severity: "high"

      - name: "code_injection"
        regex: "(?i)(```(system|prompt|instructor))"
        severity: "medium"

    # 触发时的处理策略
    on_detect: "sanitize"  # sanitize | block | warn

    # 是否记录检测日志
    log_detections: true

  # 内容过滤配置
  content_filter:
    # 启用内容过滤
    enable: true

    # 过滤级别
    level: "standard"  # strict | standard | minimal

    # 敏感词列表（文件路径或内联）
    blocklist: []

    # 替换字符
    replacement: "[已过滤]"

  # 泄密防护
  leakage_prevention:
    # 阻止 Agent 读取敏感文件模式
    blocked_file_patterns:
      - "**/.env"
      - "**/secrets.yaml"
      - "**/*password*"
      - "**/.git/credentials"

    # 阻止 Agent 输出敏感信息模式
    blocked_output_patterns:
      - "(?i)api[_-]?key"
      - "(?i)secret"
      - "(?i)password"

    # 替换为占位符
    placeholder: "[REDACTED]"
```

### 6.2 安全过滤器实现

```rust
use regex::Regex;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Detection {
    pub name: String,
    pub severity: String,
    pub matched: Vec<String>,
}

pub struct SecurityFilter {
    config: SecurityConfig,
    compiled_patterns: Vec<(String, Regex, String)>,
}

impl SecurityFilter {
    pub fn new(config: SecurityConfig) -> Result<Self, regex::Error> {
        let compiled_patterns = config
            .injection
            .patterns
            .iter()
            .map(|p| {
                let regex = Regex::new(&p.regex)?;
                Ok((p.name.clone(), regex, p.severity.clone()))
            })
            .collect::<Result<Vec<_>, _>>()?;

        Ok(Self { config, compiled_patterns })
    }

    /// 过滤输入消息
    pub fn filter_messages(&self, messages: Vec<InputMessage>) -> Vec<InputMessage> {
        let mut filtered = Vec::new();

        for mut msg in messages {
            // 1. 内容过滤
            if self.config.content_filter.enable {
                msg.content = self.filter_content(msg.content);
            }

            // 2. 注入检测
            if self.config.injection.enable {
                let detections = self.detect_injection(&msg.content);

                if !detections.is_empty() {
                    let action = self.handle_injection(&detections, &mut msg);
                    if action == "skip" {
                        continue;
                    }
                }
            }

            filtered.push(msg);
        }

        filtered
    }

    /// 过滤输出内容
    pub fn filter_output(&self, content: String, context: &AgentContext) -> String {
        // 泄密防护 - 移除敏感信息
        if let Some(ref leakage) = self.config.leakage_prevention {
            self.redact_sensitive(content, leakage)
        } else {
            content
        }
    }

    /// 检测注入攻击
    fn detect_injection(&self, content: &str) -> Vec<Detection> {
        let mut detections = Vec::new();

        for (name, pattern, severity) in &self.compiled_patterns {
            if let Some(matched) = pattern.find(content) {
                detections.push(Detection {
                    name: name.clone(),
                    severity: severity.clone(),
                    matched: pattern.captures_iter(content).map(|c| c[0].to_string()).collect(),
                });
            }
        }

        detections
    }

    /// 处理注入检测
    fn handle_injection(&self, detections: &[Detection], message: &mut InputMessage) -> &str {
        let high_severity = detections.iter().any(|d| d.severity == "high");

        if high_severity && self.config.injection.on_detect == "block" {
            tracing::warn!("Blocked injection: {:?}", detections);
            return "skip";
        }

        if self.config.injection.on_detect == "sanitize" {
            // 消毒处理
            for detection in detections {
                message.content = self.filter_content(message.content.clone());
            }
            return "sanitize";
        }

        "allow"
    }

    /// 内容过滤
    fn filter_content(&self, content: String) -> String {
        if !self.config.content_filter.enable {
            return content;
        }

        let mut result = content;
        for pattern in &self.config.content_filter.blocklist {
            if let Ok(regex) = Regex::new(pattern) {
                result = regex.replace_all(&result, self.config.content_filter.replacement.as_str()).to_string();
            }
        }
        result
    }

    /// 移除敏感信息
    fn redact_sensitive(&self, content: String, leakage: &LeakagePrevention) -> String {
        let mut result = content;
        for pattern in &leakage.blocked_output_patterns {
            if let Ok(regex) = Regex::new(pattern) {
                result = regex.replace_all(&result, leakage.placeholder.as_str()).to_string();
            }
        }
        result
    }
}
```

---

## 7. 权限模型（Permission Model）

### 7.1 设计原则

遵循 **Unix 哲学**，权限模型采用类似 `rwx` 的能力（Capability）设计：

| 原则 | 说明 |
|------|------|
| **最小权限** | 只授予完成任务所需的最小权限集 |
| **能力继承** | 高权限自动包含低权限的能力 |
| **可组合** | 权限可以灵活组合，适应不同场景 |
| **可委托** | 支持权限的委托和回收 |

### 7.2 角色定义

```rust
/// 角色枚举，类比 Unix 用户组
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum Role {
    Owner = 0o700,      // 超级管理员/拥有者
    Admin = 0o600,       // 普通管理员
    Member = 0o400,     // 普通成员
    Guest = 0o100,      // 访客（受限）
    Blocked = 0o000,    // 被封禁
}

bitflags::bitflags! {
    /// 权限枚举，类比 rwx
    pub struct Permission: u16 {
        // 基础权限
        const READ = 0o400;           // 读取权限
        const WRITE = 0o200;           // 写入权限
        const EXECUTE = 0o100;        // 执行权限

        // 消息权限
        const SEND_MESSAGE = 0o040;    // 发送消息
        const SEND_MEDIA = 0o020;      // 发送媒体
        const SEND_COMMAND = 0o010;    // 发送命令

        // 管理权限
        const MANAGE_MEMBER = 0o004;   // 管理成员
        const MANAGE_CONFIG = 0o002;   // 管理配置
        const MANAGE_PERMISSION = 0o001;  // 管理权限

        // 特殊权限
        const BOT_ADMIN = 0o700;      // Bot 管理员（全权限）
        const OWNER_ONLY = 0o100;     // 仅拥有者可用
    }
}

impl Role {
    /// 检查角色是否拥有指定权限
    pub fn has_permission(&self, permission: Permission) -> bool {
        let role_bits = self.bits();
        (role_bits & permission.bits()) == permission.bits()
    }

    /// 获取角色的权限位
    fn bits(&self) -> u16 {
        *self as u16
    }
}
```

### 7.3 能力矩阵

```
┌──────────────────┬───────┬───────┬────────┬────────┬──────────┐
│ 能力              │ OWNER │ ADMIN │ MEMBER │ GUEST │ BLOCKED  │
├──────────────────┼───────┼───────┼────────┼────────┼──────────┤
│ 读取消息          │   ✓   │   ✓   │   ✓    │   ✓   │    ✗    │
│ 发送普通消息      │   ✓   │   ✓   │   ✓    │   ✓   │    ✗    │
│ 发送媒体          │   ✓   │   ✓   │   ✓    │   ✗   │    ✗    │
│ 发送斜杠命令      │   ✓   │   ✓   │   ✓    │   ✗   │    ✗    │
│ 使用管理员命令    │   ✓   │   ✓   │   ✗    │   ✗   │    ✗    │
│ 管理成员          │   ✓   │   ✓   │   ✗    │   ✗   │    ✗    │
│ 修改配置          │   ✓   │   ✗   │   ✗    │   ✗   │    ✗    │
│ 转让所有权        │   ✓   │   ✗   │   ✗    │   ✗   │    ✗    │
│ 踢出 Bot         │   ✓   │   ✗   │   ✗    │   ✗   │    ✗    │
└──────────────────┴───────┴───────┴────────┴────────┴──────────┘
```

### 7.4 权限检查流程

```rust
use async_trait::async_trait;

#[async_trait]
pub trait PermissionCheck {
    async fn check_message(
        &self,
        event: &InputMessage,
        context: &AgentContext,
    ) -> PermissionResult;
}

pub struct PermissionMiddleware {
    role_config: RoleConfig,
    command_permissions: HashMap<String, Permission>,
}

#[derive(Debug)]
pub struct PermissionResult {
    pub allowed: bool,
    pub reason: Option<String>,
}

impl PermissionMiddleware {
    /// 检查消息权限
    async fn check_message(
        &self,
        event: &InputMessage,
        context: &AgentContext,
    ) -> PermissionResult {
        // 1. 获取发送者角色
        let role = self
            .get_user_role(&event.user_id, &event.conversation_id)
            .await;

        // 2. 检查基础消息权限
        if !role.has_permission(Permission::SEND_MESSAGE) {
            return PermissionResult {
                allowed: false,
                reason: Some("用户被禁止发送消息".into()),
            };
        }

        // 3. 检查媒体权限
        if event.has_media && !role.has_permission(Permission::SEND_MEDIA) {
            return PermissionResult {
                allowed: false,
                reason: Some("用户被禁止发送媒体".into()),
            };
        }

        // 4. 检查命令权限
        if event.is_command {
            let cmd_perm = self
                .command_permissions
                .get(&event.command_name)
                .copied()
                .unwrap_or(Permission::EXECUTE);

            if !role.has_permission(cmd_perm) {
                return PermissionResult {
                    allowed: false,
                    reason: Some(format!("用户无权执行命令: {}", event.command_name)),
                };
            }
        }

        PermissionResult { allowed: true, reason: None }
    }
}
```

### 7.5 命令权限配置

```yaml
# agent.yaml
permissions:
  # 默认角色权限
  default_role: "member"

  # 角色能力定义
  roles:
    owner:
      capabilities: 0o700
      inherits: ["admin"]

    admin:
      capabilities: 0o600
      inherits: ["member"]

    member:
      capabilities: 0o400
      inherits: ["guest"]

    guest:
      capabilities: 0o100
      inherits: []

    blocked:
      capabilities: 0o000
      inherits: []

  # 斜杠命令权限
  commands:
    # 公开命令（所有人均可使用）
    public:
      - "/help"
      - "/status"
      - "/ping"

    # 成员命令（member 及以上）
    member:
      - "/search"
      - "/weather"
      - "/translate"

    # 管理员命令（admin 及以上）
    admin:
      - "/kick"
      - "/ban"
      - "/mute"
      - "/warn"
      - "/config"

    # 拥有者命令（仅 owner）
    owner:
      - "/transfer"
      - "/delete"
      - "/backup"
      - "/reload"

  # 权限继承配置
  inheritance:
    enabled: true
    max_depth: 5  # 最大继承深度，防止循环
```

### 7.6 用户角色管理

```rust
#[async_trait]
pub trait RoleManager: Send + Sync {
    /// 获取用户在特定会话中的角色
    async fn get_role(
        &self,
        user_id: &str,
        conversation_id: &str,
    ) -> Role;

    /// 设置用户角色（需要相应权限）
    async fn set_role(
        &self,
        user_id: &str,
        conversation_id: &str,
        role: Role,
        operator_id: &str,
    ) -> Result<(), PermissionDenied>;

    /// 转让所有权
    async fn transfer_ownership(
        &self,
        conversation_id: &str,
        new_owner_id: &str,
    ) -> Result<(), PermissionDenied>;
}

pub struct SqliteRoleManager {
    pool: SqlitePool,
}

#[derive(Debug, thiserror::Error)]
pub enum PermissionDenied {
    #[error("权限不足: {0}")]
    Insufficient(String),
    #[error("无法设置比自己更高的权限")]
    CannotElevate,
}

#[async_trait]
impl RoleManager for SqliteRoleManager {
    async fn get_role(
        &self,
        user_id: &str,
        conversation_id: &str,
    ) -> Role {
        // 1. 检查全局管理员
        if self.is_global_admin(user_id).await {
            return Role::Owner;
        }

        // 2. 检查会话特定角色
        if let Some(role_data) = self.storage.get_user_role(user_id, conversation_id).await {
            return Role::from_bits(role_data.role);
        }

        // 3. 返回默认角色
        Role::Member
    }

    async fn set_role(
        &self,
        user_id: &str,
        conversation_id: &str,
        role: Role,
        operator_id: &str,
    ) -> Result<(), PermissionDenied> {
        let operator_role = self.get_role(operator_id, conversation_id).await;

        // 检查操作者权限
        if role.bits() > operator_role.bits() {
            return Err(PermissionDenied::CannotElevate);
        }

        self.storage
            .set_user_role(user_id, conversation_id, role.bits())
            .await;

        Ok(())
    }
}
```

### 7.7 会话级权限配置

```rust
#[derive(Debug, Clone)]
pub struct ConversationPermissions {
    pub conversation_id: String,

    // 基础权限
    pub default_role: Role,
    pub allow_guest_read: bool,
    pub allow_guest_send: bool,

    // 功能开关
    pub allow_media: bool,
    pub allow_commands: bool,
    pub allow_ai_responses: bool,

    // 限制
    pub max_message_length: usize,
    pub max_messages_per_minute: usize,
    pub max_commands_per_minute: usize,

    // 白名单/黑名单
    pub whitelist: Vec<String>,
    pub blacklist: Vec<String>,
}

impl ConversationPermissions {
    /// 检查用户是否允许执行操作
    pub fn check_user_allowed(&self, user_id: &str, permission: Permission) -> bool {
        if self.blacklist.contains(&user_id.to_string()) {
            return false;
        }

        if !self.whitelist.is_empty() && !self.whitelist.contains(&user_id.to_string()) {
            return false;
        }

        true
    }
}
```

### 7.8 权限事件

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionEvent {
    RoleChanged,
    PermissionDenied,
    UserBanned,
    UserUnbanned,
    CommandBlocked,
    OwnershipTransferred,
}

#[derive(Debug, Clone)]
pub struct PermissionAuditLog {
    pub event: PermissionEvent,
    pub operator_id: String,
    pub target_id: String,
    pub conversation_id: String,
    pub details: HashMap<String, String>,
    pub timestamp: i64,
}
```

### 7.9 与 Unix 的类比

```
┌─────────────────┬────────────────────────┐
│ Unix 概念        │ AstrBot 对应          │
├─────────────────┼────────────────────────┤
│ 用户 (User)      │ 用户 (User)           │
│ 用户组 (Group)   │ 会话 (Conversation)   │
│ root 用户        │ Owner (拥有者)        │
│ sudo 用户       │ Admin (管理员)        │
│ 普通用户        │ Member (成员)         │
│ 访客            │ Guest (访客)          │
│ 文件权限 rwx     │ 能力 (Capability)     │
│ chmod           │ set_role              │
│ chown           │ transfer_ownership     │
│ /etc/passwd    │ Role Storage          │
└─────────────────┴────────────────────────┘
```

---

## 8. 输出缓冲区（Output Buffer）

### 8.1 队列结构

```rust
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use tokio::sync::mpsc;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputMessage {
    pub session_id: String,
    pub content: OutputContent,
    pub format: OutputFormat,
    pub strategy: OutputStrategy,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OutputContent {
    Text(String),
    Stream(mpsc::Receiver<String>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OutputFormat {
    Plain,
    Markdown,
    Html,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OutputStrategy {
    Streaming,
    Segmented,
    Full,
}

pub struct ResultQueue {
    pub session_id: String,
    results: VecDeque<OutputMessage>,
    max_size: usize,
    allow_streaming: bool,
}

impl ResultQueue {
    pub fn new(session_id: String) -> Self {
        Self {
            session_id,
            results: VecDeque::new(),
            max_size: 100,
            allow_streaming: true,
        }
    }

    pub fn push(&mut self, msg: OutputMessage) {
        if self.results.len() >= self.max_size {
            self.results.pop_front();
        }
        self.results.push_back(msg);
    }

    pub fn pop(&mut self) -> Option<OutputMessage> {
        self.results.pop_front()
    }

    pub fn len(&self) -> usize {
        self.results.len()
    }
}
```

### 8.2 输出策略

```yaml
# agent.yaml
output:
  # 默认输出策略
  default_strategy: "streaming"  # streaming | segmented | full

  # 流式配置
  streaming:
    # 启用流式
    enable: true

    # 流式 Chunk 大小（字符数）
    chunk_size: 20

    # Chunk 之间的间隔（秒）
    chunk_interval: 0.05

  # 智能分段配置
  segmented:
    # 启用智能分段
    enable: true

    # 触发分段的字数阈值
    threshold: 500

    # 分段方式
    mode: "sentence"  # sentence | word_count | regex

    # 按句子分段时的最小长度
    min_segment_length: 50

    # 分段正则（当 mode=regex）
    split_regex: "[。！？；\n]+"

    # 段落之间的随机间隔（秒）
    random_interval: "0.5,2.0"

    # 是否在分段前添加省略号
    add_ellipsis: true

  # 平台适配
  platform_adaptation:
    # 平台与策略映射
    strategy_by_platform:
      telegram: "segmented"    # Telegram 有字数限制
      discord: "segmented"     # Discord 也有限制
      qq: "segmented"
      webchat: "streaming"     # WebChat 支持流式

    # 平台消息长度限制
    max_length_by_platform:
      telegram: 4096
      discord: 2000
      qq: 500

  # 输出缓冲配置
  buffer:
    # 最大缓冲消息数
    max_size: 100

    # 消息最大存活时间（秒）
    max_age: 300

    # 溢出策略
    overflow_strategy: "drop_oldest"
```

### 8.3 分段器实现

```rust
use regex::Regex;
use std::time::Duration;

pub struct SmartSegmenter {
    config: SegmentedConfig,
}

impl SmartSegmenter {
    pub fn new(config: SegmentedConfig) -> Self {
        Self { config }
    }

    /// 将内容分段
    pub fn segment(&self, content: &str) -> Vec<String> {
        if content.len() < self.config.threshold {
            return vec![content.to_string()];
        }

        match self.config.mode.as_str() {
            "sentence" => self.split_by_sentence(content),
            "word_count" => self.split_by_word_count(content),
            "regex" => self.split_by_regex(content),
            _ => vec![content.to_string()],
        }
    }

    /// 按句子分段
    fn split_by_sentence(&self, content: &str) -> Vec<String> {
        let regex = Regex::new(&self.config.split_regex).unwrap_or_else(|_| Regex::new("").unwrap());
        let sentences: Vec<&str> = regex.split(content).collect();

        let mut segments = Vec::new();
        let mut current = Vec::new();
        let mut current_len = 0;

        for sentence in sentences {
            if sentence.trim().is_empty() {
                continue;
            }

            current.push(sentence);
            current_len += sentence.len();

            if current_len >= self.config.threshold {
                let segment = current.join("");
                let segment = if self.config.add_ellipsis && !segments.is_empty() {
                    format!("...{}", segment.trim_start())
                } else {
                    segment
                };
                segments.push(segment);
                current.clear();
                current_len = 0;
            }
        }

        // 处理剩余内容
        if !current.is_empty() {
            let remaining = current.join("");
            if !remaining.trim().is_empty() {
                let remaining = if self.config.add_ellipsis && !segments.is_empty() {
                    format!("...{}", remaining.trim_start())
                } else {
                    remaining
                };
                segments.push(remaining);
            }
        }

        segments
    }

    /// 按字数分段
    fn split_by_word_count(&self, content: &str) -> Vec<String> {
        let chars: Vec<char> = content.chars().collect();
        let mut segments = Vec::new();
        let mut current = String::new();

        for c in chars {
            current.push(c);
            if current.len() >= self.config.threshold {
                segments.push(current.clone());
                current.clear();
            }
        }

        if !current.is_empty() {
            segments.push(current);
        }

        segments
    }

    /// 按正则分段
    fn split_by_regex(&self, content: &str) -> Vec<String> {
        let regex = Regex::new(&self.config.split_regex).unwrap_or_else(|_| Regex::new("").unwrap());
        regex.split(content).map(|s| s.to_string()).collect()
    }

    /// 生成随机间隔
    fn random_interval(&self) -> Duration {
        let parts: Vec<f64> = self.config
            .random_interval
            .split(',')
            .filter_map(|s| s.trim().parse().ok())
            .collect();

        if parts.len() >= 2 {
            let min = parts[0];
            let max = parts[1];
            let duration = min + (max - min) * rand::random::<f64>();
            Duration::from_secs_f64(duration)
        } else {
            Duration::from_millis(500)
        }
    }
}
```

### 8.4 流式输出器

```rust
pub struct StreamingOutput {
    config: StreamingConfig,
}

impl StreamingOutput {
    pub fn new(config: StreamingConfig) -> Self {
        Self { config }
    }

    /// 流式输出内容
    pub async fn stream<F, Fut>(&self, content: &str, mut sender: F)
    where
        F: FnMut(String) -> Fut,
        Fut: Future<Output = ()>,
    {
        let mut start = 0;
        let bytes = content.as_bytes();

        while start < bytes.len() {
            let end = (start + self.config.chunk_size).min(bytes.len());
            let chunk = String::from_utf8_lossy(&bytes[start..end]).to_string();

            sender(chunk).await;
            start = end;

            // 添加短暂间隔
            if start < bytes.len() {
                tokio::time::sleep(self.config.chunk_interval).await;
            }
        }
    }

    /// 创建流式迭代器
    pub fn create_stream(&self, content: String) -> impl Stream<Item = String> {
        struct StreamIter {
            content: String,
            chunk_size: usize,
            chunk_interval: Duration,
            current: usize,
        }

        impl Stream for StreamIter {
            type Item = String;

            fn poll_next(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<String>> {
                let this = &mut *self;

                if this.current >= this.content.len() {
                    return Poll::Ready(None);
                }

                let end = (this.current + this.chunk_size).min(this.content.len());
                let chunk = this.content[this.current..end].to_string();
                this.current = end;

                // Schedule next chunk after interval
                let interval = this.chunk_interval;
                let _ = cx; // suppress unused warning

                Poll::Ready(Some(chunk))
            }
        }

        StreamIter {
            content,
            chunk_size: self.config.chunk_size,
            chunk_interval: self.config.chunk_interval,
            current: 0,
        }
    }
}
```

---

## 9. 记忆管理（Memory Management）

### 9.1 记忆存储配置

```yaml
# agent.yaml
memory:
  # 记忆存储类型
  backend: "sqlite"  # sqlite | redis | memory

  # SQLite 配置
  sqlite:
    path: "$XDG_DATA_HOME/astrbot/state/memory.db"

  # Redis 配置
  redis:
    host: "localhost"
    port: 6379
    db: 0
    prefix: "astrbot:memory:"

  # 记忆保留策略
  retention:
    # 工作记忆：保留在数据库中的时间（天）
    working_memory_days: 7

    # 长期记忆：超过后转为归档
    long_term_threshold_days: 30

    # 自动摘要阈值（对话轮数）
    auto_summary_threshold: 50

    # 每次摘要保留的关键信息数
    summary_keep_key_points: 5

  # 上下文窗口内的记忆
  context_window:
    # 保留最近 N 轮对话的完整记忆
    recent_rounds: 10

    # 超出后转为摘要
    summarize_beyond: true
```

### 9.2 记忆类型

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MemoryType {
    Working,   // 工作记忆（当前会话）
    Episodic,  // 情景记忆（历史事件）
    Semantic,  // 语义记忆（持久知识）
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub id: String,
    #[serde(rename = "type")]
    pub memory_type: MemoryType,
    pub content: String,
    pub embedding: Option<Vec<f32>>,
    pub metadata: HashMap<String, String>,
    pub created_at: f64,
    pub updated_at: f64,
    pub access_count: u32,
    pub importance: f32,  // 0-1 重要性评分
}

impl MemoryEntry {
    pub fn new(memory_type: MemoryType, content: String) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();

        Self {
            id: uuid::Uuid::new_v4().to_string(),
            memory_type,
            content,
            embedding: None,
            metadata: HashMap::new(),
            created_at: now,
            updated_at: now,
            access_count: 0,
            importance: 0.5,
        }
    }
}

pub struct MemoryBank {
    config: MemoryConfig,
    backend: Box<dyn MemoryBackend>,
    cache: HashMap<String, Vec<MemoryEntry>>,
    cache_max_size: usize,
}

impl MemoryBank {
    pub fn new(config: MemoryConfig, backend: Box<dyn MemoryBackend>) -> Self {
        Self {
            config,
            backend,
            cache: HashMap::new(),
            cache_max_size: 100,
        }
    }

    /// 添加记忆
    pub async fn add(&mut self, message: &Message) -> Result<()> {
        let entry = MemoryEntry {
            id: uuid::Uuid::new_v4().to_string(),
            memory_type: MemoryType::Episodic,
            content: message.content.clone(),
            metadata: {
                let mut m = HashMap::new();
                m.insert("role".to_string(), message.role.clone());
                if let Some(user_id) = message.metadata.get("user_id") {
                    m.insert("user_id".to_string(), user_id.clone());
                }
                if let Some(session_id) = message.metadata.get("session_id") {
                    m.insert("session_id".to_string(), session_id.clone());
                }
                m
            },
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            updated_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            access_count: 0,
            importance: 0.5,
        };

        self.backend.save(entry).await
    }

    /// 搜索记忆
    pub async fn search(
        &mut self,
        query: &str,
        limit: usize,
        memory_types: Option<Vec<MemoryType>>,
    ) -> Result<Vec<MemoryEntry>> {
        // 1. 如果有缓存，直接返回
        let cache_key = format!("{}:{}", query, limit);
        if let Some(cached) = self.cache.get(&cache_key) {
            return Ok(cached.clone());
        }

        // 2. 向量搜索
        let mut results = self.backend.search(query, limit, memory_types).await?;

        // 3. 更新访问计数
        for entry in &mut results {
            entry.access_count += 1;
            let _ = self.backend.update(entry.clone()).await;
        }

        // 4. 缓存 (LRU淘汰)
        if self.cache.len() >= self.cache_max_size {
            if let Some((key, _)) = self.cache.iter()
                .min_by(|(_, a), (_, b)| a[0].access_count.cmp(&b[0].access_count))
            {
                self.cache.remove(key);
            }
        }

        self.cache.insert(cache_key, results.clone());
        Ok(results)
    }

    /// 摘要旧记忆
    pub async fn summarize_old(&mut self, before_timestamp: f64) -> Result<String> {
        // 1. 获取指定时间前的记忆
        let entries = self.backend.get_before(before_timestamp).await?;

        if entries.is_empty() {
            return Ok(String::new());
        }

        // 2. 构建摘要
        let summary_prompt = format!(
            "请简洁总结以下对话要点：\n\n{}\n\n保留关键信息：\n- 主要话题或问题\n- 已确定的结论或方案\n- 未完成的任务",
            entries.iter()
                .map(|e| format!("- {}", e.content))
                .collect::<Vec<_>>()
                .join("\n")
        );

        // 3. 调用 LLM 摘要
        let summary = self.llm_summarize(&summary_prompt).await?;

        // 4. 创建摘要记忆
        let summary_entry = MemoryEntry {
            id: uuid::Uuid::new_v4().to_string(),
            memory_type: MemoryType::Semantic,
            content: summary.clone(),
            metadata: {
                let mut m = HashMap::new();
                m.insert("original_entries".to_string(), entries.len().to_string());
                m
            },
            created_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            updated_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            access_count: 0,
            importance: 0.7,
        };

        self.backend.save(summary_entry).await?;

        // 5. 删除原始记忆
        for entry in &entries {
            let _ = self.backend.delete(&entry.id).await;
        }

        Ok(summary)
    }
}
```

---

## 10. 平台适配（Platform Adaptation）

### 10.1 平台特性

```rust
#[derive(Debug, Clone)]
pub struct PlatformCapabilities {
    pub supports_streaming: bool,
    pub max_message_length: usize,
    pub supports_markdown: bool,
    pub supports_html: bool,
    pub supports_images: bool,
    pub supports_mentions: bool,
    pub supports_reply: bool,
    pub rate_limit_rpm: u32,
    pub rate_limit_rpd: u32,
}

impl Default for PlatformCapabilities {
    fn default() -> Self {
        Self {
            supports_streaming: false,
            max_message_length: 4096,
            supports_markdown: true,
            supports_html: false,
            supports_images: true,
            supports_mentions: true,
            supports_reply: true,
            rate_limit_rpm: 60,
            rate_limit_rpd: 10000,
        }
    }
}

pub static PLATFORM_CAPABILITIES: Lazy<HashMap<&'static str, PlatformCapabilities>> =
    Lazy::new(|| {
        let mut m = HashMap::new();
        m.insert("telegram", PlatformCapabilities {
            supports_streaming: false,
            max_message_length: 4096,
            supports_markdown: true,
            supports_html: true,
            ..Default::default()
        });
        m.insert("discord", PlatformCapabilities {
            supports_streaming: false,
            max_message_length: 2000,
            supports_markdown: true,
            supports_html: false,
            supports_reply: true,
            ..Default::default()
        });
        m.insert("qq", PlatformCapabilities {
            supports_streaming: false,
            max_message_length: 500,
            supports_markdown: false,
            supports_mentions: true,
            ..Default::default()
        });
        m.insert("webchat", PlatformCapabilities {
            supports_streaming: true,
            max_message_length: 10000,
            supports_markdown: true,
            supports_html: true,
            ..Default::default()
        });
        m
    });
```

### 10.2 策略选择器

```rust
pub struct PlatformStrategySelector {
    config: PlatformAdaptationConfig,
    capabilities: &'static HashMap<&'static str, PlatformCapabilities>,
}

impl PlatformStrategySelector {
    pub fn new(config: PlatformAdaptationConfig) -> Self {
        Self {
            config,
            capabilities: &PLATFORM_CAPABILITIES,
        }
    }

    /// 选择输出策略
    pub fn select_strategy(
        &self,
        platform: &str,
        content_length: usize,
        user_preference: Option<&str>,
    ) -> OutputStrategy {
        let caps = self.capabilities.get(platform);

        // 1. 用户偏好优先
        if let Some(pref) = user_preference {
            if self.is_valid_strategy(pref, caps) {
                return OutputStrategy::from_str(pref);
            }
        }

        // 2. 平台能力判断
        let caps = match caps {
            Some(c) => c,
            None => return OutputStrategy::Full,
        };

        // 3. 平台配置覆盖
        if let Some(platform_strategy) = self.config.strategy_by_platform.get(platform) {
            return OutputStrategy::from_str(platform_strategy);
        }

        // 4. 内容长度判断
        if content_length > caps.max_message_length {
            return OutputStrategy::Segmented;
        }

        // 5. 流式支持判断
        if caps.supports_streaming {
            return OutputStrategy::Streaming;
        }

        OutputStrategy::Full
    }

    fn is_valid_strategy(&self, strategy: &str, caps: Option<&PlatformCapabilities>) -> bool {
        let strategy = OutputStrategy::from_str(strategy);
        match (strategy, caps) {
            (OutputStrategy::Streaming, Some(c)) => c.supports_streaming,
            (OutputStrategy::Segmented, Some(_)) => true,
            (OutputStrategy::Full, _) => true,
            _ => false,
        }
    }
}
```

---

## 11. 配置汇总

### 11.1 agent.yaml 完整配置

```yaml
# Agent 配置

# 输入缓冲区
input_buffer:
  max_queue_size: 1000
  max_message_age: 3600
  overflow_strategy: "drop_oldest"
  overflow_hint: "[消息过多，部分早期消息已丢弃]"

# 流控
flow_control:
  mode: "auto"
  auto:
    api_rpm_limit: 60
    messages_per_request: 5
    safety_margin: 0.8
    min_interval: 0.5
    max_interval: 10

# 上下文
context:
  max_context_tokens: 128000
  compress_threshold: 0.85
  keep_recent_messages: 6
  compress_instruction: |
    请简洁地总结对话要点...

# 工具调用
tool_calling:
  strategy: "smart"
  max_calls_per_request: 128
  timeout: 60
  max_retries: 3
  parallel_calls: true
  max_parallel_calls: 5

# 安全
security:
  injection:
    enable: true
    mode: "strict"
    patterns: [...]
    on_detect: "sanitize"
  content_filter:
    enable: true
    level: "standard"
    replacement: "[已过滤]"
  leakage_prevention:
    blocked_file_patterns: [...]
    blocked_output_patterns: [...]
    placeholder: "[REDACTED]"

# 输出
output:
  default_strategy: "streaming"
  streaming:
    chunk_size: 20
    chunk_interval: 0.05
  segmented:
    enable: true
    threshold: 500
    mode: "sentence"
    split_regex: "[。！？；\n]+"
    random_interval: "0.5,2.0"
    add_ellipsis: true
  platform_adaptation:
    strategy_by_platform:
      telegram: "segmented"
      discord: "segmented"
      webchat: "streaming"
    max_length_by_platform:
      telegram: 4096
      discord: 2000

# 记忆
memory:
  backend: "sqlite"
  sqlite:
    path: "$XDG_DATA_HOME/astrbot/state/memory.db"
  retention:
    working_memory_days: 7
    auto_summary_threshold: 50
  context_window:
    recent_rounds: 10
```

---

## 12. 错误处理与恢复

### 12.1 错误分类

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorType {
    RateLimit,   // 限流
    Timeout,     // 超时
    Network,     // 网络错误
    Api,         // API 错误
    Tool,        // 工具错误
    Security,    // 安全错误
    Internal,    // 内部错误
}

impl ErrorType {
    pub fn as_str(&self) -> &'static str {
        match self {
            ErrorType::RateLimit => "rate_limit",
            ErrorType::Timeout => "timeout",
            ErrorType::Network => "network",
            ErrorType::Api => "api",
            ErrorType::Tool => "tool",
            ErrorType::Security => "security",
            ErrorType::Internal => "internal",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ErrorRecoveryConfig {
    pub max_retries: HashMap<ErrorType, u32>,
    pub backoff_multiplier: f64,
    pub max_backoff: f64,
}

impl Default for ErrorRecoveryConfig {
    fn default() -> Self {
        let mut max_retries = HashMap::new();
        max_retries.insert(ErrorType::RateLimit, 5);
        max_retries.insert(ErrorType::Timeout, 3);
        max_retries.insert(ErrorType::Network, 3);
        max_retries.insert(ErrorType::Api, 2);
        max_retries.insert(ErrorType::Tool, 2);
        max_retries.insert(ErrorType::Security, 0);
        max_retries.insert(ErrorType::Internal, 1);

        Self {
            max_retries,
            backoff_multiplier: 1.5,
            max_backoff: 60.0,
        }
    }
}
```

### 12.2 错误处理策略

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorAction {
    Retry,
    Fail,
    Block,
    Fallback,
}

/// 处理错误并决定下一步行动
pub async fn handle_error(
    error: &dyn std::error::Error,
    context: &mut AgentContext,
    config: &ErrorRecoveryConfig,
    flow_control: &mut Option<&mut FlowControl>,
) -> ErrorAction {
    let error_type = classify_error(error);
    let retries_key = format!("retry_{}", error_type.as_str());
    let retries = context.metadata.get(&retries_key).and_then(|v| v.parse().ok()).unwrap_or(0);

    let max_retries = config.max_retries.get(&error_type).copied().unwrap_or(0);

    if retries >= max_retries {
        return ErrorAction::Fail;
    }

    // 指数退避
    if retries > 0 {
        let backoff = (config.backoff_multiplier.powi(retries as i32)).min(config.max_backoff);
        tokio::time::sleep(tokio::time::Duration::from_secs_f64(backoff)).await;
    }

    context.metadata.insert(retries_key, (retries + 1).to_string());

    match error_type {
        ErrorType::RateLimit => {
            // 更新流控配置
            if let Some(fc) = flow_control {
                fc.decrease_rate(0.8);
            }
            ErrorAction::Retry
        }
        ErrorType::Security => {
            // 安全错误不重试
            ErrorAction::Block
        }
        ErrorType::Api => {
            // API 错误，检查是否可恢复
            if is_retryable_api_error(error) {
                ErrorAction::Retry
            } else {
                ErrorAction::Fail
            }
        }
        _ => ErrorAction::Retry,
    }
}

fn classify_error(error: &dyn std::error::Error) -> ErrorType {
    let msg = error.to_string().to_lowercase();

    if msg.contains("rate limit") || msg.contains("too many requests") {
        ErrorType::RateLimit
    } else if msg.contains("timeout") {
        ErrorType::Timeout
    } else if msg.contains("network") || msg.contains("connection") {
        ErrorType::Network
    } else if msg.contains("api") {
        ErrorType::Api
    } else if msg.contains("tool") {
        ErrorType::Tool
    } else if msg.contains("security") || msg.contains("injection") {
        ErrorType::Security
    } else {
        ErrorType::Internal
    }
}

fn is_retryable_api_error(error: &dyn std::error::Error) -> bool {
    let msg = error.to_string().to_lowercase();
    // 5xx 错误可重试，4xx 通常不行
    msg.contains("500") || msg.contains("502") || msg.contains("503") || msg.contains("504")
}
```

---

## 13. 扩展点

### 13.1 插件扩展点

```rust
// 输入处理扩展
#[async_trait]
pub trait InputBufferPlugin: Send + Sync {
    /// 消息添加前拦截，返回 None 表示跳过
    async fn pre_add_message(&self, message: InputMessage) -> Option<InputMessage>;

    /// 消息添加后处理
    async fn post_add_message(&self, message: &InputMessage) {}
}

// 输出处理扩展
#[async_trait]
pub trait OutputBufferPlugin: Send + Sync {
    /// 消息发送前拦截
    async fn pre_send_message(&self, message: OutputMessage) -> Option<OutputMessage>;

    /// 消息发送后处理
    async fn post_send_message(&self, message: &OutputMessage) {}
}

// 安全扩展
#[async_trait]
pub trait SecurityPlugin: Send + Sync {
    /// 自定义注入检测
    async fn check_injection(&self, content: &str) -> Vec<SecurityIssue>;

    /// 自定义内容过滤
    async fn filter_content(&self, content: &str) -> String {
        content.to_string()
    }
}
```

### 13.2 调度器扩展

```rust
/// 自定义调度策略
#[async_trait]
pub trait CustomScheduler: Send + Sync {
    /// 选择下一条消息
    async fn select_next_message(
        &self,
        queues: &HashMap<String, UserMessageQueue>,
    ) -> Option<InputMessage>;

    /// 队列为空时的处理
    async fn on_queue_empty(&self, user_id: &str) {}
}
```

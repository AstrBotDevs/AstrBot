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

```python
class ToolRouter:
    """工具路由"""

    def __init__(
        self,
        internal_toolset: ToolSet,
        mcp_clients: dict[str, MCPClient],
        skill_executors: dict[str, SkillExecutor],
    ):
        self.internal = internal_toolset
        self.mcp = mcp_clients
        self.skills = skill_executors

    async def route_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        context: AgentContext,
    ) -> ToolResult:
        """路由工具调用"""

        # 1. 检查内部工具
        internal_tool = self.internal.get_tool(tool_name)
        if internal_tool:
            return await self._call_internal(internal_tool, arguments, context)

        # 2. 检查 MCP 工具
        for client_name, client in self.mcp.items():
            if client.has_tool(tool_name):
                return await client.call_tool(tool_name, arguments)

        # 3. 检查 Skills
        skill = self.skills.get(tool_name)
        if skill:
            return await self._execute_skill(skill, arguments, context)

        raise ToolNotFoundError(f"Tool not found: {tool_name}")
```

### 1.4 Agent 协作（ACP 协议）

```python
class ACPAgentClient:
    """ACP Agent 客户端"""

    async def call_agent(
        self,
        agent_name: str,
        action: str,
        args: dict,
        stream: bool = True,
    ) -> AsyncIterator[AgentEvent] | AgentResult:
        """调用远程 Agent"""

        request = ACPRequest(
            method="agent/call",
            params={
                "agent": agent_name,
                "action": action,
                "args": args,
            }
        )

        if stream:
            return self._stream_request(request)
        else:
            return await self._send_request(request)

    async def list_agents(self) -> list[AgentCard]:
        """列出可用 Agent"""
        response = await self._send_request(
            ACPRequest(method="agent/list")
        )
        return [AgentCard(**a) for a in response.result["agents"]]
```

### 1.5 Skills 执行

```python
class SkillExecutor:
    """Skill 执行器"""

    def __init__(self, skill_registry: SkillRegistry):
        self.registry = skill_registry

    async def execute(
        self,
        skill_name: str,
        input_data: dict,
        context: AgentContext,
    ) -> SkillResult:
        """执行 Skill"""

        skill = self.registry.get(skill_name)
        if not skill:
            raise SkillNotFoundError(f"Skill not found: {skill_name}")

        # Skill 可以包含多个步骤
        steps = skill.get_steps()

        results = []
        for step in steps:
            # 每个步骤可以是工具调用或 Agent 调用
            if step.type == "tool":
                result = await self._call_tool(step.tool, step.args)
            elif step.type == "agent":
                result = await self._call_agent(step.agent, step.action, step.args)
            elif step.type == "llm":
                result = await self._call_llm(step.prompt, context)

            results.append(result)

            # 检查是否需要停止
            if step.on_result == "stop_if_success" and result.success:
                break

        return SkillResult(
            skill_name=skill_name,
            steps=results,
            final_output=results[-1] if results else None,
        )
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

```python
@dataclass
class InputMessage:
    """输入消息单元"""
    message_id: str                    # 全局唯一 ID
    platform: str                      # 平台标识
    user_id: str                      # 用户 ID
    conversation_id: str               # 会话 ID
    content: MessageChain | str        # 消息内容
    timestamp: float                   # 到达时间
    metadata: dict                     # 扩展元数据
    priority: int = 0                 # 优先级（越高越先处理）

@dataclass
class UserMessageQueue:
    """用户消息队列"""
    user_id: str
    session_id: str
    messages: deque[InputMessage]      # 消息列表（有序）
    metadata: dict                     # 用户元数据
    created_at: float
    updated_at: float
    max_size: int = 1000              # 最大消息数
    max_age: float = 3600             # 消息最大存活时间（秒）
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

```python
async def add_message(queue: UserMessageQueue, message: InputMessage) -> None:
    if len(queue.messages) >= queue.max_size:
        if queue.overflow_strategy == "drop_oldest":
            old_msg = queue.messages.popleft()
            # 在丢弃的消息前插入提示
            hint = InputMessage(
                content=f"[{queue.overflow_hint} 丢弃于 {old_msg.timestamp}]",
                message_id="system_hint",
                # ...
            )
            queue.messages.appendleft(hint)
        elif queue.overflow_strategy == "drop_newest":
            return  # 丢弃新消息
        elif queue.overflow_strategy == "block":
            await queue.not_full.wait()  # 阻塞等待
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

```python
class TokenBucket:
    """令牌桶流控"""

    def __init__(
        self,
        rate: float,           # 每秒令牌数
        capacity: float,        # 桶容量
        burst: float = None,    # 突发容量
    ):
        self.rate = rate
        self.capacity = capacity
        self.burst = burst or capacity
        self.tokens = capacity
        self.last_update = time.monotonic()

    async def acquire(self, tokens: float = 1.0) -> float:
        """获取令牌，返回需要等待的秒数"""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0

        wait_time = (tokens - self.tokens) / self.rate
        return wait_time

    async def wait_and_acquire(self, tokens: float = 1.0) -> None:
        """等待直到获取令牌"""
        wait = await self.acquire(tokens)
        if wait > 0:
            await asyncio.sleep(wait)
```

### 3.4 优先级调度

```python
class PriorityScheduler:
    """优先级调度器"""

    def __init__(self, buckets: dict[str, TokenBucket]):
        self.buckets = buckets  # per-user or per-session

    async def next_message(self) -> InputMessage | None:
        """获取下一条待处理消息（按优先级）"""
        # 1. 收集所有非空队列
        candidates = []
        for user_id, queue in self.queues.items():
            if not queue.messages:
                continue

            # 2. 计算该用户的可用速率
            bucket = self.buckets.get(user_id)
            if not bucket:
                continue

            # 3. 获取队首消息（peek，不移除）
            msg = queue.messages[0]

            candidates.append((msg, bucket, user_id))

        if not candidates:
            return None

        # 4. 按优先级 + 可用性排序
        # 优先级相同时，优先处理令牌充足的
        candidates.sort(
            key=lambda x: (
                -x[0].priority,
                x[1].tokens / x[1].rate if x[1].rate > 0 else 0
            )
        )

        # 5. 等待最紧急消息的令牌
        msg, bucket, user_id = candidates[0]
        await bucket.wait_and_acquire(1.0)

        # 6. 移除并返回
        return queue.messages.popleft()
```

---

## 4. Agent 核心（Agent Core）

### 4.1 上下文管理（Context Manager）

```python
@dataclass
class AgentContext:
    """Agent 执行上下文"""
    messages: list[Message]            # 消息历史
    system_prompt: str                 # 系统提示
    tools: list[ToolDefinition]       # 可用工具
    memory: MemoryBank                # 记忆存储
    metadata: dict                     # 扩展元数据

class ContextManager:
    """上下文管理器"""

    def __init__(self, config: ContextConfig):
        self.max_tokens: int = config.max_context_tokens
        self.compress_threshold: float = config.compress_threshold
        self.keep_recent: int = config.keep_recent_messages

    def build_context(
        self,
        queue: UserMessageQueue,
        memory: MemoryBank,
    ) -> AgentContext:
        """构建 Agent 执行上下文"""

        # 1. 从队列获取消息
        raw_messages = list(queue.messages)

        # 2. 应用安全过滤
        raw_messages = self.apply_security_filters(raw_messages)

        # 3. 构建消息列表
        messages = self.build_message_list(raw_messages)

        # 4. 检查是否需要压缩
        total_tokens = self.estimate_tokens(messages)

        if total_tokens > self.max_tokens * self.compress_threshold:
            messages = self.compress_context(messages, memory)

        # 5. 添加系统提示
        system_prompt = self.build_system_prompt()

        return AgentContext(
            messages=messages,
            system_prompt=system_prompt,
            tools=self.get_available_tools(),
            memory=memory,
        )

    def compress_context(
        self,
        messages: list[Message],
        memory: MemoryBank,
    ) -> list[Message]:
        """压缩上下文"""

        # 保留最近 N 条消息
        recent = messages[-self.keep_recent:]

        # 提取历史消息进行压缩
        history = messages[:-self.keep_recent]

        # 摘要历史消息并存入记忆
        if history:
            summary = self.summarize(history)
            memory.add(Message(
                role="system",
                content=f"[历史摘要] {summary}",
                metadata={"type": "summary"}
            ))

        return recent
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

### 4.1 工具调用最佳实践

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

### 4.2 工具调用流程

```python
class ToolCallingPolicy:
    """工具调用策略"""

    async def execute_tools(
        self,
        llm_response: LLMResponse,
        context: AgentContext,
    ) -> list[ToolResult]:
        """执行工具调用"""

        # 1. 解析工具调用请求
        tool_calls = llm_response.tool_calls or []

        if not tool_calls:
            return []

        # 2. 按策略分组
        groups = self._group_by_dependency(tool_calls)

        results = []

        # 3. 按组执行
        for group in groups:
            if self._can_parallel(group):
                # 并行执行
                group_results = await asyncio.gather(
                    *[self._execute_single(call, context) for call in group],
                    return_exceptions=True
                )
            else:
                # 串行执行
                group_results = []
                for call in group:
                    result = await self._execute_single(call, context)
                    group_results.append(result)

            results.extend(group_results)

            # 4. 检查是否超过限制
            if len(results) >= self.config.max_calls_per_request:
                break

            # 5. 如果需要流式中间结果
            if self.config.stream_intermediate:
                yield ToolCallingEvent(
                    type="intermediate",
                    results=group_results
                )

        return results

    def _group_by_dependency(
        self,
        tool_calls: list[ToolCall],
    ) -> list[list[ToolCall]]:
        """按依赖关系分组"""

        groups = []
        current_group = []

        for call in tool_calls:
            # 检查是否依赖前一个工具的结果
            if call.arguments_depends_on_previous and current_group:
                # 依赖：将当前调用加入前一个组
                current_group.append(call)
            else:
                # 不依赖：开启新组
                if current_group:
                    groups.append(current_group)
                current_group = [call]

        if current_group:
            groups.append(current_group)

        return groups
```

### 4.3 工具选择策略

```python
class ToolSelector:
    """工具选择策略"""

    def __init__(self, config: ToolSelectionConfig):
        self.max_tools_per_request = config.max_tools_per_request
        self.prefer_recent = config.prefer_recent_tools

    def select_tools(
        self,
        available_tools: list[Tool],
        query: str,
        context: AgentContext,
    ) -> list[Tool]:
        """选择最相关的工具"""

        # 1. 计算工具与查询的相关性
        scored = []
        for tool in available_tools:
            score = self._calculate_relevance(tool, query, context)
            scored.append((score, tool))

        # 2. 排序并截取
        scored.sort(key=lambda x: -x[0])
        selected = scored[:self.max_tools_per_request]

        # 3. 如果启用了最近使用优先
        if self.prefer_recent:
            selected = self._boost_recent(selected, context)

        return [t for _, t in selected]

    def _calculate_relevance(
        self,
        tool: Tool,
        query: str,
        context: AgentContext,
    ) -> float:
        """计算相关性分数"""

        base_score = 0.0

        # 工具名称匹配
        if any(word in tool.name.lower() for word in query.lower().split()):
            base_score += 0.3

        # 工具描述匹配
        if tool.description:
            # 简单的词重叠计算
            query_words = set(query.lower().split())
            desc_words = set(tool.description.lower().split())
            overlap = len(query_words & desc_words)
            base_score += overlap * 0.1

        # 最近使用过的工具加权
        if context.metadata.get("recent_tools"):
            if tool.name in context.metadata["recent_tools"]:
                base_score += 0.2

        return base_score
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

```python
class SecurityFilter:
    """安全过滤器"""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.compiled_patterns = [
            (p["name"], re.compile(p["regex"]), p["severity"])
            for p in config.injection.patterns
        ]

    def filter_messages(
        self,
        messages: list[InputMessage],
    ) -> list[InputMessage]:
        """过滤输入消息"""

        filtered = []

        for msg in messages:
            # 1. 内容过滤
            if self.config.content_filter.enable:
                msg.content = self._filter_content(msg.content)

            # 2. 注入检测
            if self.config.injection.enable:
                detections = self._detect_injection(msg.content)

                if detections:
                    action = self._handle_injection(detections, msg)
                    if action == "skip":
                        continue

            filtered.append(msg)

        return filtered

    def filter_output(
        self,
        content: str,
        context: AgentContext,
    ) -> str:
        """过滤输出内容"""

        # 1. 泄密防护 - 移除敏感信息
        if self.config.leakage_prevention:
            content = self._redact_sensitive(content)

        return content

    def _detect_injection(self, content: str) -> list[Detection]:
        """检测注入攻击"""
        detections = []

        for name, pattern, severity in self.compiled_patterns:
            if pattern.search(content):
                detections.append(Detection(
                    name=name,
                    severity=severity,
                    matched=pattern.findall(content),
                ))

        return detections

    def _handle_injection(
        self,
        detections: list[Detection],
        message: InputMessage,
    ) -> str:
        """处理注入检测"""

        high_severity = any(d.severity == "high" for d in detections)

        if high_severity and self.config.injection.on_detect == "block":
            # 记录并阻止
            logging.warning(f"Blocked injection: {detections}")
            return "skip"

        elif self.config.injection.on_detect == "sanitize":
            # 消毒处理
            for detection in detections:
                message.content = message.content.replace(
                    detection.matched,
                    self.config.content_filter.replacement,
                )
            return "sanitize"

        return "allow"

    def _filter_content(self, content: str) -> str:
        """内容过滤"""

        if not self.config.content_filter.enable:
            return content

        for pattern in self.config.content_filter.blocklist:
            content = re.sub(pattern, self.config.content_filter.replacement, content)

        return content
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

```python
@dataclass
class OutputMessage:
    """输出消息单元"""
    session_id: str
    content: str | AsyncIterator[str]  # 支持流式
    format: str = "plain"             # plain | markdown | html
    strategy: OutputStrategy = OutputStrategy.FULL
    metadata: dict = field(default_factory=dict)

    # 流式相关
    stream_start_time: float | None = None
    total_sent: int = 0

@dataclass
class ResultQueue:
    """结果队列"""
    session_id: str
    results: deque[OutputMessage]
    max_size: int = 100
    allow_streaming: bool = True

class OutputStrategy(Enum):
    """输出策略"""
    STREAMING = "streaming"      # 流式输出
    SEGMENTED = "segmented"      # 智能分段
    FULL = "full"                 # 一次性输出
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

```python
class SmartSegmenter:
    """智能分段器"""

    def __init__(self, config: SegmentedConfig):
        self.config = config

    def segment(self, content: str) -> list[str]:
        """将内容分段"""

        if len(content) < self.config.threshold:
            return [content]

        if self.config.mode == "sentence":
            return self._split_by_sentence(content)
        elif self.config.mode == "word_count":
            return self._split_by_word_count(content)
        elif self.config.mode == "regex":
            return self._split_by_regex(content)

        return [content]

    def _split_by_sentence(self, content: str) -> list[str]:
        """按句子分段"""
        sentences = re.split(
            self.config.split_regex,
            content,
        )

        segments = []
        current = []

        for sentence in sentences:
            if not sentence.strip():
                continue

            current.append(sentence)
            current_text = "".join(current)

            # 如果当前段落达到阈值
            if len(current_text) >= self.config.threshold:
                segment = "".join(current)
                if self.config.add_ellipsis and len(segments) > 0:
                    segment = "..." + segment.lstrip()
                segments.append(segment)
                current = []

        # 处理剩余内容
        if current:
            remaining = "".join(current)
            if remaining.strip():
                if self.config.add_ellipsis and segments:
                    remaining = "..." + remaining.lstrip()
                segments.append(remaining)

        return segments

    async def stream_segments(
        self,
        content: str,
        output: OutputMessage,
        sender: Callable[[str], Awaitable[None]],
    ) -> None:
        """流式发送分段"""

        segments = self.segment(content)

        for i, segment in enumerate(segments):
            # 发送当前分段
            await sender(segment)

            # 添加间隔（随机）
            if i < len(segments) - 1:
                interval = self._random_interval()
                await asyncio.sleep(interval)

    def _random_interval(self) -> float:
        """生成随机间隔"""
        import random
        parts = self.config.random_interval.split(",")
        return random.uniform(float(parts[0]), float(parts[1]))
```

### 8.4 流式输出器

```python
class StreamingOutput:
    """流式输出器"""

    def __init__(self, config: StreamingConfig):
        self.config = config

    async def stream(
        self,
        content: str,
        sender: Callable[[str], Awaitable[None]],
    ) -> None:
        """流式输出内容"""

        start = 0
        while start < len(content):
            end = start + self.config.chunk_size
            chunk = content[start:end]

            await sender(chunk)

            start = end

            # 添加短暂间隔
            if start < len(content):
                await asyncio.sleep(self.config.chunk_interval)

    def create_stream(
        self,
        content: str,
    ) -> AsyncIterator[str]:
        """创建流式迭代器"""

        async def generator():
            start = 0
            while start < len(content):
                end = start + self.config.chunk_size
                chunk = content[start:end]
                yield chunk
                start = end

                if start < len(content):
                    await asyncio.sleep(self.config.chunk_interval)

        return generator()
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

```python
class MemoryType(Enum):
    """记忆类型"""
    WORKING = "working"      # 工作记忆（当前会话）
    EPISODIC = "episodic"    # 情景记忆（历史事件）
    SEMANTIC = "semantic"    # 语义记忆（持久知识）

@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    type: MemoryType
    content: str
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)
    created_at: float
    updated_at: float
    access_count: int = 0
    importance: float = 0.5  # 0-1 重要性评分

class MemoryBank:
    """记忆库"""

    def __init__(self, config: MemoryConfig):
        self.config = config
        self.backend = self._create_backend(config)
        self._cache: dict[str, MemoryEntry] = {}
        self._cache_max_size = 100

    async def add(self, message: Message) -> None:
        """添加记忆"""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            type=MemoryType.EPISODIC,
            content=message.content,
            metadata={
                "role": message.role,
                "user_id": message.metadata.get("user_id"),
                "session_id": message.metadata.get("session_id"),
            },
            created_at=time.time(),
            updated_at=time.time(),
        )

        await self.backend.save(entry)

    async def search(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemoryEntry]:
        """搜索记忆"""

        # 1. 如果有缓存，直接返回
        cache_key = f"{query}:{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 2. 向量搜索
        results = await self.backend.search(
            query=query,
            limit=limit,
            memory_types=memory_types,
        )

        # 3. 更新访问计数
        for entry in results:
            entry.access_count += 1
            await self.backend.update(entry)

        # 4. 缓存
        if len(self._cache) >= self._cache_max_size:
            # LRU 淘汰
            oldest = min(self._cache.values(), key=lambda x: x.access_count)
            del self._cache[oldest.id]

        self._cache[cache_key] = results

        return results

    async def summarize_old(
        self,
        before_timestamp: float,
    ) -> str:
        """摘要旧记忆"""

        # 1. 获取指定时间前的记忆
        entries = await self.backend.get_before(before_timestamp)

        if not entries:
            return ""

        # 2. 构建摘要
        summary_prompt = f"""请简洁总结以下对话要点：

{chr(10).join(f"- {e.content}" for e in entries)}

保留关键信息：
- 主要话题或问题
- 已确定的结论或方案
- 未完成的任务
"""

        # 3. 调用 LLM 摘要
        summary = await self._llm_summarize(summary_prompt)

        # 4. 创建摘要记忆
        summary_entry = MemoryEntry(
            id=str(uuid.uuid4()),
            type=MemoryType.SEMANTIC,
            content=summary,
            metadata={"original_entries": len(entries)},
            created_at=time.time(),
            updated_at=time.time(),
            importance=0.7,
        )

        await self.backend.save(summary_entry)

        # 5. 删除原始记忆
        for entry in entries:
            await self.backend.delete(entry.id)

        return summary
```

---

## 10. 平台适配（Platform Adaptation）

### 10.1 平台特性

```python
@dataclass
class PlatformCapabilities:
    """平台能力"""
    supports_streaming: bool = False
    max_message_length: int = 4096
    supports_markdown: bool = True
    supports_html: bool = False
    supports_images: bool = True
    supports_mentions: bool = True
    supports_reply: bool = True
    rate_limit_rpm: int = 60
    rate_limit_rpd: int = 10000

PLATFORM_CAPABILITIES = {
    "telegram": PlatformCapabilities(
        supports_streaming=False,
        max_message_length=4096,
        supports_markdown=True,
        supports_html=True,
    ),
    "discord": PlatformCapabilities(
        supports_streaming=False,
        max_message_length=2000,
        supports_markdown=True,
        supports_html=False,
        supports_reply=True,
    ),
    "qq": PlatformCapabilities(
        supports_streaming=False,
        max_message_length=500,
        supports_markdown=False,
        supports_mentions=True,
    ),
    "webchat": PlatformCapabilities(
        supports_streaming=True,
        max_message_length=10000,
        supports_markdown=True,
        supports_html=True,
    ),
}
```

### 10.2 策略选择器

```python
class PlatformStrategySelector:
    """平台策略选择器"""

    def __init__(self, config: PlatformAdaptationConfig):
        self.config = config
        self.capabilities = PLATFORM_CAPABILITIES

    def select_strategy(
        self,
        platform: str,
        content_length: int,
        user_preference: str | None = None,
    ) -> OutputStrategy:
        """选择输出策略"""

        caps = self.capabilities.get(platform)

        # 1. 用户偏好优先
        if user_preference and self._is_valid_strategy(user_preference, caps):
            return OutputStrategy(user_preference)

        # 2. 平台能力判断
        if not caps:
            return OutputStrategy.FULL

        # 3. 平台配置覆盖
        platform_strategy = self.config.strategy_by_platform.get(platform)
        if platform_strategy:
            return OutputStrategy(platform_strategy)

        # 4. 内容长度判断
        if content_length > caps.max_message_length:
            return OutputStrategy.SEGMENTED

        # 5. 流式支持判断
        if caps.supports_streaming:
            return OutputStrategy.STREAMING

        return OutputStrategy.FULL
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

```python
class ErrorType(Enum):
    """错误类型"""
    RATE_LIMIT = "rate_limit"           # 限流
    TIMEOUT = "timeout"                 # 超时
    NETWORK = "network"                 # 网络错误
    API = "api"                         # API 错误
    TOOL = "tool"                       # 工具错误
    SECURITY = "security"               # 安全错误
    INTERNAL = "internal"               # 内部错误

@dataclass
class ErrorRecoveryConfig:
    """错误恢复配置"""
    max_retries: dict[ErrorType, int] = field(default_factory=lambda: {
        ErrorType.RATE_LIMIT: 5,
        ErrorType.TIMEOUT: 3,
        ErrorType.NETWORK: 3,
        ErrorType.API: 2,
        ErrorType.TOOL: 2,
        ErrorType.SECURITY: 0,
        ErrorType.INTERNAL: 1,
    })

    backoff_multiplier: float = 1.5
    max_backoff: float = 60.0
```

### 12.2 错误处理策略

```python
async def handle_error(
    error: Exception,
    context: AgentContext,
    config: ErrorRecoveryConfig,
) -> ErrorAction:
    """处理错误并决定下一步行动"""

    error_type = classify_error(error)
    retries = context.metadata.get(f"retry_{error_type.value}", 0)

    if retries >= config.max_retries.get(error_type, 0):
        return ErrorAction.FAIL

    # 指数退避
    if retries > 0:
        backoff = min(
            config.backoff_multiplier ** retries,
            config.max_backoff
        )
        await asyncio.sleep(backoff)

    context.metadata[f"retry_{error_type.value}"] = retries + 1

    if error_type == ErrorType.RATE_LIMIT:
        # 更新流控配置
        flow_control.decrease_rate(0.8)
        return ErrorAction.RETRY

    elif error_type == ErrorType.SECURITY:
        # 安全错误不重试
        return ErrorAction.BLOCK

    elif error_type == ErrorType.API:
        # API 错误，检查是否可恢复
        if is_retryable_api_error(error):
            return ErrorAction.RETRY
        return ErrorAction.FAIL

    return ErrorAction.RETRY

class ErrorAction(Enum):
    """错误处理动作"""
    RETRY = "retry"
    FAIL = "fail"
    BLOCK = "block"
    FALLBACK = "fallback"
```

---

## 13. 扩展点

### 13.1 插件扩展点

```python
# 输入处理扩展
class InputBufferPlugin(ABC):
    """输入缓冲区插件"""

    async def pre_add_message(
        self,
        message: InputMessage,
    ) -> InputMessage | None:
        """消息添加前拦截，返回 None 表示跳过"""
        pass

    async def post_add_message(
        self,
        message: InputMessage,
    ) -> None:
        """消息添加后处理"""
        pass

# 输出处理扩展
class OutputBufferPlugin(ABC):
    """输出缓冲区插件"""

    async def pre_send_message(
        self,
        message: OutputMessage,
    ) -> OutputMessage | None:
        """消息发送前拦截"""
        pass

    async def post_send_message(
        self,
        message: OutputMessage,
    ) -> None:
        """消息发送后处理"""
        pass

# 安全扩展
class SecurityPlugin(ABC):
    """安全插件"""

    async def check_injection(
        self,
        content: str,
    ) -> list[SecurityIssue]:
        """自定义注入检测"""
        pass

    async def filter_content(
        self,
        content: str,
    ) -> str:
        """自定义内容过滤"""
        pass
```

### 13.2 调度器扩展

```python
# 自定义调度策略
class CustomScheduler(ABC):
    """自定义调度策略"""

    async def select_next_message(
        self,
        queues: dict[str, UserMessageQueue],
    ) -> InputMessage | None:
        """选择下一条消息"""
        pass

    async def on_queue_empty(
        self,
        user_id: str,
    ) -> None:
        """队列为空时的处理"""
        pass
```

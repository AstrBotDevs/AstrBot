# 注册自定义 Agent 执行器

> AstrBot >= 4.20.1

AstrBot 允许插件通过 `context.register_agent_runner()` 动态注册自定义的 **Agent 执行器（Agent Runner）**，注册后会自动出现在 WebUI 的执行器下拉选项中，用户可以像使用内置执行器一样选择和配置。

## 概念回顾

- **Agent 执行器**：负责「思考 + 做事」的组件，接收用户意图后执行多轮感知 → 规划 → 执行 → 观察循环。
- **Chat Provider**：负责「说话」的组件，提供单轮文本补全接口。

如果你的插件需要对接一个已有的外部 Agent 服务，就需要注册一个自定义 Agent 执行器。

## 快速上手

### 1. 实现 Agent Runner 类

继承 `BaseAgentRunner`，实现 `reset()`、`step()`、`step_until_done()`、`done()`、`get_final_llm_resp()` 方法。

```python
import typing as T
from astrbot.core.agent.runners.base import BaseAgentRunner, AgentState
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.response import AgentResponse, AgentResponseData
from astrbot.core.agent.run_context import ContextWrapper, TContext
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.message.message_event_result import MessageChain
import astrbot.core.message.components as Comp


class MyAgentRunner(BaseAgentRunner[TContext]):

    async def reset(
        self,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        provider_config: dict,
        **kwargs: T.Any,
    ) -> None:
        """初始化 Runner 状态。
        
        provider_config 为该提供商的完整配置字典，
        可以从中读取你在 provider_config_fields 中定义的字段。
        """
        self.req = request
        self._state = AgentState.IDLE
        self.agent_hooks = agent_hooks
        self.run_context = run_context
        self.final_llm_resp = None

        # 读取自定义配置
        self.api_url = provider_config.get("my_api_url", "http://127.0.0.1:8080")
        self.api_key = provider_config.get("my_api_key", "")

    async def step(self):
        """执行一步。这是一个 async generator，通过 yield 返回中间 / 最终结果。"""
        self._transition_state(AgentState.RUNNING)

        # 在这里调用你的外部 Agent 服务
        result_text = await self._call_my_agent(self.req.prompt)

        chain = MessageChain(chain=[Comp.Plain(result_text)])
        self.final_llm_resp = LLMResponse(role="assistant", result_chain=chain)
        self._transition_state(AgentState.DONE)

        yield AgentResponse(
            type="llm_result",
            data=AgentResponseData(chain=chain),
        )

    async def step_until_done(
        self, max_step: int = 30
    ) -> T.AsyncGenerator[AgentResponse, None]:
        while not self.done():
            async for resp in self.step():
                yield resp

    def done(self) -> bool:
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp

    async def _call_my_agent(self, prompt: str) -> str:
        """调用外部 Agent 服务（示例）。"""
        # 这里替换为你的实际逻辑
        return f"来自自定义 Agent 的回复: {prompt}"
```

### 2. 在插件入口注册

在插件的 `__init__` 方法中调用 `context.register_agent_runner()`：

```python
from astrbot.api import star
from astrbot.core.agent.runners.registry import AgentRunnerEntry
from .my_agent_runner import MyAgentRunner


class Main(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)

        context.register_agent_runner(
            AgentRunnerEntry(
                runner_type="my_agent",           # 唯一标识符
                runner_cls=MyAgentRunner,          # Runner 类
                provider_id_key="my_agent_provider_id",   # 配置键名
                display_name="My Agent",           # WebUI 显示名称
                provider_config_fields={           # 提供商配置字段
                    "my_api_url": {
                        "description": "API 地址",
                        "type": "string",
                        "hint": "你的 Agent 服务地址。默认 http://127.0.0.1:8080",
                    },
                    "my_api_key": {
                        "description": "API Key",
                        "type": "string",
                        "hint": "用于鉴权的 API Key。",
                    },
                },
            )
        )
```

> [!TIP]
> 注册后，你的 Agent 执行器会自动出现在 WebUI 的「模型提供商」→「新增提供商」→「Agent 执行器」下拉列表中。

## AgentRunnerEntry 字段详解

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `runner_type` | `str` | ✅ | 唯一标识符，用于配置项 `agent_runner_type` 的值 |
| `runner_cls` | `type[BaseAgentRunner]` | ✅ | 实现了 `BaseAgentRunner` 的具体类 |
| `provider_id_key` | `str` | ✅ | 存储所选提供商 ID 的配置键名 |
| `display_name` | `str` | ✅ | 在 WebUI 下拉列表中显示的名称 |
| `on_initialize` | `async callable` | ❌ | Pipeline 初始化时调用的异步回调，可用于预连接、工具同步等 |
| `conversation_id_key` | `str \| None` | ❌ | 如果 Runner 自行管理会话状态，用于存储会话/线程 ID 的键名 |
| `provider_config_fields` | `dict` | ❌ | 注入到提供商配置表单的额外字段定义 |

### provider_config_fields 格式

每个字段定义是一个字典，支持以下属性：

```python
{
    "field_name": {
        "description": "字段显示名",   # 必填
        "type": "string",              # 字段类型: string, int, bool 等
        "hint": "输入提示文本",         # 可选，WebUI 中的占位提示
        "default": "",                 # 可选，默认值
    }
}
```

## 注册生命周期

```
插件加载 (__init__)
  │
  ├─ context.register_agent_runner(entry)
  │    ├─ 注入 WebUI 下拉选项
  │    ├─ 注入提供商配置字段
  │    └─ 注册配置模板
  │
  ├─ [用户在 WebUI 创建提供商并选择该执行器]
  │
  ├─ on_initialize 回调 (如果设置)
  │    └─ 适合执行预连接、工具同步等初始化操作
  │
  └─ 消息到达时
       ├─ reset()  ← 读取 provider_config, 初始化状态
       ├─ step()   ← 执行 Agent 逻辑
       └─ done()   ← 检查是否完成
```

## 卸载 / 清理

当插件被卸载时，可在 `__del__` 或自定义清理方法中移除注册：

```python
context.unregister_agent_runner("my_agent")
```



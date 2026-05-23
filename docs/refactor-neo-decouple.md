# Neo 工具解耦重构规划

## 问题总结

`_apply_sandbox_tools()` 把三件事混在一起：Booter 环境初始化、工具注册、Prompt 注入。
导致两个直接后果：

1. **Subagent 拿不到 Neo 工具** — `_get_runtime_computer_tools()` 硬编码只返回 4 个基础工具，Neo 的 14 个工具不在其中
2. **拆不动** — Neo 工具注册与 agent 请求构建流程绑死，无法独立使用

## 约束条件

- `shipyard`（旧版）和 `shipyard_neo` 必须并行共存
- Neo 的 `capabilities` 是 **boot 后才知道的**（取决于 Bay profile 是否包含 `browser`），但工具注册发生在 boot 之前
- 不改变任何用户可见的功能行为

## 设计目标

- `_apply_sandbox_tools()` 缩回到和 `_apply_local_env_tools()` 一样简洁
- 主 Agent 和 Subagent 从同一个源获取工具，消除两条路径不一致的问题
- Neo 工具可独立加载、独立卸载，不影响非 Neo 用户

## 核心思路

参考现有插件工具模式（路径 1）：**Booter 自己声明它提供哪些工具和 prompt，agent 只负责取用**。

对于"boot 前不知道 capabilities"的问题，采用**两级策略**：
- `@classmethod get_default_tools()` — 不需要实例，根据 booter **类型**返回保守的全量工具列表（包含 browser 工具）
- `get_tools()` — 实例方法，boot 后根据**真实 capabilities** 返回精确列表（可能不含 browser）

首次请求用 default，后续请求用精确列表。行为与当前完全一致（当前代码在 capabilities 未知时也是保守注册全部工具）。

---

## 第一步：定义 Booter 类型常量

**新建文件**: `astrbot/core/computer/booters/constants.py`

```python
BOOTER_SHIPYARD = "shipyard"
BOOTER_SHIPYARD_NEO = "shipyard_neo"
BOOTER_BOXLITE = "boxlite"
```

全局替换所有硬编码字符串：

| 文件 | Before | After |
|---|---|---|
| `computer_client.py` | `"shipyard_neo"` | `BOOTER_SHIPYARD_NEO` |
| `config/default.py` | `"shipyard_neo"` | `BOOTER_SHIPYARD_NEO` |
| `dashboard/routes/config.py` | `"shipyard_neo"` | `BOOTER_SHIPYARD_NEO` |
| `dashboard/routes/skills.py` | 如有 | `BOOTER_SHIPYARD_NEO` |
| `astr_main_agent.py` | 后续步骤中删除 | — |

前端 `SkillsSection.vue` 中的字符串因跨语言无法用常量，保留字符串但加注释标记。

---

## 第二步：提取 Neo prompt 常量到 resources

**改动文件**: `astrbot/core/astr_main_agent_resources.py`

把 `_apply_sandbox_tools()` 中内联的两段 prompt 搬到 resources：

```python
NEO_FILE_PATH_PROMPT = (
    "[Shipyard Neo File Path Rule]\n"
    "When using sandbox filesystem tools (upload/download/read/write/list/delete), "
    "always pass paths relative to the sandbox workspace root. "
    "Example: use `baidu_homepage.png` instead of `/workspace/baidu_homepage.png`."
)

NEO_SKILL_LIFECYCLE_PROMPT = (
    "[Neo Skill Lifecycle Workflow]\n"
    "When user asks to create/update a reusable skill in Neo mode, "
    "use lifecycle tools instead of directly writing local skill folders.\n"
    "Preferred sequence:\n"
    "1) Use `astrbot_create_skill_payload` to store canonical payload content and get `payload_ref`.\n"
    "2) Use `astrbot_create_skill_candidate` with `skill_key` + `source_execution_ids` "
    "(and optional `payload_ref`) to create a candidate.\n"
    "3) Use `astrbot_promote_skill_candidate` to release: `stage=canary` for trial; "
    "`stage=stable` for production.\n"
    "For stable release, set `sync_to_local=true` to sync `payload.skill_markdown` into local `SKILL.md`.\n"
    "Do not treat ad-hoc generated files as reusable Neo skills unless they are captured via "
    "payload/candidate/release.\n"
    "To update an existing skill, create a new payload/candidate and promote a new release version; "
    "avoid patching old local folders directly."
)
```

同时**删除** `astr_main_agent_resources.py` 中的 14 个 Neo 工具模块级单例：

```python
# 删除这些行：
# BROWSER_EXEC_TOOL = BrowserExecTool()
# BROWSER_BATCH_EXEC_TOOL = BrowserBatchExecTool()
# RUN_BROWSER_SKILL_TOOL = RunBrowserSkillTool()
# GET_EXECUTION_HISTORY_TOOL = GetExecutionHistoryTool()
# ANNOTATE_EXECUTION_TOOL = AnnotateExecutionTool()
# CREATE_SKILL_PAYLOAD_TOOL = CreateSkillPayloadTool()
# GET_SKILL_PAYLOAD_TOOL = GetSkillPayloadTool()
# CREATE_SKILL_CANDIDATE_TOOL = CreateSkillCandidateTool()
# LIST_SKILL_CANDIDATES_TOOL = ListSkillCandidatesTool()
# EVALUATE_SKILL_CANDIDATE_TOOL = EvaluateSkillCandidateTool()
# PROMOTE_SKILL_CANDIDATE_TOOL = PromoteSkillCandidateTool()
# LIST_SKILL_RELEASES_TOOL = ListSkillReleasesTool()
# ROLLBACK_SKILL_RELEASE_TOOL = RollbackSkillReleaseTool()
# SYNC_SKILL_RELEASE_TOOL = SyncSkillReleaseTool()
```

以及对应的 import 行。非 Neo 用户不再因 import resources 而拉起整个 Neo 依赖树。

---

## 第三步：在 `ComputerBooter` 基类上声明工具提供能力

**改动文件**: `astrbot/core/computer/booters/base.py`

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class ComputerBooter:
    # ... 现有属性不变 (fs, python, shell, capabilities, browser, boot, shutdown, ...) ...

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        """返回此 booter 类型的默认工具列表（不需要实例，不需要 boot）。

        用于首次请求时 booter 尚未 boot 的场景。
        应返回保守的全量列表（宁多勿少）。
        子类必须覆写。
        """
        return []

    @classmethod
    def get_default_prompts(cls) -> list[str]:
        """返回此 booter 类型的默认 system prompt 片段（不需要实例）。

        子类必须覆写。
        """
        return []

    def get_tools(self) -> list[FunctionTool]:
        """返回基于当前实例真实状态的工具列表。

        boot 后调用，可根据 capabilities 等运行时信息精确过滤。
        默认实现委托给 get_default_tools()，子类按需覆写。
        """
        return self.__class__.get_default_tools()

    def get_system_prompt_parts(self) -> list[str]:
        """返回基于当前实例状态的 prompt 片段。

        默认实现委托给 get_default_prompts()。
        """
        return self.__class__.get_default_prompts()
```

设计要点：
- `@classmethod get_default_tools()` — **不需要实例**，纯根据 booter 类型返回，解决"boot 前也需要注册工具"
- `get_tools()` 实例方法 — boot 后调用，可利用 `self.capabilities` 精确过滤
- 默认实现委托到 classmethod，子类只需要覆写需要的

---

## 第四步：各 Booter 子类实现

### ShipyardBooter（旧版）

**改动文件**: `astrbot/core/computer/booters/shipyard.py`

```python
class ShipyardBooter(ComputerBooter):
    # ... 现有代码完全不变 ...

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        from astrbot.core.computer.tools.shell import ExecuteShellTool
        from astrbot.core.computer.tools.python import PythonTool
        from astrbot.core.computer.tools.fs import FileUploadTool, FileDownloadTool
        return [ExecuteShellTool(), PythonTool(), FileUploadTool(), FileDownloadTool()]

    @classmethod
    def get_default_prompts(cls) -> list[str]:
        from astrbot.core.astr_main_agent_resources import SANDBOX_MODE_PROMPT
        return [SANDBOX_MODE_PROMPT]

    # get_tools() 和 get_system_prompt_parts() 不需要覆写
    # 因为 shipyard 没有运行时 capabilities 变化，default 就是精确列表
```

### ShipyardNeoBooter

**改动文件**: `astrbot/core/computer/booters/shipyard_neo.py`

```python
class ShipyardNeoBooter(ComputerBooter):
    # ... 现有代码完全不变 ...

    @classmethod
    def _base_tools(cls) -> list[FunctionTool]:
        """4 个基础工具 + 11 个 Neo 生命周期工具（所有 Neo profile 都有）"""
        from astrbot.core.computer.tools.shell import ExecuteShellTool
        from astrbot.core.computer.tools.python import PythonTool
        from astrbot.core.computer.tools.fs import FileUploadTool, FileDownloadTool
        from astrbot.core.computer.tools.neo_skills import (
            GetExecutionHistoryTool, AnnotateExecutionTool,
            CreateSkillPayloadTool, GetSkillPayloadTool,
            CreateSkillCandidateTool, ListSkillCandidatesTool,
            EvaluateSkillCandidateTool, PromoteSkillCandidateTool,
            ListSkillReleasesTool, RollbackSkillReleaseTool,
            SyncSkillReleaseTool,
        )
        return [
            ExecuteShellTool(), PythonTool(),
            FileUploadTool(), FileDownloadTool(),
            GetExecutionHistoryTool(), AnnotateExecutionTool(),
            CreateSkillPayloadTool(), GetSkillPayloadTool(),
            CreateSkillCandidateTool(), ListSkillCandidatesTool(),
            EvaluateSkillCandidateTool(), PromoteSkillCandidateTool(),
            ListSkillReleasesTool(), RollbackSkillReleaseTool(),
            SyncSkillReleaseTool(),
        ]

    @classmethod
    def _browser_tools(cls) -> list[FunctionTool]:
        """3 个浏览器工具（仅 browser profile 有）"""
        from astrbot.core.computer.tools.browser import (
            BrowserExecTool, BrowserBatchExecTool, RunBrowserSkillTool,
        )
        return [BrowserExecTool(), BrowserBatchExecTool(), RunBrowserSkillTool()]

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        """未 boot 时：保守返回全量（含 browser），与当前行为一致。"""
        return cls._base_tools() + cls._browser_tools()

    @classmethod
    def get_default_prompts(cls) -> list[str]:
        from astrbot.core.astr_main_agent_resources import (
            SANDBOX_MODE_PROMPT, NEO_FILE_PATH_PROMPT, NEO_SKILL_LIFECYCLE_PROMPT,
        )
        return [NEO_FILE_PATH_PROMPT, NEO_SKILL_LIFECYCLE_PROMPT, SANDBOX_MODE_PROMPT]

    def get_tools(self) -> list[FunctionTool]:
        """boot 后：根据真实 capabilities 精确返回。"""
        caps = self.capabilities
        if caps is None:
            # 还没 boot 或 capabilities 不可用，走保守路径
            return self.__class__.get_default_tools()
        tools = self._base_tools()
        if "browser" in caps:
            tools.extend(self._browser_tools())
        return tools

    # get_system_prompt_parts() 不需要覆写，prompt 不依赖 capabilities
```

两级策略对照表：

| 场景 | 调用 | browser 工具 | 行为 |
|---|---|---|---|
| 首次请求，未 boot | `get_default_tools()` | **包含**（保守） | 与当前代码 `if caps is None` 分支一致 |
| 后续请求，已 boot，profile 有 browser | `get_tools()` | **包含** | 精确 |
| 后续请求，已 boot，profile 无 browser | `get_tools()` | **不包含** | 精确 |
| ShipyardBooter（无 capabilities 概念） | `get_default_tools()` | 无 | 始终 4 个基础工具 |

---

## 第五步：`computer_client.py` 暴露统一的工具查询 API

**改动文件**: `astrbot/core/computer/computer_client.py`

```python
from .booters.constants import BOOTER_SHIPYARD, BOOTER_SHIPYARD_NEO, BOOTER_BOXLITE


# --- Booter 类型 → Booter 类 的映射（延迟 import） ---

def _get_booter_class(booter_type: str) -> type[ComputerBooter] | None:
    """根据 booter 类型字符串返回对应的类（延迟 import）。"""
    if booter_type == BOOTER_SHIPYARD:
        from .booters.shipyard import ShipyardBooter
        return ShipyardBooter
    elif booter_type == BOOTER_SHIPYARD_NEO:
        from .booters.shipyard_neo import ShipyardNeoBooter
        return ShipyardNeoBooter
    elif booter_type == BOOTER_BOXLITE:
        from .booters.boxlite import BoxliteBooter
        return BoxliteBooter
    return None


# --- 公共 API ---

def get_sandbox_tools(session_id: str) -> list[FunctionTool]:
    """获取已 boot session 的精确工具列表。未 boot 返回空列表。"""
    booter = session_booter.get(session_id)
    if booter is None:
        return []
    return booter.get_tools()


def get_sandbox_prompts(session_id: str) -> list[str]:
    """获取已 boot session 的 prompt 片段。未 boot 返回空列表。"""
    booter = session_booter.get(session_id)
    if booter is None:
        return []
    return booter.get_system_prompt_parts()


def get_default_sandbox_tools(sandbox_cfg: dict) -> list[FunctionTool]:
    """根据配置中的 booter 类型返回默认工具列表。不需要实例，不需要 boot。

    用于首次请求或 subagent 场景，booter 尚未 boot 时的保守注册。
    """
    booter_type = sandbox_cfg.get("booter", BOOTER_SHIPYARD_NEO)
    cls = _get_booter_class(booter_type)
    if cls is None:
        return []
    return cls.get_default_tools()


def get_default_sandbox_prompts(sandbox_cfg: dict) -> list[str]:
    """根据配置中的 booter 类型返回默认 prompt 片段。不需要实例。"""
    booter_type = sandbox_cfg.get("booter", BOOTER_SHIPYARD_NEO)
    cls = _get_booter_class(booter_type)
    if cls is None:
        return []
    return cls.get_default_prompts()
```

同时将 `_discover_bay_credentials` 重命名为 `discover_bay_credentials`（去掉下划线前缀），
更新 `dashboard/routes/config.py` 和 `dashboard/routes/skills.py` 中的 import。

设计要点：
- `get_sandbox_tools(session_id)` — 已 boot 时用，走 `booter.get_tools()` 实例方法
- `get_default_sandbox_tools(cfg)` — 未 boot 时用，走 `BooterClass.get_default_tools()` 类方法
- `_get_booter_class()` 集中了 booter_type → class 的映射，同时也可复用于 `get_booter()` 中的实例创建

---

## 第六步：简化 `_apply_sandbox_tools()`

**改动文件**: `astrbot/core/astr_main_agent.py`

**Before**（70+ 行）：
```python
def _apply_sandbox_tools(config, req, session_id):
    booter = config.sandbox_cfg.get("booter", "shipyard_neo")
    if booter == "shipyard":
        os.environ["SHIPYARD_ENDPOINT"] = ...
        os.environ["SHIPYARD_ACCESS_TOKEN"] = ...
    req.func_tool.add_tool(EXECUTE_SHELL_TOOL)
    req.func_tool.add_tool(PYTHON_TOOL)
    # ... 14 个 Neo 工具逐个 add ...
    # ... 40 行内联 prompt ...
    # ... session_booter 全局字典偷读 ...
```

**After**（~15 行）：
```python
from astrbot.core.computer.computer_client import (
    get_sandbox_tools,
    get_sandbox_prompts,
    get_default_sandbox_tools,
    get_default_sandbox_prompts,
)

def _apply_sandbox_tools(
    config: MainAgentBuildConfig, req: ProviderRequest, session_id: str
) -> None:
    if req.func_tool is None:
        req.func_tool = ToolSet()
    if req.system_prompt is None:
        req.system_prompt = ""

    # 已 boot → 精确列表；未 boot → 按 booter 类型取默认列表
    tools = get_sandbox_tools(session_id) or get_default_sandbox_tools(config.sandbox_cfg)
    for tool in tools:
        req.func_tool.add_tool(tool)

    prompts = get_sandbox_prompts(session_id) or get_default_sandbox_prompts(config.sandbox_cfg)
    for prompt in prompts:
        req.system_prompt += f"\n{prompt}\n"
```

**注意**：旧版 `ShipyardBooter` 路径中的 `os.environ["SHIPYARD_ENDPOINT"]` 设置需要保留。
这个操作属于 infra 初始化，应该移到 `ShipyardBooter.boot()` 或 `get_booter()` 中处理：

```python
# computer_client.py get_booter() 中，创建 ShipyardBooter 时:
if booter_type == BOOTER_SHIPYARD:
    ep = sandbox_cfg.get("shipyard_endpoint", "")
    at = sandbox_cfg.get("shipyard_access_token", "")
    if not ep or not at:
        logger.error("Shipyard sandbox configuration is incomplete.")
        raise ValueError(...)
    os.environ["SHIPYARD_ENDPOINT"] = ep
    os.environ["SHIPYARD_ACCESS_TOKEN"] = at
    # ... 创建 ShipyardBooter ...
```

这样 `_apply_sandbox_tools()` 彻底不再关心 booter 类型。

**同时删除**：
- `astr_main_agent.py` 中所有 Neo 工具 import
- `from astrbot.core.computer.computer_client import session_booter`
- `if booter == "shipyard_neo":` 分支
- 内联的 Neo prompt 文本

---

## 第七步：修复 Subagent 的工具获取路径

**改动文件**: `astrbot/core/astr_agent_tool_exec.py`

**Before**：
```python
@classmethod
def _get_runtime_computer_tools(cls, runtime: str) -> dict[str, FunctionTool]:
    if runtime == "sandbox":
        return {
            EXECUTE_SHELL_TOOL.name: EXECUTE_SHELL_TOOL,
            PYTHON_TOOL.name: PYTHON_TOOL,
            FILE_UPLOAD_TOOL.name: FILE_UPLOAD_TOOL,
            FILE_DOWNLOAD_TOOL.name: FILE_DOWNLOAD_TOOL,
        }
    # ... 只有 4 个基础工具，Neo 全丢
```

**After**：
```python
@classmethod
def _get_runtime_computer_tools(
    cls,
    runtime: str,
    session_id: str | None = None,
    sandbox_cfg: dict | None = None,
) -> dict[str, FunctionTool]:
    if runtime == "sandbox":
        from astrbot.core.computer.computer_client import (
            get_sandbox_tools,
            get_default_sandbox_tools,
        )
        # 与 _apply_sandbox_tools() 走同一条路径
        tools = (get_sandbox_tools(session_id) if session_id else []) \
                or (get_default_sandbox_tools(sandbox_cfg) if sandbox_cfg else [])
        return {t.name: t for t in tools} if tools else {}
    if runtime == "local":
        return {
            LOCAL_EXECUTE_SHELL_TOOL.name: LOCAL_EXECUTE_SHELL_TOOL,
            LOCAL_PYTHON_TOOL.name: LOCAL_PYTHON_TOOL,
        }
    return {}
```

同步更新 `_build_handoff_toolset()` 传递 `session_id` 和 `sandbox_cfg`：

```python
@classmethod
def _build_handoff_toolset(cls, run_context, tools):
    ctx = run_context.context.context
    event = run_context.context.event
    cfg = ctx.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "local"))
    sandbox_cfg = provider_settings.get("sandbox", {})

    runtime_computer_tools = cls._get_runtime_computer_tools(
        runtime,
        session_id=event.unified_msg_origin,
        sandbox_cfg=sandbox_cfg,
    )
    # ... 后续逻辑不变 ...
```

**这是最关键的一步**：主 agent 和 subagent 从同一个源获取工具。

---

## 变更矩阵

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `booters/constants.py` | **新建** | booter 类型常量 |
| `booters/base.py` | 新增 | `get_default_tools()`, `get_default_prompts()`, `get_tools()`, `get_system_prompt_parts()` |
| `booters/shipyard.py` | 新增 | 实现 `get_default_tools()`, `get_default_prompts()` |
| `booters/shipyard_neo.py` | 新增 | 实现两级工具声明 (`_base_tools` + `_browser_tools` + 覆写 `get_tools`) |
| `computer_client.py` | 新增+重构 | 4 个公共 API + `_get_booter_class()` + 环境变量设置下沉 + 重命名 `discover_bay_credentials` |
| `astr_main_agent.py` | **大幅简化** | `_apply_sandbox_tools()` 从 70+ 行变 ~15 行 |
| `astr_main_agent_resources.py` | 增+删 | 新增 2 个 prompt 常量；删除 14 个 Neo 工具全局单例及 import |
| `astr_agent_tool_exec.py` | 修改 | `_get_runtime_computer_tools()` + `_build_handoff_toolset()` 走统一 API |
| `config/default.py` | 微调 | 常量替换 |
| `dashboard/routes/config.py` | 微调 | import 路径 + 常量替换 |
| `dashboard/routes/skills.py` | 微调 | import 路径 + 常量替换 |

---

## 重构前后对比

### Before: 两条断裂路径 + booter 类型判断散落各处

```
主 Agent                               Subagent
build_main_agent()                      _execute_handoff()
  └── _apply_sandbox_tools()              └── _build_handoff_toolset()
        ├── if booter == "shipyard": ...        └── _get_runtime_computer_tools()
        ├── 4 基础工具 ✓                              └── 硬编码 4 个基础工具 ✗
        ├── if booter == "shipyard_neo":                    (Neo 工具全丢)
        │     ├── session_booter 偷读
        │     ├── 3 浏览器工具 ✓
        │     ├── 11 Neo 工具 ✓
        │     └── 40 行内联 prompt ✓
        └── SANDBOX_MODE_PROMPT
```

### After: 统一的工具获取源，booter 自描述

```
                    ComputerBooter
                    ├── get_default_tools()    ← @classmethod, 不需要实例
                    └── get_tools()            ← 实例方法, boot 后精确过滤
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ShipyardBooter    ShipyardNeoBooter      (未来 Booter)
   4 基础工具         15 基础 + 3 browser     自定义工具
   SANDBOX_MODE       + NEO prompts           自定义 prompt

                    computer_client.py
        ┌──── get_sandbox_tools(session_id)       已 boot → 精确
        │     get_sandbox_prompts(session_id)
        │
        └──── get_default_sandbox_tools(cfg)      未 boot → 保守全量
              get_default_sandbox_prompts(cfg)
                         │
            ┌────────────┴────────────┐
            │                         │
    _apply_sandbox_tools()    _get_runtime_computer_tools()
       (主 Agent)                (Subagent handoff)
```

---

## 执行顺序

1. **第一步**（定义常量）— 最小改动，零风险，可先合并
2. **第二步**（提取 prompt 常量）— 纯搬移，不改逻辑
3. **第三步 + 第四步**（基类接口 + 子类实现）— 核心抽象，新增方法不影响现有调用
4. **第五步**（computer_client API）— 新增公共函数，不影响现有调用
5. **第六步 + 第七步**（简化 agent + 修复 handoff）— 最终切换，一起改一起测

步骤 1-4 都是**纯新增**，不修改任何现有调用路径，可以安全地逐步合并。
步骤 5-6 是**切换调用路径**，需要一起提交并完整回归测试。

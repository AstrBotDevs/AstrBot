# 修复 interactive_choice 历史回放：方案 B（plugin 驱动 + chat_service chain_type 分支）

| | | |
|---|---|---|
| **作者** | elecvoid243 | |
| **日期** | 2026-07-05 | |
| **分支** | fix/interactive-choice-history-roundtrip | |
| **状态** | implementing | |
| **范围** | `astrbot_plugin_ask_user_choice` + `astrbot/dashboard` 三处 SSE 消费 + 前端 `processStreamPayload` | |

---

## 1. 背景与根因

`astrbot_plugin_ask_user_choice` 的 `ask_user_choice` 工具（v1.0 阻塞式）调用后，会向 `webchat_queue_mgr.back_queue` 推送 `type: "interactive_choice"` 的 SSE 事件，把问题/选项/截止时间发给前端。

**前端行为（已工作）**：
- `dashboard/src/composables/useMessages.ts::processStreamPayload` 在 `msgType === "interactive_choice"` 分支里调 `applyInteractiveChoiceSse`，把 part 推到 `botRecord.content.message`（in-memory）+ 镜像进 Pinia store。✅
- 实时会话里能渲染 `<InteractiveChoiceBox>`。✅

**持久化行为（缺失）**：
- `chat_service.py::BotMessageAccumulator` 只在 `result_type ∈ {plain, image, record, file, video}` 时调对应的 `add_*` 方法；其它 type 静默丢弃。
- `live_chat_service.py` 与 `open_api_service.py` 的 SSE 消费 switch 行为一致。
- 结果：`platform_message_history` 表里**只有 `tool_call` part**（`{type: "tool_call", tool_calls: [{name: "ask_user_choice", args, result, ...}]}`），没有 `interactive_choice` part。

**用户可见症状**（spec `2026-07-03-interactive-choice-persistence-gap.md` §2.2 已记录，本次新增复现证据）：
1. **刷新后选项框全部聚集到页底**：`ChatMessageList.vue::onMounted` 跑 `interactiveChoiceStore.injectOrphans(umo, messages)`，把所有"在 store 但不在 messages 里"的 part 全部 push 到**最后一条 bot 消息**。三条 bot 消息的 box 全堆在末尾。
2. **历史里"使用了 ask_user_choice 工具"变成"使用了 tool 工具"**：`ToolCallCard` 的 `displayToolName = computed(() => toolCall.name || "tool")` 在 `toolCall.name` 为空时 fallback 到 `"tool"`。由于 `ask_user_choice` 的 tool_call data 字段是 `ask_user_choice_spec` 而不是 `name`，fallback 触发。

---

## 2. 方案

**核心思路**：让 `interactive_choice` 走与 `tool_call` / `tool_call_result` 相同的 `chain_type` 通道，由 chat_service 把它持久化进 bot 消息的 parts 数组。

### 2.1 插件（`F:\github\astrbot_plugin_ask_user_choice/ask_user_choice_tool.py`）

`_push_to_webchat_back_queue` 改 event shape：

```python
# before
await back_queue.put({
    "type": "interactive_choice",
    "data": {
        "request_id": request_id,
        "spec": spec,
        "expires_at": expires_at,
        "umo": umo,
    },
    "message_id": sse_message_id,
})

# after
import json
await back_queue.put({
    "type": "plain",  # 走通用 SSE 通道
    "chain_type": "interactive_choice",  # 新 chain_type
    "data": json.dumps({  # chat_service 期望 string
        "request_id": request_id,
        "spec": spec,
        "expires_at": expires_at,
        "umo": umo,
    }, ensure_ascii=False),
    "message_id": sse_message_id,
})
```

`_push_resolved_event_to_back_queue` 保持 `type: "interactive_choice_resolved"` 不动（只是通知，不进 bot 消息 parts）。

### 2.2 chat_service（`astrbot/dashboard/services/chat_service.py`）

在 `BotMessageAccumulator.add_plain` 的 chain_type 分发里加一个新分支：

```python
if chain_type == "interactive_choice":
    self._flush_pending_text()
    self._store_interactive_choice(result_text)
    return
```

新增私有方法（与 `_store_tool_call` / `_store_tool_call_result` 同风格）：

```python
def _store_interactive_choice(self, result_text: str) -> None:
    payload = self._parse_json_object(result_text)
    if not payload:
        return
    request_id = str(payload.get("request_id") or "").strip()
    spec = payload.get("spec")
    if not request_id or not isinstance(spec, dict):
        return
    prompt = str(spec.get("prompt") or "").strip()
    options = spec.get("options")
    if not prompt or not isinstance(options, list):
        return
    part: dict = {
        "type": "interactive_choice",
        "request_id": request_id,
        "prompt": prompt,
        "options": options,
    }
    title = spec.get("title")
    if isinstance(title, str) and title.strip():
        part["title"] = title
    placeholder = spec.get("input_placeholder")
    if isinstance(placeholder, str) and placeholder.strip():
        part["input_placeholder"] = placeholder
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, (int, float)):
        part["expires_at"] = expires_at
    self.parts.append(part)
```

### 2.3 live_chat_service / open_api_service

同样地：复用 `BotMessageAccumulator`，所以 `_store_interactive_choice` 在 3 个 service 间是同一份实现。`live_chat_service` 与 `open_api_service` 都已经调用 `message_accumulator.add_plain(result_text, chain_type=chain_type, ...)`，自动会触发新分支。**无需在这两个 service 额外写代码**（只要 `BotMessageAccumulator` 的方法在 `chat_service.py` 改了就行，因为 `BotMessageAccumulator` 是从那里 import 的）。

### 2.4 前端（`dashboard/src/composables/useMessages.ts`）

`processStreamPayload` 现有 `msgType === "plain"` 块里加一个 chain_type 分支：

```ts
if (msgType === "plain") {
    markMessageStarted(botRecord);
    if (chainType === "reasoning") { ... }
    if (chainType === "tool_call") { ... }
    if (chainType === "tool_call_result") { ... }
    // 新增
    if (chainType === "interactive_choice") {
        if (!sessionId) {
            console.warn("[interactiveChoice] SSE event without sessionId; dropping");
            return;
        }
        const inner = parseJsonSafe(data);  // 解析 json.dumps 出来的 string
        if (!inner) return;
        applyInteractiveChoiceSse(sessionId, botRecord, inner);
        return;
    }
}
```

`applyInteractiveChoiceSse` 内部继续用 `interactiveChoicePartFromSsePayload(payload)`，该函数期望 `{type: "interactive_choice", data: {request_id, spec, ...}}` 的 envelope。**所以前端需要把 chain_type 包装的 payload 重新包成 envelope**：

```ts
applyInteractiveChoiceSse(sessionId, botRecord, {
    type: "interactive_choice",
    data: inner,  // inner 已经是 {request_id, spec, ...}
});
```

这样 `interactiveChoicePartFromSsePayload` 不动，前端的 envelope 解析逻辑零改动。

### 2.5 持久化路径全图

```
LLM calls ask_user_choice
    │
    ▼
plugin.call() 校验 + 存 registry
    │
    ▼
plugin._push_to_webchat_back_queue(request_id, spec, expires_at)
    │
    │  back_queue.put({
    │      type: "plain",
    │      chain_type: "interactive_choice",
    │      data: json.dumps({request_id, spec, expires_at, umo}),
    │      message_id: sse_message_id,
    │  })
    │
    ▼
chat_service 消费 loop:
    │
    ├─► yield f"data: {json.dumps(result)}"  ──► 前端 SSE 收到
    │                                            │
    │                                            ▼
    │                                  processStreamPayload
    │                                    (msgType="plain", chainType="interactive_choice")
    │                                      │
    │                                      ▼
    │                                  parseJsonSafe(data)
    │                                    │
    │                                    ▼
    │                                  applyInteractiveChoiceSse(sessionId, botRecord, {type:"interactive_choice", data: inner})
    │                                    │
    │                                    ▼
    │                                  botRecord.content.message.push(part)  ◄── in-memory
    │                                  store.addChoice(umo, part)            ◄── Pinia + localStorage
    │
    └─► message_accumulator.add_plain(result_text, chain_type="interactive_choice")
          │
          ▼
        BotMessageAccumulator._store_interactive_choice(result_text)
          │
          ▼
        self.parts.append({type:"interactive_choice", request_id, prompt, options, ...})
          │
          ▼ (后续 end / complete 事件)
        flush_pending_bot_message → save_bot_message → DB INSERT
          │
          ▼
        platform_message_history.content.message = [...prev, interactive_choice_part, ...]
```

刷新后 history 加载 → `mirrorInteractiveChoiceParts` 直接找到 part → store 镜像成功 → `<InteractiveChoiceBox>` 渲染在正确位置。

---

## 3. 替代方案对比（参见 brainstorm 记录）

| 方案 | 评估 |
|---|---|
| A. 后端大改：3 个 service 各加 msg_type 分支 | 入侵性大；plugin 不动；本次不取 |
| **B. plugin chain_type 驱动** | **本次采用**。plugin 是 feature owner；chat_service 改动 ~30 行；不破坏 SSE 现存契约 |
| C. 纯前端从 tool_call 合成 | 启发式不稳定（submission state 还原靠 parse result 字符串）；user 已否定 |

---

## 4. 影响面

| 模块 | 改动量 | 风险 |
|---|---|---|
| `astrbot_plugin_ask_user_choice/ask_user_choice_tool.py` | +1 import, ~5 行修改 | 低（向后兼容：旧 plugin + 新 chat_service 会丢失 part；新 plugin + 旧 chat_service 会落 part 为空——两端必须同步发布） |
| `astrbot/dashboard/services/chat_service.py` | +1 method (~40 行) + 1 分支 (~5 行) | 低（新增分支不影响已有 plain / tool_call / tool_call_result / reasoning 路径） |
| `astrbot/dashboard/services/live_chat_service.py` | 0（共享 `BotMessageAccumulator`） | — |
| `astrbot/dashboard/services/open_api_service.py` | 0（同上） | — |
| `dashboard/src/composables/useMessages.ts` | +1 分支 (~12 行) | 低（加在 plain 块内，不影响其它 chain_type） |
| `dashboard/src/composables/dispatchInteractiveChoice.ts` | 0 | — |
| `dashboard/src/composables/parseInteractiveChoice.ts` | 0 | — |
| `dashboard/src/composables/parseInteractiveChoice.sse.test.ts` | 更新 wire format 示例 | — |

---

## 5. 测试策略

### 5.1 后端单元测试（新增 `tests/unit/test_chat_service_interactive_choice.py`）

- `_store_interactive_choice` 接受合法 JSON → 产出 part
- 缺 `request_id` / `prompt` / `options` → 静默丢弃
- title / input_placeholder / expires_at 可选字段处理
- `add_plain` 走 `chain_type="interactive_choice"` → 调 `_store_interactive_choice`

### 5.2 插件单元测试（更新 `test_ask_user_choice_tool.py`）

- `_push_to_webchat_back_queue` 验证新的 event shape：`type="plain"`、`chain_type="interactive_choice"`、`data` 是合法 JSON string。

### 5.3 前端单元测试（更新 `parseInteractiveChoice.sse.test.ts`）

- 保持 envelope 解析逻辑不变；只更新文档注释的 wire format 示例。

### 5.4 手动回归

- 开 dashboard，触发 ask_user_choice，选择 → 刷新页面 → box 应在原 bot 消息位置
- 切到长历史会话，多次 ask_user_choice → 刷新 → 全部在各自位置
- 验证 ToolCallCard 的"tool" 仍会出现（这是 tool_call.name 缺失的另一独立问题；本次**不修**）

---

## 6. 发布顺序

1. 合并此分支到 `all`
2. 同步更新 `astrbot_plugin_ask_user_choice` 插件并发布
3. 文档里加一句"plugin 和 dashboard 版本必须配套"

---

## 7. 关键文件锚点

| 文件 | 行 | 用途 |
|---|---|---|
| `data/plugins/astrbot_plugin_ask_user_choice/ask_user_choice_tool.py` | 165 | `_push_to_webchat_back_queue`（要改） |
| `astrbot/dashboard/services/chat_service.py` | 137-201 | `BotMessageAccumulator.add_plain`（要加分支） |
| `astrbot/dashboard/services/chat_service.py` | ~250 | `BotMessageAccumulator._store_tool_call_result`（参考实现） |
| `dashboard/src/composables/useMessages.ts` | 1035+ | `processStreamPayload` plain 分支（要加 chainType 分支） |
| `dashboard/src/composables/dispatchInteractiveChoice.ts` | 65-79 | `applyInteractiveChoiceSse`（不需要改） |

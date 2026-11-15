# 模型

直接调用模型生成回复或进行结构化判断。需要执行工具或沿用会话历史时，参见 [Agent](./agents.md)。

## 对话模型 {#chat-models}

### 获取当前会话使用的聊天模型 ID

```py
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

### 生成回复

```py
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,  # 聊天模型 ID
    prompt="Hello, world!",
)
# print(llm_resp.completion_text) # 获取返回的文本
```

## 判断模型 {#decision-models}

判断提供商用于是否回复、选择执行分支等任务。先在 WebUI **模型提供商 → 判断** 中配置提供商，再通过 `self.context.decision` 调用。

```py
should_reply = await self.context.decision.yes_no(
    question="Should the assistant reply to this message?",
    state="I cannot log in; every request returns 500.",
    threshold=0.7,
)

strategy = await self.context.decision.choose(
    question="Which reply strategy should be used?",
    criteria={"short": "A brief reply", "detailed": "A detailed reply"},
    state="The user asks for step-by-step troubleshooting.",
)
print(strategy.choice)
```

`yes_no()` 返回 `bool`，当肯定概率达到 `threshold` 时为 `True`；`choose()` 返回 `DecisionChoiceAnswer`，通过 `.choice` 读取选项值。

`state` 提供判断所需的上下文，支持文本、列表或字典。默认使用当前判断提供商，也可传入 `provider_id` 指定。

需要一次回答多个问题时，调用 `ask({问题名: 问题对象}, state=...)`，结果按问题名返回。以下类型从 `astrbot.api.provider` 导入：

| 问题类型 | 配置 | 返回类型及主要字段 |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`：待判断的陈述。 | `DecisionBooleanAnswer.probability`：陈述为真的概率。 |
| `DecisionChoiceQuestion` | `instructions` 和 `criteria`：选项 ID 到描述的映射。 | `DecisionChoiceAnswer.choice`：选中的选项 ID。 |
| `DecisionScoreQuestion` | `instructions` 和 `criteria`：由低到高的 2～10 个等级描述。 | `DecisionScoreAnswer.score`：从 0 到等级数减 1 的评分，可为小数。 |

提供商不可用、请求失败或返回结果无效时抛出 `DecisionError`。`yes_no()` 可通过 `default=False` 在这类错误发生时返回默认值。


# 模型

直接调用模型生成回复或进行结构化判断。需要执行工具或沿用会话历史时，参见 [Agent](./agent.md)。

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

`state` 提供判断所需的上下文，支持文本、列表或字典。Gemini 还支持显式多模态 `DecisionInput`，普通 JSON 仍按业务数据处理。默认使用当前判断提供商，也可传入 `provider_id` 指定。

需要一次回答多个问题时，调用 `ask({问题名: 问题对象}, state=...)`，结果按问题名返回。以下类型从 `astrbot.api.provider` 导入：

| 问题类型 | 配置 | 返回类型及主要字段 |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`：待判断的陈述。 | `DecisionBooleanAnswer.probability`：陈述为真的概率。 |
| `DecisionChoiceQuestion` | `instructions` 和 `criteria`：选项 ID 到描述的映射。 | `DecisionChoiceAnswer.choice`：选中的选项 ID。 |
| `DecisionScoreQuestion` | `instructions` 和 `criteria`：由低到高的等级描述：Gemini 支持 2～255 档，OpenAI 和 System One 支持 2～10 档。 | `DecisionScoreAnswer.score`：从 0 到等级数减 1 的评分，可为小数。 |

提供商不可用、请求失败或返回结果无效时抛出 `DecisionError`。`yes_no()` 可通过 `default=False` 在这类错误发生时返回默认值。

### 使用 Gemini Decisions

在 WebUI「模型提供商」→「判断」中新增「Gemini Decisions」模板。填写 Gemini API Key（支持 `$ENV_NAME` 环境变量引用），接口基础地址默认为 `https://generativelanguage.googleapis.com/v1beta`，模型填写 `gemini-decision-1`。AstrBot 会自动补全 `/decisions`（路径已以它结尾时不重复追加），通过 `x-goog-api-key` 请求头发送密钥。保存后使用提供商的连接测试检查访问权限。你的 Google API 项目需要具有该模型的访问权限与可用额度，添加配置本身不会开通它们。

适配器直接调用 REST 接口，无需升级 Google SDK。超时、总超时（包含排队与重试）、最大并发、代理和自定义请求头与 OpenAI Decisions 使用同一套约定。处理大媒体时，请按需调高 `timeout`（默认 5 秒）和 `total_timeout`（默认 10 秒）。它只在插件显式调用判断服务时运行，不会自动参与主对话流程。

使用上文通用的 `ask()`、`choose()` 和 `yes_no()` 方法，并指定 `provider_id="gemini_decision"`。

Gemini 布尔题使用 `noul`，表示**为真**的概率（通常位于 `[0.01, 0.99]`）。`yes_no()` 将此概率与阈值比较。适配器尚未暴露可选布尔判定描述 `true_description` 和 `false_description`，可将相应定义写入 `instructions`。

每次请求支持 1–1,000 道题，每道单选支持 2–255 个选项，评分支持 2–255 档（推荐 2–10 档）。选项 ID 须为非空字符串，描述可以为空。非法输入会在发送前抛出 `ValueError`，其余接口约束由 Google 服务端校验。调用方的问题 ID 在内部映射，返回答案仍保留原始键。

答案缺失或不一致会让整批调用抛出 `DecisionError`。[官方接口](https://aistudio.google.com/docs/decisions-api)通过 HTTP 400 返回安全拦截，`error.code` 为 `safety`、`prohibited_content`、`blocklist`、`image_safety` 或 `content_blocked`。HTTP 400 错误包含已识别的 `invalid_request` 分类（若存在），不会输出未知错误码或服务器消息；拦截不会被转换成答案。`yes_no(default=...)` 保留显式降级行为。

Gemini 将普通字典和列表（包括空容器）发送为 JSON 文本。省略 `state`、传入 `None` 或空字符串时，使用 JSON 文本 `"{}"`，因为接口不接受空输入。不支持或无法序列化的值以及 `NaN`/`Infinity` 会被拒绝。通过下方的 `DecisionInput` 显式传入媒体；问题指令仍只支持文本。

#### 显式多模态输入

从 `astrbot.api.provider` 导入 `DecisionInput` 和 `DecisionMedia`。`DecisionInput.content` 是非空的有序列表，成员为文本字符串或 `DecisionMedia` 对象。Gemini 拼接相邻文本块时不会自动插入分隔符，请自行添加空格或换行。

```py
from astrbot.api.provider import DecisionInput, DecisionMedia

photo = DecisionInput(content=[
    "Inspect this product photo.\n",
    DecisionMedia(
        type="image",
        uri="https://example.com/product.png",  # Replace with an accessible media URL.
        mime_type="image/png",
        resolution="low",
    ),
])

has_damage = await self.context.decision.yes_no(
    "Does the product have visible damage?",
    state=photo,
    provider_id="gemini_decision",
)
```

同一个 `state` 也可用于 `ask()` 和 `choose()`。每个 `DecisionMedia` 必须指定真实的 `mime_type`，并且只提供 `uri` 或 `data` 中的一项。内联媒体使用 `data=base64.b64encode(file_bytes).decode("ascii")`，不加 data URI 前缀。适配器按编码长度估算内联媒体大小（每次请求合计不超过 100 MB，每个 PDF 不超过 50 MB），不会为校验而在内存中完整解码载荷。适配器不会自动读取本地路径或上传文件。

| `type` | MIME 类型示例 | 输入方式 |
| --- | --- | --- |
| `image` | `image/png`、`image/jpeg` | base64 `data` 或 HTTPS `uri` |
| `audio` | `audio/wav`、`audio/mp3` | base64 `data` 或 HTTPS `uri` |
| `video` | `video/mp4` | base64 `data` 或 HTTPS `uri` |
| `document` | `application/pdf` | base64 `data` 或 HTTPS `uri` |

Gemini 接受公开或签名 HTTPS URL（每个外部 URL 最多 15 MB），以及 Files API 返回的 HTTPS URI；不支持 YouTube URL 或直接使用 `gs://` URI。图片和视频可选 `resolution="low"`、`"medium"` 或 `"high"`，图片还支持 `"ultra_high"`；音频和 PDF 不设置此字段。完整格式和大小限制见[官方输入说明](https://aistudio.google.com/docs/decisions-api#input)，实际文件格式、可访问性及请求和媒体大小限制由 Google 校验。

显式输入结构不合法时，会在发送前抛出 `ValueError`；接口请求失败时抛出 `DecisionError`。媒体内容不接受工具调用、思考或对话历史块。当前 OpenAI 适配器会明确以 `ValueError` 拒绝 `DecisionInput`，仍应传入文本或业务 JSON。

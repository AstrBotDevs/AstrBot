---
outline: deep
head:
  - - style
    - {}
    - '.vp-doc table:has(thead th:nth-child(3)) th:nth-child(-n + 2), .vp-doc table:has(thead th:nth-child(3)) td:nth-child(-n + 2) { white-space: nowrap; }'
---

# AstrBot 插件开发指南 🌠

欢迎来到 AstrBot 插件开发指南！本章节将引导您如何开发 AstrBot 插件。在我们开始之前，希望你能具备以下基础知识：

1. 有一定的 Python 编程经验。
2. 有一定的 Git、GitHub 使用经验。

欢迎加入我们的开发者专用 QQ 群: `975206796`。

## 环境准备

### 获取插件模板

1. 打开 AstrBot 插件模板: [helloworld](https://github.com/Soulter/helloworld)
2. 点击右上角的 `Use this template`
3. 然后点击 `Create new repository`。
4. 在 `Repository name` 处填写您的插件名。插件名格式:
   - 推荐以 `astrbot_plugin_` 开头；
   - 不能包含空格；
   - 保持全部字母小写；
   - 尽量简短。
5. 点击右下角的 `Create repository`。

### 克隆项目到本地

克隆 AstrBot 项目本体和刚刚创建的插件仓库到本地。

```bash
git clone https://github.com/AstrBotDevs/AstrBot
mkdir -p AstrBot/data/plugins
cd AstrBot/data/plugins
git clone 插件仓库地址
```

然后，使用 `VSCode` 打开 `AstrBot` 项目。找到 `data/plugins/<你的插件名字>` 目录。

更新 `metadata.yaml` 文件，填写插件的元数据信息。

> [!WARNING]
> 请务必修改此文件，AstrBot 识别插件元数据依赖于 `metadata.yaml` 文件。

### 设置插件 Logo（可选）

可以在插件目录下添加 `logo.png` 文件作为插件的 Logo。请保持长宽比为 1:1，推荐尺寸为 256x256。

![插件 logo 示例](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### 插件展示名（可选）

可以修改(或添加) `metadata.yaml` 文件中的 `display_name` 字段，作为插件在插件市场等场景中的展示名，以方便用户阅读。

插件展示名和描述支持按 WebUI 语言显示，详见[插件国际化](./guides/plugin-i18n)。

### 插件短描述（可选）

你可以在 `metadata.yaml` 中新增 `short_desc` 字段，作为插件市场卡片上的短描述。它适合写成一句简短介绍；如果没有提供，卡片会回退显示 `desc`。

```yaml
short_desc: 一句话介绍你的插件。
```

### 随插件提供 Skills（可选）

插件可以在自己的目录下提供 `skills/` 文件夹。AstrBot 加载插件后会自动把其中合法的 Skill 纳入 Skill Manager，来源会显示为对应插件。

推荐一个插件包含多个 Skill 时使用以下结构：

```text
your_plugin/
  metadata.yaml
  main.py
  skills/
    web-search-helper/
      SKILL.md
    report-writer/
      SKILL.md
```

如果 `skills/` 本身就是一个 Skill，也可以直接放置：

```text
your_plugin/
  skills/
    SKILL.md
```

这种情况下 Skill 名称会使用插件目录名。插件提供的 Skill 由插件管理，在 WebUI 的 `插件 → 技能` 页面中作为只读来源展示；可以启用或禁用，但不能从本地 Skills 页面删除或编辑。插件卸载或更新后，对应 Skill 会随插件文件变化。

### 声明支持平台（Optional）

你可以在 `metadata.yaml` 中新增 `support_platforms` 字段（`list[str]`），声明插件支持的平台适配器。WebUI 插件页会展示该字段。

```yaml
support_platforms:
  - telegram
  - discord
```

`support_platforms` 中的值需要使用 `ADAPTER_NAME_2_TYPE` 的 key，目前支持：

- `aiocqhttp`
- `qq_official`
- `qq_official_webhook`
- `telegram`
- `wecom`
- `wecom_ai_bot`
- `lark`
- `dingtalk`
- `discord`
- `slack`
- `kook`
- `vocechat`
- `weixin_official_account`
- `weixin_oc`
- `satori`
- `misskey`
- `line`
- `matrix`
- `mattermost`

### 声明 AstrBot 版本范围（Optional）

你可以在 `metadata.yaml` 中新增 `astrbot_version` 字段，声明插件要求的 AstrBot 版本范围。格式与 `pyproject.toml` 依赖版本约束一致（PEP 440），且不要加 `v` 前缀。

```yaml
astrbot_version: ">=4.16,<5"
```

可选示例：

- `>=4.17.0`
- `>=4.16,<5`
- `~=4.17`

如果你只想声明最低版本，可以直接写：

- `>=4.17.0`

当当前 AstrBot 版本不满足该范围时，插件会被阻止加载并提示版本不兼容。
在 WebUI 安装插件时，你可以选择“无视警告，继续安装”来跳过这个检查。

### 声明插件分类（Optional）

你可以在 `metadata.yaml` 中新增 `category` 字段，主动声明插件的市场分类。WebUI 与运行时都以该字段为准；插件市场里显示的分类取决于市场索引是否收录了该值，索引收录时会复制这个字段，因此只改 `metadata.yaml` 不会立刻改变市场展示。

```yaml
category: media processing
```

`category` 取值为下列英文标识之一。中文翻译只是界面上的展示文案，写进 `category` 不会被识别。

| 标识 | 中文翻译 | 适用插件 |
| --- | --- | --- |
| `ai tools` | AI 增强 | 基于大模型的单次文本能力：提示词、文本改写、总结与翻译 |
| `ai image` | AI 绘图 | 文生图、图生图、画风转换与图片编辑 |
| `ai speech` | AI 语音 | TTS 与 ASR：语音合成、音色与语气、语音识别 |
| `ai agent` | 智能体与编排 | Agent 运行、工具调用、多智能体与工作流编排 |
| `ai context` | AI 对话 | 跨轮次的对话语境：人设与角色设定、上下文压缩与注入、对话风格与情绪语气；记忆存储归「长期记忆」，读外部文档归「知识库」 |
| `long term memory` | 长期记忆 | 记忆的存储与召回、用户画像与长期上下文 |
| `knowledge base` | 知识库 | 文档入库与检索问答（RAG）、知识库管理 |
| `tools` | 工具 | 通用小工具与命令集合：编码与格式转换、计算、短链、批量处理 |
| `productivity` | 效率 | 待办、日程、笔记与个人工作流 |
| `utilities` | 生活实用 | 生活信息查询与提醒：天气、汇率、快递、黄历、单位换算 |
| `integrations` | 外部集成 | 打通第三方平台或服务账号：GitHub、网盘、RSS、音乐、Notion |
| `platform adapter` | 平台适配器 | 接入新的消息平台或协议，如 QQ、Telegram、Discord |
| `media processing` | 媒体处理 | 图片、音频、视频的解析、转码、拼接与表情包生成 |
| `automation` | 自动化与定时 | 定时推送、自动回复、由事件触发的自动化流程 |
| `security` | 安全与审核 | 内容审核、反垃圾、敏感词、权限与风控 |
| `entertainment` | 娱乐 | 普通泛娱乐，不含游戏：塔罗、运势、点歌、表情包、梗图、玩梗闲聊 |
| `group games` | 群游戏 | 直接在群里玩、玩法由插件自身实现：接龙、猜词、谁是卧底、掷骰、答题 |
| `game integration` | 游戏接入 | 围绕别的游戏的外围插件：连接器、Wiki 与资料查询、服务器状态与玩家操作（Minecraft、幻兽帕鲁、Steam） |
| `other` | 其他 | 无法归入以上任一类的插件 |

取值会做轻度归一化：首尾空格、大小写以及空格、`-`、`_` 三种分隔符都会被忽略，所以下划线写法同样能识别，`ai tools`、`AI Tools`、`ai-tools` 与 `ai_tools` 等价。

未声明 `category` 的插件会归入 `other`。如果写了不支持的分类，AstrBot 会在日志中给出告警并同样归入 `other`，但**不会**阻止插件安装或更新。新增分类需要修改 AstrBot 源码，因此请优先使用上表中的标识。

### 调试插件

AstrBot 采用在运行时注入插件的机制。因此，在调试插件时，需要启动 AstrBot 本体。

您可以使用 AstrBot 的热重载功能简化开发流程。

插件的代码修改后，在 AstrBot WebUI 的 `插件` 页找到自己的插件，点击插件卡片上的刷新图标（`重载插件`）。

如果插件因为代码错误等原因加载失败，可以在同一页面的 `加载失败插件` 列表中点击对应插件的 `重载` 按钮。

### 插件依赖管理

目前 AstrBot 对插件的依赖管理使用 `pip` 自带的 `requirements.txt` 文件。如果你的插件需要依赖第三方库，请务必在插件目录下创建 `requirements.txt` 文件并写入所使用的依赖库，以防止用户在安装你的插件时出现依赖未找到(Module Not Found)的问题。

> `requirements.txt` 的完整格式可以参考 [pip 官方文档](https://pip.pypa.io/en/stable/reference/requirements-file-format/)。

## 开发原则

感谢您为 AstrBot 生态做出贡献，开发插件请遵守以下原则，这也是良好的编程习惯。

- 功能需经过测试。
- 需包含良好的注释。
- 持久化数据请存储于 `data` 目录下，而非插件自身目录，防止更新/重装插件时数据被覆盖。
- 良好的错误处理机制，不要让插件因一个错误而崩溃。
- 在进行提交前，请使用 [ruff](https://docs.astral.sh/ruff/) 工具格式化您的代码。
- 不要使用 `requests` 库来进行网络请求，可以使用 `aiohttp`, `httpx` 等异步网络请求库。
- 如果是对某个插件进行功能扩增，请优先给那个插件提交 PR 而不是单独再写一个插件（除非原插件作者已经停止维护）。
- 如果直接借鉴了其他项目的设计、功能创意或实现思路，请在 README 中清楚说明灵感来源并附上相关项目链接。
- 如果使用、修改或移植了其他项目的代码或资源，请遵守原项目的开源许可协议，并按协议要求保留版权及许可声明。

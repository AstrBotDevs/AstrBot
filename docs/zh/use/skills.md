# Anthropic Skills

Anthropic 推出的 Agent Skills（智能体技能）是一套模块化的功能扩展标准，旨在将 Claude 从一个“通用聊天机器人”转变为具备特定领域专业知识的“任务执行者”。Skills 是包含指令、脚本、元数据和参考资源的结构化文件夹。它不仅仅是提示词（Prompt），更像是一本专门的“操作手册”，在 Agent 需要执行特定任务时才会动态加载。Tool 是模型用来与外部世界交互的“具体工具/函数接口”，而 Skill 是将指令、模板和工具组合在一起的“标准化任务执行手册”。传统 Tool 需要在对话开始时一次性将所有 API 定义填入 Prompt。如果工具超过 50 个，可能还没开始说话就消耗了数万个 Token，导致响应变慢且昂贵。

AstrBot 在 v4.13.0 之后引入了对 Anthropic Skills 的支持，使得用户可以轻松集成和使用各种预定义的技能模块，提升 Agent 在特定任务上的表现。

## 关键特性

- 按需加载 (Progressive Disclosure)：模型初始只加载技能名称和简短描述。只有当任务匹配时，才会加载详细的 SKILL.md 指令，从而节省上下文窗口并降低成本。
- 高度可复用：技能可以在不同的 Claude API 项目、Claude Code 或 Claude.ai 中通用。
- 执行能力：技能可以包含可执行代码脚本，配合 Anthropic 代码执行环境（Code Execution）直接生成或处理文件。 

## 上传 Skills 到 AstrBot

进入 AstrBot 管理面板，导航到 `插件` 页面，找到 `Skills`。

![Skills](https://files.astrbot.app/docs/source/images/skills/image.png)

你可以上传 Skills，上传格式要求如下：

1. 是一个 .zip 压缩包
2. **解压后是一个 Skill 文件夹，Skill 文件夹的名字即为这个 Skill 在 AstrBot 中的标识，请用英文命名**。
3. Skill 文件夹内必须包含一个名为 `SKILL.md` 的文件，且该文件内容最好符合 Anthropic Skills 规范。你可以参考 [Anthropic 技能](https://code.claude.com/docs/zh-CN/skills)

## 在 AstrBot 使用 Skills

Skills 提供了 Agent 操作说明书，并且内容通常包含 Python 代码段、脚本等可执行内容。因此，Agent 需要一个**执行环境**。

目前，AstrBot 提供两种执行环境：

- Local（Agent 将在你的 AstrBot 运行环境中运行。**请谨慎使用，因为这会允许 Agent 在你的环境执行任意代码，可能带来安全风险**）
- Sandbox (Agent 在隔离化的沙盒环境中运行。**需要先启动 AstrBot 沙盒模式**，请参考：[沙盒模式](/use/astrbot-agent-sandbox)，如果这个模式下不启动沙盒模式，将不会将 Skills 传给 Agent)

你可以在 `配置` 页面 - 使用电脑能力 中选择默认的执行环境。

> [!NOTE]
> 需要说明的是，如果您使用 Local 作为执行环境，AstrBot 目前仅允许 **AstrBot 管理员**请求时才真正让 Agent 操作你的本地环境，普通用户将会被禁止，Agent 将无法通过 Shell、Python 等 Tool 在本地环境执行代码，会收到相应的权限限制提示，如 `Sorry, I cannot execute code on your local environment due to permission restrictions.`。


# Anthropic Skills

Anthropic's Agent Skills are a modular extension standard designed to turn Claude from a "general-purpose chatbot" into a "task executor" with domain-specific expertise. A Skill is a structured folder containing instructions, scripts, metadata, and reference resources. It is more than just a prompt—it functions like a specialized "operation manual" that is dynamically loaded only when the Agent needs to perform a specific task. A Tool is the model's concrete interface for interacting with the outside world (APIs/functions), while a Skill standardizes the combination of instructions, templates, and tools into a reusable task execution guide. Traditional Tools require all API definitions to be injected into the prompt at conversation start. If there are more than 50 tools, tens of thousands of tokens can be consumed before any conversation begins, making responses slower and costlier.

Support for Anthropic Skills was introduced in AstrBot starting from v4.13.0, allowing users to easily integrate and use various predefined skill modules to improve the Agent's performance on specific tasks.

## Key Features

- Progressive Disclosure: The model initially loads only skill names and short descriptions. Detailed `SKILL.md` instructions are loaded only when a task matches, saving context window space and reducing cost.
- Highly Reusable: Skills can be used across different Claude API projects, Claude Code, or Claude.ai.
- Executable Capability: Skills can include executable code scripts that, together with Anthropic's code execution environment, can directly generate or process files.

## Uploading Skills to AstrBot

Open the AstrBot admin panel, navigate to the `Plugins` page, and find `Skills`.

![Skills](https://files.astrbot.app/docs/source/images/skills/image.png)

You can upload Skills with the following requirements:

1. The upload must be a `.zip` archive.
2. **After extraction, it must contain a single Skill folder. The folder name will be used as the identifier for the Skill in AstrBot—please name it using English characters.**
3. The Skill folder must include a file named `SKILL.md`, and its contents should preferably follow the Anthropic Skills specification. You can refer to Anthropic's documentation: https://code.claude.com/docs/zh-CN/skills

## Using Skills in AstrBot

Skills serve as operation manuals for Agents and often include executable Python snippets and scripts. Therefore, an Agent requires an **execution environment**.

Currently, AstrBot provides two execution environments:

- Local — The Agent runs in your AstrBot runtime environment. **Use with caution: this allows the Agent to execute arbitrary code in your environment, which may pose security risks.**
- Sandbox — The Agent runs inside an isolated sandbox environment. **You must enable AstrBot sandbox mode first.** See: /use/astrbot-agent-sandbox. If sandbox mode is not enabled, Skills will not be passed to the Agent.

You can select the default execution environment on the `Config` page under "Computer Use".

> [!NOTE]
> Please note: if you select `Local` as the execution environment, AstrBot currently only allows **AstrBot administrators** to request that the Agent operate on your local environment. Regular users are prohibited from doing so. The Agent will be prevented from executing code locally via Shell, Python, or other tools and will receive a permission restriction message such as `Sorry, I cannot execute code on your local environment due to permission restrictions.`.

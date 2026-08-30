# Agent Runner

The Agent Runner is a component in AstrBot used to execute Agents.

AstrBot currently supports five Agent Runners:

- AstrBot Built-in Agent Runner
- Dify Agent Runner
- Coze Agent Runner
- Alibaba Cloud Bailian Application Agent Runner
- DeerFlow Agent Runner

By default, the AstrBot Built-in Agent Runner is the default runner.

## Why Abstract the Agent Runner

Platforms with built-in Agent capabilities such as Dify, Coze, Alibaba Cloud Bailian Application, and DeerFlow are fundamentally different from traditional Chat Providers that only perform model completion. Treating them as plain Chat Providers creates design and usage conflicts, so AstrBot models them as independent Agent Runners.

From an architectural perspective, you can understand it as:

- Chat Provider is responsible for "talking";
- Agent Runner is responsible for "thinking + doing".

The Agent Runner calls the Chat Provider's interface and, based on the Chat Provider's response, performs multi-turn "perceive → plan → execute action → observe result → re-plan" loops.

A Chat Provider is essentially a `single-turn completion interface`, taking prompt + conversation history + tool list as input and outputting model responses (text, tool call instructions, etc.).

An Agent Runner is typically a `loop` that receives user intent, context, and environment state, makes plans based on strategy/model (Plan), selects and invokes tools (Act), reads results from the environment (Observe), understands the results again, updates internal state, decides the next action, and repeats this process until the task is completed or times out.

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/agent-arch.svg)

Platforms like Dify, Coze, Bailian Application, and DeerFlow have this loop built-in. If you treat them as regular Chat Providers, it will conflict with AstrBot's built-in Agent Runner functionality.

## Usage

By default, the AstrBot Built-in Agent Runner is the default runner. Using the default runner can already meet most needs, and you can use AstrBot's MCP, knowledge base, web search, and other features.

If you need Dify, Coze, Bailian Application, or DeerFlow, switch the runner type on the configuration profile and fill in that runner's settings. Switching types loads the new type's defaults and does not keep the previous type's fields.

## Configure an Agent Runner

In the WebUI, open Configuration -> Agent Execution Method, choose a runner type, fill in that type's fields on the same page (API key, app ID, and so on), and save.

The built-in Agent's chat model, persona, compression, and tool settings also live on the same profile. They are no longer separate model providers.

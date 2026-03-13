# Agent Runner

The Agent Runner is a component in AstrBot used to execute Agents.

Starting from version v4.7.0, we have migrated three providers—Dify, Coze, and Alibaba Cloud Bailian Application—to the Agent Runner layer, reducing some conflicts with AstrBot's existing features. Rest assured, if you upgrade from an older version to v4.7.0, you don't need to take any action as AstrBot will automatically migrate for you. Later versions also added DeerFlow support as an Agent Runner provider.

AstrBot currently supports five Agent Runners:

- AstrBot Built-in Agent Runner
- Dify Agent Runner
- Coze Agent Runner
- Alibaba Cloud Bailian Application Agent Runner
- DeerFlow Agent Runner

By default, the AstrBot Built-in Agent Runner is the default runner.

## Why Abstract the Agent Runner

In earlier versions, platforms with "built-in Agent capabilities" like Dify, Coze, and Alibaba Cloud Bailian Application were integrated into AstrBot as regular Chat Providers. In practice, we found that they are fundamentally different from traditional Chat Providers that "only handle text completion". Forcing them into the same layer caused many design and usage conflicts. Therefore, starting from v4.7.0, we abstracted them into independent Agent Runners.

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

If you need to use the capabilities of platforms like Dify, Coze, Bailian Application, or DeerFlow, you can create an Agent Runner and select the corresponding provider.

## Creating an Agent Runner

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/image-1.png)

In the WebUI, click "Model Provider" -> "Add Provider", select "Agent Runner", choose the platform or runner type you want to connect to, and fill in the relevant information.

## Changing the Default Agent Runner

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/image.png)

In the WebUI, click "Configuration" -> "Agent Execution Method", change the runner type to the Agent Runner type you just created, then select `XX Agent Runner Provider ID` as the ID of the Agent Runner provider you just created, and click save.

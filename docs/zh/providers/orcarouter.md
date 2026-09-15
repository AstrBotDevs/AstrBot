# 接入 OrcaRouter

[OrcaRouter](https://www.orcarouter.ai) 是一个同时面向模型与 Agent 的 OpenAI 兼容 AI 网关。一个密钥即可通过同一端点访问多家厂商的模型，并提供自适应路由、自动故障转移、零加价推理、可观测性、护栏以及 Agent 工具治理。它还在同一端点上为 AI Agent 提供网关级的零信任安全能力——对每一个提示词与响应进行审查，并以默认拒绝的方式治理每一次工具调用，无需修改任何应用代码。

## 端点

| 用途 | 地址 |
| --- | --- |
| 推理与模型目录 | `https://api.orcarouter.ai/v1` |
| 授权与授权码兑换 | `https://www.orcarouter.ai` |

两者是不同的公开源（origin）。AstrBot 不会用其中一个推导另一个；自托管部署可以通过 `ORCA_BASE_URL`、`ORCA_API_BASE_URL` 和 `ORCA_AUTH_BASE_URL` 指向其他地址。

## 选择登录方式

打开 AstrBot 面板，进入 **服务提供商 → 新增服务提供商 → OrcaRouter**。该卡片会并列展示两种方式，任选其一即可独立使用。

### 方式一：OrcaRouter - API

将已有的 `sk-orca-…` 密钥填入服务提供商的 API Key 字段。可在 [OrcaRouter 控制台](https://www.orcarouter.ai/console/tokens) 创建。

密钥与其他服务提供商的密钥一同保存，不会写入日志、错误信息或遥测，面板中也只会显示掩码形式。

### 方式二：OrcaRouter - 授权登录

点击 **连接 OrcaRouter**，通过 OAuth 2.0 + PKCE 使用 OrcaRouter 账户完成授权。无需客户端密钥，也无需预先注册回调地址。授权码通过一个随机生成、永不离开服务端的 verifier 与 AstrBot 进程绑定，因此即使授权码被截获也无法被他人兑换。

请根据浏览器所在位置选择交付方式：

| 模式 | 适用场景 |
| --- | --- |
| **本机浏览器**（loopback 回调） | 浏览器与 AstrBot 运行在同一台机器，授权码会自动返回。 |
| **其他设备浏览器**（带外授权码） | AstrBot 运行在 NAS、容器或远程主机上，授权页面会显示授权码，粘贴回对话框即可。 |

无论使用哪种方式，最终得到的都是一个普通的 OrcaRouter API Key：它属于你的账户、由你付费，并可随时在 [已授权应用](https://www.orcarouter.ai/console/authorized-apps) 中撤销。

通过 PKCE 签发的密钥是**长期有效但不可刷新的**。AstrBot 会持续复用已保存的密钥，直到 OrcaRouter 撤销它，且不会尝试 refresh 授予。若密钥被撤销，该服务提供商会标记为需要重新授权，请重新签发或重新连接。

OrcaRouter 限制每个用户每 24 小时最多签发 10 个 PKCE 密钥，因此 AstrBot 会复用已保存的密钥，而不会在每次启动时重新授权。

## 模型

模型 ID 会保留厂商命名空间，例如 `openai/gpt-5.5` 或 `anthropic/claude-opus-4.8`。AstrBot 使用你的密钥从 `https://api.orcarouter.ai/v1/models` 读取实时模型目录，因此只会显示你的工作区真正可以调用的模型。

模型选择器会按各入口的实际需求过滤模型：

- **文本对话**只保留声明了 OpenAI 兼容端点类型的模型，并排除图片生成、视频、rerank 与 embedding 模型。
- **多模态理解**还要求模型明确声明你实际要上传的模态（图片、音频或视频）。未声明模态的模型不会出现在对应的多模态列表中。
- **Embedding、图片生成、视频生成与 rerank** 各自要求匹配的端点类型。

如果无法访问模型目录，AstrBot 会退回到一小组经过验证的模型，并将列表标记为降级状态，而不会允许你随意填写模型名。实时目录是权威来源，且不会与回退列表混合。

## 设为默认

进入 **设置 → 服务提供商设置**，将刚添加的 OrcaRouter 模型设为默认对话模型并保存。

## 证据

- 推理端点：`https://api.orcarouter.ai/v1`
- 模型目录：`https://api.orcarouter.ai/v1/models`
- 授权入口：`https://www.orcarouter.ai/auth`（兑换地址 `/api/v1/auth/keys`）
- 密钥管理：https://www.orcarouter.ai/console/tokens
- 撤销授权：https://www.orcarouter.ai/console/authorized-apps
- 服务与条款：https://www.orcarouter.ai

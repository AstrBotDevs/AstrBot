# DeepSeek Search API

[DeepSeek Search API](https://api-docs.deepseek.com/zh-cn/guides/search) 使用 DeepSeek 自研搜索引擎提供网页搜索，并通过 Fetch 接口将指定网页提取为 Markdown 正文，帮助 AI 智能体查找和阅读实时网页资料。

本页介绍 DeepSeek Search API 的配置与使用。网页搜索的通用准备条件、提供商对比和排错方法，请参见 [网页搜索](../websearch.md)。

## 获取 API Key

1. 打开 [DeepSeek 开放平台](https://platform.deepseek.com/)，注册或登录账号。
2. 进入 [API Keys 页面](https://platform.deepseek.com/api_keys)，创建并复制 API Key。
3. 确认账号余额和服务可用状态。搜索与正文提取按请求计费，当前价格及计费规则以 [官方文档](https://api-docs.deepseek.com/zh-cn/guides/search) 为准。

## 在 AstrBot 中配置

开始前，请确认聊天使用 AstrBot 内置 AI，且对话模型及其 API 支持工具调用。AstrBot 所在的服务器或容器需要能访问 `https://api.deepseek.com`。

1. 打开侧边栏的 `配置文件`，选择聊天实际使用的配置文件。
2. 进入 `AI → 能力 → 网页搜索`，打开 `启用网页搜索`。
3. 将 `网页搜索提供商` 设为 `DeepSeek Search API`（`deepseek`）。
4. 在 `DeepSeek API Key` 列表中添加获取到的 Key。一个 Key 就可以启用网页搜索和正文提取，也可以添加多个 Key 轮询使用。
5. 点击右下角的 `保存配置`。

这些设置只对当前配置文件生效。搜索与对话模型独立配置：不要求对话模型使用 DeepSeek；即使已配置 DeepSeek 对话模型，也需要在这里单独填写搜索 Key，可以使用同一个 Key。

## 支持的能力

| 能力 | AstrBot 返回的内容 |
| --- | --- |
| 网页搜索（Search） | 标题、来源链接和摘要，默认请求 10 条，可请求 1～50 条；模型请求附带正文时，也会包含可用的网页正文 |
| 正文提取（Fetch） | 指定网页的 URL、标题和 Markdown 正文；可读取用户提供的链接，也可继续阅读搜索结果中的页面 |

搜索默认返回摘要。需要更详细的信息时，可以要求模型在搜索时附带正文，或对选定的来源链接调用正文提取工具。实际结果数量和正文是否可用取决于搜索服务与目标网站。

## 在聊天中使用

保存配置后，向机器人或 ChatUI 发送明确的请求。模型会决定是否调用工具及使用哪些参数；若希望回答依据搜索结果，可以明确要求“先搜索再回答”。

### 网页搜索

```text
请先搜索 AstrBot 的最新发布信息，再说明版本号和主要变化，并附上来源链接。
```

### 限定搜索范围

搜索支持站点、语言、日期和排除条件，可以直接在聊天请求中说明：

```text
请搜索 AstrBot 在 GitHub 上的发布信息，仅查找 2026 年以来的内容，最多返回 5 条，并附上来源链接。
```

也可以明确提供搜索表达式，要求模型按该表达式搜索：

```text
请使用 DeepSeek Search API 搜索：AstrBot site:github.com lang:zh,en after:2026-01-01
```

可组合使用 `site:`、`-site:`、`lang:`、`after:`、`before:`、精确短语（双引号）和排除词（`-关键词`）。日期支持 `YYYY` 或 `YYYY-MM-DD`。搜索表达式连同筛选条件总长不能超过 128 个字符。

### 提取网页正文

```text
请阅读这个网页并总结安装步骤：https://docs.astrbot.app/deploy/astrbot/docker.html
```

Fetch 每次读取一个 HTTP 或 HTTPS 链接。登录限制、付费内容、网站访问策略和无法提取的页面都可能导致读取失败。

## 常见问题

### 已配置 DeepSeek 对话模型，但搜索仍提示缺少 Key

在当前配置文件的 `AI → 能力 → 网页搜索` 中单独填写 `DeepSeek API Key` 并保存。对话模型配置中的 Key 不会自动填入搜索配置。

### 余额不足或请求过于频繁

`402` 表示账号余额不足，`429` 表示触发限速。Search 与 Fetch 各自按账号限速，配置多个同账号 Key 不会提高限额；Fetch 还受到目标域名限速约束。当前限额以 [官方限速说明](https://api-docs.deepseek.com/zh-cn/guides/search#限速) 为准。

多个 Key 用于请求间轮询。单次请求失败时，AstrBot 不会立即换 Key 重试；遇到限速应降低请求频率后再试。

### 搜索有结果，但正文提取失败

尝试无需登录的公开网页，并在 `数据与日志 → 日志` 中查看具体错误。Fetch 的 `403` 可能表示请求被安全策略拒绝，`404` 可能表示无法获取可用正文。其他通用问题见 [网页搜索常见问题](../websearch.md#常见问题)。

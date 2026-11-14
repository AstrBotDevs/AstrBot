# SerpApi

[SerpApi](https://serpapi.com/astrbot-github) 提供来自 Google、Bing、百度等搜索引擎的结构化实时搜索数据，帮助 AI 智能体获取实时信息，无需自行管理网页抓取基础设施。

本页介绍 SerpApi 的配置与使用。网页搜索的通用准备条件、提供商对比和排错方法，请参见 [网页搜索](../websearch.md)。

## 获取 API Key

1. 打开 [SerpApi](https://serpapi.com/astrbot-github)，注册或登录账号。
2. 进入 [API Key 页面](https://serpapi.com/manage-api-key)，复制自己的 API Key。
3. 在 SerpApi 账号中确认有可用的搜索额度。当前额度、计费和服务权限以 SerpApi 官网及账号信息为准。

## 在 AstrBot 中配置

开始前，请确认聊天使用 AstrBot 内置 AI，且对话模型及其 API 支持工具调用。AstrBot 所在的服务器或容器需要能访问 `https://serpapi.com`。

1. 打开侧边栏的 `配置文件`，选择聊天实际使用的配置文件。
2. 进入 `AI → 能力 → 网页搜索`，打开 `启用网页搜索`。
3. 将 `网页搜索提供商` 设为 `serpapi`。
4. 在 `SerpApi API Key` 列表中添加获取到的 Key。一个 Key 就可以启用以下四种能力；也可以添加多个 Key 轮询使用。
5. 点击右下角的 `保存配置`。

这些设置只对当前配置文件生效。多个 Key 会轮询使用，鉴权或额度错误时会尝试下一个 Key。

## 支持的能力

| 能力 | 使用的 SerpApi 接口 | AstrBot 返回的内容 |
| --- | --- | --- |
| 网页搜索 | [Google Search API](https://serpapi.com/search-api) | 第一页中的标题、来源链接和摘要，默认最多 5 条，可请求最多 10 条 |
| 图片搜索 | [Google Images Light API](https://serpapi.com/google-images-light-api) | 图片直链、缩略图、来源页面及可用的尺寸信息，默认最多 5 张，可请求最多 10 张 |
| 金融查询 | [Google Finance API](https://serpapi.com/google-finance-api) | 可用的行情、币种、更新时间、财务数据和新闻；指定历史区间时返回行情摘要和可用的价格序列 |
| 学术搜索 | [Google Scholar API](https://serpapi.com/google-scholar-api) | 文献标题、摘要片段、出版信息、被引次数和可用的全文链接，默认最多 5 篇，可请求最多 20 篇 |

实际返回数量和字段取决于搜索结果，可能少于请求数量。网页和图片搜索支持指定国家和界面语言，网页搜索还支持指定搜索地点；学术搜索支持按发表年份筛选。这些条件可以直接写在聊天请求中，由模型传给工具。

## 在聊天中使用

保存配置后，向机器人或 ChatUI 发送明确的搜索请求。模型会决定调用哪个工具及使用哪些参数；若希望回答依据搜索结果，可以明确要求“先搜索再回答”。

### 网页搜索

```text
请搜索 AstrBot 的最新发布信息，说明版本号和主要变化，并附上来源链接。
```

网页搜索返回标题、链接和摘要，不会自动读取网页全文。AstrBot 的 SerpApi 接入不提供网页正文提取工具；如果经常需要总结指定链接的正文，可在 [提供商对比](../websearch.md#选择搜索提供商) 中选择支持正文提取的服务。

### 图片搜索

```text
请找三张咖啡图片，并附上来源页面。
```

图片结果包含图片直链和来源页面。能否直接展示或发送图片，取决于模型后续操作和所使用的消息平台。

### 金融查询

```text
请通过 Google Finance 查询 AAPL:NASDAQ 的行情，并注明更新时间。
```

Finance 接受 `AAPL:NASDAQ`、`.INX:INDEXSP`、`BTC-USD`、`EUR-USD` 等代码。需要历史行情时，可以明确指定区间：

```text
请通过 Google Finance 查询 AAPL:NASDAQ 近一个月的历史行情，并附上来源。
```

支持的历史区间为 `1D`、`5D`、`1M`、`6M`、`YTD`、`1Y`、`5Y` 和 `MAX`。指定历史区间后，接口返回行情摘要和可用的价格序列，不包含完整财务数据和新闻。

### 学术搜索

```text
请用 Google Scholar 查找 2023 年以来的检索增强生成论文，附上被引次数和可用的 PDF 链接。
```

可以指定发表年份范围和期望数量，最多返回 20 篇文献。摘要片段不等于论文全文，PDF 或其他全文链接仅在搜索结果提供时返回。

## 常见问题

### Key 无效、额度不足或请求超时

确认填写的是 SerpApi 的 Key，并检查账号剩余额度。在 `数据与日志 → 日志` 中查看具体错误；网络超时时，检查 AstrBot 所在环境能否访问 SerpApi API。通用排查步骤见 [网页搜索常见问题](../websearch.md#常见问题)。

### 没有调用图片、金融或学术搜索

确认当前配置文件已启用网页搜索、提供商为 `serpapi`，并已保存 Key。尝试使用上面的对应示例，明确要求图片搜索、Google Finance 或 Google Scholar。四种工具共用同一个配置，不需要另外开启；实际是否调用仍由模型决定。

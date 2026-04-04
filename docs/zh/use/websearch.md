# 网页搜索

网页搜索功能旨在提供大模型调用 Google，Bing，搜狗等搜索引擎以获取世界最近信息的能力，一定程度上能够提高大模型的回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/websearch)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，您可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://soulter.top`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示让大模型触发调用搜索工具。

AstrBot 支持 5 种网页搜索源接入方式：`默认`、`Tavily`、`百度 AI 搜索`、`BoCha`、`Exa`。

前者使用 AstrBot 内置的网页搜索请求器请求 Google、Bing、搜狗搜索引擎，在能够使用 Google 的网络环境下表现最佳。**我们推荐使用 Tavily 或 Exa**。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，您可选择 `default`（默认，不推荐）、`Tavily`、`百度 AI 搜索`、`BoCha` 或 `Exa`。

### default（不推荐）

如果您的设备在国内并且有代理，可以开启代理并在 `管理面板-其他配置-HTTP代理` 填入 HTTP 代理地址以应用代理。

启用默认搜索后，大模型将获得以下工具：

#### 网页搜索（web_search）

使用 Google、Bing、搜狗等搜索引擎进行搜索。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `max_results` | number | 否 | 返回的最大搜索结果数量，默认为 5 |

#### 网页内容提取（fetch_url）

提取任意 URL 的网页全文内容，可用于让大模型阅读和总结指定网页。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 要提取内容的网页 URL |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

### Tavily

前往 [Tavily](https://app.tavily.com/home) 得到 API Key，然后填写在相应的配置项。

如果您使用 Tavily 作为网页搜索源，在 AstrBot ChatUI 上将会获得更好的体验优化，包括引用来源展示等：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

如需使用代理或自建实例，可修改 `Tavily API Base URL` 配置项。

启用 Tavily 后，大模型将获得以下工具：

#### 搜索（web_search_tavily）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `max_results` | number | 否 | 返回的最大结果数量，范围 5-20，默认 7 |
| `search_depth` | string | 否 | 搜索深度，可选 `basic`（默认）或 `advanced` |
| `topic` | string | 否 | 搜索主题，可选 `general`（默认）或 `news` |
| `days` | number | 否 | 从当前日期往前包含的天数，仅在 `topic` 为 `news` 时生效 |
| `time_range` | string | 否 | 时间范围，可选 `day`、`week`、`month`、`year`，对 `general` 和 `news` 均生效 |
| `start_date` | string | 否 | 起始日期，格式 `YYYY-MM-DD` |
| `end_date` | string | 否 | 结束日期，格式 `YYYY-MM-DD` |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

#### 网页内容提取（tavily_extract_web_page）

提取任意 URL 的网页全文内容。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 要提取内容的网页 URL |
| `extract_depth` | string | 否 | 提取深度，可选 `basic`（默认）或 `advanced` |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

### Exa

前往 [Exa](https://dashboard.exa.ai) 获取 API Key，然后填写在相应的配置项。

Exa 提供基于语义理解的搜索能力，相比传统关键词搜索能够更精准地理解搜索意图。启用 Exa 后，大模型将获得以下三个工具：

#### 搜索（web_search_exa）

Exa 的核心搜索工具，支持以下搜索类型：

- `auto`：自动模式，由 Exa 根据查询内容智能选择最佳搜索方式（推荐）
- `neural`：语义搜索，基于嵌入向量匹配，适合模糊或描述性的查询
- `fast`：快速搜索，优先返回速度，适合简单关键词查询
- `instant`：即时搜索，适合需要快速获取摘要的场景
- `deep`：深度搜索，更全面地检索相关结果，适合复杂研究类查询

此外，搜索支持按垂直领域筛选结果：

| 类别 | 说明 |
|------|------|
| `company` | 5000 万+ 公司主页 |
| `people` | 10 亿+ 个人主页/档案 |
| `research paper` | 1 亿+ 研究论文 |
| `news` | 新闻资讯 |
| `personal site` | 个人网站/博客 |
| `financial report` | 财务报告 |

**工具参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `max_results` | number | 否 | 返回的最大结果数量，范围 1-100，默认 10 |
| `search_type` | string | 否 | 搜索类型，可选 `auto`（默认）、`neural`、`fast`、`instant`、`deep` |
| `category` | string | 否 | 垂直领域筛选，默认为空（通用搜索） |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

#### 内容提取（exa_extract_web_page）

提取任意 URL 的网页全文内容，可用于让大模型阅读和总结指定网页。您可以直接对大模型说：

- `帮我总结一下这个链接：https://example.com`
- `读取这个页面的内容：https://example.com`

**工具参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 要提取内容的网页 URL |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

#### 相似链接（exa_find_similar）

Exa 独有的功能，根据给定的 URL 查找语义相似的网页。适合用于扩展阅读、查找同类资源或发现相关内容。

**工具参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 用于查找相似内容的网页 URL |
| `max_results` | number | 否 | 返回的最大结果数量，范围 1-100，默认 10 |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |

如需使用代理或自建实例，可修改 `Exa API Base URL` 配置项。

### 百度 AI 搜索

前往 [百度智能云控制台](https://console.bce.baidu.com/iam/#/iam/apikey/list) 获取 APP Builder API Key，然后填写在相应的配置项。

百度 AI 搜索通过 MCP 协议接入，启用后大模型将自动获得 `baidu_ai_search` 工具，无需额外配置工具参数。

### BoCha

前往 [BoCha](https://www.bocha.ai) 获取 API Key，然后填写在相应的配置项。

启用 BoCha 后，大模型将获得以下工具：

#### 搜索（web_search_bocha）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `freshness` | string | 否 | 时间范围筛选。可选 `noLimit`（默认，推荐）、`oneDay`、`oneWeek`、`oneMonth`、`oneYear`，或指定日期 `YYYY-MM-DD`、日期范围 `YYYY-MM-DD..YYYY-MM-DD`。建议使用 `noLimit`，搜索算法会自动优化时间相关性，手动限制可能导致无结果 |
| `summary` | boolean | 否 | 是否为每个搜索结果包含文本摘要，默认 `false` |
| `include` | string | 否 | 限定搜索域名，多个域名用 `\|` 或 `,` 分隔，最多 100 个。示例：`qq.com` 或 `qq.com\|m.163.com` |
| `exclude` | string | 否 | 排除搜索域名，多个域名用 `\|` 或 `,` 分隔，最多 100 个。示例：`qq.com` 或 `qq.com\|m.163.com` |
| `count` | number | 否 | 返回的搜索结果数量，范围 1-50，默认 10（实际返回数量可能少于指定值） |
| `timeout` | number | 否 | 请求超时时间（秒），最小 30，默认 30 |
# 网页搜索

网页搜索功能旨在为大模型提供联网检索能力，以获取最近信息，一定程度上能够提高回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/websearch)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，你可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://soulter.top`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示，让大模型触发调用搜索工具。

AstrBot 当前支持 5 种网页搜索源接入方式：`Tavily`、`BoCha`、`百度 AI 搜索`、`Brave`、`Exa`。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，你可选择 `Tavily`、`BoCha`、`百度 AI 搜索`、`Brave` 或 `Exa`。

如果你使用 Tavily 作为网页搜索源，在 AstrBot ChatUI 上会获得更好的引用来源展示体验：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

## Tavily

前往 [Tavily](https://app.tavily.com/home) 获取 API Key，然后填写在相应配置项中。

如需使用代理或自建实例，可修改 `Tavily API Base URL` 配置项。

Tavily 提供两个工具：

### 搜索（`web_search_tavily`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 搜索关键词 |
| `max_results` | number | 否 | 7 | 返回最大结果数，范围 5-20 |
| `search_depth` | string | 否 | `basic` | 搜索深度，可选 `basic` 或 `advanced` |
| `topic` | string | 否 | `general` | 搜索主题，可选 `general` 或 `news` |
| `days` | number | 否 | 3 | 向前追溯的天数，仅 `topic=news` 时生效 |
| `time_range` | string | 否 | - | 时间范围，可选 `day`、`week`、`month`、`year` |
| `start_date` | string | 否 | - | 起始日期，格式 `YYYY-MM-DD` |
| `end_date` | string | 否 | - | 结束日期，格式 `YYYY-MM-DD` |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

### 网页内容提取（`tavily_extract_web_page`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string | 是 | - | 要提取内容的网页 URL |
| `extract_depth` | string | 否 | `basic` | 提取深度，可选 `basic` 或 `advanced` |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

## 百度 AI 搜索

前往 [百度智能云控制台](https://console.bce.baidu.com/iam/#/iam/apikey/list) 获取 API Key，然后填写在 `websearch_baidu_app_builder_key` 配置项中。

百度 AI 搜索提供一个工具：

### 搜索（`web_search_baidu`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 搜索关键词 |
| `top_k` | number | 否 | 10 | 返回的网页结果数量，最大 50 |
| `search_recency_filter` | string | 否 | - | 时间范围，可选 `week`、`month`、`semiyear`、`year` |
| `site` | string | 否 | - | 限定搜索站点，多个站点可用 `,` 或 `\|` 分隔 |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

## BoCha

前往 [BoCha](https://www.bocha.ai) 获取 API Key，然后填写在相应配置项中。

BoCha 提供一个工具：

### 搜索（`web_search_bocha`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 搜索关键词 |
| `freshness` | string | 否 | `noLimit` | 时间范围筛选，可选 `noLimit`、`oneDay`、`oneWeek`、`oneMonth`、`oneYear`、`YYYY-MM-DD..YYYY-MM-DD` 或 `YYYY-MM-DD` |
| `summary` | boolean | 否 | `false` | 是否返回每条结果的摘要 |
| `include` | string | 否 | - | 仅搜索指定域名，多个域名用 `\|` 或 `,` 分隔 |
| `exclude` | string | 否 | - | 排除指定域名，多个域名用 `\|` 或 `,` 分隔 |
| `count` | number | 否 | 10 | 返回结果数量，范围 1-50 |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

## Brave

前往 Brave Search 获取 API Key，然后填写在相应配置项中。

Brave 提供一个工具：

### 搜索（`web_search_brave`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 搜索关键词 |
| `count` | number | 否 | 10 | 返回结果数量，范围 1-20 |
| `country` | string | 否 | `US` | 国家/地区代码 |
| `search_lang` | string | 否 | `zh-hans` | 搜索语言代码 |
| `freshness` | string | 否 | - | 时间范围，可选 `day`、`week`、`month`、`year` |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

## Exa

前往 [Exa](https://dashboard.exa.ai) 获取 API Key，然后填写在相应配置项中。

如需使用代理或自建实例，可修改 `Exa API Base URL` 配置项。

Exa 提供三个工具：

### 搜索（`web_search_exa`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | - | 搜索关键词 |
| `max_results` | number | 否 | 10 | 返回最大结果数，范围 1-100 |
| `search_type` | string | 否 | `auto` | 搜索类型，可选 `auto`、`neural`、`fast`、`instant`、`deep` |
| `category` | string | 否 | - | 垂直类别，可选 `company`、`people`、`research paper`、`news`、`personal site`、`financial report` |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

### 内容提取（`exa_extract_web_page`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string | 是 | - | 要提取内容的网页 URL |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

### 相似链接（`exa_find_similar`）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `url` | string | 是 | - | 用于查找相似内容的网页 URL |
| `max_results` | number | 否 | 10 | 返回最大结果数，范围 1-100 |
| `timeout` | number | 否 | 30 | 请求超时时间（秒），最小 30 |

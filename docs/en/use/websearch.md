# Web Search

The web search feature gives large language models internet retrieval capability for recent information, which can improve response accuracy and reduce hallucinations to some extent.

AstrBot's built-in web search functionality relies on the large language model's `function calling` capability. If you're not familiar with function calling, please refer to: [Function Calling](/use/websearch).

When using a large language model that supports function calling with the web search feature enabled, you can try saying:

- `Help me search for xxx`
- `Help me summarize this link: https://soulter.top`
- `Look up xxx`
- `Recent xxxx`

And other prompts with search intent to trigger the model to invoke the search tool.

AstrBot currently supports 5 web search providers: `Tavily`, `BoCha`, `Baidu AI Search`, `Brave`, and `Exa`.

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

Go to `Configuration`, scroll down to find Web Search, where you can select `Tavily`, `BoCha`, `Baidu AI Search`, `Brave`, or `Exa`.

If you use Tavily as your web search source, you will get a better experience optimization on AstrBot ChatUI, including citation source display and more:

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

## Tavily

Go to [Tavily](https://app.tavily.com/home) to get an API key, then fill it in the corresponding configuration item.

To use a proxy or self-hosted instance, modify the `Tavily API Base URL` configuration item.

Tavily exposes two tools:

### Search (`web_search_tavily`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | - | Search query |
| `max_results` | number | No | 7 | Maximum number of results to return. Range: 5-20 |
| `search_depth` | string | No | `basic` | Search depth. Must be `basic` or `advanced` |
| `topic` | string | No | `general` | Search topic. Must be `general` or `news` |
| `days` | number | No | 3 | Number of days back from today to include. Only available when `topic` is `news` |
| `time_range` | string | No | - | Time range for results. Must be `day`, `week`, `month`, or `year` |
| `start_date` | string | No | - | Start date in `YYYY-MM-DD` format |
| `end_date` | string | No | - | End date in `YYYY-MM-DD` format |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Extract Web Page (`tavily_extract_web_page`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | - | The URL to extract content from |
| `extract_depth` | string | No | `basic` | Extraction depth. Must be `basic` or `advanced` |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

## Baidu AI Search

Go to the [BCE Console](https://console.bce.baidu.com/iam/#/iam/apikey/list) to get an API key, then fill it in the `websearch_baidu_app_builder_key` configuration item.

Baidu AI Search exposes one tool:

### Search (`web_search_baidu`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | - | Search query |
| `top_k` | number | No | 10 | Number of web results to return. Maximum 50 |
| `search_recency_filter` | string | No | - | Time filter. Must be `week`, `month`, `semiyear`, or `year` |
| `site` | string | No | - | Restrict search to specific sites, separated by `,` or `\|` |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

## BoCha

Go to [BoCha](https://www.bocha.ai) to get an API key, then fill it in the corresponding configuration item.

BoCha exposes one tool:

### Search (`web_search_bocha`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | - | Search query |
| `freshness` | string | No | `noLimit` | Time range filter. Supported values: `noLimit`, `oneDay`, `oneWeek`, `oneMonth`, `oneYear`, `YYYY-MM-DD..YYYY-MM-DD`, or `YYYY-MM-DD` |
| `summary` | boolean | No | `false` | Whether to include a summary for each result |
| `include` | string | No | - | Domains to include. Multiple domains separated by `\|` or `,` |
| `exclude` | string | No | - | Domains to exclude. Multiple domains separated by `\|` or `,` |
| `count` | number | No | 10 | Number of results to return. Range: 1-50 |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

## Brave

Go to Brave Search to get an API key, then fill it in the corresponding configuration item.

Brave exposes one tool:

### Search (`web_search_brave`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | - | Search query |
| `count` | number | No | 10 | Number of results to return. Range: 1-20 |
| `country` | string | No | `US` | Country code for region-specific results |
| `search_lang` | string | No | `zh-hans` | Brave language code |
| `freshness` | string | No | - | Time range. Must be `day`, `week`, `month`, or `year` |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

## Exa

Go to [Exa](https://dashboard.exa.ai) to get an API key, then fill it in the corresponding configuration item.

To use a proxy or self-hosted instance, modify the `Exa API Base URL` configuration item.

Exa exposes three tools:

### Search (`web_search_exa`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | - | Search query |
| `max_results` | number | No | 10 | Maximum number of results to return. Range: 1-100 |
| `search_type` | string | No | `auto` | Search type. Must be `auto`, `neural`, `fast`, `instant`, or `deep` |
| `category` | string | No | - | Vertical category. Supported values: `company`, `people`, `research paper`, `news`, `personal site`, `financial report` |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Content Extraction (`exa_extract_web_page`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | - | The URL to extract content from |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Find Similar (`exa_find_similar`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | - | The URL to find similar content for |
| `max_results` | number | No | 10 | Maximum number of results to return. Range: 1-100 |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

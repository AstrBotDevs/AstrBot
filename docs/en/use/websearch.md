
# Web Search

The web search feature aims to provide large language models with the ability to invoke search engines like Google, Bing, and Sogou to obtain recent world information, which can improve the accuracy of model responses and reduce hallucinations to some extent.

AstrBot's built-in web search functionality relies on the large language model's `function calling` capability. If you're not familiar with function calling, please refer to: [Function Calling](/use/websearch).

When using a large language model that supports function calling with the web search feature enabled, you can try saying:

- `Help me search for xxx`
- `Help me summarize this link: https://soulter.top`
- `Look up xxx`
- `Recent xxxx`

And other prompts with search intent to trigger the model to invoke the search tool.

AstrBot supports 5 types of web search source integration: `default`, `Tavily`, `Baidu AI Search`, `BoCha`, and `Exa`.

The former uses AstrBot's built-in web search requester to query Google, Bing, and Sogou search engines, performing best in network environments with Google access. **We recommend using Tavily or Exa**.

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

Go to `Configuration`, scroll down to find Web Search, where you can select `default` (default, not recommended), `Tavily`, `Baidu AI Search`, `BoCha`, or `Exa`.

### default (Not Recommended)

If your device is in China and you have a proxy, you can enable the proxy and enter the HTTP proxy address in `Admin Panel - Other Configuration - HTTP Proxy` to apply the proxy.

The default provider exposes two tools:

- **`web_search`** — Searches the web via Bing and Sogou engines.
- **`fetch_url`** — Extracts the full text content from any given URL. Useful for reading and summarizing web pages when search result snippets are not sufficient. Parameters:

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | — | The URL of the web page to fetch content from |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Tavily

Go to [Tavily](https://app.tavily.com/home) to get an API Key, then fill it in the corresponding configuration item.

If you use Tavily as your web search source, you will get a better experience optimization on AstrBot ChatUI, including citation source display and more:

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

To use a proxy or self-hosted instance, modify the `Tavily API Base URL` configuration item.

The Tavily provider exposes two tools:

#### 1. Search (`web_search_tavily`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | — | Search query |
| `max_results` | number | No | 7 | Maximum number of results to return. Range: 5–20 |
| `search_depth` | string | No | `basic` | Search depth. Must be `basic` or `advanced` |
| `topic` | string | No | `general` | Search topic. Must be `general` or `news` |
| `days` | number | No | 3 | Number of days back from today to include. Only available when `topic` is `news` |
| `time_range` | string | No | — | Time range for results. Must be one of `day`, `week`, `month`, `year`. Available for both `general` and `news` topics |
| `start_date` | string | No | — | Start date for results in `YYYY-MM-DD` format |
| `end_date` | string | No | — | End date for results in `YYYY-MM-DD` format |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

#### 2. Extract Web Page (`tavily_extract_web_page`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | — | The URL to extract content from |
| `extract_depth` | string | No | `basic` | Extraction depth. Must be `basic` or `advanced` |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Baidu AI Search

Go to the [BCE Console](https://console.bce.baidu.com/iam/#/iam/apikey/list) to get an API Key, then fill it in the `websearch_baidu_app_builder_key` configuration item.

Baidu AI Search uses the MCP (Model Context Protocol) to communicate with Baidu's AI Search service. The tool is registered as `AIsearch` internally but commonly referred to as `baidu_ai_search`. Since it operates via MCP, no tool parameters are exposed directly — the model interacts with the service through the MCP protocol.

### BoCha

Go to [BoCha](https://www.bocha.ai) to get an API Key, then fill it in the corresponding configuration item.

The BoCha provider exposes one tool:

#### Search (`web_search_bocha`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | — | Search query |
| `freshness` | string | No | `noLimit` | Time range filter. Supported values: `noLimit`, `oneDay`, `oneWeek`, `oneMonth`, `oneYear`, `YYYY-MM-DD..YYYY-MM-DD` (date range), or `YYYY-MM-DD` (exact date). Using `noLimit` is recommended as the search algorithm will automatically optimize time relevance |
| `summary` | boolean | No | `false` | Whether to include a text summary for each result |
| `include` | string | No | — | Domains to include. Multiple domains separated by `\|` or `,` (max 100 domains). Example: `qq.com\|m.163.com` |
| `exclude` | string | No | — | Domains to exclude. Same format as `include` |
| `count` | number | No | 10 | Number of results to return. Range: 1–50. Actual results may be fewer |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

### Exa

Go to [Exa](https://dashboard.exa.ai) to get an API Key, then fill it in the corresponding configuration item.

Exa provides semantic search capabilities powered by neural embeddings, offering three integrated tools for the model to use:

#### 1. Search (`web_search_exa`)

The core search tool supports 5 search types:

- `auto` — Automatically selects the best search mode based on the query (default)
- `neural` — Semantic search using embeddings, ideal for conceptual or natural language queries
- `fast` — Fast keyword-based search for quick results
- `instant` — Near-instant results for simple factual queries
- `deep` — Deep search with thorough result exploration

Additionally, Exa supports 6 vertical categories for domain-specific searches:

| Category | Coverage |
|---|---|
| `company` | 50M+ company pages |
| `people` | 1B+ profiles |
| `research paper` | 100M+ academic papers |
| `news` | News articles and reports |
| `personal site` | Personal websites and blogs |
| `financial report` | Financial filings and data |

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | Yes | — | Search query |
| `max_results` | number | No | 10 | Maximum number of results to return. Range: 1–100 |
| `search_type` | string | No | `auto` | Search type. Must be one of `auto`, `neural`, `fast`, `instant`, `deep` |
| `category` | string | No | — | Vertical search category. Supported values: `company`, `people`, `research paper`, `news`, `personal site`, `financial report`. Leave empty for general web search |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

#### 2. Content Extraction (`exa_extract_web_page`)

Extracts full text content from any given URL. The model can use this to read and summarize web pages, articles, or documents when the search result snippet is not sufficient.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | — | The URL to extract content from |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

#### 3. Find Similar (`exa_find_similar`)

Finds semantically similar webpages to a given URL. This is a unique Exa feature that allows discovering related content based on neural embeddings rather than keyword matching.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | — | The URL of the webpage to find similar content for |
| `max_results` | number | No | 10 | Maximum number of similar results to return. Range: 1–100 |
| `timeout` | number | No | 30 | Request timeout in seconds. Minimum is 30 |

To use a proxy or self-hosted instance, modify the `Exa API Base URL` configuration.

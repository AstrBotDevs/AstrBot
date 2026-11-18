# SerpApi

[SerpApi](https://serpapi.com/astrbot-github) provides structured, real-time search data from Google, Bing, Baidu and other search engines, helping AI agents access real-time information without managing web scraping infrastructure.

This page covers SerpApi setup and usage. See [Web Search](../websearch.md) for general prerequisites, provider comparisons, and troubleshooting.

## Get an API key

1. Open [SerpApi](https://serpapi.com/astrbot-github) and create an account or sign in.
2. Open the [API key page](https://serpapi.com/manage-api-key) and copy your key.
3. Check that your SerpApi account has search quota available. Refer to SerpApi's website and your account for current quotas, billing, and service access.

## Configure AstrBot

Your conversation must use AstrBot Built-in AI, and both the chat model and its API must support tool calling. The server or container running AstrBot must be able to reach `https://serpapi.com`.

1. Open `Config` in the sidebar and select the profile your conversation actually uses.
2. Open `AI → Capabilities → Web Search` and turn on `Enable Web Search`.
3. Set `Web Search Provider` to `serpapi`.
4. Add your key to the `SerpApi API Key` list. One key enables all four capabilities below; you can also add multiple keys for rotation.
5. Click `Save Configuration` at the bottom right.

These settings apply only to the selected profile. Multiple keys rotate, and authentication or quota errors trigger a retry with the next key.

## Supported capabilities

| Capability | SerpApi endpoint | Content returned by AstrBot |
| --- | --- | --- |
| Web search | [Google Search API](https://serpapi.com/search-api) | Titles, source URLs, and snippets from the first page; up to 5 results by default, with a requested maximum of 10 |
| Image search | [Google Images Light API](https://serpapi.com/google-images-light-api) | Direct image URLs, thumbnails, source pages, and available dimensions; up to 5 images by default, with a requested maximum of 10 |
| Finance queries | [Google Finance API](https://serpapi.com/google-finance-api) | Available quotes, currencies, timestamps, financial data, and news; a history window returns the quote summary and available price series |
| Academic search | [Google Scholar API](https://serpapi.com/google-scholar-api) | Publication titles, snippets, publication details, citation counts, and available full-text links; up to 5 publications by default, with a requested maximum of 20 |

The actual number of results and available fields depend on the search response and may be fewer than requested. Web and image search support country and interface language settings. Web search also supports a search location, and academic search supports publication year filters. Include these requirements in your message so the model can pass them to the tool.

## Use SerpApi in a conversation

After saving, send the bot or ChatUI an explicit search request. The model chooses the tool and its parameters. Ask it to “search first, then answer” when you want an answer based on search results.

### Web search

```text
Search for AstrBot's latest release. Give the version, summarize the main changes, and include source links.
```

Web search returns titles, links, and snippets without automatically reading full pages. AstrBot's SerpApi integration does not provide a page extraction tool. If you often need to summarize a specific URL, choose a service with page extraction from the [provider comparison](../websearch.md#choose-a-search-provider).

### Image search

```text
Find three images of coffee and include their source pages.
```

Image results include direct image URLs and source pages. Displaying or sending an image depends on the model's subsequent actions and the messaging platform.

### Finance queries

```text
Look up AAPL:NASDAQ on Google Finance and include the quote timestamp.
```

Finance accepts symbols such as `AAPL:NASDAQ`, `.INX:INDEXSP`, `BTC-USD`, and `EUR-USD`. Specify a time range when you need historical prices:

```text
Look up the past month of price history for AAPL:NASDAQ on Google Finance and include the source.
```

Supported history windows are `1D`, `5D`, `1M`, `6M`, `YTD`, `1Y`, `5Y`, and `MAX`. With a history window, the API returns the quote summary and available price series instead of full financial data and news.

### Academic search

```text
Search Google Scholar for retrieval augmented generation papers published since 2023. Include citation counts and available PDF links.
```

You can specify a publication year range and request up to 20 publications. Snippets are not the full papers; PDF and other full-text links are returned only when available in the search response.

## Troubleshooting

### Invalid key, quota errors, or timeouts

Confirm that you entered a SerpApi key and check your remaining account quota. Inspect the error under `Data & Logs → Logs`. For timeouts, check whether the AstrBot environment can reach the SerpApi API. See [Web Search troubleshooting](../websearch.md#troubleshooting) for general checks.

### The model does not use image, finance, or academic search

Confirm that Web Search is enabled for the active profile, the provider is `serpapi`, and the key has been saved. Try the corresponding example above and explicitly request image search, Google Finance, or Google Scholar. All four tools share the same configuration, with no extra switch required; the model still decides whether to call them.

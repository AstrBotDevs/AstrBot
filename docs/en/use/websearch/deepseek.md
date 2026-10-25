# DeepSeek Search API

[DeepSeek Search API](https://api-docs.deepseek.com/guides/search) uses DeepSeek's own search engine for web search and provides a Fetch API that extracts a page as Markdown, helping AI agents find and read current web content.

This page covers DeepSeek Search API setup and usage. See [Web Search](../websearch.md) for general prerequisites, provider comparisons, and troubleshooting.

## Get an API key

1. Open the [DeepSeek Platform](https://platform.deepseek.com/) and create an account or sign in.
2. Open the [API Keys page](https://platform.deepseek.com/api_keys), create a key, and copy it.
3. Check your account balance and service availability. Search and Fetch are billed per request; see the [official documentation](https://api-docs.deepseek.com/guides/search) for current prices and billing rules.

## Configure AstrBot

Your conversation must use AstrBot Built-in AI, and both the chat model and its API must support tool calling. The server or container running AstrBot must be able to reach `https://api.deepseek.com`.

1. Open `Config` in the sidebar and select the profile your conversation actually uses.
2. Open `AI → Web Search` and turn on `Enable Web Search`.
3. Set `Web Search Provider` to `DeepSeek Search API` (`deepseek`).
4. Add your key to the `DeepSeek API Key` list. One key enables both web search and page extraction; you can also add multiple keys for rotation.
5. Click `Save Configuration` at the bottom right.

These settings apply only to the selected profile. Search is configured independently of the chat model: you can use a chat model from another provider. Even if your chat model already uses DeepSeek, enter the search key separately here; you may use the same key.

## Supported capabilities

| Capability | Content returned by AstrBot |
| --- | --- |
| Web search (Search) | Titles, source URLs, and summaries; 10 results requested by default, with a supported range of 1–50. Available page content is included when requested by the model |
| Page extraction (Fetch) | The URL, title, and Markdown content of a specific page, including links supplied by the user or found through search |

Search returns summaries by default. For more detail, ask the model to include page content in its search request or use the extraction tool on a selected source link. The actual number of results and availability of page content depend on the search service and target website.

## Use DeepSeek Search API in a conversation

After saving, send the bot or ChatUI an explicit request. The model decides whether to call a tool and which parameters to use. Ask it to “search first, then answer” when you want an answer based on search results.

### Web search

```text
Search for AstrBot's latest release before answering. Give the version, summarize the main changes, and include source links.
```

### Narrow the search

Search supports site, language, date, and exclusion operators. Describe these requirements in your message:

```text
Search GitHub for AstrBot release information published since the start of 2026. Return up to 5 results and include source links.
```

You can also supply an explicit search expression:

```text
Use DeepSeek Search API to search for: AstrBot site:github.com lang:zh,en after:2026-01-01
```

You can combine `site:`, `-site:`, `lang:`, `after:`, `before:`, exact phrases in double quotes, and excluded terms (`-keyword`). Dates accept `YYYY` or `YYYY-MM-DD`. The complete search expression, including operators, must not exceed 128 characters.

### Extract page content

```text
Read this page and summarize its installation steps: https://docs.astrbot.app/en/deploy/astrbot/docker.html
```

Fetch reads one HTTP or HTTPS URL at a time. Login requirements, paywalls, site access policies, and pages without extractable content can prevent extraction.

## Troubleshooting

### Search reports a missing key even though the DeepSeek chat model is configured

Enter the `DeepSeek API Key` separately under `AI → Web Search` for the active profile and save. The chat model key is not automatically used for search.

### Insufficient balance or rate limits

`402` indicates insufficient account balance, and `429` indicates a rate limit. Search and Fetch have separate account limits. Multiple keys under the same account do not increase those limits, and Fetch also has a per-domain limit. See the [official rate limits](https://api-docs.deepseek.com/guides/search#rate-limits) for current values.

Multiple keys rotate between requests. AstrBot does not immediately retry a failed request with another key; reduce the request rate before trying again after a rate limit error.

### Search works, but page extraction fails

Try a public page that does not require a login and inspect the error under `Data & Logs → Logs`. A Fetch `403` can indicate a security policy rejection; `404` can indicate that no usable page content could be retrieved. See [Web Search troubleshooting](../websearch.md#troubleshooting) for general checks.

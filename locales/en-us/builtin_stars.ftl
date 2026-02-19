### astrbot/builtin_stars/web_searcher/main.py
builtin-stars-web-searcher-legacy-tavily-key-migrated = Detected legacy websearch_tavily_key (string format); auto-migrated to list format and saved.
builtin-stars-web-searcher-scraping-web = web_searcher - scraping web: { $title } - { $url }
builtin-stars-web-searcher-bing-search-error = bing search error: { $error }, try the next one...
builtin-stars-web-searcher-bing-search-failed = search bing failed
builtin-stars-web-searcher-sogo-search-error = sogo search error: { $error }
builtin-stars-web-searcher-sogo-search-failed = search sogo failed
builtin-stars-web-searcher-tavily-key-not-configured = Error: Tavily API key is not configured in AstrBot.
builtin-stars-web-searcher-tavily-search-failed = Tavily web search failed: { $reason }, status: { $status }
builtin-stars-web-searcher-tavily-no-results = Error: Tavily web searcher does not return any results.
builtin-stars-web-searcher-command-deprecated = This command is deprecated. Please enable or disable web search in WebUI.
builtin-stars-web-searcher-search-from-engine = web_searcher - search_from_search_engine: { $query }
builtin-stars-web-searcher-default-no-results = Error: web searcher does not return any results.
builtin-stars-web-searcher-process-result-error = Error processing search result: { $error }
builtin-stars-web-searcher-link-summary-instruction = {"\u000A"}{"\u000A"}For the question, summarize key points based on the results above, and append reference links at the end when available.
builtin-stars-web-searcher-baidu-key-not-configured = Error: Baidu AI Search API key is not configured in AstrBot.
builtin-stars-web-searcher-baidu-mcp-init-success = Successfully initialized Baidu AI Search MCP server.
builtin-stars-web-searcher-search-from-tavily = web_searcher - search_from_tavily: { $query }
builtin-stars-web-searcher-url-empty = Error: url must be a non-empty string.
builtin-stars-web-searcher-bocha-key-not-configured = Error: BoCha API key is not configured in AstrBot.
builtin-stars-web-searcher-bocha-search-failed = BoCha web search failed: { $reason }, status: { $status }
builtin-stars-web-searcher-search-from-bocha = web_searcher - search_from_bocha: { $query }
builtin-stars-web-searcher-bocha-no-results = Error: BoCha web searcher does not return any results.
builtin-stars-web-searcher-baidu-tool-not-found = Cannot get Baidu AI Search MCP tool.
builtin-stars-web-searcher-baidu-mcp-init-failed = Cannot initialize Baidu AI Search MCP server: { $error }

### astrbot/builtin_stars/astrbot/main.py
builtin-stars-astrbot-main-chat-enhance-error = Chat enhancement initialization failed: { $error }
builtin-stars-astrbot-main-record-message-error = Failed to record group chat memory: { $error }
builtin-stars-astrbot-main-no-llm-provider-for-active-reply = No LLM provider found. Please configure one first. Active reply cannot continue.
builtin-stars-astrbot-main-no-conversation-active-reply = No active conversation found, cannot perform active reply. Ensure "Platform Settings -> Session Isolation (unique_session)" is disabled, then switch with /switch or create one with /new.
builtin-stars-astrbot-main-conversation-not-found-active-reply = Conversation not found, cannot perform active reply.
builtin-stars-astrbot-main-active-reply-failed = Active reply failed: { $error }
builtin-stars-astrbot-main-ltm-error = Long-term memory processing failed: { $error }

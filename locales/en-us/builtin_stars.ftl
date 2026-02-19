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

### astrbot/builtin_stars/astrbot/long_term_memory.py
builtin-stars-astrbot-ltm-invalid-max-count = Invalid long-term memory config group_message_max_cnt, fallback to default 300: { $error }
builtin-stars-astrbot-ltm-provider-not-found = Provider with ID { $provider_id } was not found.
builtin-stars-astrbot-ltm-provider-type-invalid = Invalid provider type ({ $provider_type }); cannot get image caption.
builtin-stars-astrbot-ltm-empty-image-url = Image URL is empty.
builtin-stars-astrbot-ltm-image-caption-failed = Failed to get image caption: { $error }
builtin-stars-astrbot-ltm-recorded-message = ltm | { $umo } | { $message }
builtin-stars-astrbot-ltm-recorded-ai-response = Recorded AI response: { $umo } | { $message }

### astrbot/builtin_stars/session_controller/main.py
builtin-stars-session-controller-empty-mention-llm-prompt = Note: you are chatting with a user on social media. The user only used @ to wake you up and did not provide content in this message. They may send the actual content in the next message. Please ask politely what they want to talk about or what help they need. Keep the reply aligned with persona and avoid sounding mechanical. Only output the reply content, and nothing else.
builtin-stars-session-controller-llm-response-failed = LLM response failed: { $error }
builtin-stars-session-controller-empty-mention-fallback-reply = What would you like to ask? 😄
builtin-stars-session-controller-empty-mention-handler-error = An error occurred, please contact the administrator: { $error }
builtin-stars-session-controller-handle-empty-mention-error = handle_empty_mention error: { $error }

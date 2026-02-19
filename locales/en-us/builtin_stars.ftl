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
builtin-stars-session-controller-llm-response-failed = LLM response failed: { $error }
builtin-stars-session-controller-empty-mention-fallback-reply = What would you like to ask? 😄
builtin-stars-session-controller-empty-mention-handler-error = An error occurred, please contact the administrator: { $error }
builtin-stars-session-controller-handle-empty-mention-error = handle_empty_mention error: { $error }

### astrbot/builtin_stars/builtin_commands/commands/plugin.py
builtin-stars-plugin-list-title = Loaded plugins:{"\u000A"}
builtin-stars-plugin-list-line = - `{ $name }` By { $author }: { $desc }
builtin-stars-plugin-list-disabled-tag =  (Disabled)
builtin-stars-plugin-list-empty = No plugins are loaded.
builtin-stars-plugin-list-footer = {"\u000A"}Use /plugin help <plugin_name> to view plugin help and registered commands.{"\u000A"}Use /plugin on/off <plugin_name> to enable or disable a plugin.
builtin-stars-plugin-off-demo-mode = Plugins cannot be disabled in demo mode.
builtin-stars-plugin-off-usage = /plugin off <plugin_name> to disable a plugin.
builtin-stars-plugin-off-success = Plugin { $plugin_name } has been disabled.
builtin-stars-plugin-on-demo-mode = Plugins cannot be enabled in demo mode.
builtin-stars-plugin-on-usage = /plugin on <plugin_name> to enable a plugin.
builtin-stars-plugin-on-success = Plugin { $plugin_name } has been enabled.
builtin-stars-plugin-get-demo-mode = Plugins cannot be installed in demo mode.
builtin-stars-plugin-get-usage = /plugin get <plugin_repo_url> to install a plugin
builtin-stars-plugin-get-install-start = Preparing to install plugin from { $plugin_repo }.
builtin-stars-plugin-get-success = Plugin installed successfully.
builtin-stars-plugin-get-failed-log = Failed to install plugin: { $error }
builtin-stars-plugin-get-failed-user = Failed to install plugin: { $error }
builtin-stars-plugin-help-usage = /plugin help <plugin_name> to view plugin information.
builtin-stars-plugin-help-not-found = Plugin not found.
builtin-stars-plugin-help-author-version = {"\u000A"}{"\u000A"}✨ Author: { $author }{"\u000A"}✨ Version: { $version }
builtin-stars-plugin-help-command-list-title = {"\u000A"}{"\u000A"}🔧 Command list:{"\u000A"}
builtin-stars-plugin-help-command-line = - { $command_name }
builtin-stars-plugin-help-command-line-with-desc = - { $command_name }: { $command_desc }
builtin-stars-plugin-help-command-tip = {"\u000A"}Tip: Add wake prefix to trigger commands, default is /.
builtin-stars-plugin-help-title = 🧩 Plugin { $plugin_name } help:{"\u000A"}
builtin-stars-plugin-help-readme-tip = For more details, check the plugin repository README.

### astrbot/builtin_stars/builtin_commands/commands/provider.py
builtin-stars-provider-reachability-failed = Provider reachability check failed: id={ $provider_id } type={ $provider_type } code={ $err_code } reason={ $err_reason }
builtin-stars-provider-list-llm-title = ## Loaded LLM providers{"\u000A"}
builtin-stars-provider-reachability-checking = Running provider reachability checks, please wait...
builtin-stars-provider-status-failed-with-code =  ❌(code: { $error_code })
builtin-stars-provider-status-current =  (Current)
builtin-stars-provider-list-tts-title = {"\u000A"}## Loaded TTS providers{"\u000A"}
builtin-stars-provider-list-stt-title = {"\u000A"}## Loaded STT providers{"\u000A"}
builtin-stars-provider-list-llm-switch-tip = {"\u000A"}Use /provider <index> to switch LLM provider.
builtin-stars-provider-list-tts-switch-tip = {"\u000A"}Use /provider tts <index> to switch TTS provider.
builtin-stars-provider-list-stt-switch-tip = {"\u000A"}Use /provider stt <index> to switch STT provider.
builtin-stars-provider-list-reachability-skipped = {"\u000A"}Provider reachability checks were skipped. Enable them in config if needed.
builtin-stars-provider-switch-index-required = Please input an index.
builtin-stars-provider-switch-invalid-index = Invalid provider index.
builtin-stars-provider-switch-success = Successfully switched to { $provider_id }.
builtin-stars-provider-switch-invalid-arg = Invalid argument.
builtin-stars-provider-no-llm-provider = No LLM provider found. Please configure one first.
builtin-stars-provider-model-list-failed = Failed to fetch model list: { $error }
builtin-stars-provider-model-list-title = Available models from this provider:
builtin-stars-provider-model-none = None
builtin-stars-provider-model-current = {"\u000A"}Current model: [{ $current_model }]
builtin-stars-provider-model-switch-tip = {"\u000A"}Tip: use /model <model_name/index> to switch model in real time. If the target model is not listed, input the model name directly.
builtin-stars-provider-model-invalid-index = Invalid model index.
builtin-stars-provider-model-switch-unknown-error = Unknown error when switching model: { $error }
builtin-stars-provider-model-switch-success = Model switched successfully. Current provider: [{ $provider_id }] Current model: [{ $current_model }]
builtin-stars-provider-model-switch-to = Switched model to { $current_model }.
builtin-stars-provider-key-list-title = Key:
builtin-stars-provider-key-current = {"\u000A"}Current key: { $current_key }
builtin-stars-provider-model-current-inline = {"\u000A"}Current model: { $current_model }
builtin-stars-provider-key-switch-tip = {"\u000A"}Use /key <idx> to switch key.
builtin-stars-provider-key-invalid-index = Invalid key index.
builtin-stars-provider-key-switch-unknown-error = Unknown error when switching key: { $error }
builtin-stars-provider-key-switch-success = Key switched successfully.

### astrbot/builtin_stars/builtin_commands/commands/t2i.py
builtin-stars-t2i-disabled = Text-to-image mode has been disabled.
builtin-stars-t2i-enabled = Text-to-image mode has been enabled.

### astrbot/builtin_stars/builtin_commands/commands/tts.py
builtin-stars-tts-status-enabled-prefix = Enabled
builtin-stars-tts-status-disabled-prefix = Disabled
builtin-stars-tts-enabled-but-global-disabled = { $status_text } text-to-speech for the current session. But TTS is not enabled in global config. Please enable it in WebUI.
builtin-stars-tts-toggle-result = { $status_text } text-to-speech for the current session.

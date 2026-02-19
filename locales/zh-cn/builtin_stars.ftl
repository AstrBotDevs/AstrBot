### astrbot/builtin_stars/web_searcher/main.py
builtin-stars-web-searcher-legacy-tavily-key-migrated = 检测到旧版 websearch_tavily_key（字符串格式），自动迁移为列表格式并保存。
builtin-stars-web-searcher-scraping-web = web_searcher - 抓取网页: { $title } - { $url }
builtin-stars-web-searcher-bing-search-error = bing 搜索出错: { $error }，尝试下一个搜索引擎...
builtin-stars-web-searcher-bing-search-failed = bing 搜索失败
builtin-stars-web-searcher-sogo-search-error = sogo 搜索出错: { $error }
builtin-stars-web-searcher-sogo-search-failed = sogo 搜索失败
builtin-stars-web-searcher-tavily-key-not-configured = 错误：AstrBot 中未配置 Tavily API 密钥。
builtin-stars-web-searcher-tavily-search-failed = Tavily 网页搜索失败: { $reason }, 状态码: { $status }
builtin-stars-web-searcher-tavily-no-results = 错误：Tavily 网页搜索器未返回任何结果。
builtin-stars-web-searcher-command-deprecated = 此指令已废弃，请在 WebUI 中开启或关闭网页搜索功能。
builtin-stars-web-searcher-search-from-engine = web_searcher - search_from_search_engine: { $query }
builtin-stars-web-searcher-default-no-results = 错误：网页搜索器未返回任何结果。
builtin-stars-web-searcher-process-result-error = 处理搜索结果时出错: { $error }
builtin-stars-web-searcher-link-summary-instruction = {"\u000A"}{"\u000A"}针对问题，请根据上面的结果分点总结，并在结尾附上对应内容的参考链接（如有）。
builtin-stars-web-searcher-baidu-key-not-configured = 错误：AstrBot 中未配置百度 AI Search API 密钥。
builtin-stars-web-searcher-baidu-mcp-init-success = 已成功初始化百度 AI Search MCP 服务。
builtin-stars-web-searcher-search-from-tavily = web_searcher - search_from_tavily: { $query }
builtin-stars-web-searcher-url-empty = 错误：url 必须是非空字符串。
builtin-stars-web-searcher-bocha-key-not-configured = 错误：AstrBot 中未配置 BoCha API 密钥。
builtin-stars-web-searcher-bocha-search-failed = BoCha 网页搜索失败: { $reason }, 状态码: { $status }
builtin-stars-web-searcher-search-from-bocha = web_searcher - search_from_bocha: { $query }
builtin-stars-web-searcher-bocha-no-results = 错误：BoCha 网页搜索器未返回任何结果。
builtin-stars-web-searcher-baidu-tool-not-found = 无法获取百度 AI Search MCP 工具。
builtin-stars-web-searcher-baidu-mcp-init-failed = 无法初始化百度 AI Search MCP 服务: { $error }

### astrbot/builtin_stars/astrbot/main.py
builtin-stars-astrbot-main-chat-enhance-error = 聊天增强初始化失败: { $error }
builtin-stars-astrbot-main-record-message-error = 记录群聊记忆失败: { $error }
builtin-stars-astrbot-main-no-llm-provider-for-active-reply = 未找到任何 LLM 提供商，请先配置。无法主动回复。
builtin-stars-astrbot-main-no-conversation-active-reply = 当前未处于对话状态，无法主动回复。请确保“平台设置 -> 会话隔离(unique_session)”未开启，并使用 /switch 序号 切换或 /new 创建会话。
builtin-stars-astrbot-main-conversation-not-found-active-reply = 未找到对话，无法主动回复。
builtin-stars-astrbot-main-active-reply-failed = 主动回复失败: { $error }
builtin-stars-astrbot-main-ltm-error = 长期记忆处理失败: { $error }

### astrbot/builtin_stars/astrbot/long_term_memory.py
builtin-stars-astrbot-ltm-invalid-max-count = 长期记忆配置项 group_message_max_cnt 无效，使用默认值 300: { $error }
builtin-stars-astrbot-ltm-provider-not-found = 未找到 ID 为 { $provider_id } 的提供商。
builtin-stars-astrbot-ltm-provider-type-invalid = 提供商类型错误 ({ $provider_type })，无法获取图片描述。
builtin-stars-astrbot-ltm-empty-image-url = 图片 URL 为空。
builtin-stars-astrbot-ltm-image-caption-failed = 获取图片描述失败: { $error }
builtin-stars-astrbot-ltm-recorded-message = ltm | { $umo } | { $message }
builtin-stars-astrbot-ltm-recorded-ai-response = 已记录 AI 回复: { $umo } | { $message }

### astrbot/builtin_stars/session_controller/main.py
builtin-stars-session-controller-empty-mention-llm-prompt = 注意，你正在社交媒体上与用户聊天，用户只是通过@唤醒你，但并未在这条消息中输入内容，他可能会在下一条发送想说的话。请友好地询问用户想聊什么或需要什么帮助，回复应符合人设，不要太机械化。你只需输出要回复用户的内容，不要输出其他信息。
builtin-stars-session-controller-llm-response-failed = LLM 回复失败: { $error }
builtin-stars-session-controller-empty-mention-fallback-reply = 想要问什么呢？😄
builtin-stars-session-controller-empty-mention-handler-error = 发生错误，请联系管理员: { $error }
builtin-stars-session-controller-handle-empty-mention-error = handle_empty_mention 处理失败: { $error }

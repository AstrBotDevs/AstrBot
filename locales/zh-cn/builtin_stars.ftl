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
builtin-stars-session-controller-llm-response-failed = LLM 回复失败: { $error }
builtin-stars-session-controller-empty-mention-fallback-reply = 想要问什么呢？😄
builtin-stars-session-controller-empty-mention-handler-error = 发生错误，请联系管理员: { $error }
builtin-stars-session-controller-handle-empty-mention-error = handle_empty_mention 处理失败: { $error }

### astrbot/builtin_stars/builtin_commands/commands/plugin.py
builtin-stars-plugin-list-title = 已加载的插件：{"\u000A"}
builtin-stars-plugin-list-line = - `{ $name }` By { $author }: { $desc }
builtin-stars-plugin-list-disabled-tag =  (未启用)
builtin-stars-plugin-list-empty = 没有加载任何插件。
builtin-stars-plugin-list-footer = {"\u000A"}使用 /plugin help <插件名> 查看插件帮助和加载的指令。{"\u000A"}使用 /plugin on/off <插件名> 启用或禁用插件。
builtin-stars-plugin-off-demo-mode = 演示模式下无法禁用插件。
builtin-stars-plugin-off-usage = /plugin off <插件名> 禁用插件。
builtin-stars-plugin-off-success = 插件 { $plugin_name } 已禁用。
builtin-stars-plugin-on-demo-mode = 演示模式下无法启用插件。
builtin-stars-plugin-on-usage = /plugin on <插件名> 启用插件。
builtin-stars-plugin-on-success = 插件 { $plugin_name } 已启用。
builtin-stars-plugin-get-demo-mode = 演示模式下无法安装插件。
builtin-stars-plugin-get-usage = /plugin get <插件仓库地址> 安装插件
builtin-stars-plugin-get-install-start = 准备从 { $plugin_repo } 安装插件。
builtin-stars-plugin-get-success = 安装插件成功。
builtin-stars-plugin-get-failed-log = 安装插件失败: { $error }
builtin-stars-plugin-get-failed-user = 安装插件失败: { $error }
builtin-stars-plugin-help-usage = /plugin help <插件名> 查看插件信息。
builtin-stars-plugin-help-not-found = 未找到此插件。
builtin-stars-plugin-help-author-version = {"\u000A"}{"\u000A"}✨ 作者: { $author }{"\u000A"}✨ 版本: { $version }
builtin-stars-plugin-help-command-list-title = {"\u000A"}{"\u000A"}🔧 指令列表：{"\u000A"}
builtin-stars-plugin-help-command-line = - { $command_name }
builtin-stars-plugin-help-command-line-with-desc = - { $command_name }: { $command_desc }
builtin-stars-plugin-help-command-tip = {"\u000A"}Tip: 指令触发需要添加唤醒前缀，默认为 /。
builtin-stars-plugin-help-title = 🧩 插件 { $plugin_name } 帮助信息：{"\u000A"}
builtin-stars-plugin-help-readme-tip = 更多帮助信息请查看插件仓库 README。

### astrbot/builtin_stars/builtin_commands/commands/provider.py
builtin-stars-provider-reachability-failed = Provider 可达性检测失败: id={ $provider_id } type={ $provider_type } code={ $err_code } reason={ $err_reason }
builtin-stars-provider-list-llm-title = ## 载入的 LLM 提供商{"\u000A"}
builtin-stars-provider-reachability-checking = 正在进行提供商可达性测试，请稍候...
builtin-stars-provider-status-failed-with-code =  ❌(错误码: { $error_code })
builtin-stars-provider-status-current =  (当前使用)
builtin-stars-provider-list-tts-title = {"\u000A"}## 载入的 TTS 提供商{"\u000A"}
builtin-stars-provider-list-stt-title = {"\u000A"}## 载入的 STT 提供商{"\u000A"}
builtin-stars-provider-list-llm-switch-tip = {"\u000A"}使用 /provider <序号> 切换 LLM 提供商。
builtin-stars-provider-list-tts-switch-tip = {"\u000A"}使用 /provider tts <序号> 切换 TTS 提供商。
builtin-stars-provider-list-stt-switch-tip = {"\u000A"}使用 /provider stt <序号> 切换 STT 提供商。
builtin-stars-provider-list-reachability-skipped = {"\u000A"}已跳过提供商可达性检测，如需检测请在配置文件中开启。
builtin-stars-provider-switch-index-required = 请输入序号。
builtin-stars-provider-switch-invalid-index = 无效的提供商序号。
builtin-stars-provider-switch-success = 成功切换到 { $provider_id }。
builtin-stars-provider-switch-invalid-arg = 无效的参数。
builtin-stars-provider-no-llm-provider = 未找到任何 LLM 提供商。请先配置。
builtin-stars-provider-model-list-failed = 获取模型列表失败: { $error }
builtin-stars-provider-model-list-title = 下面列出了此模型提供商可用模型:
builtin-stars-provider-model-none = 无
builtin-stars-provider-model-current = {"\u000A"}当前模型: [{ $current_model }]
builtin-stars-provider-model-switch-tip = {"\u000A"}Tips: 使用 /model <模型名/编号>，即可实时更换模型。如目标模型不存在于上表，请输入模型名。
builtin-stars-provider-model-invalid-index = 模型序号错误。
builtin-stars-provider-model-switch-unknown-error = 切换模型未知错误: { $error }
builtin-stars-provider-model-switch-success = 切换模型成功。当前提供商: [{ $provider_id }] 当前模型: [{ $current_model }]
builtin-stars-provider-model-switch-to = 切换模型到 { $current_model }。
builtin-stars-provider-key-list-title = Key:
builtin-stars-provider-key-current = {"\u000A"}当前 Key: { $current_key }
builtin-stars-provider-model-current-inline = {"\u000A"}当前模型: { $current_model }
builtin-stars-provider-key-switch-tip = {"\u000A"}使用 /key <idx> 切换 Key。
builtin-stars-provider-key-invalid-index = Key 序号错误。
builtin-stars-provider-key-switch-unknown-error = 切换 Key 未知错误: { $error }
builtin-stars-provider-key-switch-success = 切换 Key 成功。

### astrbot/builtin_stars/builtin_commands/commands/t2i.py
builtin-stars-t2i-disabled = 已关闭文本转图片模式。
builtin-stars-t2i-enabled = 已开启文本转图片模式。

### astrbot/builtin_stars/builtin_commands/commands/tts.py
builtin-stars-tts-status-enabled-prefix = 已开启
builtin-stars-tts-status-disabled-prefix = 已关闭
builtin-stars-tts-enabled-but-global-disabled = { $status_text }当前会话的文本转语音。但 TTS 功能在配置中未启用，请前往 WebUI 开启。
builtin-stars-tts-toggle-result = { $status_text }当前会话的文本转语音。

### astrbot/builtin_stars/builtin_commands/commands/llm.py
builtin-stars-llm-status-disabled = 关闭
builtin-stars-llm-status-enabled = 开启
builtin-stars-llm-toggle-result = { $status } LLM 聊天功能。

### astrbot/builtin_stars/builtin_commands/commands/setunset.py
builtin-stars-setunset-set-success = 会话 { $uid } 变量 { $key } 存储成功。使用 /unset 移除。
builtin-stars-setunset-key-not-found = 没有那个变量名。格式 /unset 变量名。
builtin-stars-setunset-unset-success = 会话 { $uid } 变量 { $key } 移除成功。

### astrbot/builtin_stars/builtin_commands/commands/sid.py
builtin-stars-sid-base-info = UMO: 「{ $sid }」 此值可用于设置白名单。{"\u000A"}UID: 「{ $user_id }」 此值可用于设置管理员。{"\u000A"}消息会话来源信息:{"\u000A"}  机器人 ID: 「{ $umo_platform }」{"\u000A"}  消息类型: 「{ $umo_msg_type }」{"\u000A"}  会话 ID: 「{ $umo_session_id }」{"\u000A"}消息来源可用于配置机器人的配置文件路由。
builtin-stars-sid-unique-session-group-tip = {"\u000A"}{"\u000A"}当前处于独立会话模式，此群 ID: 「{ $group_id }」，也可将此 ID 加入白名单来放行整个群聊。

### astrbot/builtin_stars/builtin_commands/commands/admin.py
builtin-stars-admin-op-usage = 使用方法: /op <id> 授权管理员；/deop <id> 取消管理员。可通过 /sid 获取 ID。
builtin-stars-admin-op-success = 授权成功。
builtin-stars-admin-deop-usage = 使用方法: /deop <id> 取消管理员。可通过 /sid 获取 ID。
builtin-stars-admin-deop-success = 取消授权成功。
builtin-stars-admin-deop-not-in-list = 此用户 ID 不在管理员名单内。
builtin-stars-admin-wl-usage = 使用方法: /wl <id> 添加白名单；/dwl <id> 删除白名单。可通过 /sid 获取 ID。
builtin-stars-admin-wl-success = 添加白名单成功。
builtin-stars-admin-dwl-usage = 使用方法: /dwl <id> 删除白名单。可通过 /sid 获取 ID。
builtin-stars-admin-dwl-success = 删除白名单成功。
builtin-stars-admin-dwl-not-in-list = 此 SID 不在白名单内。
builtin-stars-admin-update-dashboard-start = 正在尝试更新管理面板...
builtin-stars-admin-update-dashboard-finished = 管理面板更新完成。

### astrbot/builtin_stars/builtin_commands/commands/help.py
builtin-stars-help-no-enabled-reserved-commands = 暂无启用的内置指令
builtin-stars-help-header = AstrBot v{ $version }(WebUI: { $dashboard_version })
builtin-stars-help-reserved-command-title = 内置指令:

### astrbot/builtin_stars/builtin_commands/commands/alter_cmd.py
builtin-stars-alter-cmd-usage = 该指令用于设置指令或指令组的权限。{"\u000A"}格式: /alter_cmd <cmd_name> <admin/member>{"\u000A"}例1: /alter_cmd c1 admin 将 c1 设为管理员指令{"\u000A"}例2: /alter_cmd g1 c1 admin 将 g1 指令组的 c1 子指令设为管理员指令{"\u000A"}/alter_cmd reset config 打开 reset 权限配置
builtin-stars-alter-cmd-reset-config-menu = reset命令权限细粒度配置{"\u000A"}当前配置：{"\u000A"}1. 群聊+会话隔离开: { $group_unique_on }{"\u000A"}2. 群聊+会话隔离关: { $group_unique_off }{"\u000A"}3. 私聊: { $private }{"\u000A"}修改指令格式：{"\u000A"}/alter_cmd reset scene <场景编号> <admin/member>{"\u000A"}例如: /alter_cmd reset scene 2 member
builtin-stars-alter-cmd-scene-and-perm-required = 场景编号和权限类型不能为空
builtin-stars-alter-cmd-scene-index-invalid = 场景编号必须是 1-3 之间的数字
builtin-stars-alter-cmd-perm-type-invalid = 权限类型错误，只能是 admin 或 member
builtin-stars-alter-cmd-reset-scene-updated = 已将 reset 命令在 { $scene_name} 场景下的权限设为 { $perm_type }
builtin-stars-alter-cmd-type-invalid = 指令类型错误，可选类型有 admin, member
builtin-stars-alter-cmd-command-not-found = 未找到该指令
builtin-stars-alter-cmd-updated = 已将「{ $cmd_name }」{ $cmd_group_str } 的权限级别调整为 { $cmd_type }。
builtin-stars-alter-cmd-group-label = 指令组
builtin-stars-alter-cmd-command-label = 指令

### astrbot/builtin_stars/builtin_commands/commands/persona.py
builtin-stars-persona-none = 无
builtin-stars-persona-current-conversation-not-found = 当前对话不存在，请先使用 /new 新建一个对话。
builtin-stars-persona-name-with-custom-rule = { $persona_name } (自定义规则)
builtin-stars-persona-new-conversation = 新对话
builtin-stars-persona-overview = [Persona]{"\u000A"}{"\u000A"}- 人格情景列表: `/persona list`{"\u000A"}- 设置人格情景: `/persona 人格`{"\u000A"}- 人格情景详细信息: `/persona view 人格`{"\u000A"}- 取消人格: `/persona unset`{"\u000A"}{"\u000A"}默认人格情景: { $default_persona_name }{"\u000A"}当前对话 { $curr_cid_title } 的人格情景: { $curr_persona_name }{"\u000A"}{"\u000A"}配置人格情景请前往管理面板-配置页{"\u000A"}
builtin-stars-persona-list-title = 📂 人格列表：{"\u000A"}
builtin-stars-persona-list-total = {"\u000A"}共 { $total_count } 个人格
builtin-stars-persona-list-set-tip = {"\u000A"}*使用 `/persona <人格名>` 设置人格
builtin-stars-persona-list-view-tip = *使用 `/persona view <人格名>` 查看详细信息
builtin-stars-persona-view-need-name = 请输入人格情景名
builtin-stars-persona-view-detail-title = 人格 { $persona_name } 的详细信息：{"\u000A"}
builtin-stars-persona-view-not-found = 人格 { $persona_name } 不存在
builtin-stars-persona-unset-no-conversation = 当前没有对话，无法取消人格。
builtin-stars-persona-unset-success = 取消人格成功。
builtin-stars-persona-set-no-conversation = 当前没有对话，请先开始对话或使用 /new 创建一个对话。
builtin-stars-persona-custom-rule-warning = 提醒：由于自定义规则，您现在切换的人格将不会生效。
builtin-stars-persona-set-success = 设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。{ $force_warn_msg }
builtin-stars-persona-set-not-found = 不存在该人格情景。使用 /persona list 查看所有。

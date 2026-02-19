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

### astrbot/builtin_stars/builtin_commands/commands/llm.py
builtin-stars-llm-status-disabled = Disabled
builtin-stars-llm-status-enabled = Enabled
builtin-stars-llm-toggle-result = { $status } LLM chat feature.

### astrbot/builtin_stars/builtin_commands/commands/setunset.py
builtin-stars-setunset-set-success = Session { $uid } variable { $key } stored successfully. Use /unset to remove it.
builtin-stars-setunset-key-not-found = Variable name not found. Usage: /unset <variable_name>.
builtin-stars-setunset-unset-success = Session { $uid } variable { $key } removed successfully.

### astrbot/builtin_stars/builtin_commands/commands/sid.py
builtin-stars-sid-base-info = UMO: "{ $sid }" This value can be used for whitelist settings.{"\u000A"}UID: "{ $user_id }" This value can be used for admin settings.{"\u000A"}Message session source info:{"\u000A"}  Bot ID: "{ $umo_platform }"{"\u000A"}  Message type: "{ $umo_msg_type }"{"\u000A"}  Session ID: "{ $umo_session_id }"{"\u000A"}This source info can be used for routing config.
builtin-stars-sid-unique-session-group-tip = {"\u000A"}{"\u000A"}Unique-session mode is currently enabled. Group ID: "{ $group_id }". You can also add this ID to whitelist to allow the whole group.

### astrbot/builtin_stars/builtin_commands/commands/admin.py
builtin-stars-admin-op-usage = Usage: /op <id> to grant admin; /deop <id> to revoke admin. Use /sid to get the ID.
builtin-stars-admin-op-success = Authorization granted successfully.
builtin-stars-admin-deop-usage = Usage: /deop <id> to revoke admin. Use /sid to get the ID.
builtin-stars-admin-deop-success = Authorization revoked successfully.
builtin-stars-admin-deop-not-in-list = This user ID is not in the admin list.
builtin-stars-admin-wl-usage = Usage: /wl <id> to add whitelist; /dwl <id> to remove whitelist. Use /sid to get the ID.
builtin-stars-admin-wl-success = Added to whitelist successfully.
builtin-stars-admin-dwl-usage = Usage: /dwl <id> to remove whitelist. Use /sid to get the ID.
builtin-stars-admin-dwl-success = Removed from whitelist successfully.
builtin-stars-admin-dwl-not-in-list = This SID is not in the whitelist.
builtin-stars-admin-update-dashboard-start = Trying to update dashboard...
builtin-stars-admin-update-dashboard-finished = Dashboard update completed.

### astrbot/builtin_stars/builtin_commands/commands/help.py
builtin-stars-help-no-enabled-reserved-commands = No enabled built-in commands.
builtin-stars-help-header = AstrBot v{ $version } (WebUI: { $dashboard_version })
builtin-stars-help-reserved-command-title = Built-in commands:

### astrbot/builtin_stars/builtin_commands/commands/alter_cmd.py
builtin-stars-alter-cmd-usage = This command sets permissions for a command or command group.{"\u000A"}Format: /alter_cmd <cmd_name> <admin/member>{"\u000A"}Example 1: /alter_cmd c1 admin sets c1 as admin-only command{"\u000A"}Example 2: /alter_cmd g1 c1 admin sets sub-command c1 in group g1 as admin-only{"\u000A"}/alter_cmd reset config opens reset permission config
builtin-stars-alter-cmd-reset-config-menu = Fine-grained permission config for reset command{"\u000A"}Current config:{"\u000A"}1. Group + unique session ON: { $group_unique_on }{"\u000A"}2. Group + unique session OFF: { $group_unique_off }{"\u000A"}3. Private chat: { $private }{"\u000A"}Update format:{"\u000A"}/alter_cmd reset scene <scene_index> <admin/member>{"\u000A"}Example: /alter_cmd reset scene 2 member
builtin-stars-alter-cmd-scene-and-perm-required = Scene index and permission type are required.
builtin-stars-alter-cmd-scene-index-invalid = Scene index must be a number between 1 and 3.
builtin-stars-alter-cmd-perm-type-invalid = Invalid permission type, only admin or member is allowed.
builtin-stars-alter-cmd-reset-scene-updated = Updated reset command permission to { $perm_type } in scene { $scene_name }.
builtin-stars-alter-cmd-type-invalid = Invalid command type, available types are admin and member.
builtin-stars-alter-cmd-command-not-found = Command not found.
builtin-stars-alter-cmd-updated = Permission level of "{ $cmd_name }" { $cmd_group_str } has been set to { $cmd_type }.
builtin-stars-alter-cmd-group-label = command group
builtin-stars-alter-cmd-command-label = command

### astrbot/builtin_stars/builtin_commands/commands/persona.py
builtin-stars-persona-none = None
builtin-stars-persona-current-conversation-not-found = Current conversation does not exist. Please create one with /new first.
builtin-stars-persona-name-with-custom-rule = { $persona_name } (custom rule)
builtin-stars-persona-new-conversation = New Conversation
builtin-stars-persona-overview = [Persona]{"\u000A"}{"\u000A"}- Persona list: `/persona list`{"\u000A"}- Set persona: `/persona <persona_name>`{"\u000A"}- Persona details: `/persona view <persona_name>`{"\u000A"}- Unset persona: `/persona unset`{"\u000A"}{"\u000A"}Default persona: { $default_persona_name }{"\u000A"}Persona of current conversation { $curr_cid_title }: { $curr_persona_name }{"\u000A"}{"\u000A"}Configure personas in WebUI -> Config page{"\u000A"}
builtin-stars-persona-list-title = 📂 Persona list:{"\u000A"}
builtin-stars-persona-list-total = {"\u000A"}Total personas: { $total_count }
builtin-stars-persona-list-set-tip = {"\u000A"}*Use `/persona <persona_name>` to set persona
builtin-stars-persona-list-view-tip = *Use `/persona view <persona_name>` to view details
builtin-stars-persona-view-need-name = Please input a persona name.
builtin-stars-persona-view-detail-title = Details of persona { $persona_name }:{"\u000A"}
builtin-stars-persona-view-not-found = Persona { $persona_name } does not exist.
builtin-stars-persona-unset-no-conversation = No current conversation, cannot unset persona.
builtin-stars-persona-unset-success = Persona unset successfully.
builtin-stars-persona-set-no-conversation = No current conversation. Please start one first or create one with /new.
builtin-stars-persona-custom-rule-warning = Reminder: due to custom rules, the persona you switch to now will not take effect.
builtin-stars-persona-set-success = Persona set successfully. If you switched to a different persona, use /reset to clear context and avoid old persona context affecting the new one. { $force_warn_msg }
builtin-stars-persona-set-not-found = Persona does not exist. Use /persona list to view all.

### astrbot/builtin_stars/builtin_commands/commands/conversation.py
builtin-stars-conversation-reset-permission-denied = In scene { $scene_name }, the reset command requires admin permission. You (ID { $sender_id }) are not an admin, so this operation is not allowed.
builtin-stars-conversation-reset-success = Conversation reset successful.
builtin-stars-conversation-no-llm-provider = No LLM provider found. Please configure one first.
builtin-stars-conversation-no-active-conversation = No active conversation. Use /switch to switch or /new to create one.
builtin-stars-conversation-clear-history-success = Chat history cleared successfully!
builtin-stars-conversation-no-history = No history records
builtin-stars-conversation-history-result = Current conversation history: { $history }{"\u000A"}{"\u000A"}Page { $page } | Total { $total_pages }{"\u000A"}*Input /history 2 to jump to page 2
builtin-stars-conversation-convs-not-supported = Conversation list is not supported for { $runner_types }.
builtin-stars-conversation-list-title = Conversation list:{"\u000A"}---{"\u000A"}
builtin-stars-conversation-new = New Conversation
builtin-stars-conversation-list-line = { $index }. { $title }({ $cid }){"\u000A"}  Persona: { $persona_id }{"\u000A"}  Updated at: { $updated_at }{"\u000A"}
builtin-stars-conversation-list-divider = ---{"\u000A"}
builtin-stars-conversation-current-with-id = {"\u000A"}Current conversation: { $title }({ $cid })
builtin-stars-conversation-current-none = {"\u000A"}Current conversation: None
builtin-stars-conversation-scope-personal = {"\u000A"}Session isolation scope: Personal
builtin-stars-conversation-scope-group = {"\u000A"}Session isolation scope: Group
builtin-stars-conversation-page-info = {"\u000A"}Page { $page } | Total { $total_pages }
builtin-stars-conversation-page-jump-tip = {"\u000A"}*Input /ls 2 to jump to page 2
builtin-stars-conversation-new-conv-created = New conversation created.
builtin-stars-conversation-switch-to-new = Switched to new conversation: New Conversation({ $cid }).
builtin-stars-conversation-group-switch-to-new = Group { $session } switched to a new conversation: New Conversation({ $cid }).
builtin-stars-conversation-groupnew-need-group-id = Please provide group ID. Usage: /groupnew <group_id>.
builtin-stars-conversation-switch-type-invalid = Invalid type, please input a numeric conversation index.
builtin-stars-conversation-switch-need-index = Please provide conversation index. /switch <index>. Use /ls to list or /new to create.
builtin-stars-conversation-switch-index-invalid = Invalid conversation index, use /ls to view valid ones.
builtin-stars-conversation-switch-success = Switched to conversation: { $title }({ $cid }).
builtin-stars-conversation-rename-need-name = Please provide a new conversation name.
builtin-stars-conversation-rename-success = Conversation renamed successfully.
builtin-stars-conversation-delete-permission-denied = Session is in a group chat with unique session disabled, and you (ID { $sender_id }) are not an admin, so you do not have permission to delete the current conversation.
builtin-stars-conversation-no-active-conversation-with-index = No active conversation. Use /switch <index> to switch or /new to create.
builtin-stars-conversation-delete-success = Current conversation deleted successfully. No active conversation now. Use /switch <index> to switch or /new to create.

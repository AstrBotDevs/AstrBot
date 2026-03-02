### main.py

msg-5e25709f = Please run this project using Python 3.10 or higher.
msg-afd0ab81 = Using the specified WebUI directory:{ $webui_dir }
msg-7765f00f = Specified WebUI directory{ $webui_dir }Does not exist; default logic will be used.
msg-9af20e37 = WebUI version is already up to date.
msg-9dd5c1d2 = WebUI version detected ({ $v }) Compared to the current AstrBot version (v{ $VERSION }Does not match.
msg-ec714d4e = Starting download of management panel files...Peak hours (evenings) may result in slower speeds. If the download fails multiple times, please go to https://github.com/AstrBotDevs/AstrBot/releases/latest to download dist.zip, then extract the dist folder into the data directory.
msg-c5170c27 = Failed to download the management panel file:{ $e }.
msg-e1592ad1 = Management panel download completed.
msg-fe494da6 = { $logo_tmpl }

### astrbot\builtin_stars\astrbot\long_term_memory.py

msg-5bdf8f5c = { $e }
msg-8e11fa57 = ID not found.{ $image_caption_provider_id }Provider
msg-8ebaa397 = Provider type error{ $res }Unable to retrieve image description
msg-30954f77 = Image URL is empty.
msg-62de0c3e = Failed to retrieve image description:{ $e }
msg-d0647999 = ltm |{ $res }|{ $final_message }
msg-133c1f1d = Recorded AI response:{ $res }|{ $final_message }

### astrbot\builtin_stars\astrbot\main.py

msg-3df554a1 = Chat Enhancement Error:{ $e }
msg-5bdf8f5c = { $e }
msg-bb6ff036 = No LLM provider found. Please configure first. Unable to initiate replies.
msg-afa050be = Currently not in a conversation state, unable to initiate replies. Please ensure that **Platform Settings -> Session Isolation (unique_session)** is not enabled, and use `/switch [number]` to switch or `/new` to create a session.
msg-9a6a6b2e = No conversation found, unable to initiate a reply.
msg-78b9c276 = { $res }
msg-b177e640 = Active reply failed:{ $e }
msg-24d2f380 = Long-term memory:{ $e }

### astrbot\builtin_stars\builtin_commands\commands\admin.py

msg-ad019976 = Usage: /op <id> to grant administrator privileges; /deop <id> to revoke administrator privileges. Use /sid to retrieve your ID.
msg-1235330f = Authorization successful.
msg-e78847e0 = Usage: /deop <id> to revoke administrator privileges. The ID can be obtained via /sid.
msg-012152c1 = Authorization canceled successfully.
msg-5e076026 = This user ID is not on the administrator list.
msg-7f8eedde = Usage: /wl <id> to add to the whitelist; /dwl <id> to remove from the whitelist. ID can be obtained via /sid.
msg-de1b0a87 = Whitelist added successfully.
msg-59d6fcbe = Usage: /dwl <id> to remove from the whitelist. ID can be obtained via /sid.
msg-4638580f = Whitelist deletion successful.
msg-278fb868 = This SID is not on the whitelist.
msg-1dee5007 = Attempting to update the admin panel...
msg-76bea66c = Management panel update completed.

### astrbot\builtin_stars\builtin_commands\commands\alter_cmd.py

msg-d7a36c19 = This command is used to set permissions for a command or a group of commands.{ "\u000a" }Format: /alter_cmd <cmd_name> <admin/member>{ "\u000a" }Example 1: /alter_cmd c1 admin sets c1 as the administrator command.{ "\u000a" }Example 2: /alter_cmd g1 c1 admin sets the c1 sub-command in the g1 command group as an administrator command.{ "\u000a" }/alter_cmd reset config opens reset permission configuration
msg-afe0fa58 = { $config_menu }
msg-0c85d498 = Scenario ID and permission type cannot be empty.
msg-4e0afcd1 = The scene number must be a number between 1 and 3.
msg-830d6eb8 = Permission type error, must be either admin or member.
msg-d1180ead = The reset command has been added to{ $res }Permissions in the scenario are set to{ $perm_type }
msg-8d9bc364 = Command type error; available types are admin or member.
msg-1f2f65e0 = Command not found.
msg-cd271581 = "{ $cmd_name }"{ $cmd_group_str }The permission level has been adjusted to{ $cmd_type }.

### astrbot\builtin_stars\builtin_commands\commands\conversation.py

msg-63fe9607 = In{ $res }In this scenario, the reset command requires administrator privileges.{ $res_2 }You are not an administrator and cannot perform this operation.
msg-6f4bbe27 = Dialogue reset successful.
msg-4cdd042d = No LLM provider found. Please configure it first.
msg-69ed45be = Currently not in a conversation state, please use /switch to switch or /new to create.
msg-ed8dcc22 = { $ret }
msg-772ec1fa = Stop requested.{ $stopped_count }A running task.
msg-8d42cd8a = There are no running tasks in the current session.
msg-efdfbe3e = { $THIRD_PARTY_AGENT_RUNNER_STR }The conversation list feature is currently not supported.
msg-492c2c02 = A new conversation has been created.
msg-c7dc838d = Switch to new conversation: New conversation({ $res }).
msg-6da01230 = Group Chat{ $session }Switched to a new conversation: New conversation{ $res }).
msg-f356d65a = Please enter the group chat ID. /groupnew group chat ID.
msg-7e442185 = Type error, please enter a numeric conversation ID.
msg-00dbe29c = Please enter the conversation number. /switch conversation number. /ls view conversations /new create new conversation
msg-a848ccf6 = Dialogue sequence number error, please use /ls to check.
msg-1ec33cf6 = Switch to conversation:{ $title }({ $res }).
msg-68e5dd6c = Please enter a new conversation name.
msg-c8dd6158 = Dialogue renamed successfully.
msg-1f1fa2f2 = The session is in a group chat, independent sessions are not enabled, and you (ID{ $res }Not an administrator, therefore no permission to delete the current conversation.
msg-6a1dc4b7 = Currently not in a conversation state. Please use /switch [number] to switch or /new to create.

### astrbot\builtin_stars\builtin_commands\commands\help.py

msg-c046b6e4 = { $msg }

### astrbot\builtin_stars\builtin_commands\commands\llm.py

msg-72cd5f57 = { $status }LLM Chat Feature.

### astrbot\builtin_stars\builtin_commands\commands\persona.py

msg-4f52d0dd = The current conversation does not exist. Please use /new to create a new conversation first.
msg-e092b97c = [Persona]{ "\u000a" }{ "\u000a" }- Persona list: `/persona list`{ "\u000a" }- Set persona scenario: `/persona persona`{ "\u000a" }- Persona Scenario Details: `/persona view persona`{ "\u000a" }- Remove Persona: `/persona unset`{ "\u000a" }{ "\u000a" }Default personality scenario:{ $res }{ "\u000a" }Current conversation{ $curr_cid_title }Personality scenario:{ $curr_persona_name }{ "\u000a" }{ "\u000a" }To configure personality scenarios, please go to the management panel's configuration page.{ "\u000a" }
msg-c046b6e4 = { $msg }
msg-99139ef8 = Please enter the personality scenario name.
msg-a44c7ec0 = No active conversation found; personality cannot be deactivated.
msg-a90c75d4 = Personality cancellation successful.
msg-a712d71a = There is no current conversation. Please start a conversation or use /new to create one.
msg-4e4e746d = Setup successful. If you are switching to a different persona, please use /reset to clear the context to prevent conversations from the original persona from affecting the current one.{ $force_warn_msg }
msg-ab60a2e7 = This persona scenario does not exist. Use /persona list to view all available personas.

### astrbot\builtin_stars\builtin_commands\commands\plugin.py

msg-9cae24f5 = { $plugin_list_info }
msg-3f3a6087 = Plugins cannot be disabled in demo mode.
msg-90e17cd4 = /plugin off <plugin_name> Disables the plugin.
msg-d29d6d57 = Plugin{ $plugin_name }Disabled.
msg-f90bbe20 = Plugins cannot be enabled in demo mode.
msg-b897048f = /plugin on <plugin_name> to enable the plugin.
msg-ebfb93bb = Plugin{ $plugin_name }Enabled.
msg-9cd74a8d = Plugins cannot be installed in demo mode.
msg-d79ad78d = /plugin get <plugin repository address> to install a plugin
msg-4f293fe1 = Preparing to start from{ $plugin_repo }Install the plugin.
msg-d40e7065 = Plugin installed successfully.
msg-feff82c6 = Plugin installation failed:{ $e }
msg-5bfe9d3d = /plugin help <plugin_name> to view plugin information.
msg-02627a9b = Plugin not found.
msg-ed8dcc22 = { $ret }

### astrbot\builtin_stars\builtin_commands\commands\provider.py

msg-7717d729 = Provider accessibility check failed: id={ $res }Type={ $res_2 }Code={ $err_code }Cause={ $err_reason }
msg-f4cfd3ab = Testing provider availability, please wait...
msg-ed8dcc22 = { $ret }
msg-f3d8988e = Please enter the serial number.
msg-284759bb = Invalid provider serial number.
msg-092d9956 = Successfully switched to{ $id_ }.
msg-bf9eb668 = Invalid parameter.
msg-4cdd042d = No LLM provider found. Please configure it first.
msg-cb218e86 = Model serial number error.
msg-1756f199 = Model switched successfully. Current provider: [{ $res }Current model: [{ $res_2 }]
msg-4d4f587f = Switch model to{ $res }.
msg-584ca956 = Key sequence number is incorrect.
msg-f52481b8 = Switch Key unknown error:
msg-7a156524 = Key switched successfully.

### astrbot\builtin_stars\builtin_commands\commands\setunset.py

msg-8b56b437 = Session{ $uid }Variable{ $key }Storage successful. Use /unset to remove.
msg-dfd31d9d = That variable name does not exist. Format: /unset variable_name.
msg-bf181241 = Session{ $uid }Variable{ $key }Removed successfully.

### astrbot\builtin_stars\builtin_commands\commands\sid.py

msg-ed8dcc22 = { $ret }

### astrbot\builtin_stars\builtin_commands\commands\t2i.py

msg-855d5cf3 = Text-to-image mode has been disabled.
msg-64da24f4 = Text-to-image mode enabled.

### astrbot\builtin_stars\builtin_commands\commands\tts.py

msg-ef1b2145 = { $status_text }Text-to-speech for the current session. However, the TTS feature is not enabled in the configuration. Please go to the WebUI to enable it.
msg-deee9deb = { $status_text }Text-to-speech for the current session.

### astrbot\builtin_stars\session_controller\main.py

msg-b48bf3fe = LLM response failed:{ $e }

### astrbot\builtin_stars\web_searcher\main.py

msg-7f5fd92b = Detected legacy websearch_tavily_key (string format), automatically migrated to list format and saved.
msg-bed9def5 = web_searcher - Crawling webpage:{ $res }-{ $res_2 }
msg-8214760c = Bing Search Error:{ $e }, try the next one...
msg-8676b5aa = Bing search failed
msg-3fb6d6ad = Sogou Search Error:{ $e }
msg-fe9b336f = Search for Sogou failed
msg-c991b022 = Error: Tavily API key is not configured in AstrBot.
msg-b4fbb4a9 = Tavily web search failed:{ $reason }Status:{ $res }
msg-6769aba9 = Error: Tavily web search returned no results.
msg-b4e7334e = This command has been deprecated. Please enable or disable the web search feature in the WebUI.
msg-b1877974 = Web Searcher - Search from search engines:{ $query }
msg-2360df6b = Error processing search results:{ $processed_result }
msg-359d0443 = Error: Baidu AI Search API key is not configured in AstrBot.
msg-94351632 = Successfully initialized the Baidu AI Search MCP server.
msg-5a7207c1 = Web Searcher - Search from Tavily:{ $query }
msg-b36134c9 = Error: Tavily API key not configured in AstrBot.
msg-98ed69f4 = Error: URL must be a non-empty string.
msg-51edd9ee = Error: BoCha API key is not configured in AstrBot.
msg-73964067 = BoCha web search failed:{ $reason }Status:{ $res }
msg-34417720 = Web Searcher - Search from Bocha:{ $query }
msg-b798883b = Error: BoCha API key is not configured in AstrBot.
msg-22993708 = Unable to retrieve Baidu AI Search MCPTool.
msg-6f8d62a4 = Failed to initialize the Baidu AI Search MCP server:{ $e }

### astrbot\builtin_stars\web_searcher\engines\bing.py

msg-e3b4d1e9 = Bing search failed

### astrbot\cli\__main__.py

msg-fe494da6 = { $logo_tmpl }
msg-c8b2ff67 = Welcome to the AstrBot Command Line Interface!
msg-78b9c276 = { $res }
msg-14dd710d = Unknown command:{ $command_name }

### astrbot\cli\commands\cmd_conf.py

msg-635b8763 = The log level must be one of DEBUG, INFO, WARNING, ERROR, or CRITICAL.
msg-ebc250dc = Port must be within the range of 1-65535.
msg-6ec400b6 = Port must be numeric.
msg-0b62b5ce = Username cannot be empty
msg-89b5d3d5 = Password cannot be empty.
msg-92e7c8ad = Invalid time zone:{ $value }Please use a valid IANA timezone name.
msg-e470e37d = The callback interface base address must start with http:// or https://.
msg-6b615721 = { $root }Not a valid AstrBot root directory. Use `astrbot init` for initialization.
msg-f74c517c = Configuration file parsing failed:{ $e }
msg-d7c58bcc = Configuration path conflict:{ $res }Not a dictionary
msg-e16816cc = Unsupported configuration items:{ $key }
msg-e9cce750 = Configuration has been updated:{ $key }
msg-1ed565aa = Original value: ********
msg-1bf9569a = New value: ********
msg-f2a20ab3 = Original value:{ $old_value }
msg-0c104905 = New value:{ $validated_value }
msg-ea9b4e2c = Unknown configuration item:{ $key }
msg-4450e3b1 = Configuration setup failed:{ $e }
msg-ba464bee = { $key }:{ $value }
msg-72aab576 = Failed to retrieve configuration:{ $e }
msg-c1693d1d = Current configuration:
msg-50be9b74 = { $key }:{ $value }

### astrbot\cli\commands\cmd_init.py

msg-a90a250e = Current directory:{ $astrbot_root }
msg-4deda62e = If you confirm this is the AstrBot root directory, you need to create a .astrbot file in the current directory to mark it as the AstrBot data directory.
msg-3319bf71 = Created{ $dot_astrbot }
msg-7054f44f = { $res }:{ $path }
msg-b19edc8a = Initializing AstrBot...
msg-eebc39e3 = Unable to acquire lock file; please check if another instance is running.
msg-e16da80f = Initialization failed:{ $e }

### astrbot\cli\commands\cmd_plug.py

msg-cbd8802b = { $base }Not a valid AstrBot root directory. Use astrbot init to initialize.
msg-78b9c276 = { $res }
msg-83664fcf = { $val } { $val } { $val } { $val } { $val }
msg-56f3f0bf = { $res } { $res_2 } { $res_3 } { $res_4 } { $desc }
msg-1d802ff2 = Plugin{ $name }Already exists
msg-a7be9d23 = The version number must follow the x.y or x.y.z format.
msg-4d81299b = The repository address must start with http.
msg-93289755 = Downloading plugin template...
msg-b21682dd = Rewriting plugin information...
msg-bffc8bfa = Plugin{ $name }Created successfully
msg-08eae1e3 = No plugins installed.
msg-1a021bf4 = No installable plugins found.{ $name }May not exist or already installed
msg-c120bafd = Plugin{ $name }Does not exist or is not installed
msg-63da4867 = Plugin{ $name }Uninstalled
msg-e4925708 = Uninstall plugin{ $name }Failure:{ $e }
msg-f4d15a87 = Plugin{ $name }No update required or cannot be updated.
msg-94b035f7 = No plugins require updating.
msg-0766d599 = Discovered{ $res }A plugin requires an update.
msg-bd5ab99c = Updating plugin{ $plugin_name }...
msg-e32912b8 = No matching item found for '{ $query }'s plugin

### astrbot\cli\commands\cmd_run.py

msg-41ecc632 = { $astrbot_root }Not a valid AstrBot root directory. Use `astrbot init` for initialization.
msg-0ccaca23 = Enable plugin auto-reload
msg-220914e7 = AstrBot is offline...
msg-eebc39e3 = Unable to acquire the lock file; please check if another instance is running.
msg-85f241d3 = Runtime error occurred:{ $e }{ "\u000a" }{ $res }

### astrbot\cli\utils\basic.py

msg-f4e0fd7b = Management panel is not installed.
msg-2d090cc3 = Installing the management panel...
msg-2eeb67e0 = Management panel installation completed.
msg-9c727dca = The management panel is already the latest version.
msg-11b49913 = Management Panel Version:{ $version }
msg-f0b6145e = Failed to download the management panel:{ $e }
msg-9504d173 = Initializing admin panel directory...
msg-699e2509 = Management panel initialization completed.

### astrbot\cli\utils\plugin.py

msg-e327bc14 = Downloading from the default branch.{ $author }/{ $repo }
msg-c804f59f = Failed to retrieve release information:{ $e }, will directly use the provided URL
msg-aa398bd5 = The master branch does not exist; attempting to download the main branch.
msg-5587d9fb = Read{ $yaml_path }Failure:{ $e }
msg-8dbce791 = Failed to retrieve online plugin list:{ $e }
msg-6999155d = Plugin{ $plugin_name }Not installed, cannot be updated.
msg-fa5e129a = Fetching from{ $repo_url }   { $res }Plugin{ $plugin_name }...
msg-9ac1f4db = Plugin{ $plugin_name }   { $res }Success
msg-b9c719ae = { $res }Plugin{ $plugin_name }Error occurred at:{ $e }

### astrbot\core\astrbot_config_mgr.py

msg-7875e5bd = Configuration file{ $conf_path }For UUID{ $uuid_ }Does not exist, skip.
msg-39c4fd49 = Cannot delete the default configuration file.
msg-cf7b8991 = Configuration file{ $conf_id }Not present in the mapping
msg-2aad13a4 = Configuration file deleted:{ $conf_path }
msg-94c359ef = Delete the configuration file{ $conf_path }Failure:{ $e }
msg-44f0b770 = The configuration file has been successfully deleted.{ $conf_id }
msg-737da44e = Unable to update information in the default configuration file.
msg-9d496709 = Configuration file updated successfully.{ $conf_id }Information

### astrbot\core\astr_agent_run_util.py

msg-6b326889 = Agent has reached the maximum number of steps.{ $max_step }Enforce final response.
msg-bb15e9c7 = { $status_msg }
msg-78b9c276 = { $res }
msg-9c246298 = Error occurred in the agent completion hook.
msg-34f164d4 = { $err_msg }
msg-6d9553b2 = [Online Customer Service] Using streaming TTS (natively supports get_audio_stream)
msg-becf71bf = [Online Customer Service] Using TTS ({ $res }Using get_audio, generate audio by sentence segmentation.
msg-21723afb = [Online Customer Service] An error occurred during runtime:{ $e }
msg-ca1bf0d7 = Failed to send TTS statistics:{ $e }
msg-5ace3d96 = [Real-time Agent Feeder] Sentence segmentation:{ $temp_buffer }
msg-bc1826ea = [Real-time Agent Feeder] Error:{ $e }
msg-a92774c9 = [Real-time TTS stream] Error:{ $e }
msg-d7b3bbae = [Real-time TTS Simulation] Error processing text '{ $res }...'{ $e }
msg-035bca5f = [Real-time TTS Simulation] Critical Error:{ $e }

### astrbot\core\astr_agent_tool_exec.py

msg-e5f2fb34 = Background tasks{ $task_id }Failure:{ $e }
msg-c54b2335 = Backend Handover{ $task_id }({ $res }) Failure:{ $e }
msg-8c2fe51d = Failed to build the main agent for background tasks.{ $tool_name }.
msg-c6d4e4a6 = Background task agent did not receive a response.
msg-0b3711f1 = The local function Tool must provide events.
msg-8c19e27a = The tool must have a valid handler or override the 'run' method.
msg-24053a5f = Tool failed to send the message directly:{ $e }
msg-f940b51e = Tool{ $res }Execution timeout{ $res_2 }Seconds.
msg-7e22fc8e = Unknown method name:{ $method_name }
msg-c285315c = Tool execution value error:{ $e }
msg-41366b74 = Tool handler parameter mismatch; please check the handler definition. Handler parameters:{ $handler_param_str }
msg-e8cadf8e = Tool execution error:{ $e }Backtrace:{ $trace_ }
msg-d7b4aa84 = Previous error:{ $trace_ }

### astrbot\core\astr_main_agent.py

msg-3d3f3df8 = Specified provider not found:{ $sel_provider }.
msg-23d02c04 = The selected provider type is invalid.{ $res }), skip LLM request processing.
msg-97d98ea8 = Error occurred while selecting provider:{ $exc }
msg-507853eb = Unable to create a new conversation.
msg-24bd9273 = Error occurred while retrieving the knowledge base:{ $exc }
msg-36dc1409 = Moonshot AI file extraction API key is not set.
msg-b41a7a58 = Unsupported file extraction provider:{ $res }
msg-f2ea29f4 = Unable to retrieve image description because provider `{ $provider_id }` does not exist.
msg-91a70615 = Unable to retrieve image description because provider `{ $provider_id }` is not a valid provider.{ $res }.
msg-6097bd34 = Currently using provider{ $provider_id }Processing image descriptions
msg-7f5e3367 = Failed to process image description:{ $exc }
msg-719d5e4d = No image description provider found in the reference.
msg-633f992f = Failed to process referenced image:{ $exc }
msg-1891edf8 = Group name is shown as enabled, but the group object is empty. Group ID:{ $res }
msg-7d93dc13 = Incorrect timezone setting:{ $exc }Use the local time zone
msg-09eb6259 = Provider{ $provider }Images not supported; using placeholders.
msg-f57d475e = Provider{ $provider }Tool usage not supported; clearing Tool.
msg-2e3df24a = sanitize_context_by_modalities applied: removed_image_blocks={ $removed_image_blocks }Tool message removed={ $removed_tool_messages }Tool invocation removed={ $removed_tool_calls }
msg-5becd564 = Chat interface title generated for the session{ $chatui_session_id }:{ $title }
msg-d8cff4db = Unsupported llm_safety_mode policy:{ $res }.
msg-7ea2c5d3 = Shipyard sandbox configuration is incomplete.
msg-8271b0d7 = The specified context compression model was not found.{ $res }Skipping compression.
msg-bf48c713 = Specified context compression model{ $res }Non-dialogue model, compression will be skipped.
msg-c6c9d989 = The fallback_chat_models setting is not a list; skipping fallback providers.
msg-c48173dd = Backup chat service provider{ $fallback_id }Not found, skipping.
msg-88fd7233 = Backup chat service provider{ $fallback_id }` is an invalid type:{ $res }Skip.
msg-ee979399 = No conversation model (provider) found; skipping LLM request processing.
msg-d003c63c = Skip quoted alternate images because limit={ $res }Regarding umo={ $res_2 }
msg-65bb0f30 = Fallback image for truncated quotes in umo={ $res }reply_id={ $res_2 }From{ $res_3 }To{ $remaining_limit }
msg-617040f3 = Unable to parse fallback reference image for umo={ $res }reply_id={ $res_2 }:{ $exc }
msg-d4c7199d = An error occurred while extracting the application file:{ $exc }

### astrbot\core\astr_main_agent_resources.py

msg-509829d8 = Files downloaded from the sandbox:{ $path }->{ $local_path }
msg-b462b60d = Unable to check or download files from the sandbox:{ $e }
msg-0b3144f1 = [Knowledge Base] Session{ $umo }Configured to not use the knowledge base.
msg-97e13f98 = [Knowledge Base] The knowledge base does not exist or is not loaded:{ $kb_id }
msg-312d09c7 = [Knowledge Base] Session{ $umo }The following knowledge base configuration is invalid:{ $invalid_kb_ids }
msg-42b0e9f8 = [Knowledge Base] Using session-level configuration, number of knowledge bases:{ $res }
msg-08167007 = [Knowledge Base] Using global configuration, number of knowledge bases:{ $res }
msg-a00becc3 = [Knowledge Base] Starting knowledge base retrieval, quantity:{ $res }top_k={ $top_k }
msg-199e71b7 = [Knowledge Base] For Conversations{ $umo }Injected{ $res }Related knowledge points

### astrbot\core\conversation_mgr.py

msg-86f404dd = Session deletion callback execution failed (session:{ $unified_msg_origin }):{ $e }
msg-57dcc41f = Session ID{ $cid }Not found

### astrbot\core\core_lifecycle.py

msg-9967ec8b = Using proxy:{ $proxy_config }
msg-5a29b73d = HTTP proxy has been cleared.
msg-fafb87ce = Sub-agent orchestrator initialization failed:{ $e }
msg-f7861f86 = AstrBot migration failed:{ $e }
msg-78b9c276 = { $res }
msg-967606fd = ------- Task{ $res }An error occurred:{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = -------
msg-9556d279 = AstrBot startup completed.
msg-daaf690b = Hook (when _astrbot_ finishes loading) ->{ $res }-{ $res_2 }
msg-4719cb33 = Plugin{ $res }Abnormal termination{ $e }May lead to issues such as resource leaks.
msg-c3bbfa1d = Task{ $res }An error occurred:{ $e }
msg-af06ccab = Configuration file{ $conf_id }Does not exist

### astrbot\core\event_bus.py

msg-da466871 = PipelineScheduler with the corresponding ID was not found.{ $res }Event has been ignored.
msg-7eccffa5 = [{ $conf_name }] [{ $res }({ $res_2 })]{ $res_3 }/{ $res_4 }:{ $res_5 }
msg-88bc26f2 = [{ $conf_name }] [{ $res }({ $res_2 })]{ $res_3 }:{ $res_4 }

### astrbot\core\file_token_service.py

msg-0e444e51 = File does not exist:{ $local_path }: (Original input:{ $file_path })
msg-f61a5322 = Invalid or expired file token:{ $file_token }
msg-73d3e179 = File does not exist:{ $file_path }

### astrbot\core\initial_loader.py

msg-78b9c276 = { $res }
msg-58525c23 = 😭 Failed to initialize AstrBot:{ $e }!!!
msg-002cc3e8 = 🌈 Shutting down AstrBot...

### astrbot\core\log.py

msg-80a186b8 = Failed to add file receiver:{ $e }

### astrbot\core\persona_mgr.py

msg-51a854e6 = Loaded{ $res }Personality.
msg-1ea88f45 = ID is{ $session_id }Personality does not exist.
msg-28104dff = ID is{ $session_id }The personality already exists.
msg-08ecfd42 = { $res }The personality scenario preset dialogue format is incorrect; the number of entries must be even.
msg-b6292b94 = Failed to parse personality configuration:{ $e }

### astrbot\core\subagent_orchestrator.py

msg-5d950986 = subagent_orchestrator.agents must be a list
msg-4867eefb = Sub-agent personality{ $persona_id }Not found, fallback to inline prompt.
msg-f425c9f0 = Sub-agent Handover Tool Registered{ $res }

### astrbot\core\umop_config_router.py

msg-dedcfded = The umop key must be a string in the format [platform_id]:[message_type]:[session_id], supporting the use of wildcard * or leaving it blank to indicate all.
msg-8e3a16f3 = umop must be a string in the format [platform_id]:[message_type]:[session_id], where wildcard * or leaving it blank indicates all.

### astrbot\core\updator.py

msg-e3d42a3b = Terminating{ $res }child process.
msg-e7edc4a4 = Terminating child process{ $res }
msg-37bea42d = Child process{ $res }Not terminated normally; forcing termination now.
msg-cc6d9588 = Restart failed ({ $executable },{ $e }), please try to restart manually.
msg-0e4439d8 = Updates to AstrBot launched in this manner are not supported.
msg-3f39a942 = It is already the latest version.
msg-c7bdf215 = Version number not found.{ $version }Update file.
msg-92e46ecc = The commit hash length is incorrect; it should be 40 characters.
msg-71c01b1c = Preparing to update AstrBot Core to the specified version:{ $version }
msg-d3a0e13d = Download of AstrBot Core update file completed, extracting now...

### astrbot\core\zip_updator.py

msg-24c90ff8 = Request{ $url }Failed, status code:{ $res }Content:{ $text }
msg-14726dd8 = Request failed, status code:{ $res }
msg-fc3793c6 = An exception occurred while parsing version information:{ $e }
msg-491135d9 = Failed to parse version information.
msg-03a72cb5 = No suitable release version found.
msg-8bcbfcf0 = Downloading updates{ $repo }...
msg-ccc87294 = Fetching from the specified branch{ $branch }Download{ $author }/{ $repo }
msg-dfebcdc6 = Retrieve{ $author }/{ $repo }GitHub Releases failed:{ $e }, will attempt to download the default branch
msg-e327bc14 = Downloading from the default branch.{ $author }/{ $repo }
msg-3cd3adfb = Mirror site detected; will use mirror site for download.{ $author }/{ $repo }Repository source code:{ $release_url }
msg-1bffc0d7 = Invalid GitHub URL
msg-0ba954db = File extraction completed:{ $zip_path }
msg-90ae0d15 = Delete temporary update files:{ $zip_path }and{ $res }
msg-f8a43aa5 = Failed to delete the update file; you can delete it manually.{ $zip_path }and{ $res }

### astrbot\core\agent\mcp_client.py

msg-6a61ca88 = Warning: Missing 'mcp' dependency; MCP service will be unavailable.
msg-45995cdb = Warning: Missing 'mcp' dependency or MCP library version is too old, unable to use streaming HTTP connections.
msg-2866b896 = MCP connection configuration is missing the transport or type field.
msg-3bf7776b = MCP Server{ $name }Error:{ $msg }
msg-10f72727 = { $error_msg }
msg-19c9b509 = MCP client not initialized
msg-5b9b4918 = MCP Client{ $res }Reconnecting, skipping
msg-c1008866 = Unable to reconnect: Missing connection configuration
msg-7c3fe178 = Attempting to reconnect to the MCP server.{ $res }...
msg-783f3b85 = Successfully reconnected to the MCP server.{ $res }
msg-da7361ff = Unable to reconnect to the MCP server.{ $res }:{ $e }
msg-c0fd612e = MCP sessions are not applicable to MCP functional Tools.
msg-8236c58c = MCP Tool{ $tool_name }Call failed (ClosedResourceError), attempting to reconnect...
msg-044046ec = Error occurred while closing the current exit stack:{ $e }

### astrbot\core\agent\message.py

msg-d38656d7 = { $invalid_subclass_error_msg }
msg-42d5a315 = Unable to verify{ $value }As ContentPart
msg-ffc376d0 = Content is required unless the role is 'assistant' and the Tool call is not empty.

### astrbot\core\agent\tool.py

msg-983bc802 = FunctionTool.call() must be implemented by subclasses or have a handler set.

### astrbot\core\agent\tool_image_cache.py

msg-45da4af7 = ToolImageCache initialized, cache directory:{ $res }
msg-017bde96 = Saved Tool image to:{ $file_path }
msg-29398f55 = Failed to save Tool image:{ $e }
msg-128aa08a = Unable to read cached image.{ $file_path }:{ $e }
msg-3c111d1f = An error occurred during cache cleanup:{ $e }
msg-eeb1b849 = Cleaned{ $cleaned }Expired cached images

### astrbot\core\agent\context\compressor.py

msg-6c75531b = Failed to generate summary:{ $e }

### astrbot\core\agent\context\manager.py

msg-59241964 = An error occurred during context processing:{ $e }
msg-a0d672dc = Compression triggered, starting compression...
msg-e6ef66f0 = Compression completed.{ $prev_tokens }->{ $tokens_after_summary }Token, Compression Rate:{ $compress_rate }%.
msg-3fe644eb = Context still exceeds maximum token count after compression, applying halved truncation...

### astrbot\core\agent\runners\base.py

msg-24eb2b08 = Agent State Transition:{ $res }->{ $new_state }

### astrbot\core\agent\runners\tool_loop_agent_runner.py

msg-ec018aef = Switched from{ $res }Fallback to chat service provider:{ $candidate_id }
msg-24b29511 = Chat model{ $candidate_id }Returning error response, attempting to switch to the next provider.
msg-9af066fa = Chat model{ $candidate_id }Request error:{ $exc }
msg-81b2aeae = { $tag }RunCtx.messages -> [{ $res }]{ $res_2 }
msg-55333301 = Request not set. Please call the reset() method first.
msg-d3b77736 = Error occurred in the agent start hook:{ $e }
msg-61de315c = User requested to stop proxy execution.
msg-8eb53be3 = Error occurred in the on_agent_done hook:{ $e }
msg-508d6d17 = LLM response error:{ $res }
msg-ed80313d = The large language model returned an empty assistant message with no Tool calls.
msg-970947ae = Added{ $res }Cache images to context for LLM review.
msg-6b326889 = Agent has reached the maximum number of steps.{ $max_step }), force final response.
msg-948ea4b7 = Agent uses Tool:{ $res }
msg-a27ad3d1 = Using Tool:{ $func_tool_name }Parameters:{ $func_tool_args }
msg-812ad241 = Specified Tool not found.{ $func_tool_name }Skipping.
msg-20b4f143 = Tool{ $func_tool_name }Expected parameters:{ $res }
msg-78f6833c = Tool{ $func_tool_name }Ignore unexpected parameters:{ $ignored_params }
msg-2b523f8c = Error occurred in the tool startup hook:{ $e }
msg-ec868b73 = { $func_tool_name }No return value, or the result has been sent directly to the user.
msg-6b61e4f1 = Tool returned an unsupported type:{ $res }.
msg-34c13e02 = Error occurred in the tool end hook:{ $e }
msg-78b9c276 = { $res }
msg-a1493b6d = Tool{ $func_tool_name }Result:{ $last_tcr_content }

### astrbot\core\agent\runners\coze\coze_agent_runner.py

msg-448549b0 = Coze API Key cannot be empty.
msg-b88724b0 = Coze Bot ID cannot be empty.
msg-ea5a135a = The Coze API base URL format is incorrect; it must start with http:// or https://.
msg-55333301 = Request not set. Please call the reset() method first.
msg-d3b77736 = Error occurred in the agent start hook:{ $e }
msg-5aa3eb1c = Coze request failed:{ $res }
msg-333354c6 = Failed to process context image:{ $e }
msg-2d9e1c08 = Image processing failed.{ $url }:{ $e }
msg-1f50979d = { $content }
msg-6fe5588b = Coze message processing is complete.
msg-d2802f3b = Coze chat has been completed.
msg-ba4afcda = Coze encountered an error:{ $error_code }-{ $error_msg }
msg-ee300f25 = Coze did not return any content.
msg-8eb53be3 = Error occurred in the on_agent_done hook:{ $e }
msg-034c1858 = [Coze] Using cached file_id:{ $file_id }
msg-475d8a41 = [Coze] Image uploaded successfully and cached, file_id:{ $file_id }
msg-696dad99 = Image processing failed.{ $image_url }:{ $e }
msg-7793a347 = Image processing failed:{ $e }

### astrbot\core\agent\runners\coze\coze_api_client.py

msg-76f97104 = Coze API authentication failed. Please verify that the API Key is correct.
msg-3653b652 = File upload response status:{ $res }Content:{ $response_text }
msg-13fe060c = File upload failed, status code:{ $res }Response:{ $response_text }
msg-5604b862 = File upload response parsing failed:{ $response_text }
msg-c0373c50 = File upload failed:{ $res }
msg-010e4299 = [Coze] Image uploaded successfully, file_id:{ $file_id }
msg-719f13cb = File upload timeout
msg-121c11fb = File upload failed:{ $e }
msg-f6101892 = Failed to download image, status code:{ $res }
msg-c09c56c9 = Image download failed.{ $image_url }:{ $e }
msg-15211c7c = Image download failed:{ $e }
msg-2245219f = Coze Chat Message Payload:{ $payload }Parameters:{ $params }
msg-d8fd415c = Coze API streaming request failed with status code:{ $res }
msg-f5cc7604 = Coze API streaming request timeout{ $timeout }seconds)
msg-30c0a9d6 = Coze API streaming request failed:{ $e }
msg-11509aba = Coze API request failed with status code:{ $res }
msg-002af11d = Coze API returns a non-JSON format.
msg-c0b8fc7c = Coze API request timeout
msg-a68a33fa = Coze API request failed:{ $e }
msg-c26e068e = Failed to retrieve the Coze message list:{ $e }
msg-5bc0a49d = Uploaded file ID:{ $file_id }
msg-7c08bdaf = Event:{ $event }

### astrbot\core\agent\runners\dashscope\dashscope_agent_runner.py

msg-dc1a9e6e = Alibaba Cloud Bailian API Key cannot be empty.
msg-c492cbbc = Alibaba Cloud Bailian APP ID cannot be empty.
msg-bcc8e027 = The APP type for Alibaba Cloud Bailian cannot be empty.
msg-55333301 = Request not set. Please call the reset() method first.
msg-d3b77736 = Error occurred in the agent start hook:{ $e }
msg-e3af4efd = Alibaba Cloud Bailian request failed:{ $res }
msg-fccf5004 = dashscope streaming data block:{ $chunk }
msg-100d7d7e = Alibaba Cloud Bailian request failed: request_id={ $res }, code={ $res_2 }, message={ $res_3 }Please refer to the documentation: https://help.aliyun.com/zh/model-studio/developer-reference/error-code
msg-10f72727 = { $error_msg }
msg-e8615101 = { $chunk_text }
msg-dfb132c4 = { $ref_text }
msg-8eb53be3 = Error occurred in the on_agent_done hook:{ $e }
msg-650b47e1 = Alibaba Cloud Bailian currently does not support image input and will automatically ignore image content.

### astrbot\core\agent\runners\dify\dify_agent_runner.py

msg-55333301 = Request not set. Please call the reset() method first.
msg-d3b77736 = Error occurred in the agent start hook:{ $e }
msg-0d493427 = Dify request failed:{ $res }
msg-fe594f21 = Dify Image Upload Response:{ $file_response }
msg-3534b306 = After uploading the image, an unknown Dify response was received:{ $file_response }Images will be ignored.
msg-08441fdf = Image upload failed:{ $e }
msg-3972f693 = dify response block:{ $chunk }
msg-6c74267b = Dify message ends
msg-1ce260ba = Dify encountered an error:{ $chunk }
msg-a12417dd = Dify encountered an error status:{ $res }Message:{ $res_2 }
msg-f8530ee9 = dify workflow response block:{ $chunk }
msg-386a282e = Dify Workflow (ID:{ $res }) Starting operation.
msg-0bc1299b = Dify Workflow Node (ID:{ $res }Title:{ $res_2 }) Run completed.
msg-5cf24248 = Dify Workflow (ID:{ $res }) Run completed
msg-e2c2159f = Dify Workflow Result:{ $chunk }
msg-4fa60ef1 = Dify workflow error occurred:{ $res }
msg-1f786836 = The output of the Dify workflow does not contain the specified key name.{ $res }
msg-c4a70ffb = Unknown Dify API type:{ $res }
msg-51d321fd = The Dify request result is empty; please check the Debug log.
msg-8eb53be3 = Error occurred in the on_agent_done hook:{ $e }

### astrbot\core\agent\runners\dify\dify_api_client.py

msg-cd6cd7ac = Discard invalid dify JSON data:{ $res }
msg-3654a12d = Chat message payload:{ $payload }
msg-8e865c52 = Dify /chat-messages interface request failed:{ $res }.{ $text }
msg-2d7534b8 = workflow_run load:{ $payload }
msg-89918ba5 = Dify /workflows/run interface request failed:{ $res }.{ $text }
msg-8bf17938 = file_path and file_data cannot both be None
msg-b6ee8f38 = Dify file upload failed:{ $res }.{ $text }

### astrbot\core\backup\exporter.py

msg-c7ed7177 = Starting to export backup to{ $zip_path }
msg-8099b694 = Backup export completed:{ $zip_path }
msg-75a4910d = Backup export failed:{ $e }
msg-2821fc92 = Export table{ $table_name }:{ $res }record
msg-52b7c242 = Export table{ $table_name }Failure:{ $e }
msg-56310830 = Export knowledge base table{ $table_name }:{ $res }1 record
msg-f4e8f57e = Export knowledge base table{ $table_name }Failure:{ $e }
msg-8e4ddd12 = Failed to export knowledge base documents:{ $e }
msg-c1960618 = Export FAISS index:{ $archive_path }
msg-314bf920 = Failed to export FAISS index:{ $e }
msg-528757b2 = Failed to export knowledge base media files:{ $e }
msg-d89d6dfe = Directory does not exist, skipping.{ $full_path }
msg-94527edd = Export file{ $file_path }Failure:{ $e }
msg-cb773e24 = Export Directory{ $dir_name }:{ $file_count }This file,{ $total_size }Byte
msg-ae929510 = Export Directory{ $dir_path }Failure:{ $e }
msg-93e331d2 = Failed to export attachment:{ $e }

### astrbot\core\backup\importer.py

msg-c046b6e4 = { $msg }
msg-0e6f1f5d = Start from{ $zip_path }Import Backup
msg-2bf97ca0 = Backup import completed:{ $res }
msg-e67dda98 = Backup file lacks version information.
msg-8f871d9f = Version discrepancy warning:{ $res }
msg-2d6da12a = Table has been cleared.{ $table_name }
msg-7d21b23a = Clear the table{ $table_name }Failure:{ $e }
msg-ab0f09db = The knowledge base table has been cleared.{ $table_name }
msg-7bcdfaee = Clear the knowledge base table.{ $table_name }Failure:{ $e }
msg-43f008f1 = Clean up the knowledge base{ $kb_id }Failure:{ $e }
msg-985cae66 = Unknown table:{ $table_name }
msg-dfa8b605 = Import records to{ $table_name }Failure:{ $e }
msg-89a2120c = Import Table{ $table_name }:{ $count }One record
msg-f1dec753 = Import knowledge base records into{ $table_name }Failure:{ $e }
msg-9807bcd8 = Failed to import document block:{ $e }
msg-98a66293 = Import attachment{ $name }Failure:{ $e }
msg-39f2325f = Backup version does not support directory backup; skipping directory import.
msg-689050b6 = Existing directory has been backed up.{ $target_dir }To{ $backup_path }
msg-d51b3536 = Import Directory{ $dir_name }:{ $file_count }This file

### astrbot\core\computer\computer_client.py

msg-7cb974b8 = Uploading the skill package to the sandbox...
msg-130cf3e3 = The skill package upload to the sandbox failed.
msg-99188d69 = Unable to delete temporary skill archive:{ $zip_path }
msg-3f3c81da = Unknown bootloader type:{ $booter_type }
msg-e20cc33a = Session sandbox startup error{ $session_id }:{ $e }

### astrbot\core\computer\booters\boxlite.py

msg-019c4d18 = Operation failed:{ $res } { $error_text }
msg-b135b7bd = File upload failed:{ $e }
msg-873ed1c8 = File not found:{ $path }
msg-f58ceec6 = An unexpected error occurred while uploading the file:{ $e }
msg-900ab999 = Checking{ $res }On Sandbox{ $ship_id }Health status...
msg-2a50d6f3 = Sandbox{ $ship_id }Status Healthy
msg-fbdbe32f = Processing session{ $session_id }Starting (Boxlite), this may take some time...
msg-b1f13f5f = Session{ $session_id }The Boxlite launcher has started.
msg-e93d0c30 = Shutting down instance{ $res }Boxlite Launcher
msg-6deea473 = Example{ $res }The Boxlite launcher has stopped.

### astrbot\core\computer\booters\local.py

msg-487d0c91 = The path exceeds the allowed root directory scope of the computer.
msg-e5eb5377 = Blocked unsafe shell commands.
msg-9e1e117f = Local computer launcher has been initialized for the session:{ $session_id }
msg-2d7f95de = Local computer launcher shutdown completed.
msg-82a45196 = LocalBooter does not support the upload_file operation. Please use shell instead.
msg-0457524a = LocalBooter does not support the download_file operation. Please use shell instead.

### astrbot\core\computer\booters\shipyard.py

msg-b03115b0 = Sandbox environment acquired:{ $res }For the session:{ $session_id }
msg-c5ce8bde = Error occurred while checking Shipyard sandbox availability:{ $e }

### astrbot\core\computer\tools\fs.py

msg-99ab0efe = Upload result:{ $result }
msg-bca9d578 = File{ $local_path }Uploaded to the sandbox environment.{ $file_path }
msg-da21a6a5 = File upload error{ $local_path }:{ $e }
msg-93476abb = File{ $remote_path }Downloaded from the sandbox to{ $local_path }
msg-079c5972 = Error sending file message:{ $e }
msg-ce35bb2c = File download error{ $remote_path }:{ $e }

### astrbot\core\config\astrbot_config.py

msg-e0a69978 = Unsupported configuration type{ $res }Supported types include:{ $res_2 }
msg-b9583fc9 = Configuration item detected{ $path_ }Does not exist, default value inserted.{ $value }
msg-ee26e40e = Configuration item detected{ $path_ }Does not exist; it will be removed from the current configuration.
msg-2d7497a5 = Configuration item detected{ $path }The sub-item order was inconsistent and has been reordered.
msg-5fdad937 = Configuration item order inconsistency detected; reordering has been performed.
msg-555373b0 = Key not found: '{ $key }'

### astrbot\core\cron\manager.py

msg-2a752c91 = Skip scheduling of basic scheduled tasks{ $res }Due to a missing handler.
msg-d5c33112 = Invalid time zone{ $res }For scheduled tasks{ $res_2 }Fallback to the system.
msg-e71c28d3 = One-time task missing execution timestamp.
msg-dd46e69f = Unable to schedule timed tasks.{ $res }:{ $e }
msg-aa2e4688 = Unknown scheduled task type:{ $res }
msg-186627d9 = Scheduled Task{ $job_id }Failure:{ $e }
msg-cb955de0 = Basic cron task processor not found{ $res }
msg-2029c4b2 = ActiveAgentCronJob is missing a session.
msg-6babddc9 = Scheduled task session is invalid:{ $e }
msg-865a2b07 = Failed to build the scheduled task master agent.
msg-27c9c6b3 = Cron job agent did not receive a response.

### astrbot\core\db\migration\helper.py

msg-a48f4752 = Starting database migration...
msg-45e31e8e = Database migration completed.

### astrbot\core\db\migration\migra_3_to_4.py

msg-7805b529 = Migration{ $total_cnt }Migrating old session data to the new table...
msg-6f232b73 = Progress:{ $progress }% ({ $res }/{ $total_cnt })
msg-6b1def31 = No specific data was found for the corresponding old session.{ $conversation }Skip.
msg-b008c93f = Migrate old sessions{ $res }Failure:{ $e }
msg-6ac6313b = Successfully migrated{ $total_cnt }Migrate old session data to the new table.
msg-6b72e89b = Migrating data from the old platform, offset_sec:{ $offset_sec }Seconds.
msg-bdc90b84 = Migration{ $res }Migrating old platform data to the new table...
msg-e6caca5c = Old platform data not found, skipping migration.
msg-1e824a79 = Progress:{ $progress }% ({ $res }/{ $total_buckets })
msg-813384e2 = Migration platform statistics failed:{ $platform_id },{ $platform_type }Timestamp:{ $bucket_end }
msg-27ab191d = Successfully migrated{ $res }Migrate old platform data to the new table.
msg-8e6280ed = Migration{ $total_cnt }Migrating old WebChat session data to a new table...
msg-cad66fe1 = Migrate old WebChat sessions{ $res }Failure
msg-63748a46 = Successfully migrated{ $total_cnt }Migrate old WebChat session data to the new table.
msg-dfc93fa4 = Migration{ $total_personas }Configure Persona to the new table...
msg-ff85e45c = Progress:{ $progress }% ({ $res }/{ $total_personas })
msg-c346311e = Migrate Persona{ $res }({ $res_2 }...) Successfully migrated to the new table.
msg-b6292b94 = Failed to parse Persona configuration:{ $e }
msg-90e5039e = Migrate global preferences{ $key }Success, value:{ $value }
msg-d538da1c = Migrate Session{ $umo }Dialogue data successfully migrated to the new table, Platform ID:{ $platform_id }
msg-ee03c001 = Migrate Session{ $umo }Dialogue data failure:{ $e }
msg-5c4339cd = Migrate Session{ $umo }Service configuration migrated to the new table successfully. Platform ID:{ $platform_id }
msg-4ce2a0b2 = Migrate Session{ $umo }Service configuration failed:{ $e }
msg-2e62dab9 = Migrate Session{ $umo }Variable failure:{ $e }
msg-afbf819e = Migrate Session{ $umo }Provider preferences successfully migrated to the new table, Platform ID:{ $platform_id }
msg-959bb068 = Migrate Session{ $umo }Provider preference failed:{ $e }

### astrbot\core\db\migration\migra_45_to_46.py

msg-782b01c1 = migrate_45_to_46: abconf_data is not a dictionary type (type={ $res }). Value:{ $abconf_data }
msg-49e09620 = Starting migration from version 4.5 to 4.6.
msg-791b79f8 = Migration from version 45 to version 46 has been successfully completed.

### astrbot\core\db\migration\migra_token_usage.py

msg-c3e53a4f = Starting database migration (adding the conversations.token_usage column)...
msg-ccbd0a41 = The token_usage column already exists, skipping migration.
msg-39f60232 = Column token_usage added successfully.
msg-4f9d3876 = token_usage migration completed
msg-91571aaf = An error occurred during the migration process:{ $e }

### astrbot\core\db\migration\migra_webchat_session.py

msg-53fad3d0 = Starting database migration (WebChat session migration)...
msg-7674efb0 = No WebChat data requiring migration was found.
msg-139e39ee = Found{ $res }This WebChat session requires migration.
msg-cf287e58 = Session{ $session_id }Already exists, skipping
msg-062c72fa = WebChat session migration completed! Successfully migrated:{ $res }Skip:{ $skipped_count }
msg-a516cc9f = No new sessions require migration.
msg-91571aaf = An error occurred during the migration process:{ $e }

### astrbot\core\db\vec_db\faiss_impl\document_storage.py

msg-c2dc1d2b = Database connection not initialized, returning empty result.
msg-51fa7426 = Database connection not initialized, skipping delete operation.
msg-43d1f69f = Database connection not initialized, returning 0.

### astrbot\core\db\vec_db\faiss_impl\embedding_storage.py

msg-8e5fe535 = faiss is not installed. Please install it using 'pip install faiss-cpu' or 'pip install faiss-gpu'.
msg-9aa7b941 = Vector dimension mismatch, expected:{ $res }Actual:{ $res_2 }

### astrbot\core\db\vec_db\faiss_impl\vec_db.py

msg-9f9765dc = Generating embeddings{ $res }Content...
msg-385bc50a = Embedding vectors have been generated.{ $res }Content{ $res_2 }Seconds.

### astrbot\core\knowledge_base\kb_db_sqlite.py

msg-b850e5d8 = Knowledge base database is closed:{ $res }

### astrbot\core\knowledge_base\kb_helper.py

msg-7b3dc642 = - The{ $attempt }LLM call failed on the second attempt{ $res }/{ $res_2 }Error:{ $res_3 }
msg-4ba9530f = - Failed to process shard at{ $res }After the second attempt, use the original text.
msg-77670a3a = Knowledge Base{ $res }Embedding Provider not configured
msg-8e9eb3f9 = Unable to find ID{ $res }Embedding Provider
msg-3e426806 = Unable to find ID{ $res }Reordering Provider
msg-6e780e1e = Uploading using pre-chunked text, total{ $res }A block.
msg-f4b82f18 = When pre_chunked_text is not provided, file_content cannot be empty.
msg-975f06d7 = Document upload failed:{ $e }
msg-969b17ca = Failed to clean up multimedia files.{ $media_path }:{ $me }
msg-18d25e55 = Unable to find ID{ $doc_id }Document
msg-f5d7c34c = Error: Tavily API key is not configured in provider_settings.
msg-975d88e0 = Unable to extract content from URL{ $url }:{ $e }
msg-cfe431b3 = No content extracted from the URL:{ $url }
msg-e7f5f836 = No valid text was extracted after content cleaning. Please try disabling the content cleaning function or switching to a higher-performance LLM model and retry.
msg-693aa5c5 = Content cleaning is not enabled; using specified parameters for chunking: chunk_size={ $chunk_size }chunk_overlap={ $chunk_overlap }
msg-947d8f46 = Content cleaning is enabled, but no cleaning_provider_id is provided; skipping cleaning and using default chunking.
msg-31963d3f = Unable to find ID{ $cleaning_provider_id }The LLM provider or type is incorrect.
msg-82728272 = Initial chunking completed, generating.{ $res }This block is for fixing.
msg-6fa5fdca = Block{ $i }Handling exceptions:{ $res }Roll back to the original block.
msg-6780e950 = Text repair completed:{ $res }Original block ->{ $res_2 }The final block.
msg-79056c76 = Using provider '{ $cleaning_provider_id }Content cleaning failed:{ $e }

### astrbot\core\knowledge_base\kb_mgr.py

msg-98bfa670 = Initializing knowledge base module...
msg-7da7ae15 = Knowledge base module import failed:{ $e }
msg-842a3c65 = Please ensure the required dependencies are installed: pypdf, aiofiles, Pillow, rank-bm25.
msg-c9e943f7 = Knowledge base module initialization failed:{ $e }
msg-78b9c276 = { $res }
msg-9349e112 = Knowledge base database has been initialized.{ $DB_PATH }
msg-7605893e = The embedding_provider_id must be provided when creating a knowledge base.
msg-0b632cbd = Knowledge Base Name{ $kb_name }Already exists
msg-ca30330f = Knowledge base is closed.{ $kb_id }Failure:{ $e }
msg-00262e1f = Failed to close the knowledge base metadata database:{ $e }
msg-3fc9ef0b = ID is{ $kb_id }Knowledge base not found.

### astrbot\core\knowledge_base\chunking\recursive.py

msg-21db456a = Block size must be greater than 0.
msg-c0656f4e = Block overlap must be a non-negative number.
msg-82bd199c = The block overlap must be less than the block size.

### astrbot\core\knowledge_base\parsers\text_parser.py

msg-70cbd40d = Unable to decode file:{ $file_name }

### astrbot\core\knowledge_base\parsers\url_parser.py

msg-2de85bf5 = Error: Tavily API key not configured.
msg-98ed69f4 = Error: URL must be a non-empty string.
msg-7b14cdb7 = Tavily web page extraction failed:{ $reason }Status:{ $res }
msg-cfe431b3 = No content extracted from the URL:{ $url }
msg-b0897365 = Failed to retrieve URL{ $url }:{ $e }
msg-975d88e0 = Unable to extract content from URL{ $url }:{ $e }

### astrbot\core\knowledge_base\parsers\util.py

msg-398b3580 = Unsupported file format:{ $ext }

### astrbot\core\knowledge_base\retrieval\manager.py

msg-fcc0dde2 = Knowledge Base ID{ $kb_id }Instance not found, retrieval for this knowledge base has been skipped.
msg-320cfcff = Dense retrieval across{ $res }Base has been acquired.{ $res_2 }and return{ $res_3 }Result.
msg-90ffcfc8 = Cross-Sparse Retrieval{ $res }Base has been acquired.{ $res_2 }and return{ $res_3 }Result.
msg-12bcf404 = Ranking fusion time consumption{ $res }and return{ $res_2 }Result.
msg-28c084bc = Vector database for knowledge base ID{ $kb_id }Not FaissVecDB
msg-cc0230a3 = Knowledge Base{ $kb_id }Dense retrieval failed:{ $e }

### astrbot\core\message\components.py

msg-afb10076 = Not a valid URL
msg-fe4c33a0 = Not a valid file:{ $res }
msg-24d98e13 = callback_api_base is not configured; file service is unavailable.
msg-a5c69cc9 = Registered:{ $callback_host }/api/files/{ $token }
msg-3cddc5ef = Download failed:{ $url }
msg-1921aa47 = Not a valid file:{ $url }
msg-2ee3827c = Generated video file callback URL:{ $payload_file }
msg-32f4fc78 = No valid file or URL provided.
msg-36375f4c = Do not synchronously wait for downloads in asynchronous contexts! This warning typically appears when certain logic attempts to retrieve the content of a file message segment via `<File>.file`. Please use `await get_file()` instead of directly accessing the `<File>.file` field.
msg-4a987754 = File download failed:{ $e }
msg-7c1935ee = Download failed: URL not provided in the file component.
msg-35bb8d53 = File generation callback link:{ $payload_file }

### astrbot\core\pipeline\context_utils.py

msg-49f260d3 = Handler function parameter mismatch, please check the handler definition.
msg-d7b4aa84 = Previous error:{ $trace_ }
msg-eb8619cb = Hook{ $res }) ->{ $res_2 }-{ $res_3 }
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }Event propagation has been stopped.

### astrbot\core\pipeline\scheduler.py

msg-c240d574 = Phase{ $res }Event propagation has been terminated.
msg-609a1ac5 = Pipeline execution completed.

### astrbot\core\pipeline\__init__.py


### astrbot\core\pipeline\content_safety_check\stage.py

msg-c733275f = Your message or the large model's response contains inappropriate content and has been blocked.
msg-46c80f28 = Content security check failed. Reason:{ $info }

### astrbot\core\pipeline\content_safety_check\strategies\strategy.py

msg-27a700e0 = Before using Baidu Content Moderation, you should first execute pip install baidu-aip.

### astrbot\core\pipeline\preprocess_stage\stage.py

msg-7b9074fa = { $platform }Pre-response emoji sending failed:{ $e }
msg-43f1b4ed = Path mapping:{ $url }->{ $res }
msg-9549187d = Session{ $res }Voice-to-text model is not configured.
msg-5bdf8f5c = { $e }
msg-ad90e19e = Retrying:{ $res }/{ $retry }
msg-78b9c276 = { $res }
msg-4f3245bf = Speech-to-text conversion failed:{ $e }

### astrbot\core\pipeline\process_stage\follow_up.py

msg-12767505 = Subsequent messages from the active agent operation have been captured, umo={ $res }order_seq={ $order_seq }

### astrbot\core\pipeline\process_stage\method\agent_request.py

msg-3267978a = Identify additional wake-up prefixes for LLM chat.{ $res }Robot wake-up prefix{ $bwp }Beginning, automatically removed.
msg-97a4d573 = This pipeline does not have AI functionality enabled; skipping processing.
msg-f1a11d2b = Session{ $res }AI functionality disabled, skipping processing.

### astrbot\core\pipeline\process_stage\method\star_request.py

msg-f0144031 = Unable to find a plugin for the given processor module path:{ $res }
msg-1e8939dd = Plugin ->{ $res }-{ $res_2 }
msg-6be73b5e = { $traceback_text }
msg-d919bd27 = Star{ $res }Error handling:{ $e }
msg-ed8dcc22 = { $ret }

### astrbot\core\pipeline\process_stage\method\agent_sub_stages\internal.py

msg-73bf9e45 = Unsupported tool_schema_mode:{ $res }Rollback to skills_like
msg-9cdb2b6e = Skipping LLM request: Message is empty and no provider request.
msg-e461e5af = Preparing to request LLM service provider
msg-4d2645f7 = Subsequent tickets have been processed; stop processing.{ $res }sequence={ $res_2 }
msg-abd5ccbc = Session lock for the LLM request has been acquired.
msg-abc0d82d = Provider API Basics{ $api_base }For security reasons, access has been blocked. Please use another AI service provider.
msg-3247374d = [Internal Proxy] Real-time mode detected, enabling TTS processing.
msg-dae92399 = [Real-time Mode] TTS provider not configured; normal streaming mode will be used.
msg-1b1af61e = Error occurred while processing the proxy:{ $e }
msg-ea02b899 = An error occurred while processing the proxy request:{ $e }
msg-ee7e792b = LLM response is empty; no record saved.

### astrbot\core\pipeline\process_stage\method\agent_sub_stages\third_party.py

msg-5e551baf = Third-party agent runner error:{ $e }
msg-34f164d4 = { $err_msg }
msg-f9d76893 = Agent Runner provider ID is not filled in. Please go to the configuration page to configure it.
msg-0f856470 = Agent Runner Provider{ $res }Configuration does not exist. Please go to the configuration page to modify the settings.
msg-b3f25c81 = Unsupported third-party proxy runner type:{ $res }
msg-6c63eb68 = Agent Runner did not return a final result.

### astrbot\core\pipeline\rate_limit_check\stage.py

msg-18092978 = Session{ $session_id }Rate limited. According to the rate limiting policy, this session will be paused.{ $stall_duration }Seconds.
msg-4962387a = Session{ $session_id }Rate limited. According to the rate limiting policy, this request has been discarded until the quota is replenished.{ $stall_duration }Reset in seconds.

### astrbot\core\pipeline\respond\stage.py

msg-59539c6e = Failed to parse the interval time for segmented responses.{ $e }
msg-4ddee754 = Segment response interval:{ $res }
msg-5e2371a9 = Prepare to send -{ $res }/{ $res_2 }:{ $res_3 }
msg-df92ac24 = async_stream is empty, skipping send.
msg-858b0e4f = Application streaming output({ $res })
msg-22c7a672 = Message is empty, skipping the sending phase.
msg-e6ab7a25 = Empty content check exception:{ $e }
msg-b29b99c1 = Actual message chain is empty, skipping the sending phase. header_chain:{ $header_comps }actual_chain:{ $res }
msg-842df577 = Failed to send message chain: chain ={ $res }error ={ $e }
msg-f35465cf = The entire message chain consists of Reply and At message segments, skipping the sending phase. chain:{ $res }
msg-784e8a67 = Failed to send message chain: chain ={ $chain }error ={ $e }

### astrbot\core\pipeline\result_decorate\stage.py

msg-7ec898fd = hook(on_decorating_result) ->{ $res }-{ $res_2 }
msg-5e27dae6 = When enabling streaming output, plugins that rely on pre-send message event hooks may not function properly.
msg-caaaec29 = hook(on_decorating_result) ->{ $res }-{ $res_2 }Clear the message results.
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }Terminated event propagation.
msg-813a44bb = Streaming output enabled, skipping result decoration phase.
msg-891aa43a = Segmented response regular expression error, using default segmentation method:{ $res }
msg-82bb9025 = Session{ $res }Text-to-speech model is not configured.
msg-fb1c757a = TTS Request:{ $res }
msg-06341d25 = TTS Result:{ $audio_path }
msg-2057f670 = TTS audio file not found, message segment conversion to speech failed:{ $res }
msg-f26725cf = Registered:{ $url }
msg-47716aec = TTS failed, sending as text.
msg-ffe054a9 = Text-to-image conversion failed; sending as text.
msg-06c1aedc = Text-to-image conversion took more than 3 seconds. If it feels too slow, you can use /t2i to disable text-to-image mode.

### astrbot\core\pipeline\session_status_check\stage.py

msg-f9aba737 = Session{ $res }Closed; event propagation has been terminated.

### astrbot\core\pipeline\waking_check\stage.py

msg-df815938 = Enabled plugin names:{ $enabled_plugins_name }
msg-51182733 = Plugin{ $res }:{ $e }
msg-e0dcf0b8 = Your ID:{ $res }Insufficient permissions to use this command. Please obtain your ID via /sid and contact the administrator to add permissions.
msg-a3c3706f = Trigger{ $res }When the user (ID={ $res_2 }Insufficient permissions.

### astrbot\core\pipeline\whitelist_check\stage.py

msg-8282c664 = Session ID{ $res }Not in the conversation whitelist; event propagation has been terminated. Please add this session ID to the whitelist in the configuration file.

### astrbot\core\platform\astr_message_event.py

msg-b593f13f = Unable to convert message type{ $res }Rollback to FRIEND_MESSAGE.
msg-98bb33b7 = Clear{ $res }Additional information:{ $res_2 }
msg-0def44e2 = { $result }
msg-8e7dc862 = { $text }

### astrbot\core\platform\manager.py

msg-61bd87ae = Terminating platform adapter failed: client_id={ $client_id }error={ $e }
msg-78b9c276 = { $res }
msg-563a0a74 = Initialization{ $platform }Platform adapter failed:{ $e }
msg-3398495c = Platform ID{ $platform_id }Contains illegal characters ':' or '!', replaced with{ $sanitized_id }.
msg-31361418 = Platform ID{ $platform_id }Cannot be empty; skipping loading of this platform adapter.
msg-e395bbcc = Loading{ $res }({ $res_2 }Platform Adapter ...
msg-b4b29344 = Loading platform adapter{ $res }Failed, reason:{ $e }Please check if the dependency libraries are installed. Tip: You can install dependency libraries in the Admin Panel -> Platform Logs -> Install Pip Libraries.
msg-18f0e1fe = Loading platform adapter{ $res }Failed, reason:{ $e }.
msg-2636a882 = No applicable found for{ $res }({ $res_2 }Platform adapter, please check if it is already installed or if the name is entered incorrectly.
msg-c4a38b85 = hook(on_platform_loaded) ->{ $res }-{ $res_2 }
msg-967606fd = ------- Task{ $res }An error occurred:{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = -------
msg-38723ea8 = Attempting to terminate{ $platform_id }Platform adapter ...
msg-63f684c6 = May not have been completely removed{ $platform_id }Platform Adapter
msg-136a952f = Failed to retrieve platform statistics:{ $e }

### astrbot\core\platform\platform.py

msg-30fc9871 = Platform{ $res }Unified Webhook pattern not implemented

### astrbot\core\platform\register.py

msg-eecf0aa8 = Platform Adapter{ $adapter_name }Already registered, possibly due to an adapter naming conflict.
msg-614a55eb = Platform Adapter{ $adapter_name }Registered
msg-bb06a88d = Platform Adapter{ $res }Cancelled (from module){ $res_2 })

### astrbot\core\platform\sources\aiocqhttp\aiocqhttp_message_event.py

msg-0db8227d = Unable to send message: Missing a valid numeric session_id{ $session_id }) or event({ $event })

### astrbot\core\platform\sources\aiocqhttp\aiocqhttp_platform_adapter.py

msg-859d480d = Failed to process the request message:{ $e }
msg-6fb672e1 = Failed to process notification message:{ $e }
msg-cf4687a3 = Failed to process group message:{ $e }
msg-3a9853e3 = Failed to process private message:{ $e }
msg-ec06dc3d = aiocqhttp (OneBot v11) adapter is connected.
msg-1304a54d = [aiocqhttp] Raw message{ $event }
msg-93cbb9fa = { $err }
msg-a4487a03 = Failed to reply to the message:{ $e }
msg-48bc7bff = Guess Lagrange
msg-6ab145a1 = Failed to retrieve file:{ $ret }
msg-457454d7 = Failed to retrieve file:{ $e }This message segment will be ignored.
msg-7a299806 = Unable to construct Event object from reply message data:{ $reply_event_data }
msg-e6633a51 = Failed to retrieve referenced message:{ $e }.
msg-6e99cb8d = Failed to retrieve user information:{ $e }This message segment will be ignored.
msg-cf15fd40 = Unsupported message segment type, ignored:{ $t }, data={ $res }
msg-45d126ad = Message segment parsing failed: type={ $t }, data={ $res }.{ $e }
msg-394a20ae = aiocqhttp: ws_reverse_host or ws_reverse_port not configured, using default values: http://0.0.0.0:6199
msg-7414707c = The aiocqhttp adapter has been shut down.

### astrbot\core\platform\sources\dingtalk\dingtalk_adapter.py

msg-c81e728d = 2
msg-d6371313 = DingTalk:{ $res }
msg-a1c8b5b1 = DingTalk private chat sessions lack staff_id mapping, falling back to using session_id as the userId for sending.
msg-2abb842f = Failed to save DingTalk session mapping:{ $e }
msg-46988861 = Failed to download DingTalk file:{ $res },{ $res_2 }
msg-ba9e1288 = Failed to obtain access_token via dingtalk_stream:{ $e }
msg-835b1ce6 = Failed to obtain DingTalk robot access_token:{ $res },{ $res_2 }
msg-331fcb1f = Failed to read DingTalk staff_id mapping:{ $e }
msg-ba183a34 = DingTalk group message sending failed: access_token is empty.
msg-b8aaa69b = Failed to send DingTalk group message:{ $res },{ $res_2 }
msg-cfb35bf5 = DingTalk private message sending failed: access_token is empty.
msg-7553c219 = DingTalk private message failed to send:{ $res },{ $res_2 }
msg-5ab2d58d = Failed to clean up temporary files:{ $file_path },{ $e }
msg-c0c40912 = DingTalk voice conversion to OGG failed, falling back to AMR:{ $e }
msg-21c73eca = DingTalk media upload failed: access_token is empty.
msg-24e3054f = DingTalk media upload failed:{ $res },{ $res_2 }
msg-34d0a11d = DingTalk media upload failed:{ $data }
msg-3b0d4fb5 = DingTalk voice message sending failed:{ $e }
msg-7187f424 = DingTalk video failed to send:{ $e }
msg-e40cc45f = DingTalk private chat reply failed: Missing sender_staff_id
msg-be63618a = DingTalk adapter has been disabled.
msg-0ab22b13 = DingTalk robot failed to start:{ $e }

### astrbot\core\platform\sources\dingtalk\dingtalk_event.py

msg-eaa1f3e4 = DingTalk message sending failed: Missing adapter.

### astrbot\core\platform\sources\discord\client.py

msg-940888cb = [Discord] Client failed to load user information correctly (self.user is None)
msg-9a3c1925 = [Discord] Logged in as{ $res }(ID:{ $res_2 }Login
msg-30c1f1c8 = [Discord] Client is ready.
msg-d8c03bdf = [Discord] on_ready_once_callback execution failed:{ $e }
msg-c9601653 = Robot not ready: self.user is None
msg-4b017a7c = No valid user interactions were received.
msg-3067bdce = [Discord] Received raw message from{ $res }:{ $res_2 }

### astrbot\core\platform\sources\discord\discord_platform_adapter.py

msg-7ea23347 = [Discord] Client not ready (self.client.user is None), unable to send message.
msg-ff6611ce = [Discord] Invalid channel ID format:{ $channel_id_str }
msg-5e4e5d63 = [Discord] Unable to retrieve channel information{ $channel_id_str }Guessing the message type.
msg-32d4751b = [Discord] Message received:{ $message_data }
msg-8296c994 = [Discord] Bot Token not configured. Please set the token correctly in the configuration file.
msg-170b31df = [Discord] Login failed. Please check if your Bot Token is correct.
msg-6678fbd3 = [Discord] Connection to Discord has been closed.
msg-cd8c35d2 = [Discord] An unexpected error occurred during adapter runtime:{ $e }
msg-4df30f1d = [Discord] Client not ready (self.client.user is None), unable to process messages.
msg-f7803502 = [Discord] Received a non-Message type message:{ $res }Ignored.
msg-134e70e9 = [Discord] Terminating adapter... (step 1: canceling polling task)
msg-5c01a092 = [Discord] polling_task has been canceled.
msg-77f8ca59 = [Discord] polling_task cancellation exception:{ $e }
msg-528b6618 = [Discord] Cleaning up registered slash commands... (step 2)
msg-d0b832e6 = [Discord] Command cleanup completed.
msg-43383f5e = [Discord] An error occurred while clearing commands:{ $e }
msg-b960ed33 = [Discord] Shutting down Discord client... (step 3)
msg-5e58f8a2 = [Discord] Client closed abnormally:{ $e }
msg-d1271bf1 = [Discord] Adapter terminated.
msg-c374da7a = [Discord] Starting to collect and register slash commands...
msg-a6d37e4d = [Discord] Preparing to sync{ $res }Command:{ $res_2 }
msg-dbcaf095 = [Discord] No registerable commands found.
msg-09209f2f = [Discord] Command synchronization completed.
msg-a95055fd = [Discord] Callback function triggered:{ $cmd_name }
msg-55b13b1e = [Discord] Callback function parameters:{ $ctx }
msg-79f72e4e = [Discord] Callback function parameters:{ $params }
msg-22add467 = [Discord] Slash command '{ $cmd_name }was triggered. Original parameters:{ $params }'. Constructed command string: '{ $message_str_for_filter }'
msg-ccffc74a = [Discord] Command '{ $cmd_name }defer failed:{ $e }
msg-13402a28 = [Discord] Skipping non-compliant instructions:{ $cmd_name }

### astrbot\core\platform\sources\discord\discord_platform_event.py

msg-0056366b = [Discord] Failed to parse message chain:{ $e }
msg-fa0a9e40 = [Discord] Attempted to send an empty message; ignored.
msg-5ccebf9a = [Discord] Channel{ $res }Not a type that can send messages.
msg-1550c1eb = [Discord] An unknown error occurred while sending the message:{ $e }
msg-7857133d = [Discord] Unable to retrieve channel{ $res }
msg-050aa8d6 = [Discord] Starting to process the Image component:{ $i }
msg-57c802ef = [Discord] The Image component does not have a file attribute.{ $i }
msg-f2bea7ac = [Discord] Processing URL Images:{ $file_content }
msg-c3eae1f1 = [Discord] Processing File URI:{ $file_content }
msg-6201da92 = [Discord] Image file does not exist:{ $path }
msg-2a6f0cd4 = [Discord] Processing Base64 URI
msg-b589c643 = [Discord] Attempting to process as raw Base64
msg-41dd4b8f = [Discord] Raw Base64 decoding failed, processing as local path:{ $file_content }
msg-f59778a1 = [Discord] An unknown critical error occurred while processing the image:{ $file_info }
msg-85665612 = [Discord] Failed to retrieve file, path does not exist:{ $file_path_str }
msg-e55956fb = [Discord] Failed to retrieve file:{ $res }
msg-56cc0d48 = [Discord] Failed to process file:{ $res }Error:{ $e }
msg-c0705d4e = [Discord] Unsupported message component ignored:{ $res }
msg-0417d127 = [Discord] Message content exceeds 2000 characters and will be truncated.
msg-6277510f = [Discord] Failed to add reaction:{ $e }

### astrbot\core\platform\sources\lark\lark_adapter.py

msg-06ce76eb = No Feishu bot name is set; @bot may not receive a response.
msg-eefbe737 = [Lark] API Client IM module not initialized
msg-236bcaad = [Lark] Failed to download message resources type={ $resource_type }, key={ $file_key }, code={ $res }, msg={ $res_2 }
msg-ef9a61fe = [Lark] The message resource response does not contain a file stream:{ $file_key }
msg-7b69a8d4 = [Lark] Image message missing message_id
msg-59f1694d = [Lark] Rich text video message is missing a message_id
msg-af8f391d = [Lark] File message missing message_id
msg-d4080b76 = [Lark] File message missing file_key
msg-ab21318a = [Lark] Audio message missing message_id
msg-9ec2c30a = [Lark] Audio message missing file_key
msg-0fa9ed18 = [Lark] Video message missing message_id
msg-ae884c5c = [Lark] Video message missing file_key
msg-dac98a62 = [Lark] Failed to retrieve referenced message id={ $parent_message_id }, code={ $res }, msg={ $res_2 }
msg-7ee9f7dc = [Lark] Quoted message response is empty id={ $parent_message_id }
msg-2b3b2db9 = [Lark] Failed to parse referenced message content id={ $quoted_message_id }
msg-c5d54255 = [Lark] Received empty event (event.event is None)
msg-82f041c4 = [Lark] No message body in the event (message is None)
msg-206c3506 = [Lark] Message content is empty
msg-876aa1d2 = [Lark] Failed to parse message content:{ $res }
msg-514230f3 = [Lark] The message content is not a JSON object.{ $res }
msg-0898cf8b = [Lark] Parsing message content:{ $content_json_b }
msg-6a8bc661 = [Lark] Message is missing message_id
msg-26554571 = [Lark] Sender information is incomplete.
msg-007d863a = [Lark Webhook] Skipping duplicate event:{ $event_id }
msg-6ce17e71 = [Lark Webhook] Unhandled event type:{ $event_type }
msg-8689a644 = [Lark Webhook] Failed to process event:{ $e }
msg-20688453 = [Lark] Webhook mode is enabled, but webhook_server is not initialized.
msg-f46171bc = [Lark] Webhook mode is enabled, but webhook_uuid is not configured.
msg-dd90a367 = Lark adapter is disabled.

### astrbot\core\platform\sources\lark\lark_event.py

msg-eefbe737 = [Lark] API Client IM module not initialized
msg-a21f93fa = [Lark] When actively sending messages, receive_id and receive_id_type cannot be empty.
msg-f456e468 = [Lark] Failed to send Lark message{ $res }):{ $res_2 }
msg-1eb66d14 = [Lark] File does not exist:{ $path }
msg-1df39b24 = [Lark] API Client IM module not initialized, unable to upload files.
msg-2ee721dd = [Lark] Unable to upload file{ $res }):{ $res_2 }
msg-a04abf78 = [Lark] File uploaded successfully but no data returned (data is None)
msg-959e78a4 = [Lark] File upload successful:{ $file_key }
msg-901a2f60 = [Lark] Unable to open or upload file:{ $e }
msg-13065327 = [Lark] Image path is empty, unable to upload.
msg-37245892 = [Lark] Unable to open image file:{ $e }
msg-ad63bf53 = [Lark] The API Client IM module is not initialized; unable to upload images.
msg-ef90038b = Unable to upload Feishu images ({ $res }):{ $res_2 }
msg-d2065832 = [Lark] Image upload succeeded but no data was returned (data is None)
msg-dbb635c2 = { $image_key }
msg-d4810504 = [Lark] File component detected, will be sent separately.
msg-45556717 = [Lark] Audio component detected, will be sent separately.
msg-959070b5 = [Lark] Video component detected, will be sent separately.
msg-4e2aa152 = Feishu currently does not support message segments.{ $res }
msg-20d7c64b = [Lark] Unable to retrieve audio file path:{ $e }
msg-2f6f35e6 = [Lark] Audio file does not exist:{ $original_audio_path }
msg-528b968d = [Lark] Audio format conversion failed; attempting direct upload:{ $e }
msg-fbc7efb9 = [Lark] Deleted the converted audio file:{ $converted_audio_path }
msg-09840299 = [Lark] Failed to delete the converted audio file:{ $e }
msg-e073ff1c = [Lark] Unable to retrieve video file path:{ $e }
msg-47e52913 = [Lark] Video file does not exist:{ $original_video_path }
msg-85ded1eb = [Lark] Video format conversion failed; attempting direct upload:{ $e }
msg-b3bee05d = [Lark] Deleted the converted video file:{ $converted_video_path }
msg-775153f6 = [Lark] Failed to delete the converted video file:{ $e }
msg-45038ba7 = [Lark] API Client IM module not initialized, unable to send emoticons.
msg-8d475b01 = Failed to send Lark emoji reaction.{ $res }):{ $res_2 }

### astrbot\core\platform\sources\lark\server.py

msg-2f3bccf1 = encrypt_key not configured, unable to decrypt event
msg-e77104e2 = [Lark Webhook] Received challenge verification request:{ $challenge }
msg-34b24fa1 = [Lark Webhook] Failed to parse request body:{ $e }
msg-ec0fe13e = [Lark Webhook] Request body is empty
msg-f69ebbdb = [Lark Webhook] Signature verification failed
msg-7ece4036 = [Lark Webhook] Decrypted event:{ $event_data }
msg-f2cb4b46 = [Lark Webhook] Event decryption failed:{ $e }
msg-ef9f8906 = [Lark Webhook] Verification Token mismatch.
msg-bedb2071 = [Lark Webhook] Failed to process event callback:{ $e }

### astrbot\core\platform\sources\line\line_adapter.py

msg-68539775 = The LINE adapter requires a channel_access_token and a channel_secret.
msg-30c67081 = [LINE] webhook_uuid is empty; the unified Webhook may not be able to receive messages.
msg-64e92929 = [LINE] Invalid webhook signature
msg-321afd59 = [LINE] Invalid webhook request body:{ $e }
msg-1079248e = [LINE] Duplicate event skipped:{ $event_id }

### astrbot\core\platform\sources\line\line_api.py

msg-dc6656f8 = [LINE]{ $op_name }Message sending failed: status={ $res }Body={ $body }
msg-10996a43 = [LINE]{ $op_name }Message request failed:{ $e }
msg-5aa92977 = [LINE] Failed to retry content retrieval: message_id={ $message_id }status={ $res }Body={ $body }
msg-cf700d79 = [LINE] Failed to retrieve content: message_id={ $message_id }status={ $res }Body={ $body }

### astrbot\core\platform\sources\line\line_event.py

msg-a491ddd0 = [LINE] Failed to parse image URL:{ $e }
msg-ca47546c = [LINE] Failed to parse record URL:{ $e }
msg-616e5840 = [LINE] Failed to parse record duration:{ $e }
msg-c953a061 = [LINE] Failed to parse video link:{ $e }
msg-19078257 = [LINE] Failed to parse video cover:{ $e }
msg-eccdecff = [LINE] Failed to generate video preview:{ $e }
msg-b833dc32 = [LINE] Failed to parse file URL:{ $e }
msg-60290793 = [LINE] Failed to parse file size:{ $e }
msg-d6443173 = [LINE] The number of messages exceeds 5; any additional messages will be discarded.

### astrbot\core\platform\sources\misskey\misskey_adapter.py

msg-7bacee77 = [Misskey] Configuration incomplete, cannot start.
msg-99cdf3d3 = [Misskey] Connected users:{ $res }(ID:{ $res_2 })
msg-5579c974 = [Misskey] Failed to retrieve user information:{ $e }
msg-d9547102 = [Misskey] API client not initialized
msg-341b0aa0 = [Misskey] WebSocket connected (attempt #{ $connection_attempts })
msg-c77d157b = [Misskey] Chat channel subscribed
msg-a0c5edc0 = [Misskey] WebSocket connection failed (attempt #{ $connection_attempts })
msg-1958faa8 = [Misskey] WebSocket exception (attempt #{ $connection_attempts }):{ $e }
msg-1b47382d = [Misskey]{ $sleep_time }Reconnecting in seconds (next attempt #{ $res })
msg-a10a224d = [Misskey] Notification event received: type={ $notification_type }user_id={ $res }
msg-7f0abf4a = [Misskey] Processing post mentions:{ $res }...
msg-2da7cdf5 = [Misskey] Failed to process notification:{ $e }
msg-6c21d412 = [Misskey] Chat event received: sender_id={ $sender_id }room_id={ $room_id }, is_self={ $res }
msg-68269731 = [Misskey] Checking group chat messages:{ $raw_text }', robot username: '{ $res }'
msg-585aa62b = [Misskey] Processing group chat messages:{ $res }...
msg-426c7874 = [Misskey] Processing direct messages:{ $res }...
msg-f5aff493 = [Misskey] Failed to process chat message:{ $e }
msg-ea465183 = [Misskey] Unhandled event received: type={ $event_type }, channel={ $res }
msg-8b69eb93 = [Misskey] Message content is empty and no file attachments, skipping send.
msg-9ba9c4e5 = [Misskey] Temporary files have been cleaned:{ $local_path }
msg-91af500e = [Misskey] File count limit exceeded ({ $res }>{ $MAX_FILE_UPLOAD_COUNT }), only upload the first{ $MAX_FILE_UPLOAD_COUNT }This file
msg-9746d7f5 = [Misskey] An exception occurred during concurrent upload; continuing to send text.
msg-d6dc928c = [Misskey] Chat messages only support a single file; any additional files are ignored.{ $res }This file
msg-af584ae8 = [Misskey] Parsing visibility: visibility={ $visibility }, visible_user_ids={ $visible_user_ids }session_id={ $session_id }user_id_for_cache={ $user_id_for_cache }
msg-1a176905 = [Misskey] Failed to send message:{ $e }

### astrbot\core\platform\sources\misskey\misskey_api.py

msg-fab20f57 = The Misskey API requires aiohttp and websockets. Please install them using the following command: pip install aiohttp websockets
msg-f2eea8e1 = [Misskey WebSocket] Connected
msg-5efd11a2 = [Misskey WebSocket] Resubscribe{ $channel_type }Failure:{ $e }
msg-b70e2176 = [Misskey WebSocket] Connection failed:{ $e }
msg-b9f3ee06 = [Misskey WebSocket] Connection disconnected
msg-7cd98e54 = WebSocket is not connected
msg-43566304 = [Misskey WebSocket] Unable to parse message:{ $e }
msg-e617e390 = [Misskey WebSocket] Failed to process message:{ $e }
msg-c60715cf = [Misskey WebSocket] Connection unexpectedly closed:{ $e }
msg-da9a2a17 = [Misskey WebSocket] Connection closed (code:{ $res }Reason:{ $res_2 })
msg-bbf6a42e = [Misskey WebSocket] Handshake failed:{ $e }
msg-254f0237 = [Misskey WebSocket] Failed to listen for messages:{ $e }
msg-49f7e90e = { $channel_summary }
msg-630a4832 = [Misskey WebSocket] Channel message:{ $channel_id }Event Type:{ $event_type }
msg-0dc61a4d = [Misskey WebSocket] Using processor:{ $handler_key }
msg-012666fc = [Misskey WebSocket] Using event handlers:{ $event_type }
msg-e202168a = [Misskey WebSocket] Handler not found:{ $handler_key }Or{ $event_type }
msg-a397eef1 = [Misskey WebSocket] Direct Message Handler:{ $message_type }
msg-a5f12225 = [Misskey WebSocket] Unhandled message type:{ $message_type }
msg-ad61d480 = [Misskey API]{ $func_name }Retry{ $max_retries }Subsequent attempts still failed:{ $e }
msg-7de2ca49 = [Misskey API]{ $func_name }First{ $attempt }Second retry failed:{ $e },{ $sleep_time }Retry after s seconds
msg-f5aecf37 = [Misskey API]{ $func_name }Encountered a non-retryable exception:{ $e }
msg-e5852be5 = [Misskey API] Client has been closed.
msg-21fc185c = [Misskey API] Request parameter error:{ $endpoint }(HTTP{ $status })
msg-5b106def = Bad Request{ $endpoint }
msg-28afff67 = [Misskey API] Unauthorized Access:{ $endpoint }(HTTP{ $status })
msg-e12f2d28 = Unauthorized access{ $endpoint }
msg-beda662d = [Misskey API] Access Forbidden:{ $endpoint }(HTTP{ $status })
msg-795ca227 = Access Denied{ $endpoint }
msg-5c6ba873 = [Misskey API] Resource does not exist:{ $endpoint }(HTTP{ $status })
msg-74f2bac2 = Resource not found{ $endpoint }
msg-9ceafe4c = [Misskey API] Request body too large:{ $endpoint }(HTTP{ $status })
msg-3e336b73 = Request Entity Too Large{ $endpoint }
msg-a47067de = [Misskey API] Request Rate Limit:{ $endpoint }(HTTP{ $status })
msg-901dc2da = Request frequency limit exceeded{ $endpoint }
msg-2bea8c2e = [Misskey API] Internal Server Error:{ $endpoint }(HTTP{ $status })
msg-ae8d3725 = Internal Server Error{ $endpoint }
msg-7b028462 = [Misskey API] Gateway Error:{ $endpoint }(HTTP{ $status })
msg-978414ef = Gateway Error{ $endpoint }
msg-50895a69 = [Misskey API] Service Unavailable:{ $endpoint }(HTTP{ $status })
msg-62adff89 = Service unavailable{ $endpoint }
msg-1cf15497 = [Misskey API] Gateway Timeout:{ $endpoint }(HTTP{ $status })
msg-a8a2578d = Gateway timeout{ $endpoint }
msg-c012110a = [Misskey API] Unknown error:{ $endpoint }(HTTP{ $status })
msg-dc96bbb8 = HTTP{ $status }For{ $endpoint }
msg-4c7598b6 = [Misskey API] Retrieved{ $res }A new notification
msg-851a2a54 = [Misskey API] Request successful:{ $endpoint }
msg-5f5609b6 = [Misskey API] Response format error:{ $e }
msg-c8f7bbeb = Invalid JSON response
msg-82748b31 = [Misskey API] Request failed:{ $endpoint }- HTTP{ $res }Response:{ $error_text }
msg-c6de3320 = [Misskey API] Request failed:{ $endpoint }- HTTP{ $res }
msg-affb19a7 = [Misskey API] HTTP Request Error:{ $e }
msg-9f1286b3 = HTTP request failed:{ $e }
msg-44f91be2 = [Misskey API] Post successful:{ $note_id }
msg-fbafd3db = No upload file path provided.
msg-872d8419 = [Misskey API] Local file does not exist:{ $file_path }
msg-37186dea = File not found:{ $file_path }
msg-65ef68e0 = [Misskey API] Local file upload successful:{ $filename }->{ $file_id }
msg-0951db67 = [Misskey API] File upload network error:{ $e }
msg-e3a322f5 = Upload failed:{ $e }
msg-f28772b9 = No MD5 hash value provided for lookup by hash.
msg-25e566ef = [Misskey API] find-by-hash request: md5={ $md5_hash }
msg-a036a942 = [Misskey API] find-by-hash response: Found{ $res }A file
msg-ea3581d5 = [Misskey API] Failed to find file by hash:{ $e }
msg-1d2a84ff = No search name provided
msg-f25e28b4 = [Misskey API] find request: name={ $name }Folder ID={ $folder_id }
msg-cd43861a = [Misskey API] find response: Found{ $res }A file
msg-05cd55ef = [Misskey API] Failed to find file by name:{ $e }
msg-c01052a4 = [Misskey API] List files request: limit={ $limit }Folder ID={ $folder_id }Type={ $type }
msg-7c81620d = [Misskey API] List file response: Found{ $res }a file
msg-a187a089 = [Misskey API] Failed to list files:{ $e }
msg-9e776259 = No available sessions
msg-de18c220 = URL cannot be empty
msg-25b15b61 = [Misskey API] SSL certificate verification download failed:{ $ssl_error }, retry without SSL verification
msg-b6cbeef6 = [Misskey API] Local upload successful:{ $res }
msg-a4a898e2 = [Misskey API] Local upload failed:{ $e }
msg-46b7ea4b = [Misskey API] Chat message sent successfully:{ $message_id }
msg-32f71df4 = [Misskey API] Room message sent successfully:{ $message_id }
msg-7829f3b3 = [Misskey API] Chat message response format anomaly:{ $res }
msg-d74c86a1 = [Misskey API] Mention notification response format anomaly:{ $res }
msg-65ccb697 = Message content cannot be empty: text or media file required.
msg-b6afb123 = [Misskey API] URL media upload successful:{ $res }
msg-4e62bcdc = [Misskey API] URL media upload failed:{ $url }
msg-71cc9d61 = [Misskey API] URL media processing failed{ $url }:{ $e }
msg-75890c2b = [Misskey API] Local file upload successful:{ $res }
msg-024d0ed5 = [Misskey API] Local file upload failed:{ $file_path }
msg-f1fcb5e1 = [Misskey API] Local file processing failed{ $file_path }:{ $e }
msg-1ee80a6b = Unsupported message type:{ $message_type }

### astrbot\core\platform\sources\misskey\misskey_event.py

msg-85cb7d49 = [MisskeyEvent] send method called, message chain contains{ $res }This component
msg-252c2fca = [MisskeyEvent] Checking adapter method: hasattr(self.client, 'send_by_session') ={ $res }
msg-44d7a060 = [MisskeyEvent] Calling the adapter's send_by_session method
msg-b6e08872 = [MisskeyEvent] Content is empty, skipping send.
msg-8cfebc9c = [MisskeyEvent] New post created
msg-ed0d2ed5 = [MisskeyEvent] Send failed:{ $e }

### astrbot\core\platform\sources\qqofficial\qqofficial_message_event.py

msg-28a74d9d = [QQ Official] Skip the FormData patch for botpy.
msg-c0b123f6 = Error sending streaming message:{ $e }
msg-05d6bba5 = [QQOfficial] Unsupported message source type:{ $res }
msg-e5339577 = [QQOfficial] GroupMessage missing group_openid
msg-71275806 = Message sent to C2C:{ $ret }
msg-040e7942 = [QQ Official] Markdown sending was rejected; fallback to content mode for retry.
msg-9000f8f7 = Invalid upload parameters
msg-d72cffe7 = Failed to upload image; response is not a dictionary type:{ $result }
msg-5944a27c = Upload file response format error:{ $result }
msg-1e513ee5 = Upload request error:{ $e }
msg-f1f1733c = Failed to publish C2C message; response is not a dictionary type.{ $result }
msg-9b8f9f70 = Unsupported image file format
msg-24eb302a = Error converting audio format: Audio duration is not greater than 0.
msg-b49e55f9 = Error processing voice:{ $e }
msg-6e716579 = qq_official ignored{ $res }

### astrbot\core\platform\sources\qqofficial\qqofficial_platform_adapter.py

msg-8af45ba1 = QQ Bot Official API Adapter does not support send_by_session.
msg-8ebd1249 = Unknown message type:{ $message_type }
msg-c165744d = QQ Official Bot Interface Adapter has been gracefully shut down.

### astrbot\core\platform\sources\qqofficial_webhook\qo_webhook_adapter.py

msg-6721010c = [QQ Official Webhook] Session without cached msg_id:{ $res }skip send_by_session
msg-296dfcad = [QQ Official Webhook] Unsupported message type sent via session:{ $res }
msg-6fa95bb3 = An exception occurred during the shutdown period of the official QQ Webhook server:{ $exc }
msg-6f83eea0 = QQ Bot Official API Adapter has gracefully shut down.

### astrbot\core\platform\sources\qqofficial_webhook\qo_webhook_server.py

msg-41a3e59d = Logging into the official QQ bot...
msg-66040e15 = Logged into the official QQ bot account:{ $res }
msg-6ed59b60 = Received qq_official_webhook callback:{ $msg }
msg-ad355b59 = { $signed }
msg-4bf0bff8 = _Parser unknown event{ $event }.
msg-cef08b17 = Will be{ $res }:{ $res_2 }Port startup for the QQ official bot webhook adapter.

### astrbot\core\platform\sources\satori\satori_adapter.py

msg-ab7db6d9 = Satori WebSocket connection closed:{ $e }
msg-4ef42cd1 = Satori WebSocket connection failed:{ $e }
msg-b50d159b = Maximum retry attempts reached ({ $max_retries }), stop retrying
msg-89de477c = Satori adapter is connecting to WebSocket:{ $res }
msg-cfa5b059 = Satori Adapter HTTP API Address:{ $res }
msg-d534864b = Invalid WebSocket URL:{ $res }
msg-a110f9f7 = WebSocket URLs must begin with ws:// or wss://.{ $res }
msg-bf43ccb6 = Satori message processing exception:{ $e }
msg-89081a1a = Satori WebSocket connection exception:{ $e }
msg-5c04bfcd = Satori WebSocket closed abnormally:{ $e }
msg-b67bcee0 = WebSocket connection not established
msg-89ea8b76 = WebSocket connection has been closed.
msg-4c8a40e3 = Connection closed while sending IDENTIFY signal:{ $e }
msg-05a6b99d = Failed to send IDENTIFY signaling:{ $e }
msg-c9b1b774 = Satori WebSocket heartbeat transmission failed:{ $e }
msg-61edb4f3 = Heartbeat task anomaly:{ $e }
msg-7db44899 = Satori connection successful - Bot{ $res }platform={ $platform }user_id={ $user_id }user_name={ $user_name }
msg-01564612 = Failed to parse WebSocket message:{ $e }Message content:{ $message }
msg-3a1657ea = Handling WebSocket message exceptions:{ $e }
msg-dc6b459c = Failed to process event:{ $e }
msg-6524f582 = Error occurred while parsing the <quote> tag:{ $e }Error content:{ $content }
msg-3be535c3 = Failed to convert Satori message:{ $e }
msg-be17caf1 = XML parsing failed; using regex extraction:{ $e }
msg-f6f41d74 = Error occurred while extracting <quote> tags:{ $e }
msg-ca6dca7f = Failed to convert quoted message:{ $e }
msg-cd3b067e = Parsing error occurred while parsing Satori elements:{ $e }Error content:{ $content }
msg-03071274 = An unknown error occurred while parsing the Satori element:{ $e }
msg-775cd5c0 = HTTP session not initialized
msg-e354c8d1 = Satori HTTP request exception:{ $e }

### astrbot\core\platform\sources\satori\satori_event.py

msg-c063ab8a = Satori message sending exception:{ $e }
msg-9bc42a8d = Satori message sending failed
msg-dbf77ca2 = Image conversion to base64 failed:{ $e }
msg-8b6100fb = Satori streaming message sending exception:{ $e }
msg-3c16c45c = Voice to base64 conversion failed:{ $e }
msg-66994127 = Video file conversion failed:{ $e }
msg-30943570 = Failed to convert message component:{ $e }
msg-3e8181fc = Failed to convert forwarding node:{ $e }
msg-d626f831 = Failed to convert and forward the message:{ $e }

### astrbot\core\platform\sources\slack\client.py

msg-1d6b68b9 = Slack request signature verification failed
msg-53ef18c3 = Received Slack event:{ $event_data }
msg-58488af6 = Error occurred while processing Slack event:{ $e }
msg-477be979 = Slack Webhook server starting up and listening{ $res }:{ $res_2 }  { $res_3 }...
msg-639fee6c = Slack Webhook server has stopped.
msg-a238d798 = Socket client not initialized
msg-4e6de580 = Error occurred while processing Socket Mode event:{ $e }
msg-5bb71de9 = Slack Socket Mode client is starting up...
msg-f79ed37f = Slack Socket Mode client has stopped.

### astrbot\core\platform\sources\slack\slack_adapter.py

msg-c34657ff = Slack bot_token is required.
msg-64f8a45d = Socket mode requires an app_token.
msg-a2aba1a7 = Webhook mode requires a signing_secret.
msg-40e00bd4 = Failed to send message on Slack:{ $e }
msg-56c1d0a3 = [slack] Original message{ $event }
msg-855510b4 = Unable to download Slack file:{ $res }   { $res_2 }
msg-04ab2fae = Failed to download file:{ $res }
msg-79ed7e65 = Slack authentication test passed. Bot ID:{ $res }
msg-ec27746a = Slack Adapter (Socket Mode) starting up...
msg-34222d3a = Slack adapter (Webhook mode) starting up, now listening.{ $res }:{ $res_2 }  { $res_3 }...
msg-6d8110d2 = Unsupported connection mode:{ $res }Use 'socket' or 'webhook'
msg-d71e7f36 = Slack adapter has been disabled.

### astrbot\core\platform\sources\slack\slack_event.py

msg-b233107c = Slack file upload failed:{ $res }
msg-596945d1 = Slack file upload response:{ $response }

### astrbot\core\platform\sources\telegram\tg_adapter.py

msg-cb53f79a = Telegram base URL:{ $res }
msg-e6b6040f = Telegram Updater not initialized, unable to start polling.
msg-2c4b186e = The Telegram platform adapter is running.
msg-908d0414 = Error occurred while registering command with Telegram:{ $e }
msg-d2dfe45e = Command name '{ $cmd_name }In case of duplicate registration, the definition from the initial registration will be applied:{ $res }'
msg-63bdfab8 = Start command received but no valid conversation detected; skipping /start response.
msg-03a27b01 = Telegram message:{ $res }
msg-e47b4bb4 = Update received but no message attached.
msg-c97401c6 = [Telegram] Received a message with no sender information.
msg-f5c839ee = The Telegram document file path is empty; unable to save the file.{ $file_name }.
msg-dca991a9 = The Telegram video file path is empty; unable to save the file.{ $file_name }.
msg-56fb2950 = Creating media group cache:{ $media_group_id }
msg-0de2d4b5 = Add message to media group{ $media_group_id }Currently available{ $res }Project.
msg-9e5069e9 = Media Group{ $media_group_id }Maximum wait time reached ({ $elapsed }s >={ $res }Processing.
msg-9156b9d6 = The media team has been scheduled.{ $media_group_id }Pending{ $delay }Seconds (already waited{ $elapsed }s)
msg-2849c882 = Media Group{ $media_group_id }Not found in cache
msg-c75b2163 = Media Group{ $media_group_id }Empty
msg-0a3626c1 = Processing media group{ $media_group_id }Total{ $res }Project
msg-2842e389 = The first message in the media group failed to convert.{ $media_group_id }
msg-32fbf7c1 = Added{ $res }Component to Media Group{ $media_group_id }
msg-23bae28a = The Telegram adapter is turned off.
msg-e46e7740 = Error occurred while closing the Telegram adapter:{ $e }

### astrbot\core\platform\sources\telegram\tg_event.py

msg-7757f090 = [Telegram] Failed to send chat action:{ $e }
msg-80b075a3 = User privacy settings prevent receiving voice messages; they have been converted to audio files. To enable voice messages, go to Telegram Settings → Privacy and Security → Voice Messages → Set to "Everyone".
msg-20665ad1 = MarkdownV2 sending failed:{ $e }Use plain text instead.
msg-323cb67c = [Telegram] Failed to add reaction:{ $e }
msg-abe7fc3d = Failed to edit message (streaming-break):{ $e }
msg-f7d40103 = Unsupported message type:{ $res }
msg-d4b50a96 = Failed to edit message (streaming):{ $e }
msg-2701a78f = Failed to send message (streaming):{ $e }
msg-2a8ecebd = Markdown conversion failed, using plain text:{ $e }

### astrbot\core\platform\sources\webchat\webchat_adapter.py

msg-7177ecf8 = [WebChatAdapter] Failed to save pre-capture message:{ $e }
msg-9406158c = WebChatAdapter：{ $res }

### astrbot\core\platform\sources\webchat\webchat_event.py

msg-6b37adcd = webchat ignore:{ $res }

### astrbot\core\platform\sources\webchat\webchat_queue_mgr.py

msg-4af4f885 = Conversation listener started:{ $conversation_id }
msg-10237240 = Error processing message from session{ $conversation_id }:{ $e }

### astrbot\core\platform\sources\wecom\wecom_adapter.py

msg-d4bbf9cb = Verifying request validity:{ $res }
msg-f8694a8a = Request validation successful.
msg-8f4cda74 = Verification of request validity failed, signature is abnormal, please check the configuration.
msg-46d3feb9 = Decryption failed, signature is abnormal, please check the configuration.
msg-4d1dfce4 = Parsing successful:{ $msg }
msg-a98efa4b = Will be{ $res }:{ $res_2 }Port startup WeChat Work adapter.
msg-a616d9ce = Enterprise WeChat customer service mode does not support active sending via send_by_session.
msg-5d01d7b9 = send_by_session failed: Unable to send for session{ $res }Infer agent_id.
msg-3f05613d = Retrieved WeChat customer service list:{ $acc_list }
msg-8fd19bd9 = Failed to retrieve WeChat customer service; open_kfid is empty.
msg-5900d9b6 = Found open_kfid:{ $open_kfid }
msg-391119b8 = Please open the following link and scan the QR code using WeChat to obtain the customer service WeChat account: https://api.cl2wm.cn/api/qrcode/code?text={ $kf_url }
msg-5bdf8f5c = { $e }
msg-93c9125e = Audio conversion failed:{ $e }If ffmpeg is not installed, please install it first.
msg-b2f7d1dc = Unimplemented events:{ $res }
msg-61480a61 = abm:{ $abm }
msg-42431e46 = Unimplemented WeChat Customer Service Message Event:{ $msg }
msg-fbca491d = WeChat Work adapter has been disabled.

### astrbot\core\platform\sources\wecom\wecom_event.py

msg-e164c137 = WeChat customer service message sending method not found.
msg-c114425e = WeChat customer service image upload failed:{ $e }
msg-a90bc15d = WeChat customer service image upload returns:{ $response }
msg-38298880 = WeChat customer service voice upload failed:{ $e }
msg-3aee0caa = WeChat customer service upload voice returns:{ $response }
msg-15e6381b = Failed to delete temporary audio file:{ $e }
msg-a79ae417 = WeChat customer service file upload failed:{ $e }
msg-374455ef = WeChat customer service file upload returns:{ $response }
msg-a2a133e4 = WeChat customer service video upload failed:{ $e }
msg-2732fffd = WeChat customer service video upload returns:{ $response }
msg-60815f02 = The sending logic for this message type has not yet been implemented:{ $res }.
msg-9913aa52 = Failed to upload image on WeCom:{ $e }
msg-9e90ba91 = WeChat Work upload image returns:{ $response }
msg-232af016 = Failed to upload voice message on WeChat Work:{ $e }
msg-e5b8829d = WeChat Work upload voice returns:{ $response }
msg-f68671d7 = Failed to upload file on WeCom:{ $e }
msg-8cdcc397 = WeChat Work file upload returns:{ $response }
msg-4f3e15f5 = Failed to upload video on WeCom:{ $e }
msg-4e9aceea = WeChat Work upload video returns:{ $response }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_adapter.py

msg-bac9a65e = Enterprise WeChat message push webhook configuration is invalid:{ $e }
msg-2102fede = An exception occurred while processing the queue message:{ $e }
msg-d4ea688d = Message type unknown, ignored:{ $message_data }
msg-88aba3b0 = An exception occurred while processing the message:{ $e }
msg-740911ab = Stream has ended, returning end message:{ $stream_id }
msg-9fdbafe9 = Unable to locate the return queue corresponding to the stream ID:{ $stream_id }
msg-7a52ca2b = There are no new messages in the backend queue for the stream ID.{ $stream_id }
msg-9ffb59fb = Aggregated Content:{ $latest_plain_content }Image:{ $res }Completed:{ $finish }
msg-de9ff585 = Stream message sent successfully, stream ID:{ $stream_id }
msg-558310b9 = Message encryption failed
msg-ced70250 = An exception occurred while processing the welcome message:{ $e }
msg-480c5dac = [WecomAI] Message queued:{ $stream_id }
msg-f595dd6e = Failed to process encrypted image:{ $result }
msg-e8beeb3d = WecomAIAdapter:{ $res }
msg-0eedc642 = Failed to send proactive message: Enterprise WeChat message push Webhook URL is not configured. Please go to configure and add it. session_id={ $res }
msg-9934b024 = Enterprise WeChat message push failed (session={ $res }):{ $e }
msg-827fa8d0 = Starting the WeChat Work intelligent robot adapter, listening{ $res }:{ $res_2 }
msg-87616945 = Enterprise WeChat Smart Robot Adapter is shutting down...

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_api.py

msg-86f6ae9f = Message decryption failed, error code:{ $ret }
msg-45ad825c = Decryption successful, message content:{ $message_data }
msg-84c476a7 = JSON parsing failed:{ $e }Original message:{ $decrypted_msg }
msg-c0d8c5f9 = The decrypted message is empty.
msg-a08bcfc7 = Exception occurred during decryption process:{ $e }
msg-4dfaa613 = Message encryption failed, error code:{ $ret }
msg-6e566b12 = Message encryption successful
msg-39bf8dba = Encryption process encountered an exception:{ $e }
msg-fa5be7c5 = URL verification failed, error code:{ $ret }
msg-813a4e4e = URL verification successful
msg-65ce0d23 = URL validation exception occurred:{ $e }
msg-b1aa892f = Starting download of encrypted image:{ $image_url }
msg-10f72727 = { $error_msg }
msg-70123a82 = Image download successful, size:{ $res }Byte
msg-85d2dba1 = AES key cannot be empty.
msg-67c4fcea = Invalid AES key length: must be 32 bytes.
msg-bde4bb57 = Invalid padding length (greater than 32 bytes)
msg-63c22912 = Image decryption successful, decrypted size:{ $res }Byte
msg-6ea489f0 = Text message parsing failed
msg-eb12d147 = Image message parsing failed.
msg-ab1157ff = Stream message parsing failed
msg-e7e945d1 = Mixed message parsing failed
msg-06ada9dd = Event message parsing failed.

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_event.py

msg-e44e77b0 = Image data is empty, skipping.
msg-235f0b46 = Failed to process image message:{ $e }
msg-31b11295 = [WecomAI] Unsupported message component type:{ $res }Skip

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_queue_mgr.py

msg-8be03d44 = [WecomAI] Creating input queue:{ $session_id }
msg-9804296a = [WecomAI] Creating output queue:{ $session_id }
msg-bdf0fb78 = [WecomAI] Remove Output Queue:{ $session_id }
msg-40f6bb7b = [WecomAI] Remove Pending Response:{ $session_id }
msg-fbb807cd = [WecomAI] Mark stream has ended:{ $session_id }
msg-9d7f5627 = [WecomAI] Remove from input queue:{ $session_id }
msg-7637ed00 = [WecomAI] Set pending response:{ $session_id }
msg-5329c49b = [WecomAI] Cleaning up expired responses and queues:{ $session_id }
msg-09f098ea = [WecomAI] Starting listener for session:{ $session_id }
msg-c55856d6 = Processing session{ $session_id }Error occurred while sending message:{ $e }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_server.py

msg-adaee66c = URL validation parameter is missing.
msg-742e0b43 = Received a verification request for the WeChat Work smart bot WebHook URL.
msg-f86c030c = Message callback parameters are missing.
msg-cce4e44c = Message callback received, msg_signature={ $msg_signature }timestamp={ $timestamp }nonce={ $nonce }
msg-16a7bfed = Message decryption failed, error code:{ $ret_code }
msg-a567f8e3 = Message handler execution exception:{ $e }
msg-88aba3b0 = An exception occurred while processing the message:{ $e }
msg-1cccaaf4 = Starting the WeChat Work intelligent robot server and listening.{ $res }:{ $res_2 }
msg-866d0b8b = Server operation exception:{ $e }
msg-3269840c = Enterprise WeChat Intelligent Robot Server is shutting down...

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_utils.py

msg-14d01778 = JSON parsing failed:{ $e }Original string:{ $json_str }
msg-b1aa892f = Starting download of encrypted image:{ $image_url }
msg-70123a82 = Image download successful, size:{ $res }Byte
msg-10f72727 = { $error_msg }
msg-1d91d2bb = AES key cannot be empty.
msg-bb32bedd = Invalid AES key length: must be 32 bytes.
msg-bde4bb57 = Invalid padding length (greater than 32 bytes)
msg-63c22912 = Image decryption successful, decrypted size:{ $res }Byte
msg-6886076b = Image has been converted to base64 encoding, encoded length:{ $res }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_webhook.py

msg-a5c90267 = Message push webhook URL cannot be empty.
msg-76bfb25b = Message push webhook URL is missing the key parameter.
msg-3545eb07 = Webhook request failed: HTTP{ $res },{ $text }
msg-758dfe0d = Webhook returned an error:{ $res } { $res_2 }
msg-ad952ebe = Enterprise WeChat message push successful:{ $res }
msg-73d3e179 = File does not exist:{ $file_path }
msg-774a1821 = Failed to upload media: HTTP{ $res },{ $text }
msg-6ff016a4 = Failed to upload media:{ $res } { $res_2 }
msg-0e8252d1 = Failed to upload media: Returned missing media_id
msg-4f5f40e1 = File message missing a valid file path, skipped:{ $component }
msg-2c9fe93d = Failed to clean up temporary audio files.{ $target_voice_path }:{ $e }
msg-98d2b67a = Enterprise WeChat message push does not currently support component types.{ $res }Skipped

### astrbot\core\platform\sources\wecom_ai_bot\WXBizJsonMsgCrypt.py

msg-5bdf8f5c = { $e }
msg-fe69e232 = Received ID does not match.
msg-00b71c27 = Signature mismatch
msg-5cfb5c20 = { $signature }

### astrbot\core\platform\sources\weixin_official_account\weixin_offacc_adapter.py

msg-d4bbf9cb = Verifying request validity:{ $res }
msg-b2edb1b2 = Unknown response, please check if the callback address is entered correctly.
msg-f8694a8a = Request validation successful.
msg-8f4cda74 = Verification of request validity failed, signature is abnormal, please check the configuration.
msg-46d3feb9 = Decryption failed, signature is abnormal, please check the configuration.
msg-e23d8bff = Parsing failed. The message is None.
msg-4d1dfce4 = Parsing successful:{ $msg }
msg-193d9d7a = User message buffer status: user={ $from_user }status={ $state }
msg-57a3c1b2 = wx buffer hit on trigger: user={ $from_user }
msg-bed995d9 = Retry window triggered WeChat buffer hit: user={ $from_user }
msg-3a94b6ab = wx passive window message sending completed: user={ $from_user }Message ID={ $msg_id }
msg-50c4b253 = wx completed message sending in the passive window but not in the final state: user={ $from_user }Message ID={ $msg_id }
msg-7d8b62e7 = wx completed in the window but not in final state; return placeholder: user={ $from_user }Message ID={ $msg_id }
msg-2b9b8aed = wx task execution failed in the passive window.
msg-7bdf4941 = wx Passive Window Timeout: User={ $from_user }Message ID={ $msg_id }
msg-98489949 = When wx triggers reflection: user={ $from_user }
msg-01d0bbeb = wx new trigger: user={ $from_user }Message ID={ $msg_id }
msg-52bb36cd = wx start task: user={ $from_user }Message ID={ $msg_id }Preview={ $preview }
msg-ec9fd2ed = wx buffer immediate hit: user={ $from_user }
msg-61c91fb9 = wx not completed in the first window; returning placeholder: user={ $from_user }Message ID={ $msg_id }
msg-35604bba = The wx task failed to execute in the first window.
msg-e56c4a28 = WeChat initial window timeout: user={ $from_user }Message ID={ $msg_id }
msg-e163be40 = Will be{ $res }:{ $res_2 }Start the WeChat public platform adapter on the port.
msg-c1740a04 = Duplicate message ID verified:{ $res }
msg-04718b37 = Future results have been obtained:{ $result }
msg-296e66c1 = Callback processing message timeout: message_id={ $res }
msg-eb718c92 = Exception occurred while converting message:{ $e }
msg-93c9125e = Audio conversion failed:{ $e }If ffmpeg is not installed, please install it first.
msg-b2f7d1dc = Unimplemented events:{ $res }
msg-61480a61 = abm:{ $abm }
msg-2e7e0187 = User message buffer state not found, unable to process message: user={ $res }message_id={ $res_2 }
msg-84312903 = WeChat Official Account Platform adapter has been disabled.

### astrbot\core\platform\sources\weixin_official_account\weixin_offacc_event.py

msg-fa7f7afc = Split plain text into{ $res }Passive reply chunking. Message not sent.
msg-59231e07 = WeChat Official Account Platform image upload failed:{ $e }
msg-d3968fc5 = WeChat Official Account Platform image upload returns:{ $response }
msg-7834b934 = WeChat Official Account Platform failed to upload voice:{ $e }
msg-4901d769 = WeChat Official Account Platform upload voice interface returns:{ $response }
msg-15e6381b = Failed to delete temporary audio file:{ $e }
msg-60815f02 = The sending logic for this message type has not been implemented yet.{ $res }.

### astrbot\core\provider\entities.py

msg-7fc6f623 = Image{ $image_url }The result obtained is empty and will be ignored.

### astrbot\core\provider\func_tool_manager.py

msg-0c42a4d9 = Add function call tool:{ $name }
msg-e8fdbb8c = MCP service configuration file not found; default configuration file has been created.{ $mcp_json_file }
msg-cf8aed84 = Received MCP client{ $name }Termination signal
msg-3d7bcc64 = Initializing MCP client{ $name }Failure
msg-1b190842 = MCP Server{ $name }List Tool responses:{ $tools_res }
msg-6dc4f652 = Connected to MCP service{ $name }Tools:{ $tool_names }
msg-a44aa4f2 = Clear MCP Client Resources{ $name }:{ $e }.
msg-e9c96c53 = MCP service has been closed.{ $name }
msg-10f72727 = { $error_msg }
msg-85f156e0 = Testing MCP server connection with configuration:{ $config }
msg-93c54ce0 = Clean up residual files after MCP client test connection.
msg-368450ee = This function call belongs to the Tool's plugin.{ $res }Disabled, please enable it in the admin panel before activating this Tool.
msg-4ffa2135 = Failed to load MCP configuration:{ $e }
msg-a486ac39 = Failed to save MCP configuration:{ $e }
msg-58dfdfe7 = Synchronized from ModelScope{ $synced_count }An MCP server
msg-75f1222f = No available ModelScope MCP server found.
msg-c9f6cb1d = ModelScope API request failed: HTTP{ $res }
msg-c8ebb4f7 = Network connection error:{ $e }
msg-0ac6970f = Error occurred while synchronizing the ModelScope MCP server:{ $e }

### astrbot\core\provider\manager.py

msg-9e1a7f1f = Provider{ $provider_id }Does not exist, cannot be set.
msg-5fda2049 = Unknown provider type:{ $provider_type }
msg-a5cb19c6 = ID not found.{ $provider_id }This may be due to your modification of the provider (model) ID.
msg-78b9c276 = { $res }
msg-5bdf8f5c = { $e }
msg-b734a1f4 = Provider{ $provider_id }Configuration item key{ $idx }Using environment variables{ $env_key }But not configured.
msg-664b3329 = Provider{ $res }Disabled, skipping
msg-f43f8022 = Loading{ $res }({ $res_2 }Service Provider ...
msg-edd4aefe = Loading{ $res }({ $res_2 }Provider adapter failed:{ $e }Possibly due to missing dependencies.
msg-78e514a1 = Loading{ $res }({ $res_2 }Provider adapter failure:{ $e }Cause unknown
msg-4636f83c = No applicable{ $res }({ $res_2 }) provider adapter, please check if it is already installed or if the name is entered incorrectly. Skipped.
msg-e9c6c4a2 = Not found{ $res }Class
msg-f705cf50 = Provider Class{ $cls_type }Not a subclass of an STT provider.
msg-d20620aa = Selected{ $res }({ $res_2 }As the current speech-to-text provider adapter.
msg-afbe5661 = Provider Class{ $cls_type }Not a subclass of a TTS provider.
msg-74d437ed = Selected{ $res }({ $res_2 }As the current text-to-speech provider adapter.
msg-08cd85c9 = Provider Class{ $cls_type }Not a subclass of the provider
msg-16a2b8e0 = Selected{ $res }({ $res_2 }As the current provider adapter.
msg-0e1707e7 = Provider Class{ $cls_type }Not a subclass of the Embedding provider.
msg-821d06e0 = Provider Class{ $cls_type }Not a subclass of the Rerank provider.
msg-14c35664 = Unknown provider type:{ $res }
msg-186fd5c6 = Instantiation{ $res }({ $res_2 }Provider adapter failure:{ $e }
msg-ede02a99 = Provider in user configuration:{ $config_ids }
msg-95dc4227 = Auto-select{ $res }As the current provider adapter.
msg-a6187bac = Auto-select{ $res }As the current speech-to-text provider adapter.
msg-bf28f7e2 = Auto-select{ $res }As the current text-to-speech provider adapter.
msg-dba10c27 = Terminate{ $provider_id }Provider Adapter{ $res },{ $res_2 },{ $res_3 }...
msg-9d9d9765 = { $provider_id }Provider adapter has terminated.{ $res },{ $res_2 },{ $res_3 })
msg-925bb70a = Provider{ $target_prov_ids }Removed from the configuration.
msg-a1657092 = New provider configuration must include an 'id' field.
msg-1486c653 = Provider ID{ $npid }Already exists
msg-f9fc1545 = Provider ID{ $origin_provider_id }Not found
msg-4e2c657c = Error occurred while disabling the MCP server.

### astrbot\core\provider\provider.py

msg-e6f0c96f = Program Type{ $provider_type_name }Not registered
msg-c7953e3f = Batch{ $batch_idx }Processing failed, retry attempted.{ $max_retries }Next:{ $e }
msg-10f72727 = { $error_msg }
msg-7ff71721 = Reordering provider test failed; no results were returned.

### astrbot\core\provider\register.py

msg-19ddffc0 = Large model provider adapter detected.{ $provider_type_name }Registered; a naming conflict may have occurred with the adapter type of the large model provider.
msg-7e134b0d = Service Provider{ $provider_type_name }Registered

### astrbot\core\provider\sources\anthropic_source.py

msg-d6b1df6e = Unable to parse image data URI:{ $res }...
msg-6c2c0426 = Unsupported image URL format by Anthropic:{ $res }...
msg-999f7680 = Completed:{ $completion }
msg-8d2c43ec = The API returned an empty completion.
msg-26140afc = Anthropic API returned a completion that cannot be parsed:{ $completion }.
msg-8e4c8c24 = Tool call parameter JSON parsing failed:{ $tool_info }
msg-7fc6f623 = Image{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = Unsupported additional content block type:{ $res }

### astrbot\core\provider\sources\azure_tts_source.py

msg-93d9b5cf = [Azure TTS] Using proxy:{ $res }
msg-9eea5bcb = Client not initialized. Please use the 'async with' context.
msg-fd53d21d = Time synchronization failed
msg-77890ac4 = OTTS request failed:{ $e }
msg-c6ec6ec7 = OTTS did not return an audio file.
msg-5ad71900 = Invalid Azure subscription key
msg-6416da27 = [Azure TTS Native] Using proxy:{ $res }
msg-90b31925 = Missing OTTS parameters:{ $res }
msg-10f72727 = { $error_msg }
msg-60b044ea = Configuration Error: Missing Required Parameters{ $e }
msg-5c7dee08 = Subscription key format is invalid; it should be a 32-character alphanumeric or other[...] format.

### astrbot\core\provider\sources\bailian_rerank_source.py

msg-dc1a9e6e = Alibaba Cloud Bailian API Key cannot be empty.
msg-f7079f37 = AstrBot Hundred Refinements Rerank initialization completed. Model:{ $res }
msg-5b6d35ce = Bailian API Error:{ $res }–{ $res_2 }
msg-d600c5e2 = Bailian Rerank returns empty results.{ $data }
msg-d3312319 = Result{ $idx }Missing relevance_score, using default value 0.0
msg-2855fb44 = Parsing result{ $idx }Error occurred at:{ $e }, result={ $result }
msg-392f26e8 = Bailian Rerank Token Consumption:{ $tokens }
msg-595e0cf9 = The Hundred Refinements Rerank client session has been closed, returning empty results.
msg-d0388210 = The document list is empty, returning an empty result.
msg-44d6cc76 = Query text is empty, returning empty results.
msg-bd8b942a = Number of documents ({ $res }Exceeds limit (500), truncating the first 500 documents.
msg-0dc3bca4 = Bailian Rerank Request: query='{ $res }...', document_count={ $res_2 }
msg-4a9f4ee3 = Bailian Rerank returned successfully.{ $res }This result
msg-fa301307 = Bailian Rerank network request failed:{ $e }
msg-10f72727 = { $error_msg }
msg-9879e226 = Bailian Rerank processing failed:{ $e }
msg-4f15074c = Close the Bailian Rerank client session.
msg-d01b1b0f = Error occurred while closing the Baichuan Rerank client:{ $e }

### astrbot\core\provider\sources\dashscope_tts.py

msg-f23d2372 = Dashscope TTS model is not configured.
msg-74a7cc0a = Audio synthesis failed; the returned content is empty. This may be due to an unsupported model or service unavailability.
msg-bc8619d3 = The dashscope SDK is missing the MultiModalConversation module. Please upgrade the dashscope package to use the Qwen TTS model.
msg-95bbf71e = No voice specified for the Qwen TTS model; using the default voice 'Cherry'.
msg-3c35d2d0 = Audio synthesis for the model failed{ $model }'.'{ $response }
msg-16dc3b00 = Unable to decode base64 audio data.
msg-26603085 = Unable to download audio from the URL.{ $url }:{ $e }
msg-78b9c276 = { $res }

### astrbot\core\provider\sources\edge_tts_source.py

msg-f4ab0713 = pyffmpeg conversion failed:{ $e }, try using the ffmpeg command line for conversion.
msg-ddc3594a = [EdgeTTS] FFmpeg standard output:{ $res }
msg-1b8c0a83 = FFmpeg error output:{ $res }
msg-1e980a68 = [EdgeTTS] Return value (0 indicates success):{ $res }
msg-c39d210c = The generated WAV file does not exist or is empty.
msg-57f60837 = FFmpeg conversion failed:{ $res }
msg-ca94a42a = FFmpeg conversion failed:{ $e }
msg-be660d63 = Audio generation failed:{ $e }

### astrbot\core\provider\sources\fishaudio_tts_api_source.py

msg-c785baf0 = [FishAudio TTS] Using proxy:{ $res }
msg-822bce1c = Invalid FishAudio reference model ID: '{ $res }Please ensure the ID is a 32-digit hexadecimal string (e.g., 626bb6d3f3364c9cbc3aa6a67300a664). You can obtain valid model IDs from https://fish.audio/zh-CN/discovery.
msg-5956263b = Fish Audio API request failed: Status code{ $res }Response content:{ $error_text }

### astrbot\core\provider\sources\gemini_embedding_source.py

msg-173efb0e = [Gemini Embedding] Using proxy:{ $proxy }
msg-58a99789 = Gemini Embedding API request failed:{ $res }
msg-5c4ea38e = Gemini Embedding API batch request failed:{ $res }

### astrbot\core\provider\sources\gemini_source.py

msg-1474947f = [Gemini] Using a proxy:{ $proxy }
msg-e2a81024 = Key anomaly detected({ $res }), attempting to change the API key and retry... Current Key:{ $res_2 }...
msg-0d388dae = Key anomaly detected ({ $res }), and there are no available keys left. Current Key:{ $res_2 }...
msg-1465290c = Rate limit reached for Gemini, please try again later...
msg-7e9c01ca = Streaming output does not support image modality; it has been automatically downgraded to text modality.
msg-89bac423 = The code execution tool and the search tool are mutually exclusive; the search tool has been ignored.
msg-301cf76e = Code execution tool and URL context tool are mutually exclusive; the URL context tool has been ignored.
msg-356e7b28 = The current SDK version does not support URL context tools; this setting has been ignored. Please upgrade the google-genai package.
msg-7d4e7d48 = gemini-2.0-lite does not support code execution, search tools, or URL context; these settings will be ignored.
msg-cc5c666f = Native tools have been enabled; function tools will be ignored.
msg-aa7c77a5 = Invalid thinking level:{ $thinking_level }Use HIGH
msg-59e1e769 = The text content is empty; a space placeholder has been added.
msg-34c5c910 = Unable to decode Google Gemini thought signature:{ $e }
msg-a2357584 = The message content for the assistant role is empty; a space placeholder has been added.
msg-f627f75d = Gemini native tools are enabled, and function calls are present in the context. It is recommended to use /reset to reset the context.
msg-cb743183 = The received candidate.content is empty:{ $candidate }
msg-34b367fc = The candidate.content returned by the API is empty.
msg-73541852 = Model-generated content failed the safety check on the Gemini platform.
msg-ae3cdcea = Model-generated content violates the Gemini platform policy.
msg-5d8f1711 = The received candidate.content.parts is empty:{ $candidate }
msg-57847bd5 = The candidate.content.parts returned by the API are empty.
msg-a56c85e4 = genai result:{ $result }
msg-42fc0767 = Request failed, the returned candidates are empty:{ $result }
msg-faf3a0dd = Request failed; the returned candidates are empty.
msg-cd690916 = The temperature parameter has exceeded the maximum value of 2, yet recitation still occurs.
msg-632e23d7 = A recitation has occurred; temperature is being increased to{ $temperature }Retry...
msg-41ff84bc = { $model }System prompt not supported, automatically removed (affects personality settings).
msg-ef9512f7 = { $model }Function calls are not supported and have been automatically removed.
msg-fde41b1d = { $model }Multimodal output is not supported; downgrading to text modality.
msg-4e168d67 = The received chunk contains empty candidates:{ $chunk }
msg-11af7d46 = The received chunk has empty content:{ $chunk }
msg-8836d4a2 = Request failed.
msg-757d3828 = Failed to retrieve model list:{ $res }
msg-7fc6f623 = Image{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = Unsupported additional content block type:{ $res }

### astrbot\core\provider\sources\gemini_tts_source.py

msg-29fe386a = [Gemini TTS] Using a proxy:{ $proxy }
msg-012edfe1 = Gemini TTS API did not return audio content.

### astrbot\core\provider\sources\genie_tts.py

msg-583dd8a6 = Please install genie_tts first.
msg-935222b4 = Unable to load character{ $res }:{ $e }
msg-a6886f9e = Genie TTS was not saved to a file.
msg-e3587d60 = Genie TTS generation failed:{ $e }
msg-3303e3a8 = Genie TTS is unable to generate audio for the following content:{ $text }
msg-1cfe1af1 = Genie TTS Stream Error:{ $e }

### astrbot\core\provider\sources\gsvi_tts_source.py

msg-520e410f = GSVI TTS API request failed with status code:{ $res }Error:{ $error_text }

### astrbot\core\provider\sources\gsv_selfhosted_source.py

msg-5fb63f61 = [GSV TTS] Initialization complete
msg-e0c38c5b = [GSV TTS] Initialization failed:{ $e }
msg-4d57bc4f = [GSV TTS] Provider HTTP session is not ready or has been closed.
msg-2a4a0819 = [GSV TTS] Request URL:{ $endpoint }Parameters:{ $params }
msg-5fdee1da = [GSV TTS] Sent to{ $endpoint }Request failed, status code{ $res }:{ $error_text }
msg-3a51c2c5 = [GSV TTS] Request{ $endpoint }First{ $res }Failure:{ $e }Retrying...
msg-49c1c17a = [GSV TTS] Request{ $endpoint }Final failure:{ $e }
msg-1beb6249 = [GSV TTS] Successfully set GPT model path:{ $res }
msg-17f1a087 = [GSV TTS] GPT model path not configured, will use built-in GPT model
msg-ddeb915f = [GSV TTS] Successfully set SoVITS model path:{ $res }
msg-bee5c961 = [GSV TTS] SoVITS model path not configured; will use the built-in SoVITS model.
msg-423edb93 = [GSV TTS] A network error occurred while setting the model path:{ $e }
msg-7d3c79cb = [GSV TTS] An unknown error occurred while setting the model path:{ $e }
msg-d084916a = [GSV TTS] TTS text cannot be empty
msg-fa20c883 = [GSV TTS] Calling the speech synthesis interface with parameters:{ $params }
msg-a7fc38eb = [GSV TTS] Synthesis failed, input text:{ $text }Error message:{ $result }
msg-a49cb96b = [GSV TTS] Session closed

### astrbot\core\provider\sources\minimax_tts_api_source.py

msg-77c88c8a = Failed to parse JSON data from SSE message.
msg-7873b87b = MiniMax TTS API request failed:{ $e }

### astrbot\core\provider\sources\openai_embedding_source.py

msg-cecb2fbc = [OpenAI Embedding] Using proxy:{ $proxy }

### astrbot\core\provider\sources\openai_source.py

msg-c891237f = Image request failed ({ $reason }Image removed and retry attempted (text content preserved).
msg-d6f6a3c2 = Failed to retrieve model list:{ $e }
msg-1f850e09 = API returned an incorrect completion type:{ $res }:{ $completion }.
msg-999f7680 = Completed:{ $completion }
msg-844635f7 = Unexpected dictionary format content:{ $raw_content }
msg-8d2c43ec = The API returned an empty completion.
msg-87d75331 = { $completion_text }
msg-0614efaf = Toolset not provided.
msg-c46f067a = The API returned completion was rejected due to content security filtering (not AstrBot).
msg-647f0002 = Unable to parse the completion returned by the API:{ $completion }.
msg-5cc50a15 = API calls are too frequent; try using another key to retry. Current Key:{ $res }
msg-c4e639eb = Context length exceeds limit. Attempting to pop the earliest record and retry. Current record count:{ $res }
msg-5f8be4fb = { $res }Function tool calls are not supported and have been automatically removed, with no impact on usage.
msg-45591836 = It appears that this model does not support function call tool invocation. Please enter /tool off_all
msg-6e47d22a = API call failed, retrying{ $max_retries }This attempt still failed.
msg-974e7484 = Unknown error
msg-7fc6f623 = Image{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = Unsupported additional content block type:{ $res }

### astrbot\core\provider\sources\openai_tts_api_source.py

msg-d7084760 = [OpenAI TTS] Using a proxy:{ $proxy }

### astrbot\core\provider\sources\sensevoice_selfhosted_source.py

msg-ee0daf96 = Downloading or loading the SenseVoice model may take some time...
msg-cd6da7e9 = SenseVoice model loaded.
msg-28cbbf07 = File does not exist:{ $audio_url }
msg-d98780e5 = Converting silk file to wav...
msg-4e8f1d05 = Copy recognized by SenseVoice:{ $res }
msg-55668aa2 = Failed to extract emotional information.
msg-0cdbac9b = Error processing audio file:{ $e }

### astrbot\core\provider\sources\vllm_rerank_source.py

msg-6f160342 = Rerank API returned empty list data. Original response:{ $response_data }

### astrbot\core\provider\sources\volcengine_tts.py

msg-4b55f021 = Request header:{ $headers }
msg-d252d96d = Request URL:{ $res }
msg-72e07cfd = Request body:{ $res }...
msg-fb8cdd69 = Response status code:{ $res }
msg-4c62e457 = Response content:{ $res }...
msg-1477973b = Volcano Engine TTS API returned an error:{ $error_msg }
msg-75401c15 = Volcano Engine TTS API request failed:{ $res },{ $response_text }
msg-a29cc73d = Volcano Engine TTS Exception Details:{ $error_details }
msg-01433007 = Volcano Engine TTS Exception:{ $e }

### astrbot\core\provider\sources\whisper_api_source.py

msg-28cbbf07 = File does not exist:{ $audio_url }
msg-b335b8db = Currently using tencent_silk_to_wav to convert silk files to wav...
msg-68b5660f = Converting AMR files to WAV using convert_to_pcm_wav...
msg-cad3735e = Unable to delete temporary files.{ $audio_url }:{ $e }

### astrbot\core\provider\sources\whisper_selfhosted_source.py

msg-27fda50a = Downloading or loading the Whisper model may take some time...
msg-4e70f563 = Whisper model loaded.
msg-28cbbf07 = File does not exist:{ $audio_url }
msg-d98780e5 = Converting silk file to wav...
msg-e3e1215c = Whisper model is not initialized.

### astrbot\core\provider\sources\xinference_rerank_source.py

msg-1ec1e6e4 = Xinference Reordering: Authenticate using API keys.
msg-7bcb6e1b = Xinference Rerank: No API key provided.
msg-b0d1e564 = Model{ $res }' is already running, user ID:{ $uid }
msg-16965859 = Starting up{ $res }Model...
msg-7b1dfdd3 = Model started.
msg-3fc7310e = Model{ $res }Not running with auto-start disabled. The provider will be unavailable.
msg-15f19a42 = Failed to initialize the Xinference model:{ $e }
msg-01af1651 = Xinference initialization failed, exception details:{ $e }
msg-2607cc7a = Xinference reranking model is not initialized.
msg-3d28173b = Reordering API Response:{ $response }
msg-4c63e1bd = Rerank API returned an empty list. Original response:{ $response }
msg-cac71506 = Xinference reranking failed:{ $e }
msg-4135cf72 = Xinference reranking failed, exception message:{ $e }
msg-ea2b36d0 = Shutting down the Xinference reranking client...
msg-633a269f = Unable to close the Xinference client:{ $e }

### astrbot\core\provider\sources\xinference_stt_provider.py

msg-4e31e089 = Xinference STT: Authenticating with API key.
msg-e291704e = Xinference STT: API key not provided.
msg-b0d1e564 = Model{ $res }' is already running, user ID:{ $uid }
msg-16965859 = Starting up{ $res }Model...
msg-7b1dfdd3 = Model started.
msg-3fc7310e = Model{ $res }Not running with auto-start disabled. The provider will be unavailable.
msg-15f19a42 = Failed to initialize the Xinference model:{ $e }
msg-01af1651 = Xinference initialization failed, error details:{ $e }
msg-42ed8558 = Xinference STT model is not initialized.
msg-bbc43272 = Unable to download audio.{ $audio_url }Status:{ $res }
msg-f4e53d3d = File not found:{ $audio_url }
msg-ebab7cac = Audio bytes are empty.
msg-7fd63838 = Audio conversion required ({ $conversion_type }Using temporary files...
msg-d03c4ede = Converting silk format to wav format...
msg-79486689 = Converting AMR to WAV...
msg-c4305a5b = Xinference Speech-to-Text Result:{ $text }
msg-d4241bd5 = Xinference STT transcription failed with status{ $res }:{ $error_text }
msg-8efe4ef1 = Xinference speech-to-text conversion failed:{ $e }
msg-b1554c7c = Xinference STT failed, exception information:{ $e }
msg-9d33941a = Temporary files have been removed.{ $temp_file }
msg-7dc5bc44 = Unable to delete temporary files.{ $temp_file }:{ $e }
msg-31904a1c = Shutting down the Xinference STT client...
msg-633a269f = Unable to close the Xinference client:{ $e }

### astrbot\core\skills\skill_manager.py

msg-ed9670ad = Compressed file not found:{ $zip_path }
msg-73f9cf65 = The uploaded file is not a valid ZIP archive.
msg-69eb5f95 = The compressed archive is empty.
msg-9e9abb4c = { $top_dirs }
msg-20b8533f = The ZIP archive must contain a top-level folder.
msg-1db1caf7 = Invalid skill folder name.
msg-d7814054 = The archive contains absolute paths.
msg-179bd10e = The compressed archive contains invalid relative paths.
msg-90f2904e = The archive contains unexpected top-level entries.
msg-95775a4d = No SKILL.md file found in the skill folder.
msg-a4117c0b = No skill folder found after extraction.
msg-94041ef2 = Skill already exists.

### astrbot\core\star\base.py

msg-57019272 = Failed to retrieve configuration:{ $e }

### astrbot\core\star\command_management.py

msg-011581bb = The specified handler does not exist or is not a command.
msg-a0c37004 = Command name cannot be empty.
msg-ae8b2307 = Command name '{ $candidate_full }' is already occupied by another command.
msg-247926a7 = Alias{ $alias_full }' is already occupied by another command.
msg-dbd19a23 = Permission type must be admin or member.
msg-9388ea1e = The plugin to which the instruction belongs was not found.
msg-0dd9b70d = Instruction parsing and processing function{ $res }Failed, skipping this instruction. Reason:{ $e }

### astrbot\core\star\config.py

msg-c2189e8d = namespace cannot be empty.
msg-97f66907 = Namespace cannot start with internal_.
msg-09179604 = key only supports the str type.
msg-1163e4f1 = value only supports str, int, float, bool, and list types.
msg-ed0f93e4 = Configuration file{ $namespace }.json does not exist.
msg-e3b5cdfb = Configuration Item{ $key }It does not exist.

### astrbot\core\star\context.py

msg-60eb9e43 = Provider{ $chat_provider_id }Not found
msg-da70a6fb = Agent did not generate the final LLM response.
msg-141151fe = Provider not found
msg-a5cb19c6 = ID not found.{ $provider_id }This may be due to your modification of the provider (model) ID.
msg-2a44300b = The dialogue model (provider) type for this conversation source is incorrect:{ $res }
msg-37c286ea = The returned provider is not a TTS provider type.
msg-ff775f3b = The returned provider is not an STT provider type.
msg-fd8c8295 = Unable to locate the session platform.{ $res }Message not sent
msg-2b806a28 = Plugin (Module Path){ $module_path }LLMTool has been added:{ $res }

### astrbot\core\star\session_llm_manager.py

msg-7b90d0e9 = Session{ $session_id }The TTS status has been updated to:{ $res }

### astrbot\core\star\session_plugin_manager.py

msg-16cc2a7a = Plugin{ $res }In the session{ $session_id }Disabled in the middle, skipping the processor{ $res_2 }

### astrbot\core\star\star_manager.py

msg-bfa28c02 = watchfiles is not installed, so hot reloading for plugins cannot be implemented.
msg-f8e1c445 = Plugin hot reload monitoring task exception:{ $e }
msg-78b9c276 = { $res }
msg-28aeca68 = File change detected:{ $changes }
msg-aeec7738 = Plugin detected{ $plugin_name }File changed, reloading...
msg-4f989555 = Plugin{ $d }main.py not found or{ $d }.py, skip.
msg-74b32804 = Installing plugin{ $p }Required dependencies:{ $pth }
msg-936edfca = Update plugin{ $p }Dependency failure. Code:{ $e }
msg-ebd47311 = Plugin{ $root_dir_name }Import failed, attempting recovery from installed dependencies:{ $import_exc }
msg-1b6e94f1 = Plugin{ $root_dir_name }Dependencies have been restored from site-packages, skipping reinstallation.
msg-81b7c9b9 = Plugin{ $root_dir_name }Dependency recovery failed; reinstalling dependencies:{ $recover_exc }
msg-22fde75d = The plugin does not exist.
msg-3a307a9e = Plugin metadata information is incomplete. The name, description, version, and author fields are required.
msg-55e089d5 = Delete module{ $key }
msg-64de1322 = Delete module{ $module_name }
msg-66823424 = Module{ $module_name }Not loaded
msg-45c8df8d = Plugin cleared.{ $dir_name }中{ $key }Module
msg-f7d9aa9b = Processor Cleanup:{ $res }
msg-3c492aa6 = Clean Tool:{ $res }
msg-e0002829 = Plugin{ $res }Abnormal termination:{ $e }May cause abnormal operation of this plugin.
msg-0fe27735 = Loading plugins{ $root_dir_name }...
msg-b2ec4801 = { $error_trace }
msg-db351291 = Plugin{ $root_dir_name }Import failed. Reason:{ $e }
msg-a3db5f45 = Failed plugins remain in the plugin list; cleaning up...
msg-58c66a56 = Plugin{ $root_dir_name }Metadata loading failed:{ $e }Use default metadata.
msg-da764b29 = { $metadata }
msg-17cd7b7d = Plugin{ $res }Disabled.
msg-4baf6814 = Plugin{ $path }Not registered via decorator. Attempting to load via legacy method.
msg-840994d1 = Plugin not found{ $plugin_dir_path }metadata.
msg-944ffff1 = Insert permission filter{ $cmd_type }To{ $res }of{ $res_2 }Method.
msg-64edd12c = Hook (triggered when plugin loads){ $res }-{ $res_2 }
msg-db49f7a1 = ----- Plugin{ $root_dir_name }Failed to load -----
msg-26039659 = |{ $line }
msg-4292f44d = ----------------------------------
msg-d2048afe = Synchronization command configuration failed:{ $e }
msg-df515dec = Cleaned up the directory of the plugin that failed to install:{ $plugin_path }
msg-1f2aa1a9 = Failed to clean up the installation directory for the failed plugin:{ $plugin_path }Reason:{ $e }
msg-1e947210 = Cleaned up configuration for failed plugin installation:{ $plugin_config_path }
msg-7374541f = Cleanup of failed plugin configuration installation failed:{ $plugin_config_path }Reason:{ $e }
msg-81022b43 = Plugin deleted{ $plugin_label }Configuration file
msg-9e7e8a1a = Failed to delete the plugin configuration file ({ $plugin_label }):{ $e }
msg-22803d05 = Plugin deleted{ $plugin_label }Persistent data ({ $data_dir_name })
msg-d7c25823 = Failed to delete plugin persistent data ({ $data_dir_name },{ $plugin_label }):{ $e }
msg-e871b08f = Read Plugin{ $dir_name }README.md file failed:{ $e }
msg-b3fbe3a2 = Install plugin{ $dir_name }Failed, plugin installation directory:{ $plugin_path }
msg-70ca4592 = This plugin is a reserved component of AstrBot and cannot be uninstalled.
msg-e247422b = Plugin{ $plugin_name }Not properly terminated{ $e }, which may lead to issues such as resource leaks.
msg-0c25dbf4 = Plugin{ $plugin_name }Data incomplete, cannot uninstall.
msg-d6f8142c = Plugin removed successfully, but failed to delete the plugin folder:{ $e }You can manually delete the folder located under addons/plugins/.
msg-3d1e8733 = Plugin directory does not exist; considered in a partially uninstalled state. Proceeding to clean up failed plugin records and optional artifacts:{ $plugin_path }
msg-e1853811 = Plugin removed{ $plugin_name }Processing function{ $res }({ $res_2 })
msg-95b20050 = Plugin removed{ $plugin_name }Platform Adapter{ $adapter_name }
msg-9f248e88 = This plugin is a reserved component of AstrBot and cannot be updated.
msg-ff435883 = Terminating plugin{ $res }...
msg-355187b7 = Plugin{ $res }Not activated, no termination required, skip.
msg-4369864f = hook(on_plugin_unloaded) ->{ $res }-{ $res_2 }
msg-1b95e855 = Plugin{ $plugin_name }Does not exist.
msg-c1bc6cd6 = Plugin detected{ $res }Installed, terminating the old plugin...
msg-4f3271db = Duplicate plugin detected{ $res }Exists in different directories{ $res_2 }, terminating...
msg-d247fc54 = Failed to read the new plugin's metadata.yaml; skipping duplicate name check:{ $e }
msg-0f8947f8 = Failed to delete plugin archive:{ $e }
msg-7ee81bbf = Install plugin{ $dir_name }Failed, plugin installation directory:{ $desti_dir }

### astrbot\core\star\star_tools.py

msg-397b7bf9 = StarTools is not initialized.
msg-ca30e638 = Adapter not found: AiocqhttpAdapter
msg-77ca0ccb = Unsupported platforms:{ $platform }
msg-3ed67eb2 = Unable to retrieve caller module information
msg-e77ccce6 = Unable to retrieve module{ $res }Metadata information
msg-76ac38ee = Unable to retrieve plugin name.
msg-751bfd23 = Unable to create directory{ $data_dir }Insufficient permissions
msg-68979283 = Unable to create directory{ $data_dir }:{ $e }

### astrbot\core\star\updator.py

msg-66be72ec = Plugin{ $res }No repository address specified.
msg-7a29adea = Plugin{ $res }The root directory name is not specified.
msg-99a86f88 = Updating plugin, path:{ $plugin_path }Repository address:{ $repo_url }
msg-df2c7e1b = Delete old version plugins{ $plugin_path }Folder failure:{ $e }, use the overlay installation.
msg-b3471491 = Extracting archive:{ $zip_path }
msg-7197ad11 = Delete temporary files:{ $zip_path }and{ $res }
msg-f8a43aa5 = Failed to delete the update file; you can delete it manually.{ $zip_path }and{ $res }

### astrbot\core\star\filter\command.py

msg-995944c2 = Parameter '{ $param_name }(GreedyStr) must be the last parameter.
msg-04dbdc3a = Required parameters missing. Complete parameters for this command:{ $res }
msg-bda71712 = Parameters{ $param_name }Must be a boolean value (true/false, yes/no, 1/0).
msg-a9afddbf = Parameters{ $param_name }Type error. Full parameters:{ $res }

### astrbot\core\star\filter\custom_filter.py

msg-8f3eeb6e = The operand must be a subclass of CustomFilter.
msg-732ada95 = The CustomFilter class can only be used in conjunction with other CustomFilter classes.
msg-51c0c77d = The CustomFilter class can only be used in conjunction with other CustomFilter classes.

### astrbot\core\star\register\star.py

msg-64619f8e = The 'register_star' decorator is deprecated and will be removed in a future version.

### astrbot\core\star\register\star_handler.py

msg-7ff2d46e = Registration command{ $command_name }The sub_command parameter was not provided when issuing the sub-command.
msg-b68436e1 = The command_name parameter was not provided during the registration of the bare command.
msg-1c183df2 = { $command_group_name }The sub-command sub_command in the command group is not specified.
msg-9210c7e8 = The name of the root instruction group is not specified.
msg-678858e7 = Failed to register command group.
msg-6c3915e0 = LLM Function Tools{ $res }_{ $llm_tool_name }parameters{ $res_2 }Missing type annotations.
msg-1255c964 = LLM Function Tools{ $res }_{ $llm_tool_name }Unsupported parameter type:{ $res_2 }

### astrbot\core\utils\history_saver.py

msg-5e287ce4 = Failed to parse conversation history:{ $exc }

### astrbot\core\utils\io.py

msg-665b0191 = SSL certificate verification failed{ $url }Disabling SSL verification (CERT_NONE) as a fallback is insecure and exposes the application to man-in-the-middle attacks. Please check and resolve the certificate issue.
msg-04ab2fae = Failed to download file:{ $res }
msg-63dacf99 = File size:{ $res }KB | File Path:{ $url }
msg-14c3d0bb = { "\u000a" }Download progress:{ $res }Speed:{ $speed }KB/s
msg-4e4ee68e = SSL certificate verification failed; SSL verification has been disabled (unsafe, for temporary download only). Please check the target server's certificate configuration.
msg-5a3beefb = SSL certificate verification failed{ $url }Falling back to unverified connection (CERT_NONE). This is insecure and exposes the application to man-in-the-middle attacks. Please check the remote server's certificate issues.
msg-315e5ed6 = Preparing to download the specified release version of AstrBot WebUI files:{ $dashboard_release_url }
msg-c709cf82 = Preparing to download the specified version of AstrBot WebUI:{ $url }

### astrbot\core\utils\llm_metadata.py

msg-d6535d03 = Successfully obtained{ $res }Metadata for a large language model.
msg-8cceaeb0 = Failed to retrieve LLM metadata:{ $e }

### astrbot\core\utils\media_utils.py

msg-2f697658 = [Media Utils] Get media duration:{ $duration_ms }ms
msg-52dfbc26 = [Media Utils] Unable to retrieve media file duration:{ $file_path }
msg-486d493a = [Media Utils] ffprobe is not installed or not in PATH, unable to retrieve media duration. Please install ffmpeg: https://ffmpeg.org/
msg-0f9c647b = [Media Utils] Error occurred while retrieving media duration:{ $e }
msg-aff4c5f8 = [Media Utils] Cleaned up failed opus output files:{ $output_path }
msg-82427384 = [Media Utils] Error occurred while cleaning up failed opus output files:{ $e }
msg-215a0cfc = [Media Utils] ffmpeg audio conversion failed:{ $error_msg }
msg-8cce258e = ffmpeg conversion failed:{ $error_msg }
msg-f0cfcb92 = [Media Utils] Audio conversion successful:{ $audio_path }->{ $output_path }
msg-ead1395b = [Media Utils] ffmpeg is not installed or not in the PATH, unable to convert audio format. Please install ffmpeg: https://ffmpeg.org/
msg-5df3a5ee = ffmpeg not found
msg-6322d4d2 = [Media Utils] Error converting audio format:{ $e }
msg-e125b1a5 = [Media Utils] Cleaned up failed items{ $output_format }Output file:{ $output_path }
msg-5cf417e3 = [Media Utils] Cleanup failed{ $output_format }Error occurred while outputting the file:{ $e }
msg-3766cbb8 = [Media Utils] ffmpeg video conversion failed:{ $error_msg }
msg-77f68449 = [Media Utils] Video conversion successful:{ $video_path }->{ $output_path }
msg-3fb20b91 = [Media Utils] ffmpeg is not installed or not in the PATH, unable to convert video format. Please install ffmpeg: https://ffmpeg.org/
msg-696c4a46 = [Media Utils] Error converting video format:{ $e }
msg-98cc8fb8 = [Media Utils] Error occurred while cleaning up failed audio output files:{ $e }
msg-3c27d5e8 = [Media Utils] Error occurred while cleaning up failed video cover files:{ $e }
msg-072774ab = ffmpeg failed to extract the cover:{ $error_msg }

### astrbot\core\utils\metrics.py

msg-314258f2 = Failed to save metrics to the database:{ $e }

### astrbot\core\utils\migra_helper.py

msg-497ddf83 = Third-party agent runner configuration migration failed:{ $e }
msg-78b9c276 = { $res }
msg-e21f1509 = Migration Provider{ $res }Convert to the new structure
msg-dd3339e6 = Provider - Source structure migration completed.
msg-1cb6c174 = Migration from version 4.5 to 4.6 failed:{ $e }
msg-a899acc6 = Webchat session migration failed:{ $e }
msg-b9c52817 = Migration of the token_usage column failed:{ $e }
msg-d9660ff5 = Migration provider source structure failed:{ $e }

### astrbot\core\utils\network_utils.py

msg-54b8fda8 = [{ $provider_label }Network/Proxy connection failed ({ $error_type }Proxy address:{ $effective_proxy }Error:{ $error }
msg-ea7c80f1 = [{ $provider_label }Network connection failed ({ $error_type }Error:{ $error }
msg-f8c8a73c = [{ $provider_label }Using proxy:{ $proxy }

### astrbot\core\utils\path_util.py

msg-cf211d0f = Path mapping rule error:{ $mapping }
msg-ecea161e = Path mapping:{ $url }->{ $srcPath }

### astrbot\core\utils\pip_installer.py

msg-aa9e40b8 = pip module is not available (sys.executable={ $res }frozen={ $res_2 }ASTRBOT_DESKTOP_CLIENT={ $res_3 })
msg-4c3d7a1c = Failed to read dependency file; skipping conflict detection:{ $exc }
msg-fbf35dfa = Failed to read site-packages metadata; using fallback module name:{ $exc }
msg-c815b9dc = { $conflict_message }
msg-842a7c69 = Loaded{ $module_name }From the plugin site package:{ $module_location }
msg-d93a8842 = Dependencies have been restored.{ $dependency_name }while prioritizing{ $module_name }From the plugin site package.
msg-7632a3cc = Module{ $module_name }Plugin site package not found:{ $site_packages_path }
msg-cd739739 = Unable to prioritize module selection{ $module_name }From the plugin site package:{ $reason }
msg-de510412 = Failed to patch the pip distlib finder for the loader.{ $res }({ $package_name }):{ $exc }
msg-d2de9221 = Distlib finder patch did not take effect on the loader.{ $res }({ $package_name }).
msg-58ebda51 = Patched pip distlib finder for frozen loaders:{ $res }({ $package_name })
msg-b1fa741c = Skipping patching the distlib finder because _finder_registry is unavailable.
msg-4ef0e609 = Skipping patching of the distlib finder because the registration API is unavailable.
msg-b8c741dc = Pip package manager: pip{ $res }
msg-6b72a960 = Installation failed, error code:{ $result_code }
msg-c8325399 = { $line }

### astrbot\core\utils\session_waiter.py

msg-0c977996 = Timeout
msg-ac406437 = session_filter must be SessionFilter

### astrbot\core\utils\shared_preferences.py

msg-9a1e6a9a = When retrieving specific preferences, scope_id and key cannot be None.

### astrbot\core\utils\temp_dir_cleaner.py

msg-752c7cc8 = Invalid{ $res }={ $configured }Rollback to{ $res_2 }MB.
msg-b1fc3643 = Skip temporary files{ $path }Due to a state error:{ $e }
msg-5e61f6b7 = Unable to delete temporary files.{ $res }:{ $e }
msg-391449f0 = Temporary directory exceeds limit ({ $total_size }>{ $limit }). Removed{ $removed_files }File has been published.{ $released }Byte (Target{ $target_release }Byte count.
msg-aaf1e12a = TempDirCleaner started. Interval={ $res }cleanup_ratio={ $res_2 }
msg-e6170717 = TempDirCleaner execution failed:{ $e }
msg-0fc33fbc = The temporary directory cleaner has stopped.

### astrbot\core\utils\tencent_record_helper.py

msg-377ae139 = The pilk module is not installed. Please go to Admin Panel -> Platform Logs -> Install pip library to install the pilk library.
msg-f4ab0713 = pyffmpeg conversion failed:{ $e }Attempting to use the ffmpeg command line for conversion.
msg-33c88889 = [FFmpeg] Standard output:{ $res }
msg-2470430c = [FFmpeg] Standard error output:{ $res }
msg-1321d5f7 = [FFmpeg] Return code:{ $res }
msg-c39d210c = The generated WAV file does not exist or is empty.
msg-6e04bdb8 = pilk is not installed: please run pip install pilk

### astrbot\core\utils\trace.py

msg-fffce1b9 = [trace]{ $payload }
msg-78b9c276 = { $res }

### astrbot\core\utils\webhook_utils.py

msg-64c7ddcf = Failed to retrieve callback_api_base:{ $e }
msg-9b5d1bb1 = Failed to retrieve the dashboard port:{ $e }
msg-3db149ad = Failed to retrieve dashboard SSL configuration:{ $e }
msg-3739eec9 = { $display_log }

### astrbot\core\utils\quoted_message\extractor.py

msg-80530653 = quoted_message_parser: Stop retrieving nested forwarded messages{ $max_fetch }Hop count

### astrbot\core\utils\quoted_message\image_resolver.py

msg-6dfa6994 = quoted_message_parser: Skipping non-image local path references{ $res }
msg-9326ec62 = quoted_message_parser: Unable to parse referenced image ref={ $res }Afterwards{ $res_2 }Operation

### astrbot\core\utils\quoted_message\onebot_client.py

msg-03ad9f29 = quoted_message_parser: Operation{ $action }Parameter transfer failed{ $res }:{ $exc }
msg-519d0dec = quoted_message_parser: All attempts for this operation have failed.{ $action }last_params={ $res }Error={ $last_error }

### astrbot\core\utils\t2i\local_strategy.py

msg-94a58a1e = Unable to load any fonts.
msg-d5c7d255 = Failed to load image: HTTP{ $res }
msg-7d59d0a0 = Failed to load image:{ $e }

### astrbot\core\utils\t2i\network_strategy.py

msg-be0eeaa7 = Successfully obtained{ $res }Official T2I endpoint.
msg-3bee02f4 = Failed to retrieve the official endpoint:{ $e }
msg-829d3c71 = HTTP{ $res }
msg-05fb621f = Endpoint{ $endpoint }Failure:{ $e }Attempting the next...
msg-9a836926 = All endpoints have failed:{ $last_exception }

### astrbot\core\utils\t2i\renderer.py

msg-4225607b = Failed to render image via AstrBot API:{ $e }Falling back to local rendering.

### astrbot\core\utils\t2i\template_manager.py

msg-47d72ff5 = Template name contains illegal characters.
msg-d1b2131b = Template does not exist.
msg-dde05b0f = A template with the same name already exists.
msg-0aa209bf = User template does not exist and cannot be deleted.

### astrbot\dashboard\server.py

msg-e88807e2 = Route not found
msg-06151c57 = Missing API key
msg-88dca3cc = Invalid API key
msg-fd267dc8 = Insufficient API key permissions
msg-076fb3a3 = Unauthorized
msg-6f214cc1 = Token has expired.
msg-5041dc95 = Token is invalid
msg-1241c883 = Check port{ $port }An error occurred:{ $e }
msg-cbf13328 = Process name:{ $process_name }
msg-baf82821 = PID:{ $process_pid }
msg-c160ccf4 = Execution path:{ $process_exe }
msg-cfe052ba = Working directory:{ $process_cwd }
msg-01ee16c6 = Start command:{ $process_cmdline }
msg-50aec749 = Unable to retrieve process details (administrator privileges may be required):{ $e }
msg-7c3ba89d = Random JWT key has been initialized for the dashboard.
msg-a3adcb66 = WebUI has been disabled.
msg-44832296 = Starting WebUI, listening address:{ $scheme }//{ $host }:{ $port }
msg-3eed4a73 = Note: The WebUI will listen on all network interfaces; please be mindful of security. (You can configure dashboard.host in data/cmd_config.json to modify the host.)
msg-289a2fe8 = { "\u000a" }Error: Port{ $port }Already occupied{ "\u000a" }Occupied information:{ "\u000a" } { $process_info }Please ensure:{ "\u000a" }1. No other AstrBot instances are currently running.{ "\u000a" }2. Port{ $port }Not occupied by other programs{ "\u000a" }3. If you need to use other ports, modify the configuration file.
msg-6d1dfba8 = Port{ $port }Already occupied
msg-228fe31e = { "\u000a" }✨✨✨{ "\u000a" }AstrBot v{ $VERSION }WebUI has started and is accessible.{ "\u000a" }{ "\u000a" }
msg-3749e149 = ➜  Local:{ $scheme }//localhost:{ $port }{ "\u000a" }
msg-3c2a1175 = ➜  Network:{ $scheme }//{ $ip }:{ $port }{ "\u000a" }
msg-d1ba29cb = ➜   Default username and password: astrbot{ "\u000a" }✨✨✨{ "\u000a" }
msg-d5182f70 = You can configure dashboard.host in data/cmd_config.json for remote access.{ "\u000a" }
msg-c0161c7c = { $display }
msg-ac4f2855 = When dashboard.ssl.enable is set to true, cert_file and key_file must be configured.
msg-3e87aaf8 = SSL certificate file does not exist:{ $cert_path }
msg-5ccf0a9f = SSL private key file does not exist:{ $key_path }
msg-5e4aa3eb = SSL CA certificate file does not exist:{ $ca_path }
msg-cb049eb2 = AstrBot WebUI has been gracefully shut down.

### astrbot\dashboard\utils.py

msg-32a21658 = Missing required libraries for generating t-SNE visualization. Please install matplotlib and scikit-learn:{ $e }
msg-aa3a3dbf = Knowledge base not found.
msg-0e404ea3 = FAISS index does not exist:{ $index_path }
msg-8d92420c = Index is empty
msg-24c0450e = Extract{ $res }This vector is used for visualization...
msg-632d0acf = Starting t-SNE dimensionality reduction...
msg-61f0449f = Generating visual charts...
msg-4436ad2b = Error occurred while generating t-SNE visualization:{ $e }
msg-78b9c276 = { $res }

### astrbot\dashboard\routes\api_key.py

msg-8e0249fa = At least one valid scope is required.
msg-1b79360d = Invalid scope
msg-d6621696 = expires_in_days must be an integer
msg-33605d95 = expires_in_days must be greater than 0
msg-209030fe = Missing key: key_id
msg-24513a81 = API key not found

### astrbot\dashboard\routes\auth.py

msg-ee9cf260 = For security reasons, please change the default password as soon as possible.
msg-87f936b8 = Username or password is incorrect.
msg-1198c327 = You cannot perform this operation in demo mode.
msg-25562cd3 = The original password is incorrect.
msg-d31087d2 = New username and password cannot both be empty.
msg-b512c27e = The two new passwords entered do not match.
msg-7b947d8b = JWT key is not set in cmd_config.

### astrbot\dashboard\routes\backup.py

msg-6920795d = Cleaning up expired upload sessions:{ $upload_id }
msg-3e96548d = Failed to clean up expired upload sessions:{ $e }
msg-259677a9 = Failed to clean up shard directory:{ $e }
msg-d7263882 = Failed to read backup manifest:{ $e }
msg-40f76598 = Skipping invalid backup file:{ $filename }
msg-18a49bfc = Failed to retrieve backup list:{ $e }
msg-78b9c276 = { $res }
msg-6e08b5a5 = Failed to create backup:{ $e }
msg-9cce1032 = Background export task{ $task_id }Failure:{ $e }
msg-55927ac1 = Missing backup file
msg-374cab8a = Please upload the backup file in ZIP format.
msg-d53d6730 = The uploaded backup file has been saved:{ $unique_filename }(Original name:{ $res })
msg-98e64c7f = Failed to upload backup file:{ $e }
msg-49c3b432 = Missing filename parameter
msg-df33d307 = Invalid file size
msg-162ad779 = Initialize multipart upload: upload_id={ $upload_id }filename={ $unique_filename }, total_chunks={ $total_chunks }
msg-de676924 = Failed to initialize multipart upload:{ $e }
msg-eecf877c = Missing required parameters
msg-f175c633 = Invalid shard index
msg-ad865497 = Missing shard data
msg-947c2d56 = Upload session does not exist or has expired.
msg-f3a464a5 = Shard index out of range
msg-7060da1d = Receiving chunk: upload_id={ $upload_id }chunk={ $res }/{ $total_chunks }
msg-06c107c1 = Upload chunk failed:{ $e }
msg-f040b260 = Backup marked as upload source:{ $zip_path }
msg-559c10a8 = Failed to mark backup source:{ $e }
msg-d1d752ef = Missing upload_id parameter
msg-390ed49a = Shard incomplete, missing:{ $res }...
msg-8029086a = Chunk upload completed:{ $filename }, size={ $file_size }chunks={ $total }
msg-4905dde5 = Failed to complete multipart upload:{ $e }
msg-b63394b1 = Cancel multipart upload:{ $upload_id }
msg-2b39da46 = Upload cancellation failed:{ $e }
msg-f12b1f7a = Invalid file name
msg-44bb3b89 = Backup file does not exist:{ $filename }
msg-b005980b = Pre-check of backup file failed:{ $e }
msg-65b7ede1 = Please confirm the import first. The import will clear and overwrite existing data, and this operation cannot be undone.
msg-b152e4bf = Import backup failed:{ $e }
msg-5e7f1683 = Background Import Task{ $task_id }Failure:{ $e }
msg-6906aa65 = Missing parameter task_id
msg-5ea3d72c = Task not found.
msg-f0901aef = Failed to retrieve task progress:{ $e }
msg-8d23792b = Missing parameter filename
msg-4188ede6 = Missing parameter token
msg-0c708312 = Server configuration error
msg-cc228d62 = Token has expired, please refresh the page and try again.
msg-5041dc95 = Token is invalid
msg-96283fc5 = The backup file does not exist.
msg-00aacbf8 = Download backup failed:{ $e }
msg-3ea8e256 = Failed to delete backup:{ $e }
msg-e4a57714 = Missing parameter new_name
msg-436724bb = The new file name is invalid.
msg-9f9d8558 = File name '{ $new_filename }Already exists
msg-a5fda312 = Backup file renaming:{ $filename }->{ $new_filename }
msg-e7c82339 = Rename backup failed:{ $e }

### astrbot\dashboard\routes\chat.py

msg-a4a521ff = Missing key: file name
msg-c9746528 = Invalid file path
msg-3c2f6dee = File access error
msg-e5b19b36 = Missing key value: attachment_id
msg-cfa38c4d = Attachment not found
msg-377a7406 = Missing key: file
msg-bae87336 = Failed to create attachment.
msg-5c531303 = Missing JSON request body
msg-1c3efd8f = Missing key: message or file
msg-04588d0f = Missing key value: session_id or conversation_id
msg-c6ec40ff = Message content is empty (replies with empty content are not allowed)
msg-2c3fdeb9 = All messages are empty.
msg-9bc95e22 = session_id is empty
msg-344a401b = [WebChat] User{ $username }Disconnect the chat long connection.
msg-6b54abec = WebChat stream error:{ $e }
msg-53509ecb = Network chat stream message ID mismatch.
msg-1211e857 = [WebChat] User{ $username }Disconnect the chat long connection.{ $e }
msg-be34e848 = Failed to extract web search references:{ $e }
msg-80bbd0ff = WebChat stream unexpected error:{ $e }
msg-dbf41bfc = Missing key value: session_id
msg-d922dfa3 = Session{ $session_id }Not found
msg-c52a1454 = Permission denied
msg-e800fd14 = Failed to delete UMO route.{ $unified_msg_origin }During session cleanup:{ $exc }
msg-44c45099 = Unable to delete the attachment file.{ $res }:{ $e }
msg-f033d8ea = Failed to retrieve attachment:{ $e }
msg-e6f655bd = Failed to delete attachment:{ $e }
msg-a6ef3b67 = Missing key: display_name

### astrbot\dashboard\routes\chatui_project.py

msg-04827ead = Missing key: title
msg-34fccfbb = Missing key: project_id
msg-a7c08aee = Project{ $project_id }Not found
msg-c52a1454 = Permission denied
msg-dbf41bfc = Missing key value: session_id
msg-d922dfa3 = Session{ $session_id }Not found

### astrbot\dashboard\routes\command.py

msg-1d47363b = handler_full_name and enabled are both required fields.
msg-35374718 = handler_full_name and new_name are both required fields.
msg-f879f2f4 = handler_full_name and permission are both required.

### astrbot\dashboard\routes\config.py

msg-680e7347 = Configuration Item{ $path }  { $key }No type definition, skipping validation.
msg-ef2e5902 = Saving configuration, is_core={ $is_core }
msg-78b9c276 = { $res }
msg-acef166d = An exception occurred during configuration verification:{ $e }
msg-42f62db0 = Format validation failed:{ $errors }
msg-3e668849 = Missing configuration data
msg-196b9b25 = Missing provider_source_id
msg-dbbbc375 = No corresponding provider source found
msg-a77f69f4 = Missing original_id
msg-96f154c4 = Missing or incorrect configuration data
msg-c80b2c0f = Provider source ID '{ $res }'already exists, please try a different ID.
msg-537b700b = Routing table data is missing or incorrect.
msg-b5079e61 = Failed to update routing table:{ $e }
msg-cf97d400 = Missing UMO or configuration file ID
msg-2a05bc8d = Missing UMO
msg-7098aa3f = Failed to delete routing table entry:{ $e }
msg-902aedc3 = Missing configuration file ID
msg-b9026977 = abconf_id cannot be empty
msg-acf0664a = Deletion failed
msg-59c93c1a = Failed to delete configuration file:{ $e }
msg-930442e2 = Update failed
msg-7375d4dc = Failed to update configuration file:{ $e }
msg-53a8fdb2 = Attempting to check provider:{ $res }(ID:{ $res_2 }Type:{ $res_3 }Model:{ $res_4 })
msg-8b0a48ee = Provider{ $res }(ID:{ $res_2 }Available.
msg-7c7180a7 = Provider{ $res }(ID:{ $res_2 }) Unavailable. Error:{ $error_message }
msg-1298c229 = Backtracking{ $res }:{ $res_2 }
msg-d7f9a42f = { $message }
msg-cd303a28 = API call: /config/provider/check_one id={ $provider_id }
msg-55b8107a = ID is '{ $provider_id }Provider not found in provider_manager.
msg-d1a98a9b = ID is '{ $provider_id }Not found
msg-cb9c402c = Missing parameter provider_type
msg-e092d4ee = Missing parameter provider_id
msg-1ff28fed = ID not found.{ $provider_id }Provider
msg-92347c35 = Provider{ $provider_id }Type does not support retrieving the model list.
msg-d0845a10 = Missing parameter provider_config
msg-5657fea4 = provider_config is missing the type field
msg-09ed9dc7 = Provider adapter failed to load. Please check the provider type configuration or review the server logs.
msg-1cce1cd4 = No applicable{ $provider_type }Provider Adapter
msg-8361e44d = Not found{ $provider_type }Class
msg-4325087c = Provider is not of type EmbeddingProvider.
msg-a9873ea4 = Detected{ $res }The embedding vector dimension is{ $dim }
msg-d170e384 = Failed to retrieve embedding dimensions:{ $e }
msg-abfeda72 = Missing parameter source_id
msg-0384f4c9 = ID not found.{ $provider_source_id }provider_source
msg-aec35bdb = provider_source is missing the type field.
msg-cbb9d637 = Dynamic import of provider adapter failed:{ $e }
msg-468f64b3 = Provider{ $provider_type }Unable to retrieve model list
msg-cb07fc1c = Provider source has been obtained.{ $provider_source_id }Model List:{ $models }
msg-d2f6e16d = Failed to retrieve model list:{ $e }
msg-25ea8a96 = Unsupported permission scope:{ $scope }
msg-23c8933f = Missing name or key parameter
msg-536e77ae = Plugin{ $name }Not found or not configured
msg-1b6bc453 = Configuration item not found or not a file type.
msg-fc0a457e = No files have been uploaded.
msg-31c718d7 = Invalid name parameter
msg-e1edc16e = Missing name parameter
msg-8e634b35 = Invalid path parameter
msg-0b52a254 = Plugin{ $name }Not found
msg-bff0e837 = Parameter error
msg-2f29d263 = Robot name cannot be modified.
msg-1478800f = No corresponding platform found
msg-ca6133f7 = Missing parameter id
msg-1199c1f9 = Using cached platform logo token.{ $res }
msg-889a7de5 = Platform class not found{ $res }
msg-317f359c = Platform Logo Token has been registered.{ $res }
msg-323ec1e2 = Platform{ $res }Logo file not found:{ $logo_file_path }
msg-bc6d0bcf = Unable to import the required modules for the platform.{ $res }:{ $e }
msg-b02b538d = Platform file system error{ $res }Logo:{ $e }
msg-31123607 = An unexpected error occurred during platform logo registration.{ $res }:{ $e }
msg-af06ccab = Configuration file{ $conf_id }Does not exist
msg-082a5585 = Plugin{ $plugin_name }Does not exist
msg-ca334960 = Plugin{ $plugin_name }No registration configuration

### astrbot\dashboard\routes\conversation.py

msg-62392611 = Database query error:{ $e }{ "\u000a" }{ $res }
msg-b21b052b = Database query error:{ $e }
msg-10f72727 = { $error_msg }
msg-036e6190 = Failed to retrieve conversation list:{ $e }
msg-a16ba4b4 = Missing required parameters: user_id and cid
msg-9a1fcec9 = The conversation does not exist.
msg-73a8a217 = Failed to retrieve conversation details:{ $e }{ "\u000a" }{ $res }
msg-976cd580 = Failed to retrieve conversation details:{ $e }
msg-c193b9c4 = Failed to update conversation information:{ $e }{ "\u000a" }{ $res }
msg-9f96c4ee = Failed to update conversation information:{ $e }
msg-e1cb0788 = The conversations parameter cannot be empty during batch deletion.
msg-38e3c4ba = Failed to delete conversation:{ $e }{ "\u000a" }{ $res }
msg-ebf0371a = Failed to delete conversation:{ $e }
msg-af54ee29 = Missing required parameter: history
msg-b72552c8 = history must be a valid JSON string or array
msg-fdf757f3 = Failed to update conversation history:{ $e }{ "\u000a" }{ $res }
msg-33762429 = Failed to update conversation history:{ $e }
msg-498f11f8 = Export list cannot be empty.
msg-98aa3644 = Export conversation failed: user_id={ $user_id }, cid={ $cid }error={ $e }
msg-ed77aa37 = No conversations were successfully exported.
msg-f07b18ee = Batch export of conversations failed:{ $e }{ "\u000a" }{ $res }
msg-85dc73fa = Batch export of conversations failed:{ $e }

### astrbot\dashboard\routes\cron.py

msg-fb5b419b = Cron Manager not initialized
msg-78b9c276 = { $res }
msg-112659e5 = Unable to list assignments:{ $e }
msg-8bc87eb5 = Invalid payload
msg-29f616c2 = Session required
msg-ae7c99a4 = When run_once=true, run_at must be specified.
msg-4bb8c206 = When run_once is false, cron_expression is required.
msg-13fbf01e = run_at must be an ISO-formatted datetime.
msg-da14d97a = Failed to create assignment:{ $e }
msg-804b6412 = Assignment not found
msg-94b2248d = Failed to update assignment:{ $e }
msg-42c0ee7a = Failed to delete assignment:{ $e }

### astrbot\dashboard\routes\file.py

msg-78b9c276 = { $res }

### astrbot\dashboard\routes\knowledge_base.py

msg-ce669289 = Upload document{ $res }Failure:{ $e }
msg-87e99c2d = Background Upload Task{ $task_id }Failure:{ $e }
msg-78b9c276 = { $res }
msg-d5355233 = Import document{ $file_name }Failure:{ $e }
msg-5e7f1683 = Background Import Task{ $task_id }Failure:{ $e }
msg-e1949850 = Failed to retrieve knowledge base list:{ $e }
msg-299af36d = Knowledge base name cannot be empty.
msg-faf380ec = Missing parameter embedding_provider_id
msg-9015b689 = Embedding model does not exist or type is incorrect.{ $res })
msg-a63b3aa9 = Embedding vector dimension mismatch, actual dimension is{ $res }However, the configuration is{ $res_2 }
msg-9b281e88 = Testing the embedding model failed:{ $e }
msg-d3fb6072 = The reordering model does not exist.
msg-fbec0dfd = Abnormal results returned by the ranking model.
msg-872feec8 = Test reordering model failed:{ $e }Please check the platform log output.
msg-a4ac0b9e = Failed to create knowledge base:{ $e }
msg-c8d487e9 = Missing parameter kb_id
msg-978b3c73 = The knowledge base does not exist.
msg-2137a3e6 = Failed to retrieve knowledge base details:{ $e }
msg-e7cf9cfd = At least one update field must be provided.
msg-d3d82c22 = Failed to update knowledge base:{ $e }
msg-5d5d4090 = Failed to delete knowledge base:{ $e }
msg-787a5dea = Failed to retrieve knowledge base statistics:{ $e }
msg-97a2d918 = Failed to retrieve document list:{ $e }
msg-b170e0fa = Content-Type must be multipart/form-data
msg-5afbfa8e = Missing file
msg-6636fd31 = A maximum of 10 files can be uploaded.
msg-975f06d7 = Document upload failed:{ $e }
msg-35bacf60 = Missing parameter documents or incorrect format.
msg-6cc1edcd = Document format error; must include file_name and chunks.
msg-376d7d5f = chunks must be a list
msg-e7e2f311 = chunks must be a list of non-empty strings
msg-42315b8d = Failed to import document:{ $e }
msg-6906aa65 = Missing parameter task_id
msg-5ea3d72c = Task not found.
msg-194def99 = Failed to retrieve upload progress:{ $e }
msg-df6ec98e = Missing parameter doc_id
msg-7c3cfe22 = Document does not exist.
msg-b54ab822 = Failed to retrieve document details:{ $e }
msg-0ef7f633 = Failed to delete document:{ $e }
msg-2fe40cbd = Missing parameter chunk_id
msg-fc13d42a = Failed to delete text block:{ $e }
msg-4ef8315b = Failed to retrieve block list:{ $e }
msg-b70a1816 = Missing parameter query
msg-82ee646e = Missing parameter kb_names or incorrect format.
msg-07a61a9a = Failed to generate t-SNE visualization:{ $e }
msg-20a3b3f7 = Retrieval failed:{ $e }
msg-1b76f5ab = Missing parameter url
msg-5dc86dc6 = Failed to upload document from URL:{ $e }
msg-890b3dee = Background URL upload task{ $task_id }Failure:{ $e }

### astrbot\dashboard\routes\live_chat.py

msg-40f242d5 = [Live Chat]{ $res }Start speaking stamp={ $stamp }
msg-a168d76d = [Live Chat] Stamp mismatch or not in speaking state:{ $stamp }vs{ $res }
msg-e01b2fea = [Live Chat] No audio frame data available
msg-33856925 = [Live Chat] Audio file saved:{ $audio_path }Size:{ $res }bytes
msg-9e9b7e59 = [Live Chat] Failed to assemble WAV file:{ $e }
msg-21430f56 = [Live Chat] Temporary files deleted:{ $res }
msg-6b4f88bc = [Live Chat] Failed to delete temporary files:{ $e }
msg-0849d043 = [Live Chat] WebSocket connection established:{ $username }
msg-5477338a = [Live Chat] WebSocket Error:{ $e }
msg-fdbfdba8 = [Live Chat] WebSocket connection closed:{ $username }
msg-8cffeb57 = [Live Chat] chat subscription forward failed ({ $chat_session_id }):{ $e }
msg-78381f26 = [Live Chat] Failed to extract web search refs:{ $e }
msg-56fe3df0 = [Live Chat] Failed to process chat message:{ $e }
msg-7be90ac0 = [Live Chat] start_speaking missing stamp
msg-8215062a = [Live Chat] Failed to decode audio data:{ $e }
msg-438980ea = [Live Chat] end_speaking missing stamp
msg-b35a375c = [Live Chat] User interruption:{ $res }
msg-2c3e7bbc = [Live Chat] STT Provider Not Configured
msg-0582c8ba = [Live Chat] STT recognition result is empty
msg-57c2b539 = [Live Chat] STT Result:{ $user_text }
msg-6b7628c6 = [Live Chat] User interruption detected
msg-2cab2269 = [Live Chat] Message ID mismatch:{ $result_message_id }!={ $message_id }
msg-74c2470e = [Live Chat] Failed to parse AgentStats:{ $e }
msg-4738a2b3 = [Live Chat] Failed to parse TTSStats:{ $e }
msg-944d5022 = [Live Chat] Audio stream playback started
msg-009104d8 = [Live Chat] Bot reply completed:{ $bot_text }
msg-0c4c3051 = [Live Chat] Audio processing failed:{ $e }
msg-140caa36 = [Live Chat] Save interrupted message:{ $interrupted_text }
msg-869f51ea = [Live Chat] User message:{ $user_text }(session:{ $res }ts:{ $timestamp })
msg-d26dee52 = [Live Chat] Bot Message (Interruption):{ $interrupted_text }(session:{ $res }ts:{ $timestamp })
msg-1377f378 = [Live Chat] Failed to record message:{ $e }

### astrbot\dashboard\routes\log.py

msg-5bf500c1 = Log SSE Historical Error Resend:{ $e }
msg-e4368397 = Log SSE connection error:{ $e }
msg-547abccb = Failed to retrieve log history:{ $e }
msg-cb5d4ebb = Failed to retrieve Trace settings:{ $e }
msg-7564d3b0 = Request data is empty.
msg-d2a1cd76 = Failed to update Trace settings:{ $e }

### astrbot\dashboard\routes\open_api.py

msg-855e0b38 = Failed to create chat session.{ $session_id }:{ $e }
msg-fc15cbcd = { $username_err }
msg-bc3b3977 = Invalid username
msg-2cd6e70f = { $ensure_session_err }
msg-53632573 = { $resolve_err }
msg-d4765667 = Failed to update the chat configuration route.{ $umo }Using Configuration{ $config_id }:{ $e }
msg-7c7a9f55 = Failed to update chat configuration route:{ $e }
msg-ba0964a1 = OpenAPI WebSocket stream message ID mismatch
msg-ca769cde = OpenAPI WebSocket failed to extract webpage search references:{ $e }
msg-0f97a5df = OpenAPI WebSocket chat failure:{ $e }
msg-d6873ba9 = OpenAPI WebSocket connection closed:{ $e }
msg-74bff366 = page and page_size must be integers
msg-2b00f931 = Missing key: message
msg-a29d9adb = Missing key: umo
msg-4990e908 = Invalid umo:{ $e }
msg-45ac857c = Robot or platform not found{ $platform_id }The robot above is not running.
msg-ec0f0bd2 = OpenAPI message sending failed:{ $e }
msg-d04109ab = Failed to send message:{ $e }

### astrbot\dashboard\routes\persona.py

msg-4a12aead = Failed to retrieve personality list:{ $e }{ "\u000a" }{ $res }
msg-c168407f = Failed to retrieve personality list:{ $e }
msg-63c6f414 = Missing required parameter: persona_id
msg-ce7da6f3 = Personality does not exist.
msg-9c07774d = Failed to retrieve personality details:{ $e }{ "\u000a" }{ $res }
msg-ee3b44ad = Failed to retrieve personality details:{ $e }
msg-ad455c14 = Persona ID cannot be empty.
msg-43037094 = System prompt cannot be empty.
msg-eca21159 = Custom error response messages must be strings.
msg-ec9dda44 = The number of preset dialogues must be even (alternating between user and assistant).
msg-26b214d5 = Failed to create persona:{ $e }{ "\u000a" }{ $res }
msg-8913dfe6 = Failed to create persona:{ $e }
msg-3d94d18d = Failed to update personality:{ $e }{ "\u000a" }{ $res }
msg-f2cdfbb8 = Failed to update personality:{ $e }
msg-51d84afc = Personality deletion failed:{ $e }{ "\u000a" }{ $res }
msg-8314a263 = Personality deletion failed:{ $e }
msg-b8ecb8f9 = Failed to move personality:{ $e }{ "\u000a" }{ $res }
msg-ab0420e3 = Failed to move personality:{ $e }
msg-e5604a24 = Failed to retrieve folder list:{ $e }{ "\u000a" }{ $res }
msg-4d7c7f4a = Failed to retrieve folder list:{ $e }
msg-cf0ee4aa = Failed to retrieve folder tree:{ $e }{ "\u000a" }{ $res }
msg-bb515af0 = Failed to retrieve folder tree:{ $e }
msg-c92b4863 = Missing required parameter: folder_id
msg-77cdd6fa = The folder does not exist.
msg-2d34652f = Failed to retrieve folder details:{ $e }{ "\u000a" }{ $res }
msg-650ef096 = Failed to retrieve folder details:{ $e }
msg-27c413df = Folder name cannot be empty.
msg-b5866931 = Failed to create folder:{ $e }{ "\u000a" }{ $res }
msg-5e57f3b5 = Failed to create folder:{ $e }
msg-9bd8f820 = Failed to update folder:{ $e }{ "\u000a" }{ $res }
msg-1eada044 = Failed to update folder:{ $e }
msg-9cef0256 = Failed to delete folder:{ $e }{ "\u000a" }{ $res }
msg-22020727 = Failed to delete folder:{ $e }
msg-7a69fe08 = items cannot be empty
msg-e71ba5c2 = Each item must include the id, type, and sort_order fields.
msg-dfeb8320 = The type field must be 'persona' or 'folder'.
msg-aec43ed3 = Update sorting failed:{ $e }{ "\u000a" }{ $res }
msg-75ec4427 = Update sorting failed:{ $e }

### astrbot\dashboard\routes\platform.py

msg-bcc64513 = Webhook UUID not found for{ $webhook_uuid }The platform
msg-1478800f = No corresponding platform found
msg-378cb077 = Platform{ $res }webhook_callback method not implemented
msg-2d797305 = Platform does not support a unified Webhook mode.
msg-83f8dedf = An error occurred while processing the webhook callback:{ $e }
msg-af91bc78 = Failed to process callback
msg-136a952f = Failed to retrieve platform statistics:{ $e }
msg-60bb0722 = Failed to retrieve statistics:{ $e }

### astrbot\dashboard\routes\plugin.py

msg-1198c327 = You cannot perform this operation in demo mode.
msg-adce8d2f = Missing plugin directory name
msg-2f1b67fd = Reload failed:{ $err }
msg-71f9ea23 = /api/plugin/reload-failed:{ $res }
msg-27286c23 = /api/plugin/reload:{ $res }
msg-b33c0d61 = Cache MD5 matches, using cached plugin marketplace data.
msg-64b4a44c = Remote plugin marketplace data is empty:{ $url }
msg-fdbffdca = Successfully retrieved remote plugin market data, including{ $res }This plugin
msg-48c42bf8 = Request{ $url }Failed, status code:{ $res }
msg-6ac25100 = Request{ $url }Failed, error:{ $e }
msg-7e536821 = Remote plugin marketplace data retrieval failed; using cached data.
msg-d4b4c53a = Failed to retrieve the plugin list, and no cached data is available.
msg-37f59b88 = Failed to load cache MD5:{ $e }
msg-8048aa4c = Failed to retrieve remote MD5:{ $e }
msg-593eacfd = No MD5 information found in the cache file.
msg-dedcd957 = Unable to retrieve remote MD5, will use cached version.
msg-21d7e754 = Plugin data MD5: Local={ $cached_md5 }remote={ $remote_md5 }Valid={ $is_valid }
msg-0faf4275 = Cache validation failed:{ $e }
msg-e26aa0a5 = Loading cache file:{ $cache_file }Cache time:{ $res }
msg-23d627a1 = Failed to load plugin marketplace cache:{ $e }
msg-22d12569 = Plugin market data has been cached to:{ $cache_file }, MD5:{ $md5 }
msg-478c99a9 = Failed to save plugin marketplace cache:{ $e }
msg-3838d540 = Failed to retrieve plugin logo:{ $e }
msg-da442310 = Installing plugin{ $repo_url }
msg-e0abd541 = Install plugin{ $repo_url }Success.
msg-78b9c276 = { $res }
msg-acfcd91e = Installing user-uploaded plugins{ $res }
msg-48e05870 = Install plugin{ $res }Success
msg-8af56756 = Uninstalling plugin{ $plugin_name }
msg-6d1235b6 = Uninstall plugin{ $plugin_name }Success
msg-83c7ffba = Missing failure plugin directory name
msg-2e306f45 = Uninstalling failed plugins{ $dir_name }
msg-44e9819e = Failed to uninstall plugin{ $dir_name }Success
msg-7055316c = Updating plugin{ $plugin_name }
msg-d258c060 = Update plugin{ $plugin_name }Success.
msg-398370d5 = /api/plugin/update:{ $res }
msg-2d225636 = Plugin list cannot be empty.
msg-32632e67 = Batch Update Plugins{ $name }
msg-08dd341c = /api/plugin/update-all: Update plugins{ $name }Failure:{ $res }
msg-cb230226 = Disable plugin{ $plugin_name }.
msg-abc710cd = /api/plugin/off:{ $res }
msg-06e2a068 = Enable plugin{ $plugin_name }.
msg-82c412e7 = /api/plugin/on:{ $res }
msg-77e5d67e = Fetching plugins{ $plugin_name }README file content
msg-baed1b72 = Plugin name is empty.
msg-773cca0a = Plugin name cannot be empty.
msg-082a5585 = Plugin{ $plugin_name }Does not exist
msg-ba106e58 = Plugin{ $plugin_name }Directory does not exist
msg-e38e4370 = Unable to locate the plugin directory:{ $plugin_dir }
msg-df027f16 = Plugin not found{ $plugin_name }Catalog
msg-5f304f4b = Plugin{ $plugin_name }No README file
msg-a3ed8739 = /api/plugin/readme:{ $res }
msg-2f9e2c11 = Failed to read the README file:{ $e }
msg-dcbd593f = Fetching plugins{ $plugin_name }Update Log
msg-ea5482da = /api/plugin/changelog:{ $res }
msg-8e27362e = Failed to read update log:{ $e }
msg-0842bf8b = Plugin{ $plugin_name }No update log file
msg-8e36313d = sources fields must be a list
msg-643e51e7 = /api/plugin/source/save:{ $res }

### astrbot\dashboard\routes\session_management.py

msg-e1949850 = Failed to retrieve knowledge base list:{ $e }
msg-3cd6eb8c = Failed to retrieve rule list:{ $e }
msg-363174ae = Missing required parameter: umo
msg-809e51d7 = Missing required parameter: rule_key
msg-ce203e7e = Unsupported rule key:{ $rule_key }
msg-2726ab30 = Failed to update session rules:{ $e }
msg-f021f9fb = Failed to delete session rule:{ $e }
msg-6bfa1fe5 = Missing required parameter: umos
msg-4ce0379e = Parameter umos must be an array.
msg-979c6e2f = Delete umo{ $umo }Rule failure:{ $e }
msg-77d2761d = Batch deletion of session rules failed:{ $e }
msg-6619322c = Failed to retrieve UMO list:{ $e }
msg-b944697c = Failed to retrieve session status list:{ $e }
msg-adba3c3b = At least one status to be modified must be specified.
msg-4a8eb7a6 = Please specify the group ID.
msg-67f15ab7 = Group '{ $group_id }does not exist
msg-50fbcccb = No matching sessions found
msg-59714ede = Update{ $umo }Service status failure:{ $e }
msg-31640917 = Batch update service status failed:{ $e }
msg-4d83eb92 = Missing required parameters: provider_type, provider_id
msg-5f333041 = Unsupported provider_type:{ $provider_type }
msg-6fa017d7 = Update{ $umo }Provider failed:{ $e }
msg-07416020 = Batch update of Provider failed:{ $e }
msg-94c745e6 = Failed to retrieve group list:{ $e }
msg-fb7cf353 = Group name cannot be empty.
msg-ae3fce8a = Failed to create group:{ $e }
msg-07de5ff3 = Group ID cannot be empty.
msg-35b8a74f = Failed to update group:{ $e }
msg-3d41a6fd = Failed to delete group:{ $e }

### astrbot\dashboard\routes\skills.py

msg-78b9c276 = { $res }
msg-1198c327 = You cannot perform this operation in demo mode.
msg-52430f2b = File missing
msg-2ad598f3 = Only .zip files are supported.
msg-a11f2e1c = Failed to delete temporary skill file:{ $temp_path }
msg-67367a6d = Missing skill name

### astrbot\dashboard\routes\stat.py

msg-1198c327 = You cannot perform this operation in demo mode.
msg-78b9c276 = { $res }
msg-0e5bb0b1 = proxy_url is a required field.
msg-f0e0983e = Failed. Status code:{ $res }
msg-68e65093 = Error:{ $e }
msg-b5979fe8 = Version parameter is required.
msg-b88a1887 = Invalid version format
msg-8cb9bb6b = Path traversal attempt detected:{ $version }->{ $changelog_path }
msg-7616304c = Version Update Log{ $version }Not found

### astrbot\dashboard\routes\subagent.py

msg-78b9c276 = { $res }
msg-eda47201 = Failed to retrieve subagent configuration:{ $e }
msg-3e5b1fe0 = Configuration must be a JSON object.
msg-9f285dd3 = Failed to save subagent configuration:{ $e }
msg-665f4751 = Failed to retrieve available tools:{ $e }

### astrbot\dashboard\routes\t2i.py

msg-76cc0933 = Error occurred while retrieving the activity template.
msg-5350f35b = Template not found
msg-d7b101c5 = Name and content are required fields.
msg-e910b6f3 = A template with the same name already exists.
msg-18cfb637 = Content is required.
msg-2480cf2f = Template not found.
msg-9fe026f1 = Template name cannot be empty.
msg-eeefe1dc = Template '{ $name }It does not exist and cannot be applied.
msg-0048e060 = Error occurred while setting up the activity template.
msg-8fde62dd = Error occurred while resetting the default template.

### astrbot\dashboard\routes\tools.py

msg-78b9c276 = { $res }
msg-977490be = Failed to retrieve MCP server list:{ $e }
msg-50a07403 = Server name cannot be empty.
msg-23d2bca3 = A valid server configuration must be provided.
msg-31252516 = Server{ $name }Already exists
msg-20b8309f = Enable MCP server{ $name }Timeout.
msg-fff3d0c7 = Enable MCP server{ $name }Failure:{ $e }
msg-7f1f7921 = Failed to save configuration
msg-a7f06648 = Failed to add MCP server:{ $e }
msg-278dc41b = Server{ $old_name }Does not exist
msg-f0441f4b = Disable the MCP server before enabling it.{ $old_name }Timeout:{ $e }
msg-7c468a83 = Disable the MCP server before enabling it.{ $old_name }Failure:{ $e }
msg-8a4c8128 = Disable MCP Server{ $old_name }Timeout.
msg-9ac9b2fc = Disable MCP Server{ $old_name }Failure:{ $e }
msg-b988392d = Failed to update MCP server:{ $e }
msg-c81030a7 = Server{ $name }Does not exist
msg-4cdbd30d = Disable MCP Server{ $name }Timeout.
msg-1ed9a96e = Disable MCP Server{ $name }Failure:{ $e }
msg-a26f2c6a = Failed to delete MCP server:{ $e }
msg-bbc84cc5 = Invalid MCP server configuration
msg-aa0e3d0d = MCP server configuration cannot be empty.
msg-d69cbcf2 = Only one MCP server configuration can be set up at a time.
msg-bd43f610 = Testing MCP connection failed:{ $e }
msg-057a3970 = Failed to retrieve tool list:{ $e }
msg-29415636 = Missing required parameter: name or action
msg-75d85dc1 = Failed to enable tool:{ $e }
msg-21a922b8 = Tool{ $tool_name }Does not exist or operation failed.
msg-20143f28 = Operation tool failed:{ $e }
msg-295ab1fe = Unknown:{ $provider_name }
msg-fe38e872 = Sync failed:{ $e }

### astrbot\dashboard\routes\update.py

msg-a3503781 = Migration failed:{ $res }
msg-543d8e4d = Migration failed:{ $e }
msg-251a5f4a = Check for updates failed:{ $e }(Does not affect normal use except for project updates)
msg-aa6bff26 = /api/update/releases:{ $res }
msg-c5170c27 = Failed to download the management panel file:{ $e }.
msg-db715c26 = Updating dependencies...
msg-9a00f940 = Failed to update dependencies:{ $e }
msg-6f96e3ba = /api/update_project:{ $res }
msg-3217b509 = Failed to download the management panel file:{ $e }
msg-9cff28cf = /api/update_dashboard:{ $res }
msg-1198c327 = You cannot perform this operation in demo mode.
msg-38e60adf = Missing parameter package or parameter is invalid.
msg-a1191473 = /api/update_pip:{ $res }

### astrbot\i18n\ftl_translate.py

msg-c861e2c1 = Translation error:{ $e }
msg-b0bed5f4 = Review Error:{ $e }
msg-75f207ed = File not found:{ $ftl_path }
msg-1bb0fe21 = Start translation and review{ $res }Element...
msg-afe74fa1 = Workflow failed due to an element:{ $e }
msg-af13b7d6 = Success! Saved to{ $ftl_path }

### astrbot\utils\http_ssl_common.py

msg-5304f0e3 = Unable to load the certifi CA certificate bundle into the SSL context; falling back to the system trust store only.{ $exc }

### scripts\generate_changelog.py

msg-a79937ef = Warning: The openai package is not installed. Please install it using the following command: pip install openai
msg-090bfd36 = Warning: Failed to call LLM API:{ $e }
msg-a3ac9130 = Rolling back to simple changelog generation...
msg-6f1011c5 = Latest Tags:{ $latest_tag }
msg-8c7f64d7 = Error: Tag not found in repository.
msg-a89fa0eb = No submissions have been found since the last submission.{ $latest_tag }
msg-846ebecf = Found{ $res }Number of commits since last submission{ $latest_tag }
msg-9ad686af = Warning: Unable to parse version information from the tag.{ $latest_tag }
msg-f5d43a54 = Generating changelog{ $version }...
msg-e54756e8 = ✓ Changelog generated:{ $changelog_file }
msg-82be6c98 = Preview:
msg-321ac5b1 = { $changelog_content }

### astrbot\core\pipeline\__init__.py


### astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py

msg-76945a59 = { $error_text }

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/third_party.py

msg-371b6b3d = Failed to parse custom error message for personality:{ $e }

### astrbot/core/platform/sources/webchat/message_parts_helper.py

msg-697561eb = The message part must be an object.
msg-2c4bf283 = The reply section is missing the message_id.
msg-60ddb927 = Unsupported message part type:{ $part_type }
msg-6fa997ae = { $part_type }Some parts are missing paths.
msg-e565c4b5 = File not found:{ $file_path }
msg-1389e46a = Message must be a string or list.
msg-58e0b84a = { $part_type }Some parts are missing the attachment_id.
msg-cf310369 = Attachment not found:{ $attachment_id }

### astrbot/core/agent/runners/tool_loop_agent_runner.py

msg-76945a59 = { $error_text }

### astrbot/core/star/star_manager.py

msg-d64cbb23 = Read Plugin{ $root_dir_name }Metadata failure:{ $metadata_error }

### astrbot/core/astr_main_agent.py

msg-7a34e35a = For the session{ $chatui_session_id }Failed to generate webpage chat title:{ $e }

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/third_party.py

msg-67c22b5b = { $RUNNER_NO_FINAL_RESPONSE_LOG }
msg-e9587c7e = { $RUNNER_NO_RESULT_LOG }
msg-cdb7e5b6 = { $RUNNER_NO_RESULT_FALLBACK_MESSAGE }
msg-13ea140b = Third-party runner flow in{ $timeout_sec }Not consumed within seconds; close the runner to avoid resource leakage.
msg-87a7a566 = An exception occurred when the stream monitor shut down the third-party runner.
msg-966b8ef7 = Unable to cleanly shut down third-party runner:{ $e }

### astrbot/core/utils/config_number.py

msg-c5d2510a = { $source } { $label }Should be a numeric value, but a boolean value was obtained. Fallback to{ $default }.
msg-6040637c = { $source } { $label }Value '{ $value }' is not a numeric value. Fallback to{ $default }.
msg-19aad160 = { $source } { $label }Has unsupported types{ $res }Rollback to{ $default }.
msg-21ec4bb0 = { $source } { $label }={ $parsed }Below the minimum value{ $min_value }Rollback to{ $min_value }.

### astrbot/core/agent/runners/deerflow/deerflow_api_client.py

msg-8f689453 = DeerFlow SSE parser buffer overflow{ $SSE_MAX_BUFFER_CHARS }No delimiter found after scanning this many characters; refresh oversized chunk to prevent unlimited memory growth.
msg-d1db013a = DeerFlowAPIClient is closed.
msg-8b9e7967 = DeerFlow failed to create a thread:{ $res }.{ $text }
msg-93a10841 = deerflow stream_run load summary: thread_id={ $thread_id }keys={ $res }, message count={ $message_count }Stream mode={ $res_2 }
msg-9a9d9119 = DeerFlow run/stream request failed:{ $res }.{ $text }
msg-7746c84c = Unable to cleanly close the DeerFlowAPIClient session:{ $e }
msg-e15f3d95 = DeerFlowAPIClient was garbage collected while the session was still open; the runner lifecycle should call an explicit close() (or use `async with`).

### astrbot/core/agent/runners/deerflow/deerflow_content_mapper.py

msg-3958eaa0 = Skip DeerFlow image input because the value is not a string:{ $res }
msg-582f6f32 = Skip the DeerFlow image input because the value is empty.
msg-935c7c66 = Skip the DeerFlow image input because it is neither a URL/data URI nor valid base64.
msg-764cafe0 = All{ $skipped_invalid_images }The provided DeerFlow image input was rejected for being invalid or unsupported.
msg-7d6f7e4d = { $skipped_invalid_images }The DeerFlow image input was rejected for being invalid or unsupported.
msg-67438dc2 = Skip{ $skipped_invalid_images }This is not a valid DeerFlow image input, as it is neither a URL/data URI nor valid base64.

### astrbot/core/agent/runners/deerflow/deerflow_agent_runner.py

msg-d5533e66 = Failed to close DeerFlowAPIClient during runner shutdown:{ $e }
msg-6ac10910 = { $err_text }
msg-e4ca153b = DeerFlow API base URL format is invalid. It must start with http:// or https://.
msg-d6691163 = Unable to cleanly shut down the previous DeerFlow API client:{ $e }
msg-940b0a9f = DeerFlow request failed:{ $err_msg }
msg-20f437c9 = max_step must be greater than 0
msg-adeda135 = DeerFlow agent reached max_step without completing the task.{ $max_step }).
msg-7449f8a7 = DeerFlow thread creation returned an invalid payload:{ $thread }
msg-3bde4a11 = { $delta }
msg-6c9836cd = { $delta_text }
msg-e6e01cca = DeerFlow did not return text content in the stream event.
msg-1a5b13c5 = DeerFlow stream returns an error event:{ $data }
msg-298cca9c = DeerFlow stream in thread_id={ $thread_id }Time{ $res }Timeout in seconds; returning partial results.

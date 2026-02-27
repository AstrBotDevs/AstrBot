### main.py

msg-5e25709f = Please use Python3.10+ to run this project.
msg-afd0ab81 = Use the specified WebUI directory:{ $webui_dir }
msg-7765f00f = Specified WebUI directory{ $webui_dir }Does not exist, default logic will be used.
msg-9af20e37 = The WebUI version is already up to date.
msg-9dd5c1d2 = Detected WebUI version ({ $v }) and the current AstrBot version (v{ $VERSION }) does not match.
msg-ec714d4e = Start downloading the management panel files...Peak hours (evening) may result in slower speeds. If the download fails multiple times, please go to https://github.com/AstrBotDevs/AstrBot/releases/latest to download dist.zip, and extract the dist folder into the data directory.
msg-c5170c27 = Failed to download the management panel file:{ $e }.
msg-e1592ad1 = Management panel download completed.
msg-fe494da6 = { $logo_tmpl }

### astrbot/core/lang.py

msg-d103bc8e = Namespace must not be empty.
msg-f66527da = Namespace must not contain '.'.
msg-b3665aee = Locale directory does not exist:{ $base_dir }
msg-3fe89e6a = No locale directories found under:{ $base_dir }
msg-c79b2c75 = Namespace '{ $namespace }' already exists. Set replace=True to overwrite.
msg-7db3fccf = Default namespace cannot be unregistered.
msg-3d066f64 = Namespace '{ $namespace }' is not registered.

### astrbot/core/persona_mgr.py

msg-51a854e6 = Loaded{ $res }Personality.
msg-1ea88f45 = Persona with ID{ $persona_id }does not exist.
msg-28104dff = Persona with ID{ $persona_id }already exists.
msg-08ecfd42 = { $res }The personality scenario preset dialogue format is incorrect; the number of entries should be even.
msg-b6292b94 = Failed to parse Persona configuration:{ $e }

### astrbot/core/initial_loader.py

msg-78b9c276 = { $res }
msg-58525c23 = 😭 Failed to initialize AstrBot:{ $e }!!!
msg-002cc3e8 = 🌈 Shutting down AstrBot...

### astrbot/core/log.py

msg-80a186b8 = Failed to add file sink:{ $e }

### astrbot/core/astrbot_config_mgr.py

msg-7875e5bd = Config file{ $conf_path }for UUID{ $uuid_ }does not exist, skipping.
msg-39c4fd49 = Cannot delete the default configuration file
msg-cf7b8991 = Configuration file{ $conf_id }Not present in the mapping
msg-2aad13a4 = Deleted configuration file:{ $conf_path }
msg-94c359ef = Delete configuration file{ $conf_path }Failure:{ $e }
msg-44f0b770 = Configuration file deleted successfully{ $conf_id }
msg-737da44e = Cannot update information in the default configuration file
msg-9d496709 = Configuration file updated successfully{ $conf_id }Information of

### astrbot/core/zip_updator.py

msg-24c90ff8 = Request{ $url }Failed, status code:{ $res }, Content:{ $text }
msg-14726dd8 = Request failed, status code:{ $res }
msg-fc3793c6 = Exception occurred while parsing version information:{ $e }
msg-491135d9 = Failed to parse version information
msg-03a72cb5 = No suitable release version found
msg-8bcbfcf0 = 正在下载更新{ $repo }...
msg-ccc87294 = Fetching from specified branch{ $branch }Download{ $author }/{ $repo }
msg-dfebcdc6 = Acquire{ $author }/{ $repo }GitHub Releases failed:{ $e }, will attempt to download the default branch
msg-e327bc14 = Downloading from the default branch{ $author }待翻译文本：{ $repo }
msg-3cd3adfb = Mirror site detected, will use mirror site for downloading.{ $author }Text to be translated:{ $repo }Repository Source Code:{ $release_url }
msg-1bffc0d7 = Invalid GitHub URL
msg-0ba954db = File decompression completed:{ $zip_path }
msg-90ae0d15 = Delete temporary update file:{ $zip_path }and{ $res }
msg-f8a43aa5 = Failed to delete the update file. You can delete it manually.{ $zip_path }and{ $res }

### astrbot/core/file_token_service.py

msg-0e444e51 = File does not exist:{ $local_path }Text to be translated: (Original input:{ $file_path }Text to be translated:
msg-f61a5322 = Invalid or expired file token:{ $file_token }
msg-73d3e179 = File does not exist:{ $file_path }

### astrbot/core/subagent_orchestrator.py

msg-5d950986 = subagent_orchestrator.agents must be a list
msg-29e3b482 = SubAgent persona %s not found, fallback to inline prompt.
msg-f425c9f0 = Registered subagent handoff tool:{ $res }

### astrbot/core/astr_main_agent.py

msg-8dcf5caa = Specified provider not found: %s.
msg-61d46ee5 = Invalid provider type selected (%s), skipping LLM request processing.
msg-496864bc = Error occurred while selecting provider: %s
msg-507853eb = Unable to create a new conversation.
msg-66870b7e = Error occurred while retrieving knowledge base: %s
msg-36dc1409 = Moonshot AI API key for file extraction is not set
msg-8534047e = Unsupported file extract provider: %s
msg-f2ea29f4 = Cannot get image caption because provider `{ $provider_id }` does not exist.
msg-91a70615 = Cannot get image caption because provider `{ $provider_id }` is not a valid Provider, it is{ $res }.
msg-b1840df0 = Processing image caption with provider: %s
msg-089421fc = Failed to process image description: %s
msg-719d5e4d = No provider found for image captioning in quote.
msg-e16a974b = Failed to process referenced image: %s
msg-037dad2e = Group name display enabled but group object is None. Group ID: %s
msg-58b47bcd = Timezone setting error: %s, using local timezone
msg-938af433 = Provider %s does not support image, using placeholder.
msg-83d739f8 = Provider %s does not support tool_use, clearing tools.
msg-3dbad2d9 = sanitize_context_by_modalities applied: removed_image_blocks=%s, removed_tool_messages=%s, removed_tool_calls=%s
msg-4214b760 = Generated chatui title for session %s: %s
msg-cb6db56e = Unsupported llm_safety_mode strategy: %s.
msg-7ea2c5d3 = Shipyard sandbox configuration is incomplete.
msg-9248b273 = The specified context compression model %s was not found; compression will be skipped.
msg-16fe8ea5 = The specified context compression model %s is not a conversational model and will be skipped for compression.
msg-c6c9d989 = The fallback_chat_models setting is not a list, skipping fallback providers.
msg-614aebad = Fallback chat provider `%s` not found, skip.
msg-1a2e87dd = Fallback chat provider `%s` is of an invalid type: %s, skipping.
msg-ee979399 = No conversation models (providers) found, skipping LLM request processing.
msg-7a7b4529 = Skip quoted fallback images due to limit=%d for umo=%s
msg-46bcda31 = Truncate quoted fallback images for umo=%s, reply_id=%s from %d to %d
msg-cbceb923 = Failed to resolve fallback quoted images for umo=%s, reply_id=%s: %s
msg-31483e80 = Error occurred while applying file extract: %s

### astrbot/core/umop_config_router.py

msg-dedcfded = umop keys must be strings in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all
msg-8e3a16f3 = umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all

### astrbot/core/event_bus.py

msg-da466871 = PipelineScheduler not found for id:{ $res }, event ignored.
msg-7eccffa5 = Text to be translated:{ $conf_name }] [{ $res }Text to translate: ({ $res_2 })]{ $res_3 }Text to be translated: /{ $res_4 }Text to be translated:{ $res_5 }
msg-88bc26f2 = Text to translate:{ $conf_name }] [{ $res }Text to be translated:{ $res_2 })]{ $res_3 }Text to be translated:{ $res_4 }

### astrbot/core/astr_agent_tool_exec.py

msg-e5f2fb34 = Background task{ $task_id }failed:{ $e }
msg-c54b2335 = Background handoff{ $task_id }Text to be translated:{ $res }) failed:{ $e }
msg-8c2fe51d = Failed to build main agent for background task{ $tool_name }.
msg-c6d4e4a6 = background task agent got no response
msg-0b3711f1 = Event must be provided for local function tools.
msg-8c19e27a = Tool must have a valid handler or override 'run' method.
msg-24053a5f = Tool failed to send message directly:{ $e }
msg-f940b51e = tool{ $res }execution timeout after{ $res_2 }seconds.
msg-7e22fc8e = Unknown method name:{ $method_name }
msg-c285315c = Tool execution ValueError:{ $e }
msg-41366b74 = Tool handler parameter mismatch, please check the handler definition. Handler parameters:{ $handler_param_str }
msg-e8cadf8e = Tool execution error:{ $e }. Traceback:{ $trace_ }
msg-d7b4aa84 = Previous Error:{ $trace_ }

### astrbot/core/astr_agent_run_util.py

msg-6b326889 = Agent reached max steps ({ $max_step }), forcing a final response.
msg-bb15e9c7 = { $status_msg }
msg-78b9c276 = { $res }
msg-9c246298 = Error in on_agent_done hook
msg-34f164d4 = { $err_msg }
msg-6d9553b2 = [Live Agent] Using streaming TTS (natively supports get_audio_stream)
msg-becf71bf = [Live Agent] Using TTS ({ $res }Using get_audio, audio will be generated in sentence-based chunks
msg-21723afb = [Live Agent] Runtime error occurred:{ $e }
msg-ca1bf0d7 = Failed to send TTS statistics:{ $e }
msg-5ace3d96 = [Live Agent Feeder] Sentence segmentation:{ $temp_buffer }
msg-bc1826ea = [Live Agent Feeder] Error:{ $e }
msg-a92774c9 = [Live TTS Stream] Error:{ $e }
msg-d7b3bbae = [Live TTS Simulated] Error processing text '{ $res }'...':{ $e }
msg-035bca5f = [Live TTS Simulated] Critical Error:{ $e }

### astrbot/core/astr_main_agent_resources.py

msg-509829d8 = Downloaded file from sandbox:{ $path }->{ $local_path }
msg-b462b60d = Failed to check/download file from sandbox:{ $e }
msg-0b3144f1 = [Knowledge Base] Session{ $umo }It has been configured to not use the knowledge base.
msg-97e13f98 = [Knowledge Base] Knowledge base does not exist or is not loaded:{ $kb_id }
msg-312d09c7 = [Knowledge Base] Session{ $umo }The following configured knowledge base is invalid:{ $invalid_kb_ids }
msg-42b0e9f8 = [Knowledge Base] Using session-level configuration, number of knowledge bases:{ $res }
msg-08167007 = [Knowledge Base] Using global configuration, number of knowledge bases:{ $res }
msg-a00becc3 = [Knowledge Base] Start retrieving knowledge base, count:{ $res }, top_k={ $top_k }
msg-199e71b7 = [Knowledge Base] for Conversation{ $umo }Injected{ $res }knowledge blocks

### astrbot/core/conversation_mgr.py

msg-86f404dd = Session deletion callback execution failed (session:{ $unified_msg_origin }):{ $e }
msg-57dcc41f = Conversation with id{ $cid }not found

### astrbot/core/updator.py

msg-e3d42a3b = Terminating{ $res }child processes.
msg-e7edc4a4 = 正在终止子进程{ $res }
msg-37bea42d = Child process{ $res }Not terminated normally, forcing a kill.
msg-cc6d9588 = Restart failed ({ $executable }{ $e }Please try to restart manually.
msg-0e4439d8 = Updating AstrBot started in this way is not supported.
msg-3f39a942 = Current version is already up to date.
msg-c7bdf215 = Version number not found{ $version }Update files.
msg-92e46ecc = The commit hash length is incorrect; it should be 40 characters.
msg-71c01b1c = Preparing to update AstrBot Core to the specified version:{ $version }
msg-d3a0e13d = Download of AstrBot Core update file completed, extracting now...

### astrbot/core/core_lifecycle.py

msg-9967ec8b = Using proxy:{ $proxy_config }
msg-5a29b73d = HTTP proxy cleared
msg-fafb87ce = Subagent orchestrator init failed:{ $e }
msg-f7861f86 = AstrBot migration failed:{ $e }
msg-78b9c276 = { $res }
msg-967606fd = Task{ $res }An error occurred:{ $e }
msg-a2cd77f3 = Text to be translated:{ $line }
msg-1f686eeb = Text to be translated:
msg-9556d279 = AstrBot startup completed.
msg-daaf690b = hook(on_astrbot_loaded) ->{ $res }-{ $res_2 }
msg-4719cb33 = Plugin{ $res }Not properly terminated{ $e }, which may lead to resource leaks and other issues.
msg-c3bbfa1d = Task{ $res }An error occurred:{ $e }
msg-af06ccab = Configuration file{ $conf_id }不存在

### astrbot/core/pipeline/context_utils.py

msg-49f260d3 = Handler function parameter mismatch, please check the handler definition.
msg-d7b4aa84 = Previous Error:{ $trace_ }
msg-eb8619cb = hook{ $res }) ->{ $res_2 }-{ $res_3 }
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }Terminated event propagation.

### astrbot/core/pipeline/__init__.py


### astrbot/core/pipeline/scheduler.py

msg-c240d574 = Stage{ $res }Event propagation has been terminated.
msg-609a1ac5 = The pipeline execution is complete.

### astrbot/core/pipeline/rate_limit_check/stage.py

msg-18092978 = Session{ $session_id }Rate limited. According to the rate limiting policy, this session processing will be paused.{ $stall_duration }Second
msg-4962387a = Session{ $session_id }Rate limited. According to the rate limiting policy, this request has been discarded until the quota resets at{ $stall_duration }Reset in seconds.

### astrbot/core/pipeline/whitelist_check/stage.py

msg-8282c664 = Session ID{ $res }Not in the conversation whitelist, event propagation has been terminated. Please add the conversation ID to the whitelist in the configuration file.

### astrbot/core/pipeline/process_stage/follow_up.py

msg-df881b01 = Captured follow-up message for active agent run, umo=%s, order_seq=%s

### astrbot/core/pipeline/process_stage/method/agent_request.py

msg-3267978a = Identify additional wake-up prefixes for LLM chats{ $res }Wake-up prefix for the robot{ $bwp }Start, automatically removed.
msg-97a4d573 = This pipeline does not enable AI capability, skip processing.
msg-f1a11d2b = The session{ $res }AI capability has been disabled, skipping processing.

### astrbot/core/pipeline/process_stage/method/star_request.py

msg-f0144031 = Cannot find plugin for given handler module path:{ $res }
msg-1e8939dd = plugin ->{ $res }-{ $res_2 }
msg-6be73b5e = { $traceback_text }
msg-d919bd27 = Star{ $res }handle error:{ $e }
msg-ed8dcc22 = { $ret }

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py

msg-60493581 = Unsupported tool_schema_mode: %s, fallback to skills_like
msg-9cdb2b6e = skip llm request: empty message and no provider_request
msg-e461e5af = ready to request llm provider
msg-be33dd11 = Follow-up ticket already consumed, stopping processing. umo=%s, seq=%s
msg-abd5ccbc = acquired session lock for llm request
msg-f9d617d7 = Provider API base %s is blocked due to security reasons. Please use another AI provider.
msg-3247374d = [Internal Agent] Live Mode detected, enabling TTS processing.
msg-dae92399 = [Live Mode] TTS Provider is not configured, will use normal streaming mode.
msg-1b1af61e = Error occurred while processing agent:{ $e }
msg-ea02b899 = Error occurred while processing agent request:{ $e }
msg-ee7e792b = LLM response is empty, no record saved.

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/third_party.py

msg-5e551baf = Third party agent runner error:{ $e }
msg-34f164d4 = { $err_msg }
msg-f9d76893 = The Agent Runner provider ID is not filled in. Please go to the configuration page to configure it.
msg-0f856470 = Agent Runner Provider{ $res }Configuration does not exist. Please go to the configuration page to modify the configuration.
msg-b3f25c81 = Unsupported third party agent runner type:{ $res }
msg-6c63eb68 = Agent Runner did not return the final result.

### astrbot/core/pipeline/result_decorate/stage.py

msg-7ec898fd = hook(on_decorating_result) ->{ $res }-{ $res_2 }
msg-5e27dae6 = When streaming output is enabled, plugins that rely on the pre-message-send event hook may not function correctly.
msg-caaaec29 = hook(on_decorating_result) ->{ $res }-{ $res_2 }Clear message results.
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }Terminated event propagation.
msg-813a44bb = Streaming output enabled, skipping result decoration phase
msg-891aa43a = Segmented reply regular expression error, using default segmentation method:{ $res }
msg-82bb9025 = Session{ $res }No text-to-speech model is configured.
msg-fb1c757a = TTS Request:{ $res }
msg-06341d25 = TTS Result:{ $audio_path }
msg-2057f670 = Failed to convert message segment to speech due to missing TTS audio file:{ $res }
msg-f26725cf = Registered:{ $url }
msg-47716aec = TTS failed, sending as text.
msg-ffe054a9 = Text to image conversion failed, sending as text.
msg-06c1aedc = Text-to-image conversion took more than 3 seconds. If it feels slow, you can use /t2i to turn off the text-to-image mode.

### astrbot/core/pipeline/waking_check/stage.py

msg-df815938 = enabled_plugins_name:{ $enabled_plugins_name }
msg-51182733 = Plugin{ $res }Text to be translated:{ $e }
msg-e0dcf0b8 = You (ID:{ $res }You do not have sufficient permissions to use this command. Obtain your ID via /sid and ask an administrator to add it.
msg-a3c3706f = Trigger{ $res }When, user(ID={ $res_2 }Insufficient permissions.

### astrbot/core/pipeline/session_status_check/stage.py

msg-f9aba737 = Session{ $res }Closed, event propagation terminated.

### astrbot/core/pipeline/respond/stage.py

msg-59539c6e = Failed to parse the interval time for segmented responses.{ $e }
msg-4ddee754 = Segment response interval:{ $res }
msg-5e2371a9 = Prepare to send -{ $res }Text to be translated:{ $res_2 }Text to translate:{ $res_3 }
msg-df92ac24 = async_stream is empty, skip sending.
msg-858b0e4f = Application streaming output({ $res }Text to be translated: )
msg-22c7a672 = Message is empty, skipping sending phase.
msg-e6ab7a25 = Empty content check exception:{ $e }
msg-b29b99c1 = The actual message chain is empty, skipping the send phase. header_chain:{ $header_comps }, actual_chain:{ $res }
msg-842df577 = Failed to send message chain: chain ={ $res }, error ={ $e }
msg-f35465cf = The message chain consists entirely of Reply and At message segments, skipping the sending stage. chain:{ $res }
msg-784e8a67 = Failed to send message chain: chain ={ $chain }, error ={ $e }

### astrbot/core/pipeline/content_safety_check/stage.py

msg-c733275f = Your message or the AI's response contains inappropriate content and has been blocked.
msg-46c80f28 = Content security check failed, reason:{ $info }

### astrbot/core/pipeline/content_safety_check/strategies/strategy.py

msg-27a700e0 = To use Baidu content moderation, you should first pip install baidu-aip.

### astrbot/core/pipeline/preprocess_stage/stage.py

msg-7b9074fa = { $platform }Pre-response emoji sending failed:{ $e }
msg-43f1b4ed = Path mapping:{ $url }->{ $res }
msg-9549187d = Session{ $res }Speech-to-text model not configured.
msg-5bdf8f5c = { $e }
msg-ad90e19e = Retrying:{ $res }Text to translate:{ $retry }
msg-78b9c276 = { $res }
msg-4f3245bf = Speech to text failed:{ $e }

### astrbot/core/config/astrbot_config.py

msg-e0a69978 = Unsupported configuration type{ $res }Supported types include:{ $res_2 }
msg-b9583fc9 = Configuration item detected{ $path_ }Not exist, default value inserted{ $value }
msg-ee26e40e = Configuration item detected{ $path_ }Does not exist, will be deleted from current configuration
msg-2d7497a5 = Configuration item detected{ $path }The order of sub-items is inconsistent and has been reordered.
msg-5fdad937 = Configuration item order inconsistency detected, order has been reset.
msg-555373b0 = Key not found: '{ $key }Text to be translated:

### astrbot/core/platform/register.py

msg-eecf0aa8 = Platform adapter{ $adapter_name }Already registered, possible adapter naming conflict.
msg-614a55eb = Platform Adapter{ $adapter_name }Registered
msg-bb06a88d = Platform Adapter{ $res }已注销 (来自模块{ $res_2 })

### astrbot/core/platform/platform.py

msg-30fc9871 = Platform{ $res }Unified Webhook mode not implemented

### astrbot/core/platform/astr_message_event.py

msg-b593f13f = Failed to convert message type{ $res }to MessageType. Falling back to FRIEND_MESSAGE.
msg-98bb33b7 = Clear{ $res }Additional information:{ $res_2 }
msg-0def44e2 = { $result }
msg-8e7dc862 = { $text }

### astrbot/core/platform/manager.py

msg-464b7ab7 = Failed to terminate platform adapter: client_id=%s, error=%s
msg-78b9c276 = { $res }
msg-563a0a74 = Initialization{ $platform }Platform adapter failed:{ $e }
msg-8432d24e = Platform ID %r contains illegal characters ':' or '!', replaced with %r.
msg-31361418 = Platform ID{ $platform_id }Cannot be empty, skip loading this platform adapter.
msg-e395bbcc = Loading{ $res }({ $res_2 }) Platform adapter ...
msg-b4b29344 = Loading platform adapters{ $res }Failed, reason:{ $e }Please check if the dependency library is installed. Tip: You can install dependency libraries in Admin Panel -> Platform Logs -> Install Pip Libraries.
msg-18f0e1fe = Loading platform adapter{ $res }Failed, reason:{ $e }.
msg-2636a882 = No applicable{ $res }Text to translate: ({ $res_2 }) Platform adapter, please check if it has been installed or the name is filled in incorrectly.
msg-c4a38b85 = hook(on_platform_loaded) ->{ $res }-{ $res_2 }
msg-967606fd = Task{ $res }An error has occurred:{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = Text to be translated: -------
msg-38723ea8 = Attempting to terminate{ $platform_id }Platform adapter ...
msg-63f684c6 = Possibly not completely removed{ $platform_id }Platform Adapter
msg-136a952f = Failed to retrieve platform statistics:{ $e }

### astrbot/core/platform/sources/dingtalk/dingtalk_adapter.py

msg-c81e728d = 2
msg-d6371313 = dingtalk:{ $res }
msg-a1c8b5b1 = DingTalk private chat session lacks staff_id mapping, falling back to using session_id as userId for sending.
msg-2abb842f = Failed to save DingTalk conversation mapping:{ $e }
msg-46988861 = Failed to download DingTalk file:{ $res }待翻译文本：,{ $res_2 }
msg-ba9e1288 = Failed to obtain access_token via dingtalk_stream:{ $e }
msg-835b1ce6 = Failed to get DingTalk robot access token:{ $res }{ $res_2 }
msg-331fcb1f = Failed to read DingTalk staff_id mapping:{ $e }
msg-ba183a34 = DingTalk group message sending failed: access_token is empty
msg-b8aaa69b = Failed to send DingTalk group message:{ $res },{ $res_2 }
msg-cfb35bf5 = DingTalk private message sending failed: access_token is empty
msg-7553c219 = DingTalk private chat message sending failed:{ $res }{ $res_2 }
msg-5ab2d58d = Failed to clean up temporary files:{ $file_path },{ $e }
msg-c0c40912 = DingTalk voice conversion to OGG failed, fallback to AMR:{ $e }
msg-21c73eca = DingTalk media upload failed: access_token is empty
msg-24e3054f = DingTalk media upload failed:{ $res },{ $res_2 }
msg-34d0a11d = DingTalk media upload failed:{ $data }
msg-3b0d4fb5 = DingTalk voice message sending failed:{ $e }
msg-7187f424 = DingTalk video sending failed:{ $e }
msg-e40cc45f = DingTalk private chat reply failed: missing sender_staff_id
msg-be63618a = DingTalk adapter has been disabled.
msg-0ab22b13 = DingTalk robot startup failed:{ $e }

### astrbot/core/platform/sources/dingtalk/dingtalk_event.py

msg-eaa1f3e4 = DingTalk message sending failed: adapter missing

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py

msg-41a3e59d = Logging in to QQ Official Bot...
msg-66040e15 = Logged into the official QQ bot account:{ $res }
msg-6ed59b60 = Received qq_official_webhook callback:{ $msg }
msg-ad355b59 = { $signed }
msg-1f6260e4 = _parser unknown event %s.
msg-cef08b17 = Will be{ $res }Text to be translated:{ $res_2 }Port starts QQ official bot webhook adapter.

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_adapter.py

msg-3803e307 = [QQOfficialWebhook] No cached msg_id for session: %s, skip send_by_session
msg-08fd28cf = [QQOfficialWebhook] Unsupported message type for send_by_session: %s
msg-6fa95bb3 = Exception occurred during QQOfficialWebhook server shutdown:{ $exc }
msg-6f83eea0 = QQ bot official API adapter has been gracefully shut down

### astrbot/core/platform/sources/discord/discord_platform_event.py

msg-0056366b = [Discord] Failed to parse message chain:{ $e }
msg-fa0a9e40 = [Discord] Attempted to send an empty message, ignored.
msg-5ccebf9a = [Discord] Channel{ $res }Not a type of message that can be sent
msg-1550c1eb = [Discord] An unknown error occurred while sending the message:{ $e }
msg-7857133d = [Discord] Failed to retrieve channel{ $res }
msg-050aa8d6 = [Discord] Start processing Image component:{ $i }
msg-57c802ef = [Discord] Image component does not have a file attribute:{ $i }
msg-f2bea7ac = [Discord] Processing URL image:{ $file_content }
msg-c3eae1f1 = [Discord] Processing File URI:{ $file_content }
msg-6201da92 = [Discord] Image file does not exist:{ $path }
msg-2a6f0cd4 = [Discord] Processing Base64 URI
msg-b589c643 = [Discord] Attempt to process as raw Base64
msg-41dd4b8f = [Discord] Raw Base64 decoding failed, treating as local path:{ $file_content }
msg-f59778a1 = [Discord] An unknown critical error occurred while processing the image:{ $file_info }
msg-85665612 = [Discord] Failed to retrieve file, path does not exist:{ $file_path_str }
msg-e55956fb = [Discord] Failed to fetch file:{ $res }
msg-56cc0d48 = [Discord] Failed to process file:{ $res }, Error:{ $e }
msg-c0705d4e = [Discord] Ignored unsupported message component:{ $res }
msg-0417d127 = [Discord] Message content exceeds 2000 characters and will be truncated.
msg-6277510f = [Discord] Failed to add reaction:{ $e }

### astrbot/core/platform/sources/discord/client.py

msg-940888cb = [Discord] Client failed to load user information properly (self.user is None)
msg-9a3c1925 = [Discord] has been added as{ $res }(ID:{ $res_2 }) Sign in
msg-30c1f1c8 = [Discord] Client is ready.
msg-d8c03bdf = [Discord] on_ready_once_callback execution failed:{ $e }
msg-c9601653 = Bot is not ready: self.user is None
msg-4b017a7c = Interaction received without a valid user
msg-3067bdce = [Discord] Received original message from{ $res }Text to be translated:{ $res_2 }

### astrbot/core/platform/sources/discord/discord_platform_adapter.py

msg-7ea23347 = [Discord] Client not ready (self.client.user is None), cannot send message
msg-ff6611ce = [Discord] Invalid channel ID format:{ $channel_id_str }
msg-5e4e5d63 = [Discord] Can't get channel info for{ $channel_id_str }, will guess message type.
msg-32d4751b = [Discord] Received message:{ $message_data }
msg-8296c994 = [Discord] Bot Token is not configured. Please set the token correctly in the configuration file.
msg-170b31df = [Discord] Login failed. Please check if your Bot Token is correct.
msg-6678fbd3 = [Discord] Connection to Discord has been closed.
msg-cd8c35d2 = [Discord] An unexpected error occurred in the adapter runtime:{ $e }
msg-4df30f1d = [Discord] Client not ready (self.client.user is None), unable to process messages
msg-f7803502 = [Discord] Received a non-Message type message:{ $res }, ignored.
msg-134e70e9 = [Discord] Terminating adapter... (step 1: cancel polling task)
msg-5c01a092 = [Discord] polling_task has been canceled.
msg-77f8ca59 = [Discord] polling_task cancellation exception:{ $e }
msg-528b6618 = [Discord] Cleaning up registered slash commands... (step 2)
msg-d0b832e6 = [Discord] Command cleanup completed.
msg-43383f5e = [Discord] An error occurred while clearing commands:{ $e }
msg-b960ed33 = [Discord] Shutting down Discord client... (step 3)
msg-5e58f8a2 = [Discord] Client closed abnormally:{ $e }
msg-d1271bf1 = [Discord] Adapter has terminated.
msg-c374da7a = [Discord] Starting to collect and register slash commands...
msg-a6d37e4d = [Discord] Preparing to sync{ $res }commands:{ $res_2 }
msg-dbcaf095 = [Discord] No registerable commands found.
msg-09209f2f = [Discord] Command synchronization completed.
msg-a95055fd = [Discord] Callback function triggered:{ $cmd_name }
msg-55b13b1e = [Discord] Callback function parameters:{ $ctx }
msg-79f72e4e = [Discord] Callback function parameters:{ $params }
msg-22add467 = [Discord] Slash command '{ $cmd_name }Triggered. Original parameters:{ $params }'. Built command string: '{ $message_str_for_filter }Text to be translated:
msg-ccffc74a = [Discord] Command '{ $cmd_name }defer failed:{ $e }
msg-13402a28 = [Discord] Skipping non-compliant commands:{ $cmd_name }

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py

msg-859d480d = Handle request message failed:{ $e }
msg-6fb672e1 = Failed to handle notification message:{ $e }
msg-cf4687a3 = Handle group message failed:{ $e }
msg-3a9853e3 = Handle private message failed:{ $e }
msg-ec06dc3d = aiocqhttp (OneBot v11) adapter is connected.
msg-1304a54d = [aiocqhttp] RawMessage{ $event }
msg-93cbb9fa = { $err }
msg-a4487a03 = Failed to reply to the message:{ $e }
msg-48bc7bff = guessing lagrange
msg-6ab145a1 = Failed to get file:{ $ret }
msg-457454d7 = Failed to retrieve file:{ $e }This message segment will be ignored.
msg-7a299806 = Unable to construct Event object from reply message data:{ $reply_event_data }
msg-e6633a51 = Failed to get referenced message:{ $e }.
msg-6e99cb8d = Failed to get user information:{ $e }This message segment will be ignored.
msg-cf15fd40 = Unsupported message segment type, ignored:{ $t }, data={ $res }
msg-45d126ad = Message segment parsing failed: type={ $t }, data={ $res }.{ $e }
msg-394a20ae = aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port，将使用默认值：http://0.0.0.0:6199
msg-7414707c = The aiocqhttp adapter has been shut down.

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py

msg-0db8227d = Unable to send message: Missing valid numeric session_id{ $session_id }) or event({ $event }待翻译文本：

### astrbot/core/platform/sources/lark/server.py

msg-2f3bccf1 = encrypt_key is not configured, unable to decrypt event
msg-e77104e2 = [Lark Webhook] Received challenge verification request:{ $challenge }
msg-34b24fa1 = [Lark Webhook] Failed to parse request body:{ $e }
msg-ec0fe13e = [Lark Webhook] The request body is empty
msg-f69ebbdb = [Lark Webhook] Signature verification failed
msg-7ece4036 = [Lark Webhook] Decrypted event:{ $event_data }
msg-f2cb4b46 = [Lark Webhook] Decrypt event failed:{ $e }
msg-ef9f8906 = [Lark Webhook] Verification Token does not match.
msg-bedb2071 = [Lark Webhook] Failed to process event callback:{ $e }

### astrbot/core/platform/sources/lark/lark_event.py

msg-eefbe737 = [Lark] API Client im module not initialized
msg-a21f93fa = [Lark] When sending a message proactively, receive_id and receive_id_type cannot be empty.
msg-f456e468 = [Lark] Failed to send Lark message({ $res }):{ $res_2 }
msg-1eb66d14 = [Lark] File does not exist:{ $path }
msg-1df39b24 = [Lark] API Client IM module not initialized, unable to upload file
msg-2ee721dd = [Lark] Failed to upload file({ $res }):{ $res_2 }
msg-a04abf78 = [Lark] File uploaded successfully but no data returned (data is None)
msg-959e78a4 = [Lark] File upload successful:{ $file_key }
msg-901a2f60 = [Lark] Unable to open or upload file:{ $e }
msg-13065327 = [Lark] The image path is empty, unable to upload.
msg-37245892 = [Lark] Unable to open image file:{ $e }
msg-ad63bf53 = [Lark] API Client im module is not initialized, unable to upload image.
msg-ef90038b = Unable to upload Feishu images({ $res }):{ $res_2 }
msg-d2065832 = [Lark] Image uploaded successfully but no data returned (data is None)
msg-dbb635c2 = { $image_key }
msg-d4810504 = [Lark] File components detected, will be sent separately.
msg-45556717 = [Lark] Audio component detected, will send separately
msg-959070b5 = [Lark] Video component detected, will be sent separately.
msg-4e2aa152 = Feishu currently does not support message segments:{ $res }
msg-20d7c64b = [Lark] Failed to retrieve audio file path:{ $e }
msg-2f6f35e6 = [Lark] Audio file does not exist:{ $original_audio_path }
msg-528b968d = [Lark] Audio format conversion failed, will attempt direct upload:{ $e }
msg-fbc7efb9 = [Lark] Deleted converted audio file:{ $converted_audio_path }
msg-09840299 = [Lark] Failed to delete the converted audio file:{ $e }
msg-e073ff1c = [Lark] Unable to get video file path:{ $e }
msg-47e52913 = [Lark] The video file does not exist:{ $original_video_path }
msg-85ded1eb = [Lark] Video format conversion failed, will attempt direct upload:{ $e }
msg-b3bee05d = [Lark] Deleted converted video file:{ $converted_video_path }
msg-775153f6 = [Lark] Failed to delete the converted video file:{ $e }
msg-45038ba7 = [Lark] API Client im module not initialized, unable to send emoji
msg-8d475b01 = Failed to send Lark emoji reaction{ $res }):{ $res_2 }

### astrbot/core/platform/sources/lark/lark_adapter.py

msg-06ce76eb = No Feishu bot name set, @ bot may not get a reply.
msg-eefbe737 = [Lark] API Client im module not initialized
msg-236bcaad = [Lark] Failed to download message resource type={ $resource_type }, key={ $file_key }, code={ $res }, msg={ $res_2 }
msg-ef9a61fe = [Lark] No file stream included in the message resource response:{ $file_key }
msg-7b69a8d4 = [Lark] Image message missing message_id
msg-59f1694d = [Lark] Rich text video message is missing message_id
msg-af8f391d = [Lark] The file message is missing a message_id
msg-d4080b76 = [Lark] File message is missing file_key
msg-ab21318a = [Lark] Audio message is missing message_id
msg-9ec2c30a = [Lark] Audio message missing file_key
msg-0fa9ed18 = [Lark] Video message is missing message_id
msg-ae884c5c = [Lark] Video message missing file_key
msg-dac98a62 = [Lark] Failed to fetch quoted message id={ $parent_message_id }, code={ $res }, msg={ $res_2 }
msg-7ee9f7dc = [Lark] Quoted message response is empty id={ $parent_message_id }
msg-2b3b2db9 = [Lark] Failed to parse referenced message content id={ $quoted_message_id }
msg-c5d54255 = [Lark] Received empty event (event.event is None)
msg-82f041c4 = [Lark] No message body in the event (message is None)
msg-206c3506 = [Lark] The message content is empty
msg-876aa1d2 = [Lark] Failed to parse message content:{ $res }
msg-514230f3 = [Lark] The message content is not a JSON Object:{ $res }
msg-0898cf8b = [Lark] Parsing message content:{ $content_json_b }
msg-6a8bc661 = [Lark] Message missing message_id
msg-26554571 = [Lark] Incomplete sender information
msg-007d863a = [Lark Webhook] Skipped duplicate event:{ $event_id }
msg-6ce17e71 = [Lark Webhook] Unhandled event type:{ $event_type }
msg-8689a644 = [Lark Webhook] Failed to process event:{ $e }
msg-20688453 = [Lark] Webhook mode is enabled, but webhook_server is not initialized.
msg-f46171bc = [Lark] Webhook mode is enabled, but webhook_uuid is not configured.
msg-dd90a367 = Lark adapter is disabled.

### astrbot/core/platform/sources/wecom/wecom_event.py

msg-e164c137 = WeChat customer service message sending method not found.
msg-c114425e = WeChat customer service failed to upload the image:{ $e }
msg-a90bc15d = WeChat Customer Service Upload Image Return:{ $response }
msg-38298880 = WeChat customer service voice upload failed:{ $e }
msg-3aee0caa = WeChat customer service uploads voice and returns:{ $response }
msg-15e6381b = Failed to delete temporary audio file:{ $e }
msg-a79ae417 = WeChat customer service file upload failed:{ $e }
msg-374455ef = WeChat customer service file upload returns:{ $response }
msg-a2a133e4 = WeChat customer service failed to upload video:{ $e }
msg-2732fffd = WeChat customer service upload video returns:{ $response }
msg-60815f02 = Not yet implemented the sending logic for this message type:{ $res }
msg-9913aa52 = WeChat Work failed to upload the image:{ $e }
msg-9e90ba91 = WeChat Work upload image returns:{ $response }
msg-232af016 = Failed to upload voice message on WeChat Work:{ $e }
msg-e5b8829d = WeChat Work voice upload returns:{ $response }
msg-f68671d7 = Failed to upload file in WeCom:{ $e }
msg-8cdcc397 = WeChat Work upload file returns:{ $response }
msg-4f3e15f5 = Enterprise WeChat video upload failed:{ $e }
msg-4e9aceea = Enterprise WeChat upload video returns:{ $response }

### astrbot/core/platform/sources/wecom/wecom_adapter.py

msg-d4bbf9cb = Verify request validity:{ $res }
msg-f8694a8a = Verification of request validity successful.
msg-8f4cda74 = Verification of request validity failed, signature exception, please check configuration.
msg-46d3feb9 = Decryption failed, signature exception, please check the configuration.
msg-4d1dfce4 = Parse successful:{ $msg }
msg-a98efa4b = Will be{ $res }Text to translate:{ $res_2 }Port startup WeChat Work adapter.
msg-a616d9ce = WeChat Work customer service mode does not support sending messages actively via send_by_session.
msg-5d01d7b9 = send_by_session failed: Unable to send for session{ $res }Infer agent_id.
msg-3f05613d = Retrieved WeChat customer service list:{ $acc_list }
msg-8fd19bd9 = Failed to get WeChat customer service, open_kfid is empty.
msg-5900d9b6 = Found open_kfid:{ $open_kfid }
msg-391119b8 = Please open the following link and scan the QR code with WeChat to get the customer service WeChat account: https://api.cl2wm.cn/api/qrcode/code?text={ $kf_url }
msg-5bdf8f5c = { $e }
msg-93c9125e = Failed to convert audio:{ $e }If ffmpeg is not installed, please install it first.
msg-b2f7d1dc = Unimplemented events:{ $res }
msg-61480a61 = abm:{ $abm }
msg-42431e46 = Unimplemented WeChat customer service message event:{ $msg }
msg-fbca491d = WeChat Work Adapter has been disabled

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_event.py

msg-fa7f7afc = split plain into{ $res }chunks for passive reply. Message not sent.
msg-59231e07 = WeChat Public Platform failed to upload image:{ $e }
msg-d3968fc5 = WeChat Public Platform upload image returns:{ $response }
msg-7834b934 = WeChat Official Account Platform upload voice failed:{ $e }
msg-4901d769 = WeChat Official Account Platform Upload Audio Return:{ $response }
msg-15e6381b = Failed to delete temporary audio file:{ $e }
msg-60815f02 = The sending logic for this message type has not been implemented yet:{ $res }

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_adapter.py

msg-d4bbf9cb = Verify request validity:{ $res }
msg-b2edb1b2 = Unknown response, please check if the callback address is filled in correctly.
msg-f8694a8a = Request validation successful.
msg-8f4cda74 = Failed to validate request effectiveness, signature exception, please check configuration.
msg-46d3feb9 = Decryption failed, signature abnormal, please check the configuration.
msg-e23d8bff = Parsing failed. The msg is None.
msg-4d1dfce4 = Parse succeeded:{ $msg }
msg-193d9d7a = User message buffer status: user={ $from_user }state={ $state }
msg-57a3c1b2 = wx buffer hit on trigger: user={ $from_user }
msg-bed995d9 = wx buffer hit on retry window: user={ $from_user }
msg-3a94b6ab = wx finished message sending in passive window: user={ $from_user }msg_id={ $msg_id }
msg-50c4b253 = wx finished message sending in passive window but not final: user={ $from_user }msg_id={ $msg_id }
msg-7d8b62e7 = wx finished in window but not final; return placeholder: user={ $from_user }msg_id={ $msg_id }
msg-2b9b8aed = wx task failed in passive window
msg-7bdf4941 = wx passive window timeout: user={ $from_user }msg_id={ $msg_id }
msg-98489949 = wx trigger while thinking: user={ $from_user }
msg-01d0bbeb = wx new trigger: user={ $from_user }msg_id={ $msg_id }
msg-52bb36cd = wx start task: user={ $from_user }msg_id={ $msg_id }preview={ $preview }
msg-ec9fd2ed = wx buffer hit immediately: user={ $from_user }
msg-61c91fb9 = wx not finished in first window; return placeholder: user={ $from_user }msg_id={ $msg_id }
msg-35604bba = wx task failed in first window
msg-e56c4a28 = wx first window timeout: user={ $from_user }msg_id={ $msg_id }
msg-e163be40 = Will be{ $res }Text to translate:{ $res_2 }Port startup WeChat public platform adapter.
msg-c1740a04 = duplicate message id checked:{ $res }
msg-04718b37 = Got future result:{ $result }
msg-296e66c1 = callback message processing timeout: message_id={ $res }
msg-eb718c92 = An exception occurred while converting the message:{ $e }
msg-93c9125e = Failed to convert audio:{ $e }If ffmpeg is not installed, please install it first.
msg-b2f7d1dc = Unimplemented events:{ $res }
msg-61480a61 = abm:{ $abm }
msg-2e7e0187 = User message buffering status not found, unable to process message: user={ $res }Message ID={ $res_2 }
msg-84312903 = WeChat Public Platform adapter has been disabled

### astrbot/core/platform/sources/misskey/misskey_adapter.py

msg-7bacee77 = [Misskey] Configuration is incomplete, cannot start.
msg-99cdf3d3 = [Misskey] Connected users:{ $res }(ID:{ $res_2 }Text to be translated: )
msg-5579c974 = [Misskey] Failed to retrieve user information:{ $e }
msg-d9547102 = [Misskey] API client not initialized
msg-341b0aa0 = [Misskey] WebSocket connected (Attempt #{ $connection_attempts })
msg-c77d157b = [Misskey] Chat channel subscribed
msg-a0c5edc0 = [Misskey] WebSocket connection failed (attempt #{ $connection_attempts })
msg-1958faa8 = [Misskey] WebSocket Exception (Attempt #{ $connection_attempts }):{ $e }
msg-1b47382d = [Misskey]{ $sleep_time }Reconnect in seconds (next attempt #{ $res })
msg-a10a224d = [Misskey] Received notification event: type={ $notification_type }, user_id={ $res }
msg-7f0abf4a = [Misskey] Processing post mentions:{ $res }...
msg-2da7cdf5 = [Misskey] Failed to process notification:{ $e }
msg-6c21d412 = [Misskey] Received chat event: sender_id={ $sender_id }, room_id={ $room_id }, is_self={ $res }
msg-68269731 = [Misskey] Checking group chat messages: '{ $raw_text }', Bot username: '{ $res }Text to translate:
msg-585aa62b = [Misskey] Processing group chat message:{ $res }...
msg-426c7874 = [Misskey] Processing private message:{ $res }...
msg-f5aff493 = [Misskey] Failed to process chat message:{ $e }
msg-ea465183 = [Misskey] Unhandled event received: type={ $event_type }, channel={ $res }
msg-8b69eb93 = [Misskey] Message content is empty and no file components, skipping send.
msg-9ba9c4e5 = [Misskey] Temporary files cleaned:{ $local_path }
msg-91af500e = [Misskey] The number of files exceeds the limit{ $res }>{ $MAX_FILE_UPLOAD_COUNT }Only upload the first{ $MAX_FILE_UPLOAD_COUNT }file
msg-9746d7f5 = [Misskey] An exception occurred during concurrent uploads; continuing to send text.
msg-d6dc928c = [Misskey] Chat messages only support a single file, ignoring the rest{ $res }files
msg-af584ae8 = [Misskey] Parsing visibility: visibility={ $visibility }, visible_user_ids={ $visible_user_ids }, session_id={ $session_id }, user_id_for_cache={ $user_id_for_cache }
msg-1a176905 = [Misskey] Failed to send message:{ $e }

### astrbot/core/platform/sources/misskey/misskey_api.py

msg-fab20f57 = aiohttp and websockets are required for Misskey API. Please install them with: pip install aiohttp websockets
msg-f2eea8e1 = [Misskey WebSocket] Connected
msg-5efd11a2 = [Misskey WebSocket] Resubscribe{ $channel_type }Failure:{ $e }
msg-b70e2176 = [Misskey WebSocket] Connection failed:{ $e }
msg-b9f3ee06 = [Misskey WebSocket] Connection disconnected
msg-7cd98e54 = WebSocket is not connected
msg-43566304 = [Misskey WebSocket] Failed to parse message:{ $e }
msg-e617e390 = [Misskey WebSocket] Failed to process message:{ $e }
msg-c60715cf = [Misskey WebSocket] Connection closed unexpectedly:{ $e }
msg-da9a2a17 = [Misskey WebSocket] Connection closed (Code:{ $res }, Reason:{ $res_2 })
msg-bbf6a42e = [Misskey WebSocket] Handshake failed:{ $e }
msg-254f0237 = [Misskey WebSocket] Failed to listen to messages:{ $e }
msg-49f7e90e = { $channel_summary }
msg-630a4832 = [Misskey WebSocket] Channel Message:{ $channel_id }Event Type:{ $event_type }
msg-0dc61a4d = [Misskey WebSocket] Using handler:{ $handler_key }
msg-012666fc = [Misskey WebSocket] Using event handler:{ $event_type }
msg-e202168a = [Misskey WebSocket] Handler not found:{ $handler_key }Or{ $event_type }
msg-a397eef1 = [Misskey WebSocket] Direct Message Handler:{ $message_type }
msg-a5f12225 = [Misskey WebSocket] Unhandled message type:{ $message_type }
msg-ad61d480 = [Misskey API]{ $func_name }Retry{ $max_retries }Failed again after retry:{ $e }
msg-7de2ca49 = [Misskey API]{ $func_name }Page{ $attempt }Secondary retry failed:{ $e }Text to be translated:{ $sleep_time }Retry after s
msg-f5aecf37 = [Misskey API]{ $func_name }Encountered a non-retryable exception:{ $e }
msg-e5852be5 = [Misskey API] Client has closed
msg-21fc185c = [Misskey API] Request parameter error:{ $endpoint }(HTTP{ $status })
msg-5b106def = Bad request for{ $endpoint }
msg-28afff67 = [Misskey API] Unauthorized access:{ $endpoint }(HTTP{ $status })
msg-e12f2d28 = Unauthorized access for{ $endpoint }
msg-beda662d = [Misskey API] Access Denied:{ $endpoint }(HTTP{ $status }Text to be translated:
msg-795ca227 = Forbidden access for{ $endpoint }
msg-5c6ba873 = [Misskey API] Resource not found:{ $endpoint }(HTTP{ $status })
msg-74f2bac2 = Resource not found for{ $endpoint }
msg-9ceafe4c = [Misskey API] Request body too large:{ $endpoint }(HTTP{ $status }Text to be translated:
msg-3e336b73 = Request entity too large{ $endpoint }
msg-a47067de = [Misskey API] Request rate limit:{ $endpoint }(HTTP{ $status }Text to be translated:
msg-901dc2da = Rate limit exceeded for{ $endpoint }
msg-2bea8c2e = [Misskey API] Server internal error:{ $endpoint }(HTTP{ $status }待翻译文本：
msg-ae8d3725 = Internal server error for{ $endpoint }
msg-7b028462 = [Misskey API] Gateway Error:{ $endpoint }(HTTP{ $status })
msg-978414ef = Bad gateway for{ $endpoint }
msg-50895a69 = [Misskey API] Service Unavailable:{ $endpoint }(HTTP{ $status })
msg-62adff89 = Service unavailable for{ $endpoint }
msg-1cf15497 = [Misskey API] Gateway Timeout:{ $endpoint }(HTTP{ $status })
msg-a8a2578d = Gateway timeout for{ $endpoint }
msg-c012110a = [Misskey API] Unknown error:{ $endpoint }(HTTP{ $status }Text to be translated:
msg-dc96bbb8 = HTTP{ $status }for{ $endpoint }
msg-4c7598b6 = [Misskey API] Fetched{ $res }New notification
msg-851a2a54 = [Misskey API] Request successful:{ $endpoint }
msg-5f5609b6 = [Misskey API] Invalid response format:{ $e }
msg-c8f7bbeb = Invalid JSON response
msg-82748b31 = [Misskey API] Request failed:{ $endpoint }- HTTP{ $res }, Response:{ $error_text }
msg-c6de3320 = [Misskey API] Request failed:{ $endpoint }- HTTP{ $res }
msg-affb19a7 = [Misskey API] HTTP request error:{ $e }
msg-9f1286b3 = HTTP request failed:{ $e }
msg-44f91be2 = [Misskey API] Post successfully sent:{ $note_id }
msg-fbafd3db = No file path provided for upload
msg-872d8419 = [Misskey API] Local file does not exist:{ $file_path }
msg-37186dea = File not found:{ $file_path }
msg-65ef68e0 = [Misskey API] Local file upload successful:{ $filename }->{ $file_id }
msg-0951db67 = [Misskey API] Network error in file upload:{ $e }
msg-e3a322f5 = Upload failed:{ $e }
msg-f28772b9 = No MD5 hash provided for find-by-hash
msg-25e566ef = [Misskey API] find-by-hash request: md5={ $md5_hash }
msg-a036a942 = [Misskey API] find-by-hash response: Found{ $res }files
msg-ea3581d5 = [Misskey API] Failed to find file by hash:{ $e }
msg-1d2a84ff = No name provided for find
msg-f25e28b4 = [Misskey API] find request: name={ $name }, folder_id={ $folder_id }
msg-cd43861a = [Misskey API] find response: found{ $res }files
msg-05cd55ef = [Misskey API] Failed to find file by name:{ $e }
msg-c01052a4 = [Misskey API] List file request: limit={ $limit }, folder_id={ $folder_id }, type={ $type }
msg-7c81620d = [Misskey API] List files response: Found{ $res }files
msg-a187a089 = [Misskey API] Failed to list files:{ $e }
msg-9e776259 = No existing session available
msg-de18c220 = URL cannot be empty
msg-25b15b61 = [Misskey API] SSL certificate download failed:{ $ssl_error }, retry without verifying SSL
msg-b6cbeef6 = [Misskey API] Local upload successful:{ $res }
msg-a4a898e2 = [Misskey API] Local upload failed:{ $e }
msg-46b7ea4b = [Misskey API] Chat message sent successfully:{ $message_id }
msg-32f71df4 = [Misskey API] Room message sent successfully:{ $message_id }
msg-7829f3b3 = [Misskey API] Chat message response format is abnormal:{ $res }
msg-d74c86a1 = [Misskey API] Mention notification response format is abnormal:{ $res }
msg-65ccb697 = Message content cannot be empty: text or media file is required.
msg-b6afb123 = [Misskey API] URL media upload succeeded:{ $res }
msg-4e62bcdc = [Misskey API] URL media upload failed:{ $url }
msg-71cc9d61 = [Misskey API] URL media processing failed{ $url }Text to be translated:{ $e }
msg-75890c2b = [Misskey API] Local file upload successful:{ $res }
msg-024d0ed5 = [Misskey API] Local file upload failed:{ $file_path }
msg-f1fcb5e1 = [Misskey API] Local file processing failed{ $file_path }Text to translate:{ $e }
msg-1ee80a6b = Unsupported message type:{ $message_type }

### astrbot/core/platform/sources/misskey/misskey_event.py

msg-85cb7d49 = [MisskeyEvent] send method was called, message chain contains{ $res }Components
msg-252c2fca = [MisskeyEvent] Check adapter method: hasattr(self.client, 'send_by_session') ={ $res }
msg-44d7a060 = [MisskeyEvent] Calling the adapter's send_by_session method
msg-b6e08872 = [MisskeyEvent] Content is empty, skipping send
msg-8cfebc9c = [MisskeyEvent] Create new post
msg-ed0d2ed5 = [MisskeyEvent] Sending failed:{ $e }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_webhook.py

msg-a5c90267 = Message push webhook URL cannot be empty
msg-76bfb25b = Message push webhook URL missing key parameter
msg-3545eb07 = Webhook request failed: HTTP{ $res }{ $text }
msg-758dfe0d = Webhook returned an error:{ $res } { $res_2 }
msg-c056646b = Enterprise WeChat message push successful: %s
msg-73d3e179 = File does not exist:{ $file_path }
msg-774a1821 = Upload media failed: HTTP{ $res }待翻译文本：,{ $text }
msg-6ff016a4 = Upload media failed:{ $res } { $res_2 }
msg-0e8252d1 = Upload media failed: Return missing media_id
msg-9dbc2296 = File message missing valid file path, skipped: %s
msg-2e567c36 = Failed to clean up temporary voice files %s: %s
msg-e99c4df9 = Enterprise WeChat message push does not currently support component type %s, skipped.

### astrbot/core/platform/sources/wecom_ai_bot/WXBizJsonMsgCrypt.py

msg-5bdf8f5c = { $e }
msg-fe69e232 = receiveid not match
msg-00b71c27 = signature not match
msg-5cfb5c20 = { $signature }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_event.py

msg-e44e77b0 = Image data is empty, skipping.
msg-30d116ed = Failed to process image message: %s
msg-31b11295 = [WecomAI] Unsupported message component type:{ $res }, skip

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_adapter.py

msg-277cdd37 = Enterprise WeChat message push webhook configuration invalid: %s
msg-2102fede = An exception occurred while processing the queue message:{ $e }
msg-d4ea688d = Message type unknown, ignored:{ $message_data }
msg-15ba426f = Exception occurred while processing message: %s
msg-740911ab = Stream already finished, returning end message:{ $stream_id }
msg-9fdbafe9 = Cannot find back queue for stream_id:{ $stream_id }
msg-7a52ca2b = No new messages in back queue for stream_id:{ $stream_id }
msg-9ffb59fb = Aggregated content:{ $latest_plain_content }, image:{ $res }finish:{ $finish }
msg-de9ff585 = Stream message sent successfully, stream_id:{ $stream_id }
msg-558310b9 = Message encryption failed
msg-251652f9 = An exception occurred while processing the welcome message: %s
msg-480c5dac = [WecomAI] Message enqueued:{ $stream_id }
msg-f595dd6e = Failed to process encrypted image:{ $result }
msg-e8beeb3d = WecomAIAdapter:{ $res }
msg-6f8ad811 = Active message sending failed: Enterprise WeChat message push Webhook URL not configured, please go to configuration to add. session_id=%s
msg-84439b09 = Enterprise WeChat message push failed (session=%s): %s
msg-f70f5008 = Start the WeChat Work smart robot adapter, listening on %s:%d
msg-87616945 = Enterprise WeChat intelligent robot adapter is shutting down...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_api.py

msg-86f6ae9f = Message decryption failed, error code:{ $ret }
msg-45ad825c = Decryption successful, message content:{ $message_data }
msg-84c476a7 = JSON parsing failed:{ $e }Original message:{ $decrypted_msg }
msg-c0d8c5f9 = Decrypted message is empty
msg-a08bcfc7 = Decryption process exception occurred:{ $e }
msg-4dfaa613 = Message encryption failed, error code:{ $ret }
msg-6e566b12 = Message encrypted successfully
msg-39bf8dba = Encryption process exception occurred:{ $e }
msg-fa5be7c5 = URL verification failed, error code:{ $ret }
msg-813a4e4e = URL verification successful
msg-65ce0d23 = An exception occurred during URL validation:{ $e }
msg-b1aa892f = Start downloading encrypted image:{ $image_url }
msg-10f72727 = { $error_msg }
msg-70123a82 = Image downloaded successfully, size:{ $res }Byte
msg-85d2dba1 = AES key cannot be empty
msg-67c4fcea = Invalid AES key length: should be 32 bytes
msg-bde4bb57 = Invalid padding length (greater than 32 bytes)
msg-63c22912 = Image decryption successful, decrypted size:{ $res }Byte
msg-6ea489f0 = Text message parsing failed
msg-eb12d147 = Image message parsing failed
msg-ab1157ff = Stream message parsing failed
msg-e7e945d1 = Mixed message parsing failed
msg-06ada9dd = Event message parsing failed

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_server.py

msg-adaee66c = URL validation parameter missing
msg-742e0b43 = Received a verification request for the Enterprise WeChat Smart Bot WebHook URL.
msg-f86c030c = Message callback parameters are missing
msg-cce4e44c = Message received callback, msg_signature={ $msg_signature }, timestamp={ $timestamp }, nonce={ $nonce }
msg-7f018a3c = Message decryption failed, error code: %d
msg-9d42e548 = Message handler execution exception: %s
msg-15ba426f = An exception occurred while processing the message: %s
msg-5bf7dffa = Starting the enterprise WeChat intelligent robot server, listening on %s:%d
msg-445921d5 = Server running abnormally: %s
msg-3269840c = Enterprise WeChat intelligent robot server is shutting down...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_queue_mgr.py

msg-8be03d44 = [WecomAI] Creating input queue:{ $session_id }
msg-9804296a = [WecomAI] Creating output queue:{ $session_id }
msg-bdf0fb78 = [WecomAI] Remove Output Queue:{ $session_id }
msg-40f6bb7b = [WecomAI] Remove pending response:{ $session_id }
msg-fbb807cd = [WecomAI] Stream marking has ended:{ $session_id }
msg-9d7f5627 = [WecomAI] Remove from input queue:{ $session_id }
msg-7637ed00 = [WecomAI] Set pending response:{ $session_id }
msg-5329c49b = [WecomAI] Cleaning up expired responses and queues:{ $session_id }
msg-09f098ea = [WecomAI] Starting listener for conversation:{ $session_id }
msg-c55856d6 = Processing sessions{ $session_id }An error occurred while messaging:{ $e }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_utils.py

msg-14d01778 = JSON parsing failed:{ $e }Original string:{ $json_str }
msg-df346cf5 = Start downloading encrypted image: %s
msg-cb266fb3 = Image downloaded successfully, size: %d bytes
msg-10f72727 = { $error_msg }
msg-1d91d2bb = AES key cannot be empty
msg-bb32bedd = Invalid AES key length: must be 32 bytes
msg-bde4bb57 = Invalid padding length (greater than 32 bytes)
msg-3cf2120e = Image decryption successful, decrypted size: %d bytes
msg-3f8ca8aa = Image has been converted to base64 encoding, encoded length: %d

### astrbot/core/platform/sources/line/line_api.py

msg-06e3f874 = [LINE] %s message failed: status=%s body=%s
msg-1478c917 = [LINE] %s message request failed: %s
msg-39941f06 = [LINE] get content retry failed: message_id=%s status=%s body=%s
msg-1fe70511 = [LINE] get content failed: message_id=%s status=%s body=%s

### astrbot/core/platform/sources/line/line_event.py

msg-4068a191 = [LINE] Failed to resolve image URL: %s
msg-2233b256 = [LINE] Failed to resolve record URL: %s
msg-a7455817 = [LINE] resolve record duration failed: %s
msg-9d0fee66 = [LINE] Failed to resolve video URL: %s
msg-3b8ea946 = [LINE] resolve video cover failed: %s
msg-aea2081a = [LINE] Failed to generate video preview: %s
msg-af426b7e = [LINE] resolve file url failed: %s
msg-fe44c12d = [LINE] resolve file size failed: %s
msg-d6443173 = [LINE] message count exceeds 5, extra segments will be dropped.

### astrbot/core/platform/sources/line/line_adapter.py

msg-68539775 = The LINE adapter requires channel_access_token and channel_secret.
msg-30c67081 = [LINE] webhook_uuid is empty, the unified webhook may not be able to receive messages.
msg-64e92929 = [LINE] invalid webhook signature
msg-71bc0b77 = [LINE] invalid webhook body: %s
msg-8c7d9bab = [LINE] duplicate event skipped: %s

### astrbot/core/platform/sources/telegram/tg_event.py

msg-7757f090 = [Telegram] Failed to send chat action:{ $e }
msg-80b075a3 = User privacy settings prevent receiving voice messages, falling back to sending an audio file. To enable voice messages, go to Telegram Settings → Privacy and Security → Voice Messages → set to 'Everyone'.
msg-20665ad1 = MarkdownV2 send failed:{ $e }. Using plain text instead.
msg-323cb67c = [Telegram] Failed to add reaction:{ $e }
msg-abe7fc3d = Edit message failed(streaming-break):{ $e }
msg-f7d40103 = Unsupported message type:{ $res }
msg-d4b50a96 = Edit message failed (streaming):{ $e }
msg-2701a78f = Failed to send message (streaming):{ $e }
msg-2a8ecebd = Markdown conversion failed, using plain text:{ $e }

### astrbot/core/platform/sources/telegram/tg_adapter.py

msg-cb53f79a = Telegram base url:{ $res }
msg-e6b6040f = Telegram Updater is not initialized. Cannot start polling.
msg-2c4b186e = Telegram Platform Adapter is running.
msg-908d0414 = Error occurred while registering command to Telegram:{ $e }
msg-d2dfe45e = Command name '{ $cmd_name }Duplicate registration, will use the first registration definition:{ $res }Text to translate:
msg-63bdfab8 = Received a start command without an effective chat, skipping /start reply.
msg-03a27b01 = Telegram message:{ $res }
msg-e47b4bb4 = Received an update without a message.
msg-c97401c6 = [Telegram] Received a message without a from_user.
msg-f5c839ee = Telegram document file_path is None, cannot save the file{ $file_name }.
msg-dca991a9 = Telegram video file_path is None, cannot save the file{ $file_name }.
msg-56fb2950 = Create media group cache:{ $media_group_id }
msg-0de2d4b5 = Add message to media group{ $media_group_id }currently has{ $res }items.
msg-9e5069e9 = Media group{ $media_group_id }has reached max wait time ({ $elapsed }s >={ $res }s), processing immediately.
msg-9156b9d6 = Scheduled media group{ $media_group_id }to be processed in{ $delay }seconds (already waited{ $elapsed }s)
msg-2849c882 = Media group{ $media_group_id }not found in cache
msg-c75b2163 = Media group{ $media_group_id }is empty
msg-0a3626c1 = Processing media group{ $media_group_id }, total{ $res }items
msg-2842e389 = Failed to convert the first message of media group{ $media_group_id }
msg-32fbf7c1 = Added{ $res }Components to media group{ $media_group_id }
msg-23bae28a = Telegram adapter has been closed.
msg-e46e7740 = Error occurred while closing Telegram adapter:{ $e }

### astrbot/core/platform/sources/slack/client.py

msg-1d6b68b9 = Slack request signature verification failed
msg-53ef18c3 = Received Slack event:{ $event_data }
msg-58488af6 = Error processing Slack event:{ $e }
msg-477be979 = Slack Webhook server is starting, listening{ $res }Text to be translated:{ $res_2 }{ $res_3 }...
msg-639fee6c = Slack Webhook server has stopped
msg-a238d798 = Socket client is not initialized
msg-4e6de580 = Error occurred while handling Socket Mode event:{ $e }
msg-5bb71de9 = Slack Socket Mode client is starting...
msg-f79ed37f = Slack Socket Mode client has stopped

### astrbot/core/platform/sources/slack/slack_adapter.py

msg-c34657ff = The Slack bot_token is required.
msg-64f8a45d = Socket Mode requires an app_token
msg-a2aba1a7 = Webhook Mode requires signing_secret
msg-40e00bd4 = Failed to send Slack message:{ $e }
msg-56c1d0a3 = [slack] RawMessage{ $event }
msg-855510b4 = Failed to download Slack file:{ $res } { $res_2 }
msg-04ab2fae = Failed to download file:{ $res }
msg-79ed7e65 = Slack auth test OK. Bot ID:{ $res }
msg-ec27746a = Slack Adapter (Socket Mode) is starting...
msg-34222d3a = Slack Adapter (Webhook Mode) Starting, Listening{ $res }Text to be translated:{ $res_2 }{ $res_3 }...
msg-6d8110d2 = Unsupported connection mode:{ $res }, please use 'socket' or 'webhook'
msg-d71e7f36 = Slack adapter has been closed.

### astrbot/core/platform/sources/slack/slack_event.py

msg-b233107c = Slack file upload failed:{ $res }
msg-596945d1 = Slack file upload response:{ $response }

### astrbot/core/platform/sources/satori/satori_adapter.py

msg-ab7db6d9 = Satori WebSocket connection closed:{ $e }
msg-4ef42cd1 = Satori WebSocket connection failed:{ $e }
msg-b50d159b = Maximum retry count reached ({ $max_retries })，stop retrying
msg-89de477c = Satori adapter is connecting to WebSocket:{ $res }
msg-cfa5b059 = Satori Adapter HTTP API Address:{ $res }
msg-d534864b = Invalid WebSocket URL:{ $res }
msg-a110f9f7 = WebSocket URL must start with ws:// or wss://{ $res }
msg-bf43ccb6 = Satori encountered an error while processing the message:{ $e }
msg-89081a1a = Satori WebSocket connection exception:{ $e }
msg-5c04bfcd = Satori WebSocket closed abnormally:{ $e }
msg-b67bcee0 = WebSocket connection not established
msg-89ea8b76 = WebSocket connection has been closed
msg-4c8a40e3 = Connection closed while sending IDENTIFY signal:{ $e }
msg-05a6b99d = Failed to send IDENTIFY signal:{ $e }
msg-c9b1b774 = Satori WebSocket heartbeat sending failed:{ $e }
msg-61edb4f3 = Heartbeat task exception:{ $e }
msg-7db44899 = Satori Connection Successful - Bot{ $res }platform={ $platform }, user_id={ $user_id }, user_name={ $user_name }
msg-01564612 = Failed to parse WebSocket message:{ $e }, Message content:{ $message }
msg-3a1657ea = Exception processing WebSocket message:{ $e }
msg-dc6b459c = Processing event failed:{ $e }
msg-6524f582 = Error occurred while parsing <quote> tag:{ $e }, Error content:{ $content }
msg-3be535c3 = Failed to convert Satori message:{ $e }
msg-be17caf1 = XML parsing failed, using regex extraction:{ $e }
msg-f6f41d74 = Error occurred when extracting <quote> tags:{ $e }
msg-ca6dca7f = Failed to convert reference message:{ $e }
msg-cd3b067e = Parsing error occurred while parsing Satori element:{ $e }, Error content:{ $content }
msg-03071274 = An unknown error occurred while parsing the Satori element:{ $e }
msg-775cd5c0 = HTTP session is not initialized
msg-e354c8d1 = Satori HTTP request exception:{ $e }

### astrbot/core/platform/sources/satori/satori_event.py

msg-c063ab8a = Satori message sending exception:{ $e }
msg-9bc42a8d = Satori message sending failed
msg-dbf77ca2 = Failed to convert image to base64:{ $e }
msg-8b6100fb = Satori streaming message sending exception:{ $e }
msg-3c16c45c = Failed to convert voice to base64:{ $e }
msg-66994127 = Video file conversion failed:{ $e }
msg-30943570 = Failed to convert message component:{ $e }
msg-3e8181fc = Failed to convert forwarding node:{ $e }
msg-d626f831 = Failed to convert and forward the merged message:{ $e }

### astrbot/core/platform/sources/webchat/webchat_queue_mgr.py

msg-4af4f885 = Started listener for conversation:{ $conversation_id }
msg-10237240 = Error processing message from conversation{ $conversation_id }Text to be translated:{ $e }

### astrbot/core/platform/sources/webchat/webchat_adapter.py

msg-9406158c = WebChatAdapter:{ $res }

### astrbot/core/platform/sources/webchat/webchat_event.py

msg-6b37adcd = webchat ignore:{ $res }

### astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py

msg-8af45ba1 = QQ Bot Official API Adapter does not support send_by_session
msg-8ebd1249 = Unknown message type:{ $message_type }
msg-c165744d = QQ Official Bot Interface Adapter has been gracefully shut down

### astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py

msg-28a74d9d = [QQOfficial] Skip botpy FormData patch.
msg-c0b123f6 = Error sending streaming message:{ $e }
msg-05d6bba5 = [QQOfficial] Unsupported message source type:{ $res }
msg-e5339577 = [QQOfficial] GroupMessage is missing group_openid
msg-71275806 = Message sent to C2C:{ $ret }
msg-040e7942 = [QQOfficial] markdown sending was rejected, falling back to content mode for retry.
msg-9000f8f7 = Invalid upload parameters
msg-d72cffe7 = Failed to upload image, response is not dict:{ $result }
msg-5944a27c = Upload file response format error:{ $result }
msg-1e513ee5 = Upload request error:{ $e }
msg-f1f1733c = Failed to post c2c message, response is not dict:{ $result }
msg-9b8f9f70 = Unsupported image file format
msg-24eb302a = Error converting audio format: audio duration is not greater than 0
msg-b49e55f9 = Error processing voice:{ $e }
msg-6e716579 = qq_official ignore{ $res }

### astrbot/core/provider/provider.py

msg-e6f0c96f = Provider type{ $provider_type_name }not registered
msg-c7953e3f = Batch{ $batch_idx }Processing failed, retried{ $max_retries }Second:{ $e }
msg-10f72727 = { $error_msg }
msg-7ff71721 = Rerank provider test failed, no results returned

### astrbot/core/provider/register.py

msg-19ddffc0 = Detected a large model provider adapter{ $provider_type_name }Already registered, possibly due to a naming conflict in the adapter type of the large model provider.
msg-7e134b0d = Service Provider{ $provider_type_name }Registered

### astrbot/core/provider/func_tool_manager.py

msg-0c42a4d9 = Add function call tool:{ $name }
msg-e8fdbb8c = MCP service configuration file not found, a default configuration file has been created.{ $mcp_json_file }
msg-cf8aed84 = Received MCP client{ $name }Termination signal
msg-3d7bcc64 = Initializing MCP Client{ $name }Failed
msg-1b190842 = MCP server{ $name }list tools response:{ $tools_res }
msg-6dc4f652 = Connected to MCP service{ $name }, Tools:{ $tool_names }
msg-a44aa4f2 = Clear MCP client resources{ $name }Text to be translated:{ $e }.
msg-e9c96c53 = MCP service has been disabled.{ $name }
msg-10f72727 = { $error_msg }
msg-85f156e0 = Testing MCP server connection with config:{ $config }
msg-93c54ce0 = Cleaning up MCP client after testing connection.
msg-368450ee = The plugin to which this function call tool belongs{ $res }Disabled. Please enable this tool in the admin panel first.
msg-4ffa2135 = Failed to load MCP configuration:{ $e }
msg-a486ac39 = Failed to save MCP configuration:{ $e }
msg-58dfdfe7 = Synchronized from ModelScope{ $synced_count }MCP Servers
msg-75f1222f = No available ModelScope MCP server found
msg-c9f6cb1d = ModelScope API request failed: HTTP{ $res }
msg-c8ebb4f7 = Network connection error:{ $e }
msg-0ac6970f = Error occurred while synchronizing ModelScope MCP server:{ $e }

### astrbot/core/provider/entities.py

msg-7fc6f623 = Image{ $image_url }The obtained result is empty and will be ignored.

### astrbot/core/provider/manager.py

msg-9e1a7f1f = Provider{ $provider_id }Does not exist, cannot be set.
msg-5fda2049 = Unknown provider type:{ $provider_type }
msg-a5cb19c6 = No ID found for{ $provider_id }The provider, which might be due to you having modified the provider (model) ID.
msg-78b9c276 = { $res }
msg-5bdf8f5c = { $e }
msg-b734a1f4 = Provider{ $provider_id }Configuration item key[{ $idx }] Use environment variables{ $env_key }but not set.
msg-664b3329 = Provider{ $res }is disabled, skipping
msg-f43f8022 = Loading{ $res }Text to translate: ({ $res_2 }Service Provider ...
msg-edd4aefe = Loading{ $res }({ $res_2 }) Provider adapter failed:{ $e }It might be due to uninstalled dependencies.
msg-78e514a1 = Loading{ $res }({ $res_2 }) Provider adapter failed:{ $e }Unknown reason
msg-4636f83c = No applicable{ $res }Text to translate:{ $res_2 }) provider adapter, please check if it is already installed or if the name is entered incorrectly. Skipped.
msg-e9c6c4a2 = Unable to find{ $res }class
msg-f705cf50 = Provider class{ $cls_type }is not a subclass of STTProvider
msg-d20620aa = Selected{ $res }Text to be translated:{ $res_2 }) as the current speech-to-text provider adapter.
msg-afbe5661 = Provider class{ $cls_type }is not a subclass of TTSProvider
msg-74d437ed = Selected{ $res }Text to translate:{ $res_2 }) as the current text-to-speech provider adapter.
msg-08cd85c9 = Provider class{ $cls_type }is not a subclass of Provider
msg-16a2b8e0 = Selected{ $res }({ $res_2 }) as the current provider adapter.
msg-0e1707e7 = Provider class{ $cls_type }is not a subclass of EmbeddingProvider
msg-821d06e0 = Provider class{ $cls_type }is not a subclass of RerankProvider
msg-14c35664 = Unknown provider type:{ $res }
msg-186fd5c6 = Instantiate{ $res }Text to translate: ({ $res_2 }) Provider adapter failed:{ $e }
msg-ede02a99 = providers in user's config:{ $config_ids }
msg-95dc4227 = Auto-select{ $res }As the current provider adapter.
msg-a6187bac = Auto-select{ $res }As the current speech-to-text provider adapter.
msg-bf28f7e2 = Auto-select{ $res }As the current text-to-speech provider adapter.
msg-dba10c27 = Terminate{ $provider_id }Provider adapter ({ $res }{ $res_2 }待翻译文本：{ $res_3 }) ...
msg-9d9d9765 = { $provider_id }Provider adapter has terminated ({ $res }{ $res_2 },{ $res_3 })
msg-925bb70a = Provider{ $target_prov_ids }Removed from configuration.
msg-a1657092 = New provider config must have an 'id' field
msg-1486c653 = Provider ID{ $npid }already exists
msg-f9fc1545 = Provider ID{ $origin_provider_id }not found
msg-4e2c657c = Error while disabling MCP servers

### astrbot/core/provider/sources/gemini_embedding_source.py

msg-173efb0e = [Gemini Embedding] Using proxy:{ $proxy }
msg-58a99789 = Gemini Embedding API request failed:{ $res }
msg-5c4ea38e = Gemini Embedding API batch request failed:{ $res }

### astrbot/core/provider/sources/bailian_rerank_source.py

msg-dc1a9e6e = Alibaba Cloud Bailian API Key cannot be empty.
msg-f7079f37 = AstrBot Hundred Refinements Rerank initialization complete. Model:{ $res }
msg-5b6d35ce = Bailian API Error:{ $res }待翻译文本：{ $res_2 }
msg-d600c5e2 = Bailian Rerank returns empty results:{ $data }
msg-d3312319 = Result{ $idx }Missing relevance_score, using default value 0.0
msg-2855fb44 = Analysis Result{ $idx }Error occurred:{ $e }, result={ $result }
msg-392f26e8 = Bailian Rerank Token Consumption:{ $tokens }
msg-595e0cf9 = Bailian Rerank client session has been closed, returning empty result.
msg-d0388210 = Document list is empty, returning empty result
msg-44d6cc76 = Query text is empty, returning empty results
msg-bd8b942a = Number of Documents({ $res }) exceeds limit (500), will truncate first 500 documents
msg-0dc3bca4 = Bailian Rerank request: query='{ $res }..., document count={ $res_2 }
msg-4a9f4ee3 = Bailian Rerank returned successfully{ $res }result
msg-fa301307 = Bailian Rerank network request failed:{ $e }
msg-10f72727 = { $error_msg }
msg-9879e226 = Bailian Rerank processing failed:{ $e }
msg-4f15074c = Close Baichuan Rerank client session
msg-d01b1b0f = Error closing the Baichuan Rerank client:{ $e }

### astrbot/core/provider/sources/edge_tts_source.py

msg-f4ab0713 = pyffmpeg conversion failed:{ $e }, try using the ffmpeg command line for conversion
msg-ddc3594a = [EdgeTTS] FFmpeg standard output:{ $res }
msg-1b8c0a83 = FFmpeg error output:{ $res }
msg-1e980a68 = [EdgeTTS] Return value (0 for success):{ $res }
msg-c39d210c = The generated WAV file does not exist or is empty.
msg-57f60837 = FFmpeg conversion failed:{ $res }
msg-ca94a42a = FFmpeg conversion failed:{ $e }
msg-be660d63 = Audio generation failed:{ $e }

### astrbot/core/provider/sources/whisper_api_source.py

msg-28cbbf07 = File does not exist:{ $audio_url }
msg-b335b8db = Converting silk file to wav using tencent_silk_to_wav...
msg-68b5660f = Converting amr file to wav using convert_to_pcm_wav...
msg-cad3735e = Failed to remove temp file{ $audio_url }Text to be translated:{ $e }

### astrbot/core/provider/sources/gemini_source.py

msg-1474947f = [Gemini] Using Proxy:{ $proxy }
msg-e2a81024 = Key anomaly detected({ $res })，Trying to change API Key and retry... Current Key:{ $res_2 }...
msg-0d388dae = Detected Key anomaly({ $res }), and no more Keys are available. Current Key:{ $res_2 }...
msg-1465290c = Reached Gemini rate limit, please try again later...
msg-7e9c01ca = Streaming output does not support image modality and has been automatically downgraded to text modality.
msg-89bac423 = Code execution tool and search tool are mutually exclusive, search tool has been ignored.
msg-301cf76e = The code execution tool and the URL context tool are mutually exclusive. The URL context tool has been ignored.
msg-356e7b28 = Current SDK version does not support the URL context tool; this setting has been ignored. Please upgrade the google-genai package.
msg-7d4e7d48 = gemini-2.0-lite does not support code execution, search tools, and URL context; these settings will be ignored.
msg-cc5c666f = Native tools are enabled, function tools will be ignored.
msg-aa7c77a5 = Invalid thinking level:{ $thinking_level }, using HIGH
msg-59e1e769 = The text content is empty, placeholder space has been added
msg-34c5c910 = Failed to decode google gemini thinking signature:{ $e }
msg-a2357584 = The message content of the assistant role is empty; a space placeholder has been added.
msg-f627f75d = Detected that Gemini native tools are enabled and there are function calls in the context. It is recommended to use /reset to reset the context.
msg-cb743183 = Received candidate.content is empty:{ $candidate }
msg-34b367fc = The candidate.content returned by the API is empty.
msg-73541852 = The model-generated content failed the safety check on the Gemini platform.
msg-ae3cdcea = Model-generated content violates Gemini platform policies
msg-5d8f1711 = The received candidate.content.parts is empty:{ $candidate }
msg-57847bd5 = The candidate.content.parts returned by the API is empty.
msg-a56c85e4 = genai result:{ $result }
msg-42fc0767 = Request failed, returned candidates are empty:{ $result }
msg-faf3a0dd = Request failed, the returned candidates are empty.
msg-cd690916 = The temperature parameter has exceeded the maximum value of 2, yet recitation still occurred.
msg-632e23d7 = Recitation occurred, increasing temperature to{ $temperature }Retry...
msg-41ff84bc = { $model }System prompt not supported, automatically removed (affects persona settings).
msg-ef9512f7 = { $model }Function calls are not supported and have been automatically removed.
msg-fde41b1d = { $model }Multimodal output is not supported, downgraded to text mode.
msg-4e168d67 = Received chunk has empty candidates:{ $chunk }
msg-11af7d46 = Received chunk content is empty:{ $chunk }
msg-8836d4a2 = Request failed.
msg-757d3828 = Failed to get model list:{ $res }
msg-7fc6f623 = Image{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = Unsupported additional content block type:{ $res }

### astrbot/core/provider/sources/gsvi_tts_source.py

msg-520e410f = GSVI TTS API request failed, status code:{ $res }Error:{ $error_text }

### astrbot/core/provider/sources/anthropic_source.py

msg-d6b1df6e = Failed to parse image data URI:{ $res }...
msg-6c2c0426 = Unsupported image URL format for Anthropic:{ $res }...
msg-999f7680 = completion:{ $completion }
msg-8d2c43ec = The API returned an empty completion.
msg-26140afc = Failed to parse the completion returned by the Anthropic API:{ $completion }Text to be translated:
msg-8e4c8c24 = Tool call parameter JSON parsing failed:{ $tool_info }
msg-7fc6f623 = Image{ $image_url }The obtained result is empty and will be ignored.
msg-0b041916 = Unsupported additional content block type:{ $res }

### astrbot/core/provider/sources/openai_source.py

msg-bbb399f6 = Image request failed (%s) detected, image removed and retried (text content preserved).
msg-d6f6a3c2 = Failed to retrieve model list:{ $e }
msg-1f850e09 = The API returned an incorrect completion type:{ $res }Text to translate:{ $completion }Text to be translated: .
msg-999f7680 = completion:{ $completion }
msg-844635f7 = Unexpected dict format content:{ $raw_content }
msg-8d2c43ec = The API returned an empty completion.
msg-87d75331 = { $completion_text }
msg-0614efaf = Toolset not provided
msg-c46f067a = The completion returned by the API was rejected due to content security filtering (not AstrBot).
msg-647f0002 = The completion returned by the API cannot be parsed:{ $completion }.
msg-5cc50a15 = API calls are too frequent, try using another key to retry. Current Key:{ $res }
msg-c4e639eb = Context length exceeds the limit. Try popping the earliest record and retry. Current record count:{ $res }
msg-5f8be4fb = { $res }Function tool calls are not supported; they have been automatically removed and will not affect usage.
msg-45591836 = The model does not seem to support function calls or tool invocation. Please enter /tool off_all
msg-6e47d22a = API call failed, retrying{ $max_retries }Failed again.
msg-974e7484 = Unknown error
msg-7fc6f623 = Image{ $image_url }The result is empty and will be ignored.
msg-0b041916 = Unsupported extra content block type:{ $res }

### astrbot/core/provider/sources/gemini_tts_source.py

msg-29fe386a = [Gemini TTS] Using proxy:{ $proxy }
msg-012edfe1 = No audio content returned from Gemini TTS API.

### astrbot/core/provider/sources/genie_tts.py

msg-583dd8a6 = Please install genie_tts first.
msg-935222b4 = Failed to load character{ $res }Text to be translated:{ $e }
msg-a6886f9e = Genie TTS did not save to file.
msg-e3587d60 = Genie TTS generation failed:{ $e }
msg-3303e3a8 = Genie TTS failed to generate audio for:{ $text }
msg-1cfe1af1 = Genie TTS stream error:{ $e }

### astrbot/core/provider/sources/dashscope_tts.py

msg-f23d2372 = Dashscope TTS model is not configured.
msg-74a7cc0a = Audio synthesis failed, returned empty content. The model may not be supported or the service is unavailable.
msg-bc8619d3 = The dashscope SDK is missing MultiModalConversation. Please upgrade the dashscope package to use Qwen TTS models.
msg-95bbf71e = No voice specified for Qwen TTS model, using default 'Cherry'.
msg-3c35d2d0 = Audio synthesis failed for model '{ $model }'.{ $response }
msg-16dc3b00 = Failed to decode base64 audio data.
msg-26603085 = Failed to download audio from URL{ $url }Text to be translated:{ $e }
msg-78b9c276 = { $res }

### astrbot/core/provider/sources/whisper_selfhosted_source.py

msg-27fda50a = Downloading or loading the Whisper model, which may take some time...
msg-4e70f563 = Whisper model loading completed.
msg-28cbbf07 = File does not exist:{ $audio_url }
msg-d98780e5 = Converting silk file to wav ...
msg-e3e1215c = Whisper model not initialized

### astrbot/core/provider/sources/openai_tts_api_source.py

msg-d7084760 = [OpenAI TTS] Using proxy:{ $proxy }

### astrbot/core/provider/sources/xinference_rerank_source.py

msg-1ec1e6e4 = Xinference Rerank: Using API key for authentication.
msg-7bcb6e1b = Xinference Rerank: No API key provided.
msg-b0d1e564 = Model '{ $res }' is already running with UID:{ $uid }
msg-16965859 = Launching{ $res }model...
msg-7b1dfdd3 = Model launched.
msg-3fc7310e = Model{ $res }' is not running and auto-launch is disabled. Provider will not be available.
msg-15f19a42 = Failed to initialize Xinference model:{ $e }
msg-01af1651 = Xinference initialization failed with exception:{ $e }
msg-2607cc7a = Xinference rerank model is not initialized.
msg-3d28173b = Rerank API response:{ $response }
msg-4c63e1bd = Rerank API returned an empty list. Original response:{ $response }
msg-cac71506 = Xinference rerank failed:{ $e }
msg-4135cf72 = Xinference rerank failed with exception:{ $e }
msg-ea2b36d0 = Closing Xinference rerank client...
msg-633a269f = Failed to close Xinference client:{ $e }

### astrbot/core/provider/sources/minimax_tts_api_source.py

msg-77c88c8a = Failed to parse JSON data from SSE message
msg-7873b87b = MiniMax TTS API request failed:{ $e }

### astrbot/core/provider/sources/azure_tts_source.py

msg-93d9b5cf = [Azure TTS] Using proxy:{ $res }
msg-9eea5bcb = Client not initialized. Please use 'async with' context.
msg-fd53d21d = Time synchronization failed
msg-77890ac4 = OTTS request failed:{ $e }
msg-c6ec6ec7 = OTTS did not return an audio file
msg-5ad71900 = Invalid Azure subscription key
msg-6416da27 = [Azure TTS Native] Using proxy:{ $res }
msg-90b31925 = Missing OTTS parameter:{ $res }
msg-10f72727 = { $error_msg }
msg-60b044ea = Configuration error: Missing required parameters{ $e }
msg-5c7dee08 = The subscription key format is invalid, it should be a 32-character alphanumeric or other[...] format.

### astrbot/core/provider/sources/openai_embedding_source.py

msg-cecb2fbc = [OpenAI Embedding] Using proxy:{ $proxy }

### astrbot/core/provider/sources/vllm_rerank_source.py

msg-6f160342 = Rerank API returned an empty list data. Original response:{ $response_data }

### astrbot/core/provider/sources/xinference_stt_provider.py

msg-4e31e089 = Xinference STT: Using API key for authentication.
msg-e291704e = Xinference STT: No API key provided.
msg-b0d1e564 = Model{ $res }' is already running with UID:{ $uid }
msg-16965859 = Launching{ $res }model...
msg-7b1dfdd3 = Model launched.
msg-3fc7310e = Model{ $res }' is not running and auto-launch is disabled. Provider will not be available.
msg-15f19a42 = Failed to initialize Xinference model:{ $e }
msg-01af1651 = Xinference initialization failed with exception:{ $e }
msg-42ed8558 = Xinference STT model is not initialized.
msg-bbc43272 = Failed to download audio from{ $audio_url }, status:{ $res }
msg-f4e53d3d = File not found:{ $audio_url }
msg-ebab7cac = Audio bytes are empty.
msg-7fd63838 = Audio requires conversion ({ $conversion_type }), using temporary files...
msg-d03c4ede = Converting silk to wav ...
msg-79486689 = Converting amr to wav ...
msg-c4305a5b = Xinference STT result:{ $text }
msg-d4241bd5 = Xinference STT transcription failed with status{ $res }Text to translate:{ $error_text }
msg-8efe4ef1 = Xinference STT failed:{ $e }
msg-b1554c7c = Xinference STT failed with exception:{ $e }
msg-9d33941a = Removed temporary file:{ $temp_file }
msg-7dc5bc44 = Failed to remove temporary file{ $temp_file }Text to be translated:{ $e }
msg-31904a1c = Closing Xinference STT client...
msg-633a269f = Failed to close Xinference client:{ $e }

### astrbot/core/provider/sources/fishaudio_tts_api_source.py

msg-c785baf0 = [FishAudio TTS] Using Proxy:{ $res }
msg-822bce1c = Invalid FishAudio reference model ID: '{ $res }'. Please ensure the ID is a 32-digit hexadecimal string (e.g., 626bb6d3f3364c9cbc3aa6a67300a664). You can obtain a valid model ID from https://fish.audio/zh-CN/discovery.
msg-5956263b = Fish Audio API request failed: status code{ $res }, Response content:{ $error_text }

### astrbot/core/provider/sources/gsv_selfhosted_source.py

msg-5fb63f61 = [GSV TTS] Initialization complete
msg-e0c38c5b = [GSV TTS] Initialization failed:{ $e }
msg-4d57bc4f = [GSV TTS] Provider HTTP session is not ready or closed.
msg-2a4a0819 = [GSV TTS] Request URL:{ $endpoint }, Parameters:{ $params }
msg-5fdee1da = [GSV TTS] Request to{ $endpoint }failed with status{ $res }Text to be translated:{ $error_text }
msg-3a51c2c5 = [GSV TTS] Request{ $endpoint }Page{ $res }Failed{ $e }, retrying...
msg-49c1c17a = [GSV TTS] Request{ $endpoint }Final failure:{ $e }
msg-1beb6249 = [GSV TTS] Successfully set GPT model path:{ $res }
msg-17f1a087 = [GSV TTS] GPT model path is not configured, will use the built-in GPT model.
msg-ddeb915f = [GSV TTS] Successfully set the SoVITS model path:{ $res }
msg-bee5c961 = [GSV TTS] SoVITS model path not configured, will use built-in SoVITS model.
msg-423edb93 = [GSV TTS] A network error occurred while setting the model path:{ $e }
msg-7d3c79cb = [GSV TTS] An unknown error occurred while setting the model path:{ $e }
msg-d084916a = [GSV TTS] TTS text cannot be empty
msg-fa20c883 = [GSV TTS] Calling the speech synthesis interface, parameters:{ $params }
msg-a7fc38eb = [GSV TTS] Synthesis failed, input text:{ $text }, Error message:{ $result }
msg-a49cb96b = [GSV TTS] Session has been closed

### astrbot/core/provider/sources/volcengine_tts.py

msg-4b55f021 = Request header:{ $headers }
msg-d252d96d = Request URL:{ $res }
msg-72e07cfd = Request body:{ $res }...
msg-fb8cdd69 = Response status code:{ $res }
msg-4c62e457 = Response content:{ $res }...
msg-1477973b = Volcano Engine TTS API returned an error:{ $error_msg }
msg-75401c15 = Volcano Engine TTS API request failed:{ $res },{ $response_text }
msg-a29cc73d = Volcano Engine TTS Exception Details:{ $error_details }
msg-01433007 = Volcano Engine TTS Exception:{ $e }

### astrbot/core/provider/sources/sensevoice_selfhosted_source.py

msg-ee0daf96 = Downloading or loading the SenseVoice model, this may take some time...
msg-cd6da7e9 = SenseVoice model loading completed.
msg-28cbbf07 = File does not exist:{ $audio_url }
msg-d98780e5 = Converting silk file to wav ...
msg-4e8f1d05 = Copy recognized by SenseVoice:{ $res }
msg-55668aa2 = Failed to extract emotion information
msg-0cdbac9b = Error processing audio file:{ $e }

### astrbot/core/message/components.py

msg-afb10076 = not a valid url
msg-fe4c33a0 = not a valid file:{ $res }
msg-24d98e13 = callback_api_base is not configured, file service is unavailable
msg-a5c69cc9 = Registered:{ $callback_host }/api/file/{ $token }
msg-3cddc5ef = download failed:{ $url }
msg-1921aa47 = not a valid file:{ $url }
msg-2ee3827c = Generated video file callback link:{ $payload_file }
msg-32f4fc78 = No valid file or URL provided
msg-36375f4c = 不可以在异步上下文中同步等待下载! 这个警告通常发生于某些逻辑试图通过 <File>.file 获取文件消息段的文件内容。请使用 await get_file() 代替直接获取 <File>.file 字段
msg-4a987754 = File download failed:{ $e }
msg-7c1935ee = Download failed: No URL provided in File component.
msg-35bb8d53 = Generated file callback link:{ $payload_file }

### astrbot/core/utils/metrics.py

msg-314258f2 = Failed to save indicator to database:{ $e }

### astrbot/core/utils/trace.py

msg-fffce1b9 = [trace]{ $payload }
msg-78b9c276 = { $res }

### astrbot/core/utils/webhook_utils.py

msg-64c7ddcf = Failed to get callback_api_base:{ $e }
msg-9b5d1bb1 = Failed to get dashboard port:{ $e }
msg-3db149ad = Failed to get dashboard SSL configuration:{ $e }
msg-3739eec9 = { $display_log }

### astrbot/core/utils/path_util.py

msg-cf211d0f = Path mapping rule error:{ $mapping }
msg-ecea161e = Path mapping:{ $url }->{ $srcPath }

### astrbot/core/utils/media_utils.py

msg-2f697658 = [Media Utils] Get media duration:{ $duration_ms }ms
msg-52dfbc26 = [Media Utils] Failed to get media file duration:{ $file_path }
msg-486d493a = [Media Utils] ffprobe未安装或不在PATH中，无法获取媒体时长。请安装ffmpeg: https://ffmpeg.org/
msg-0f9c647b = [Media Utils] Failed to get media duration:{ $e }
msg-aff4c5f8 = [Media Utils] Cleaned up failed opus output files:{ $output_path }
msg-82427384 = [Media Utils] Error occurred while cleaning up failed opus output file:{ $e }
msg-215a0cfc = [Media Utils] ffmpeg audio conversion failed:{ $error_msg }
msg-8cce258e = ffmpeg conversion failed:{ $error_msg }
msg-f0cfcb92 = [Media Utils] Audio conversion successful:{ $audio_path }->{ $output_path }
msg-ead1395b = [Media Utils] ffmpeg is not installed or not in PATH, unable to convert audio format. Please install ffmpeg: https://ffmpeg.org/
msg-5df3a5ee = ffmpeg not found
msg-6322d4d2 = [Media Utils] Error converting audio format:{ $e }
msg-e125b1a5 = [Media Utils] Failed cleanups have been cleared{ $output_format }Output file:{ $output_path }
msg-5cf417e3 = [Media Utils] Cleanup failed{ $output_format }Error when outputting file:{ $e }
msg-3766cbb8 = [Media Utils] ffmpeg video conversion failed:{ $error_msg }
msg-77f68449 = [Media Utils] Video conversion successful:{ $video_path }->{ $output_path }
msg-3fb20b91 = [Media Utils] ffmpeg is not installed or not in the PATH, unable to convert video format. Please install ffmpeg: https://ffmpeg.org/
msg-696c4a46 = [Media Utils] Error converting video format:{ $e }
msg-98cc8fb8 = [Media Utils] Error occurred while cleaning up failed audio output files:{ $e }
msg-3c27d5e8 = [Media Utils] Error occurred while cleaning up failed video cover files:{ $e }
msg-072774ab = ffmpeg extract cover failed:{ $error_msg }

### astrbot/core/utils/session_waiter.py

msg-0c977996 = Wait timeout
msg-ac406437 = session_filter must be SessionFilter

### astrbot/core/utils/history_saver.py

msg-fb7718cb = Failed to parse conversation history: %s

### astrbot/core/utils/io.py

msg-665b0191 = SSL certificate verification failed for{ $url }. Disabling SSL verification (CERT_NONE) as a fallback. This is insecure and exposes the application to man-in-the-middle attacks. Please investigate and resolve certificate issues.
msg-04ab2fae = Download file failed:{ $res }
msg-63dacf99 = File size:{ $res }KB | File Address:{ $url }
msg-14c3d0bb = Download progress:{ $res }Speed:{ $speed }KB/s
msg-4e4ee68e = SSL certificate verification failed, SSL verification has been turned off (unsafe, for temporary download only). Please check the target server's certificate configuration.
msg-5a3beefb = SSL certificate verification failed for{ $url }. Falling back to unverified connection (CERT_NONE). This is insecure and exposes the application to man-in-the-middle attacks. Please investigate certificate issues with the remote server.
msg-315e5ed6 = Preparing to download the AstrBot WebUI files for the specified release version:{ $dashboard_release_url }
msg-c709cf82 = Preparing to download the specified version of AstrBot WebUI:{ $url }

### astrbot/core/utils/shared_preferences.py

msg-9a1e6a9a = scope_id and key cannot be None when getting a specific preference.

### astrbot/core/utils/migra_helper.py

msg-497ddf83 = Migration for third party agent runner configs failed:{ $e }
msg-78b9c276 = { $res }
msg-e21f1509 = Migrating provider{ $res }to new structure
msg-dd3339e6 = Provider-source structure migration completed
msg-1cb6c174 = Migration from version 4.5 to 4.6 failed:{ $e }
msg-a899acc6 = Migration for webchat session failed:{ $e }
msg-b9c52817 = Migration for token_usage column failed:{ $e }
msg-d9660ff5 = Migration for provider-source structure failed:{ $e }

### astrbot/core/utils/temp_dir_cleaner.py

msg-752c7cc8 = Invalid{ $res }={ $configured }, fallback to{ $res_2 }MB.
msg-b1fc3643 = Skip temp file{ $path }due to stat error:{ $e }
msg-5e61f6b7 = Failed to delete temp file{ $res }Text to be translated:{ $e }
msg-391449f0 = Temp dir exceeded limit ({ $total_size }Text to be translated:{ $limit }). Removed{ $removed_files }files, released{ $released }bytes (target{ $target_release }bytes).
msg-aaf1e12a = TempDirCleaner started. interval={ $res }cleanup_ratio={ $res_2 }
msg-e6170717 = TempDirCleaner run failed:{ $e }
msg-0fc33fbc = TempDirCleaner stopped.

### astrbot/core/utils/tencent_record_helper.py

msg-377ae139 = The pilk module is not installed. Please go to Admin Panel -> Platform Logs -> Install pip Libraries to install the pilk library.
msg-f4ab0713 = pyffmpeg conversion failed:{ $e }, try using the ffmpeg command line for conversion
msg-33c88889 = [FFmpeg] stdout:{ $res }
msg-2470430c = [FFmpeg] stderr:{ $res }
msg-1321d5f7 = [FFmpeg] return code:{ $res }
msg-c39d210c = The generated WAV file does not exist or is empty.
msg-6e04bdb8 = pilk not installed: pip install pilk

### astrbot/core/utils/pip_installer.py

msg-aa9e40b8 = pip module is unavailable (sys.executable={ $res }, frozen={ $res_2 }, ASTRBOT_DESKTOP_CLIENT={ $res_3 })
msg-560f11f2 = Failed to read dependency file, skipping conflict detection: %s
msg-91ae1d17 = Failed to read site-packages metadata, using fallback module name: %s
msg-c815b9dc = { $conflict_message }
msg-e8d4b617 = Loaded %s from plugin site-packages: %s
msg-4ef5d900 = Recovered dependency %s while preferring %s from plugin site-packages.
msg-0bf22754 = Module %s not found in plugin site-packages: %s
msg-76a41595 = Failed to prefer module %s from plugin site-packages: %s
msg-3d4de966 = Failed to patch pip distlib finder for loader %s (%s): %s
msg-117d9cf4 = Distlib finder patch did not take effect for loader %s (%s).
msg-b7975236 = Patched pip distlib finder for frozen loader: %s (%s)
msg-b1fa741c = Skip patching distlib finder because _finder_registry is unavailable.
msg-4ef0e609 = Skip patching distlib finder because register API is unavailable.
msg-b8c741dc = Pip Package Manager: pip{ $res }
msg-6b72a960 = Installation failed, error code:{ $result_code }
msg-c8325399 = { $line }

### astrbot/core/utils/llm_metadata.py

msg-d6535d03 = Successfully fetched metadata for{ $res }LLMs.
msg-8cceaeb0 = Failed to fetch LLM metadata:{ $e }

### astrbot/core/utils/network_utils.py

msg-54b8fda8 = Text to translate:{ $provider_label }Network/Proxy Connection Failed{ $error_type }Proxy Address:{ $effective_proxy }, Error:{ $error }
msg-ea7c80f1 = 待翻译文本：{ $provider_label }Network connection failed{ $error_type })。 Error:{ $error }
msg-f8c8a73c = Text to be translated:{ $provider_label }] Use proxy:{ $proxy }

### astrbot/core/utils/t2i/renderer.py

msg-4225607b = Failed to render image via AstrBot API:{ $e }. Falling back to local rendering.

### astrbot/core/utils/t2i/local_strategy.py

msg-94a58a1e = Unable to load any fonts
msg-d5c7d255 = Failed to load image: HTTP{ $res }
msg-7d59d0a0 = Failed to load image:{ $e }

### astrbot/core/utils/t2i/template_manager.py

msg-47d72ff5 = Template name contains illegal characters.
msg-d1b2131b = Template does not exist.
msg-dde05b0f = A template with the same name already exists.
msg-0aa209bf = User template does not exist and cannot be deleted.

### astrbot/core/utils/t2i/network_strategy.py

msg-be0eeaa7 = Successfully got{ $res }official T2I endpoints.
msg-3bee02f4 = Failed to get official endpoints:{ $e }
msg-829d3c71 = HTTP{ $res }
msg-05fb621f = Endpoint{ $endpoint }failed:{ $e }, trying next...
msg-9a836926 = All endpoints failed:{ $last_exception }

### astrbot/core/utils/quoted_message/extractor.py

msg-24049c48 = quoted_message_parser: stop fetching nested forward messages after %d hops

### astrbot/core/utils/quoted_message/onebot_client.py

msg-062923e6 = quoted_message_parser: action %s failed with params %s: %s
msg-f33f59d5 = quoted_message_parser: all attempts failed for action %s, last_params=%s, error=%s

### astrbot/core/utils/quoted_message/image_resolver.py

msg-94224a01 = quoted_message_parser: skip non-image local path ref=%s
msg-3e6c0d14 = quoted_message_parser: failed to resolve quoted image ref=%s after %d actions

### astrbot/core/agent/tool_image_cache.py

msg-45da4af7 = ToolImageCache initialized, cache dir:{ $res }
msg-017bde96 = Saved tool image to:{ $file_path }
msg-29398f55 = Failed to save tool image:{ $e }
msg-128aa08a = Failed to read cached image{ $file_path }Text to be translated:{ $e }
msg-3c111d1f = Error during cache cleanup:{ $e }
msg-eeb1b849 = Cleaned up{ $cleaned }expired cached images

### astrbot/core/agent/message.py

msg-d38656d7 = { $invalid_subclass_error_msg }
msg-42d5a315 = Cannot validate{ $value }as ContentPart
msg-ffc376d0 = content is required unless role='assistant' and tool_calls is not None

### astrbot/core/agent/mcp_client.py

msg-6a61ca88 = Warning: Missing 'mcp' dependency, MCP services will be unavailable.
msg-45995cdb = Warning: Missing 'mcp' dependency or MCP library version too old, Streamable HTTP connection unavailable.
msg-2866b896 = MCP connection config missing transport or type field
msg-3bf7776b = MCP Server{ $name }Error:{ $msg }
msg-10f72727 = { $error_msg }
msg-19c9b509 = MCP Client is not initialized
msg-5b9b4918 = MCP Client{ $res }is already reconnecting, skipping
msg-c1008866 = Cannot reconnect: missing connection configuration
msg-7c3fe178 = Attempting to reconnect to MCP server{ $res }...
msg-783f3b85 = Successfully reconnected to MCP server{ $res }
msg-da7361ff = Failed to reconnect to MCP server{ $res }Text to be translated:{ $e }
msg-c0fd612e = MCP session is not available for MCP function tools.
msg-8236c58c = MCP tool{ $tool_name }call failed (ClosedResourceError), attempting to reconnect...
msg-044046ec = Error closing current exit stack:{ $e }

### astrbot/core/agent/tool.py

msg-983bc802 = FunctionTool.call() must be implemented by subclasses or set a handler.

### astrbot/core/agent/context/compressor.py

msg-6c75531b = Failed to generate summary:{ $e }

### astrbot/core/agent/context/manager.py

msg-59241964 = Error during context processing:{ $e }
msg-a0d672dc = Compress triggered, starting compression...
msg-e6ef66f0 = Compress completed.{ $prev_tokens }->{ $tokens_after_summary }tokens, compression rate:{ $compress_rate }%.
msg-3fe644eb = Context still exceeds max tokens after compression, applying halving truncation...

### astrbot/core/agent/runners/tool_loop_agent_runner.py

msg-960ef181 = Switched from %s to fallback chat provider: %s
msg-4f999913 = Chat Model %s returns error response, trying fallback to next provider.
msg-c042095f = Chat Model %s request error: %s
msg-81b2aeae = { $tag }RunCtx.messages -> [{ $res }Text to be translated: ]{ $res_2 }
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook:{ $e }
msg-61de315c = Agent execution was requested to stop by user.
msg-8eb53be3 = Error in on_agent_done hook:{ $e }
msg-508d6d17 = LLM response error:{ $res }
msg-ed80313d = LLM returned empty assistant message with no tool calls.
msg-970947ae = Appended{ $res }cached image(s) to context for LLM review
msg-6b326889 = Agent reached max steps ({ $max_step }), forcing a final response.
msg-948ea4b7 = Agent using tool:{ $res }
msg-a27ad3d1 = Using tool:{ $func_tool_name }Parameters:{ $func_tool_args }
msg-812ad241 = Specified tool not found:{ $func_tool_name }, will be skipped.
msg-20b4f143 = Tools{ $func_tool_name }Expected parameters:{ $res }
msg-78f6833c = Tools{ $func_tool_name }Ignore unexpected parameters:{ $ignored_params }
msg-2b523f8c = Error in on_tool_start hook:{ $e }
msg-ec868b73 = { $func_tool_name }No return value, or the result has been directly sent to the user.
msg-6b61e4f1 = Tool returned an unsupported type:{ $res }.
msg-34c13e02 = Error in on_tool_end hook:{ $e }
msg-78b9c276 = { $res }
msg-a1493b6d = Tool `{ $func_tool_name }Result:{ $last_tcr_content }

### astrbot/core/agent/runners/base.py

msg-24eb2b08 = Agent state transition:{ $res }->{ $new_state }

### astrbot/core/agent/runners/dashscope/dashscope_agent_runner.py

msg-dc1a9e6e = Alibaba Cloud Bailian API Key cannot be empty.
msg-c492cbbc = Alibaba Cloud Bailian APP ID cannot be empty.
msg-bcc8e027 = The Alibaba Cloud Bailian APP type cannot be empty.
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook:{ $e }
msg-e3af4efd = Alibaba Cloud Bailian request failed:{ $res }
msg-fccf5004 = dashscope stream chunk:{ $chunk }
msg-100d7d7e = Alibaba Cloud Bailian request failed: request_id={ $res }, code={ $res_2 }, message={ $res_3 }, please refer to the documentation: https://help.aliyun.com/zh/model-studio/developer-reference/error-code
msg-10f72727 = { $error_msg }
msg-e8615101 = { $chunk_text }
msg-dfb132c4 = { $ref_text }
msg-8eb53be3 = Error in on_agent_done hook:{ $e }
msg-650b47e1 = Alibaba Cloud Bailian does not currently support image input and will automatically ignore image content.

### astrbot/core/agent/runners/coze/coze_agent_runner.py

msg-448549b0 = Coze API Key cannot be empty.
msg-b88724b0 = Coze Bot ID cannot be empty.
msg-ea5a135a = The Coze API Base URL format is incorrect; it must start with http:// or https://.
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook:{ $e }
msg-5aa3eb1c = Coze request failed:{ $res }
msg-333354c6 = Failed to process context image:{ $e }
msg-2d9e1c08 = Failed to process image{ $url }Text to be translated:{ $e }
msg-1f50979d = { $content }
msg-6fe5588b = Coze message completed
msg-d2802f3b = Coze chat completed
msg-ba4afcda = Coze error:{ $error_code }-{ $error_msg }
msg-ee300f25 = Coze did not return any content
msg-8eb53be3 = Error in on_agent_done hook:{ $e }
msg-034c1858 = [Coze] Using cached file_id:{ $file_id }
msg-475d8a41 = [Coze] Image uploaded successfully and cached, file_id:{ $file_id }
msg-696dad99 = Failed to process image{ $image_url }Text to translate:{ $e }
msg-7793a347 = Image processing failed:{ $e }

### astrbot/core/agent/runners/coze/coze_api_client.py

msg-76f97104 = Coze API authentication failed, please check if the API Key is correct
msg-3653b652 = File upload response status:{ $res }, content:{ $response_text }
msg-13fe060c = File upload failed, status code:{ $res }, response:{ $response_text }
msg-5604b862 = File upload response parsing failed:{ $response_text }
msg-c0373c50 = File upload failed:{ $res }
msg-010e4299 = [Coze] Image uploaded successfully, file_id:{ $file_id }
msg-719f13cb = File upload timeout
msg-121c11fb = File upload failed:{ $e }
msg-f6101892 = Failed to download image, status code:{ $res }
msg-c09c56c9 = Failed to download the image{ $image_url }Text to translate:{ $e }
msg-15211c7c = Failed to download image:{ $e }
msg-2245219f = Coze chat_messages payload:{ $payload }, params:{ $params }
msg-d8fd415c = Coze API streaming request failed, status code:{ $res }
msg-f5cc7604 = Coze API Streaming Request Timeout{ $timeout }second(s)
msg-30c0a9d6 = Coze API streaming request failed:{ $e }
msg-11509aba = Coze API request failed, status code:{ $res }
msg-002af11d = Coze API returns non-JSON format
msg-c0b8fc7c = Coze API request timeout
msg-a68a33fa = Coze API request failed:{ $e }
msg-c26e068e = Failed to get Coze message list:{ $e }
msg-5bc0a49d = Uploaded file_id:{ $file_id }
msg-7c08bdaf = Event:{ $event }

### astrbot/core/agent/runners/dify/dify_api_client.py

msg-cd6cd7ac = Drop invalid dify json data:{ $res }
msg-3654a12d = chat_messages payload:{ $payload }
msg-8e865c52 = Dify /chat-messages API request failed:{ $res }.{ $text }
msg-2d7534b8 = workflow_run payload:{ $payload }
msg-89918ba5 = Dify /workflows/run interface request failed:{ $res }.{ $text }
msg-8bf17938 = file_path and file_data cannot both be None
msg-b6ee8f38 = Dify file upload failed:{ $res }.{ $text }

### astrbot/core/agent/runners/dify/dify_agent_runner.py

msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook:{ $e }
msg-0d493427 = Dify request failed:{ $res }
msg-fe594f21 = Dify upload image response:{ $file_response }
msg-3534b306 = Received an unknown Dify response after uploading the image:{ $file_response }, images will be ignored.
msg-08441fdf = Upload image failed:{ $e }
msg-3972f693 = dify resp chunk:{ $chunk }
msg-6c74267b = Dify message end
msg-1ce260ba = Dify encountered an error:{ $chunk }
msg-a12417dd = Dify encountered an error status:{ $res }message:{ $res_2 }
msg-f8530ee9 = dify workflow resp chunk:{ $chunk }
msg-386a282e = Dify Workflow (ID:{ $res }Start running.
msg-0bc1299b = Dify workflow node (ID:{ $res }Title:{ $res_2 }) Running completed.
msg-5cf24248 = Dify workflow (ID:{ $res }) Run completed
msg-e2c2159f = Dify Workflow Result:{ $chunk }
msg-4fa60ef1 = Dify workflow error:{ $res }
msg-1f786836 = Dify workflow output does not contain the specified key name:{ $res }
msg-c4a70ffb = Unknown Dify API type:{ $res }
msg-51d321fd = Dify request result is empty, please check the Debug logs.
msg-8eb53be3 = Error in on_agent_done hook:{ $e }

### astrbot/core/star/session_plugin_manager.py

msg-16cc2a7a = Plugin{ $res }In session{ $session_id }Disabled in, skipping processor{ $res_2 }

### astrbot/core/star/star_manager.py

msg-bfa28c02 = watchfiles is not installed, hot reloading of plugins cannot be achieved.
msg-f8e1c445 = Plugin hot reload monitoring task exception:{ $e }
msg-78b9c276 = { $res }
msg-28aeca68 = File change detected:{ $changes }
msg-aeec7738 = Plugin detected{ $plugin_name }File changed, reloading...
msg-4f989555 = Plugin{ $d }main.py not found{ $d }.py，跳过。
msg-74b32804 = Installing plugin{ $p }Required dependencies:{ $pth }
msg-936edfca = Update plugin{ $p }Dependency failure. Code:{ $e }
msg-ebd47311 = Plugin{ $root_dir_name }Import failed, attempting to recover from installed dependencies:{ $import_exc }
msg-1b6e94f1 = Plugin{ $root_dir_name }Dependencies have been restored from site-packages, skipping reinstallation.
msg-81b7c9b9 = Plugin{ $root_dir_name }Failed to restore installed dependencies, will reinstall dependencies:{ $recover_exc }
msg-22fde75d = The plugin does not exist.
msg-3a307a9e = Plugin metadata information is incomplete. name, desc, version, and author are required fields.
msg-55e089d5 = Delete module{ $key }
msg-64de1322 = Delete Module{ $module_name }
msg-66823424 = Module{ $module_name }Not loaded
msg-45c8df8d = Cleared plugin{ $dir_name }In{ $key }Module
msg-f7d9aa9b = Cleanup Processor:{ $res }
msg-3c492aa6 = Cleanup Tool:{ $res }
msg-e0002829 = Plugin{ $res }Not properly terminated:{ $e }, may cause this plugin to malfunction.
msg-0fe27735 = Loading plugins{ $root_dir_name }...
msg-b2ec4801 = { $error_trace }
msg-db351291 = Plugin{ $root_dir_name }Import failed. Reason:{ $e }
msg-a3db5f45 = Failed plugins are still in the plugin list, cleaning up...
msg-58c66a56 = Plugin{ $root_dir_name }Metadata load failed:{ $e }Use default metadata.
msg-da764b29 = { $metadata }
msg-17cd7b7d = Plugin{ $res }It has been disabled.
msg-4baf6814 = Plugin{ $path }Not registered via decorator. Attempting to load using legacy method.
msg-840994d1 = Plugin not found{ $plugin_dir_path }metadata of
msg-944ffff1 = Insert permission filter{ $cmd_type }To{ $res }of{ $res_2 }Method.
msg-64edd12c = hook(on_plugin_loaded) ->{ $res }-{ $res_2 }
msg-db49f7a1 = ----- Plugin{ $root_dir_name }Failed to load
msg-26039659 = |{ $line }
msg-4292f44d = Text to be translated: ----------------------------------
msg-d2048afe = Synchronization command configuration failed:{ $e }
msg-df515dec = Cleaned up installation failed plugin directory:{ $plugin_path }
msg-1f2aa1a9 = Failed to clean up the installation directory for the failed plugin:{ $plugin_path }Reason:{ $e }
msg-1e947210 = Cleaned up configuration for failed plugin installation:{ $plugin_config_path }
msg-7374541f = Failed to clean up configuration of unsuccessfully installed plugins:{ $plugin_config_path }, Reason:{ $e }
msg-e871b08f = Reading plugins{ $dir_name }Failed to read the README.md file:{ $e }
msg-70ca4592 = This plugin is a reserved plugin of AstrBot and cannot be uninstalled.
msg-e247422b = Plugin{ $plugin_name }Not normally terminated{ $e }, which may lead to resource leaks and other issues.
msg-0c25dbf4 = Plugin{ $plugin_name }Data is incomplete, cannot uninstall.
msg-d6f8142c = Plugin removed successfully, but failed to delete plugin folder:{ $e }You can manually delete this folder located under addons/plugins/.
msg-6313500c = Deleted plugin{ $plugin_name }configuration file
msg-f0f01b67 = Failed to delete plugin configuration file:{ $e }
msg-c4008b30 = Deleted plugin{ $plugin_name }Persistent data (plugin_data)
msg-88d1ee05 = Failed to delete plugin persistent data (plugin_data):{ $e }
msg-ba805469 = Deleted plugin{ $plugin_name }persistent data (plugins_data)
msg-cf6eb821 = Failed to delete plugin persistent data (plugins_data):{ $e }
msg-e1853811 = Removed plugin{ $plugin_name }Processing function{ $res }Text to translate: ({ $res_2 })
msg-95b20050 = Removed plugin{ $plugin_name }Platform Adapter{ $adapter_name }
msg-9f248e88 = This plugin is a reserved plugin for AstrBot and cannot be updated.
msg-ff435883 = Terminating plugin{ $res }...
msg-355187b7 = Plugin{ $res }Not activated, no need to terminate, skip.
msg-4369864f = hook(on_plugin_unloaded) ->{ $res }-{ $res_2 }
msg-1b95e855 = Plugin{ $plugin_name }It does not exist.
msg-c1bc6cd6 = Plug-in detected{ $res }Installed, terminating old plugin...
msg-4f3271db = Duplicate plugin detected{ $res }Exists in different directories{ $res_2 }, terminating...
msg-d247fc54 = Failed to read new plugin metadata.yaml, skipping duplicate name check:{ $e }
msg-0f8947f8 = Failed to delete plugin archive:{ $e }

### astrbot/core/star/session_llm_manager.py

msg-7b90d0e9 = Session{ $session_id }The TTS status has been updated to:{ $res }

### astrbot/core/star/config.py

msg-c2189e8d = Namespace cannot be empty.
msg-97f66907 = Namespace cannot start with internal_.
msg-09179604 = key only supports str type.
msg-1163e4f1 = value only supports str, int, float, bool, list types.
msg-ed0f93e4 = Configuration file{ $namespace }.json does not exist.
msg-e3b5cdfb = Configuration item{ $key }Does not exist.

### astrbot/core/star/star_tools.py

msg-397b7bf9 = StarTools not initialized
msg-ca30e638 = No adapter found: AiocqhttpAdapter
msg-77ca0ccb = Unsupported platform:{ $platform }
msg-3ed67eb2 = Unable to retrieve caller module information
msg-e77ccce6 = Unable to retrieve module{ $res }Metadata information
msg-76ac38ee = Unable to retrieve plugin name
msg-751bfd23 = Cannot create directory{ $data_dir }Insufficient permissions
msg-68979283 = Unable to create directory{ $data_dir }Text to be translated：{ $e }

### astrbot/core/star/context.py

msg-60eb9e43 = Provider{ $chat_provider_id }not found
msg-da70a6fb = Agent did not produce a final LLM response
msg-141151fe = Provider not found
msg-a5cb19c6 = ID not found for{ $provider_id }provider, which may be caused by you modifying the provider (model) ID.
msg-2a44300b = The conversation model (provider) type for the session source is incorrect:{ $res }
msg-37c286ea = The returned Provider is not of type TTSProvider.
msg-ff775f3b = The returned Provider is not of type STTProvider
msg-fd8c8295 = cannot find platform for session{ $res }, message not sent
msg-2b806a28 = plugin(module_path){ $module_path }) added LLM tool:{ $res }

### astrbot/core/star/updator.py

msg-66be72ec = Plugin{ $res }No repository address specified.
msg-7a29adea = Plugin{ $res }The root directory name is not specified.
msg-99a86f88 = Updating plugin, path:{ $plugin_path }Repository address:{ $repo_url }
msg-df2c7e1b = Delete old version plugins{ $plugin_path }Folder failed:{ $e }, using the overwrite installation.
msg-b3471491 = Unzipping archive:{ $zip_path }
msg-7197ad11 = Delete temporary files:{ $zip_path }and{ $res }
msg-f8a43aa5 = Failed to delete the update file. You can delete it manually.{ $zip_path }and{ $res }

### astrbot/core/star/command_management.py

msg-011581bb = The specified handler function does not exist or is not an instruction.
msg-a0c37004 = Command name cannot be empty.
msg-ae8b2307 = Command name '{ $candidate_full }' is already occupied by another instruction.
msg-247926a7 = Alias{ $alias_full }It has been occupied by other instructions.
msg-dbd19a23 = Permission type must be admin or member.
msg-9388ea1e = Plugin for the command not found
msg-0dd9b70d = Parse instruction processing function{ $res }Failed, skipping this instruction. Reason:{ $e }

### astrbot/core/star/base.py

msg-57019272 = get_config() failed:{ $e }

### astrbot/core/star/register/star.py

msg-64619f8e = The 'register_star' decorator is deprecated and will be removed in a future version.

### astrbot/core/star/register/star_handler.py

msg-7ff2d46e = Registration instruction{ $command_name }The sub_command parameter was not provided when using the sub-command.
msg-b68436e1 = No command_name parameter provided when registering a bare instruction.
msg-1c183df2 = { $command_group_name }The sub_command of the command group is not specified.
msg-9210c7e8 = The name of the root command group is not specified.
msg-678858e7 = Registration of the instruction group failed.
msg-6c3915e0 = LLM Function Tools{ $res }_{ $llm_tool_name }'s parameters{ $res_2 }Missing type annotation.
msg-1255c964 = LLM function tools{ $res }_{ $llm_tool_name }Unsupported parameter type:{ $res_2 }

### astrbot/core/star/filter/command.py

msg-995944c2 = Parameter '{ $param_name }(GreedyStr) must be the last argument.
msg-04dbdc3a = Required parameters missing. Full parameters for this command:{ $res }
msg-bda71712 = Parameter{ $param_name }Must be a boolean value (true/false, yes/no, 1/0).
msg-a9afddbf = Parameter{ $param_name }Type error. Full parameters:{ $res }

### astrbot/core/star/filter/custom_filter.py

msg-8f3eeb6e = Operands must be subclasses of CustomFilter.
msg-732ada95 = The CustomFilter class can only operate with other CustomFilter.
msg-51c0c77d = CustomFilter class can only operate with other CustomFilter.

### astrbot/core/db/vec_db/faiss_impl/document_storage.py

msg-c2dc1d2b = Database connection is not initialized, returning empty result
msg-51fa7426 = Database connection is not initialized, skipping delete operation
msg-43d1f69f = Database connection is not initialized, returning 0

### astrbot/core/db/vec_db/faiss_impl/embedding_storage.py

msg-8e5fe535 = faiss is not installed. Please install it using 'pip install faiss-cpu' or 'pip install faiss-gpu'.
msg-9aa7b941 = Vector dimension mismatch, expected:{ $res }, actual:{ $res_2 }

### astrbot/core/db/vec_db/faiss_impl/vec_db.py

msg-9f9765dc = Generating embeddings for{ $res }contents...
msg-385bc50a = Generated embeddings for{ $res }contents in{ $res_2 }seconds.

### astrbot/core/db/migration/migra_token_usage.py

msg-c3e53a4f = Starting database migration (adding conversations.token_usage column)...
msg-ccbd0a41 = The token_usage column already exists, skipping migration
msg-39f60232 = token_usage column added successfully
msg-4f9d3876 = token_usage migration completed
msg-91571aaf = An error occurred during migration:{ $e }

### astrbot/core/db/migration/migra_3_to_4.py

msg-7805b529 = Migration{ $total_cnt }Migrating old session data to the new table...
msg-6f232b73 = Progress:{ $progress }% ({ $res }Text to be translated:{ $total_cnt })
msg-6b1def31 = No specific data found for this old session:{ $conversation }, skip.
msg-b008c93f = Migrate old sessions{ $res }Failed:{ $e }
msg-6ac6313b = Successfully migrated{ $total_cnt }Migrate old session data to the new table.
msg-6b72e89b = Migrate data from the old platform, offset_sec:{ $offset_sec }Seconds.
msg-bdc90b84 = Migration{ $res }Migrating old platform data to the new table...
msg-e6caca5c = No old platform data found, skipping migration.
msg-1e824a79 = Progress:{ $progress }% ({ $res }Text to translate:{ $total_buckets })
msg-813384e2 = Migration platform statistics failed:{ $platform_id },{ $platform_type }, Timestamp:{ $bucket_end }
msg-27ab191d = Migration successful{ $res }Migrate old platform data to the new table.
msg-8e6280ed = Migration{ $total_cnt }Migrating old WebChat session data to the new table...
msg-cad66fe1 = Migrate old WebChat sessions{ $res }Failed
msg-63748a46 = Successfully migrated{ $total_cnt }Migrate old WebChat session data to the new table.
msg-dfc93fa4 = Migration{ $total_personas }Configuring Persona to new table...
msg-ff85e45c = Progress:{ $progress }% ({ $res }Text to be translated:{ $total_personas })
msg-c346311e = Migrate Persona{ $res }Text to be translated:{ $res_2 }...) to new table succeeded.
msg-b6292b94 = Failed to parse Persona configuration:{ $e }
msg-90e5039e = Migrate global preference settings{ $key }Success, value:{ $value }
msg-d538da1c = Migrate Session{ $umo }Dialogue data successfully migrated to new table, Platform ID:{ $platform_id }
msg-ee03c001 = Migrate Session{ $umo }Failed to retrieve conversation data:{ $e }
msg-5c4339cd = Migrate Session{ $umo }Service configuration migrated to new table successfully, platform ID:{ $platform_id }
msg-4ce2a0b2 = Migration session{ $umo }Service configuration failed:{ $e }
msg-2e62dab9 = Migrate Session{ $umo }Failed to set variable:{ $e }
msg-afbf819e = Migration session{ $umo }Provider preferences migrated to new table successfully, platform ID:{ $platform_id }
msg-959bb068 = Migrate Session{ $umo }Provider preference failed:{ $e }

### astrbot/core/db/migration/helper.py

msg-a48f4752 = Starting database migration...
msg-45e31e8e = Database migration completed.

### astrbot/core/db/migration/migra_45_to_46.py

msg-782b01c1 = migrate_45_to_46: abconf_data is not a dict (type={ $res }). Value:{ $abconf_data }
msg-49e09620 = Starting migration from version 4.5 to 4.6
msg-791b79f8 = Migration from version 45 to 46 completed successfully

### astrbot/core/db/migration/migra_webchat_session.py

msg-53fad3d0 = Start executing database migration (WebChat session migration)...
msg-7674efb0 = No WebChat data requiring migration was found.
msg-139e39ee = Find{ $res }A WebChat session requires migration
msg-cf287e58 = Session{ $session_id }Already exists, skipping
msg-062c72fa = WebChat session migration completed! Successfully migrated:{ $res }, skip:{ $skipped_count }
msg-a516cc9f = No new sessions need to be migrated.
msg-91571aaf = An error occurred during the migration:{ $e }

### astrbot/core/knowledge_base/kb_helper.py

msg-7b3dc642 = - LLM call failed on attempt{ $res }/{ $res_2 }. Error:{ $res_3 }
msg-4ba9530f = - Failed to process chunk after{ $res }attempts. Using original text.
msg-77670a3a = Knowledge Base{ $res }Embedding Provider is not configured
msg-8e9eb3f9 = Could not find ID{ $res }Embedding Provider
msg-3e426806 = Unable to find ID{ $res }Rerank Provider
msg-6e780e1e = Using pre-chunked text for upload, total{ $res }blocks.
msg-f4b82f18 = When pre_chunked_text is not provided, file_content cannot be empty.
msg-975f06d7 = Failed to upload document:{ $e }
msg-969b17ca = Failed to clean up multimedia files{ $media_path }Text to be translated:{ $me }
msg-18d25e55 = Unable to find ID{ $doc_id }Documentation
msg-f5d7c34c = Error: Tavily API key is not configured in provider_settings.
msg-975d88e0 = Failed to extract content from URL{ $url }Text to be translated:{ $e }
msg-cfe431b3 = No content extracted from URL:{ $url }
msg-e7f5f836 = No valid text extracted after content cleaning. Please try disabling the content cleaning feature or retry with a higher-performance LLM model.
msg-693aa5c5 = Content cleaning is not enabled, using specified parameters for chunking: chunk_size={ $chunk_size }, chunk_overlap={ $chunk_overlap }
msg-947d8f46 = Content cleaning is enabled, but no cleaning_provider_id is provided, skipping cleaning and using default chunking.
msg-31963d3f = Unable to find ID{ $cleaning_provider_id }The LLM Provider or type is incorrect.
msg-82728272 = Initial chunking completed, generating{ $res }blocks to repair.
msg-6fa5fdca = Block{ $i }Handling exceptions:{ $res }Fallback to original block.
msg-6780e950 = Text repair completed:{ $res }original blocks{ $res_2 }Final block.
msg-79056c76 = Use Provider '{ $cleaning_provider_id }Failed to clean content:{ $e }

### astrbot/core/knowledge_base/kb_mgr.py

msg-98bfa670 = Initializing the knowledge base module...
msg-7da7ae15 = Knowledge base module import failed:{ $e }
msg-842a3c65 = Please ensure the required dependencies are installed: pypdf, aiofiles, Pillow, rank-bm25
msg-c9e943f7 = Knowledge base module initialization failed:{ $e }
msg-78b9c276 = { $res }
msg-9349e112 = KnowledgeBase database initialized:{ $DB_PATH }
msg-7605893e = You must provide an embedding_provider_id when creating a knowledge base.
msg-0b632cbd = Knowledge base name{ $kb_name }already exists
msg-ca30330f = Close Knowledge Base{ $kb_id }Failed:{ $e }
msg-00262e1f = Failed to close the knowledge base metadata database:{ $e }
msg-3fc9ef0b = Knowledge base with id{ $kb_id }not found.

### astrbot/core/knowledge_base/kb_db_sqlite.py

msg-b850e5d8 = Knowledge base database is closed:{ $res }

### astrbot/core/knowledge_base/parsers/util.py

msg-398b3580 = Temporarily unsupported file format:{ $ext }

### astrbot/core/knowledge_base/parsers/url_parser.py

msg-2de85bf5 = Error: Tavily API keys are not configured.
msg-98ed69f4 = Error: url must be a non-empty string.
msg-7b14cdb7 = Tavily web extraction failed:{ $reason }, status:{ $res }
msg-cfe431b3 = No content extracted from URL:{ $url }
msg-b0897365 = Failed to fetch URL{ $url }Text to be translated:{ $e }
msg-975d88e0 = Failed to extract content from URL{ $url }Text to be translated:{ $e }

### astrbot/core/knowledge_base/parsers/text_parser.py

msg-70cbd40d = Unable to decode file:{ $file_name }

### astrbot/core/knowledge_base/chunking/recursive.py

msg-21db456a = chunk_size must be greater than 0
msg-c0656f4e = chunk_overlap must be non-negative
msg-82bd199c = chunk_overlap must be less than chunk_size

### astrbot/core/knowledge_base/retrieval/manager.py

msg-fcc0dde2 = Knowledge Base ID{ $kb_id }Instance not found, skipped retrieval for this knowledge base.
msg-320cfcff = Dense retrieval across{ $res }bases took{ $res_2 }s and returned{ $res_3 }Results.
msg-90ffcfc8 = Sparse retrieval across{ $res }bases took{ $res_2 }s and returned{ $res_3 }results.
msg-12bcf404 = Rank fusion took{ $res }s and returned{ $res_2 }results.
msg-28c084bc = vec_db for kb_id{ $kb_id }is not FaissVecDB
msg-cc0230a3 = Knowledge Base{ $kb_id }Dense retrieval failed:{ $e }

### astrbot/core/skills/skill_manager.py

msg-ed9670ad = Zip file not found:{ $zip_path }
msg-73f9cf65 = Uploaded file is not a valid zip archive.
msg-69eb5f95 = Zip archive is empty.
msg-9e9abb4c = { $top_dirs }
msg-20b8533f = Zip archive must contain a single top-level folder.
msg-1db1caf7 = Invalid skill folder name.
msg-d7814054 = Zip archive contains absolute paths.
msg-179bd10e = Zip archive contains invalid relative paths.
msg-90f2904e = Zip archive contains unexpected top-level entries.
msg-95775a4d = SKILL.md not found in the skill folder.
msg-a4117c0b = Skill folder not found after extraction.
msg-94041ef2 = Skill already exists.

### astrbot/core/backup/importer.py

msg-c046b6e4 = { $msg }
msg-0e6f1f5d = Start from{ $zip_path }Import Backup
msg-2bf97ca0 = Backup import completed:{ $res }
msg-e67dda98 = Backup file lacks version information
msg-8f871d9f = Version Difference Warning:{ $res }
msg-2d6da12a = Table cleared{ $table_name }
msg-7d21b23a = Clear Table{ $table_name }Failure:{ $e }
msg-ab0f09db = Knowledge base table has been cleared{ $table_name }
msg-7bcdfaee = Clear knowledge base table{ $table_name }Failed:{ $e }
msg-43f008f1 = Clean up knowledge base{ $kb_id }Failed:{ $e }
msg-985cae66 = Unknown table:{ $table_name }
msg-dfa8b605 = Import records to{ $table_name }Failed:{ $e }
msg-89a2120c = Import table{ $table_name }Text to translate:{ $count }records
msg-f1dec753 = Import knowledge base records to{ $table_name }Failed:{ $e }
msg-9807bcd8 = Failed to import document block:{ $e }
msg-98a66293 = Import attachment{ $name }Failed:{ $e }
msg-39f2325f = Backup version does not support directory backup, skipping directory import.
msg-689050b6 = Existing directory has been backed up{ $target_dir }To{ $backup_path }
msg-d51b3536 = Import Directory{ $dir_name }Text to be translated:{ $file_count }file

### astrbot/core/backup/exporter.py

msg-c7ed7177 = Start exporting backup to{ $zip_path }
msg-8099b694 = Backup export completed:{ $zip_path }
msg-75a4910d = Backup export failed:{ $e }
msg-2821fc92 = Export Table{ $table_name }Text to translate:{ $res }Records
msg-52b7c242 = Export Table{ $table_name }Failed:{ $e }
msg-56310830 = Export Knowledge Base Table{ $table_name }Text to be translated:{ $res }records
msg-f4e8f57e = Export knowledge base table{ $table_name }Failed:{ $e }
msg-8e4ddd12 = Failed to export knowledge base documents:{ $e }
msg-c1960618 = Export FAISS Index:{ $archive_path }
msg-314bf920 = Failed to export FAISS index:{ $e }
msg-528757b2 = Export knowledge base media files failed:{ $e }
msg-d89d6dfe = Directory does not exist, skipping:{ $full_path }
msg-94527edd = Export file{ $file_path }Failure:{ $e }
msg-cb773e24 = Export directory{ $dir_name }Text to be translated:{ $file_count }files,{ $total_size }Byte
msg-ae929510 = Export Directory{ $dir_path }Failed:{ $e }
msg-93e331d2 = Export attachment failed:{ $e }

### astrbot/core/computer/computer_client.py

msg-7cb974b8 = Uploading skills bundle to sandbox...
msg-130cf3e3 = Failed to upload skills bundle to sandbox.
msg-99188d69 = Failed to remove temp skills zip:{ $zip_path }
msg-3f3c81da = Unknown booter type:{ $booter_type }
msg-e20cc33a = Error booting sandbox for session{ $session_id }Text to translate:{ $e }

### astrbot/core/computer/tools/fs.py

msg-99ab0efe = Upload result:{ $result }
msg-bca9d578 = File{ $local_path }uploaded to sandbox at{ $file_path }
msg-da21a6a5 = Error uploading file{ $local_path }Text to translate:{ $e }
msg-93476abb = File{ $remote_path }downloaded from sandbox to{ $local_path }
msg-079c5972 = Error sending file message:{ $e }
msg-ce35bb2c = Error downloading file{ $remote_path }Text to be translated:{ $e }

### astrbot/core/computer/booters/local.py

msg-487d0c91 = Path is outside the allowed computer roots.
msg-e5eb5377 = Blocked unsafe shell command.
msg-9e1e117f = Local computer booter initialized for session:{ $session_id }
msg-2d7f95de = Local computer booter shutdown complete.
msg-82a45196 = LocalBooter does not support upload_file operation. Use shell instead.
msg-0457524a = LocalBooter does not support download_file operation. Use shell instead.

### astrbot/core/computer/booters/shipyard.py

msg-b03115b0 = Got sandbox ship:{ $res }for session:{ $session_id }
msg-c5ce8bde = Error checking Shipyard sandbox availability:{ $e }

### astrbot/core/computer/booters/boxlite.py

msg-019c4d18 = Failed to exec operation:{ $res } { $error_text }
msg-b135b7bd = Failed to upload file:{ $e }
msg-873ed1c8 = File not found:{ $path }
msg-f58ceec6 = Unexpected error uploading file:{ $e }
msg-900ab999 = Checking health for sandbox{ $ship_id }on{ $res }...
msg-2a50d6f3 = Sandbox{ $ship_id }is healthy
msg-fbdbe32f = Booting(Boxlite) for session:{ $session_id }, this may take a while...
msg-b1f13f5f = Boxlite booter started for session:{ $session_id }
msg-e93d0c30 = Shutting down Boxlite booter for ship:{ $res }
msg-6deea473 = Boxlite booter for ship:{ $res }stopped

### astrbot/core/cron/manager.py

msg-724e64a9 = Skip scheduling basic cron job %s due to missing handler.
msg-78ef135f = Invalid timezone %s for cron job %s, fallback to system.
msg-e71c28d3 = run_once job missing run_at timestamp
msg-dd46e69f = Failed to schedule cron job{ $res }Text to be translated:{ $e }
msg-aa2e4688 = Unknown cron job type:{ $res }
msg-186627d9 = Cron job{ $job_id }failed:{ $e }
msg-cb955de0 = Basic cron job handler not found for{ $res }
msg-2029c4b2 = ActiveAgentCronJob missing session.
msg-6babddc9 = Invalid session for cron job:{ $e }
msg-865a2b07 = Failed to build main agent for cron job.
msg-27c9c6b3 = Cron job agent got no response

### astrbot/utils/http_ssl_common.py

msg-7957c9b6 = Failed to load certifi CA bundle into SSL context; falling back to system trust store only: %s

### astrbot/cli/__main__.py

msg-fe494da6 = { $logo_tmpl }
msg-c8b2ff67 = Welcome to AstrBot CLI!
msg-78b9c276 = { $res }
msg-14dd710d = Unknown command:{ $command_name }

### astrbot/cli/utils/basic.py

msg-f4e0fd7b = Management panel is not installed
msg-2d090cc3 = Installing management panel...
msg-2eeb67e0 = Management panel installation completed
msg-9c727dca = Management panel is already the latest version.
msg-11b49913 = Admin panel version:{ $version }
msg-f0b6145e = Download management panel failed:{ $e }
msg-9504d173 = Initializing admin panel directory...
msg-699e2509 = Admin panel initialization completed

### astrbot/cli/utils/plugin.py

msg-e327bc14 = Downloading from the default branch{ $author }/{ $repo }
msg-c804f59f = Failed to get release information:{ $e }, the provided URL will be used directly
msg-aa398bd5 = The master branch does not exist, attempting to download the main branch.
msg-5587d9fb = Read{ $yaml_path }Failed:{ $e }
msg-8dbce791 = Failed to retrieve online plugin list:{ $e }
msg-6999155d = Plugin{ $plugin_name }Not installed, cannot update
msg-fa5e129a = 正在从{ $repo_url } { $res }Plugin{ $plugin_name }...
msg-9ac1f4db = Plugin{ $plugin_name } { $res }Success
msg-b9c719ae = { $res }Plugin{ $plugin_name }Error occurred:{ $e }

### astrbot/cli/commands/cmd_conf.py

msg-635b8763 = Log level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL
msg-ebc250dc = Port must be within the range 1-65535
msg-6ec400b6 = Port must be a number
msg-0b62b5ce = Username cannot be empty
msg-89b5d3d5 = Password cannot be empty
msg-92e7c8ad = Invalid timezone:{ $value }Please use a valid IANA timezone name
msg-e470e37d = Callback interface base address must start with http:// or https://
msg-6b615721 = { $root }Not a valid AstrBot root directory. If you need to initialize, please use astrbot init
msg-f74c517c = Configuration file parsing failed:{ $e }
msg-d7c58bcc = Configuration path conflict:{ $res }Not a dictionary
msg-e16816cc = Unsupported configuration item:{ $key }
msg-e9cce750 = Configuration updated:{ $key }
msg-1ed565aa = Original value: ********
msg-1bf9569a = New value: ********
msg-f2a20ab3 = Original value:{ $old_value }
msg-0c104905 = New value:{ $validated_value }
msg-ea9b4e2c = Unknown configuration item:{ $key }
msg-4450e3b1 = Failed to set configuration:{ $e }
msg-ba464bee = { $key }Text to be translated:{ $value }
msg-72aab576 = Failed to get configuration:{ $e }
msg-c1693d1d = Current configuration:
msg-50be9b74 = { $key }Text to translate:{ $value }

### astrbot/cli/commands/cmd_init.py

msg-a90a250e = Current Directory:{ $astrbot_root }
msg-4deda62e = If you confirm this is the AstrBot root directory, you need to create an .astrbot file in the current directory to mark it as the AstrBot data directory.
msg-3319bf71 = Created{ $dot_astrbot }
msg-7054f44f = { $res }Text to translate:{ $path }
msg-b19edc8a = Initializing AstrBot...
msg-eebc39e3 = Unable to acquire the lock file. Please check if another instance is running.
msg-e16da80f = Initialization failed:{ $e }

### astrbot/cli/commands/cmd_run.py

msg-41ecc632 = { $astrbot_root }Not a valid AstrBot root directory. Use 'astrbot init' to initialize if needed.
msg-0ccaca23 = Enable plugin auto-reload
msg-220914e7 = AstrBot is closed...
msg-eebc39e3 = Unable to acquire lock file, please check if another instance is running.
msg-85f241d3 = Runtime error occurred:{ $e }{ "\u000A" }{ $res }

### astrbot/cli/commands/cmd_plug.py

msg-cbd8802b = { $base }Not a valid AstrBot root directory. Use astrbot init if you need to initialize.
msg-78b9c276 = { $res }
msg-83664fcf = { $val } { $val } { $val } { $val } { $val }
msg-56f3f0bf = { $res } { $res_2 } { $res_3 } { $res_4 } { $desc }
msg-1d802ff2 = Plugin{ $name }Already exists
msg-a7be9d23 = Version number must be in x.y or x.y.z format.
msg-4d81299b = The repository address must start with http
msg-93289755 = Downloading plugin template...
msg-b21682dd = Rewriting plugin information...
msg-bffc8bfa = Plugin{ $name }Creation successful
msg-08eae1e3 = No plugins installed
msg-1a021bf4 = No installable plugins found{ $name }, may not exist or has already been installed
msg-c120bafd = Plugin{ $name }Does not exist or is not installed
msg-63da4867 = Plugin{ $name }Uninstalled
msg-e4925708 = Uninstall plugin{ $name }Failed:{ $e }
msg-f4d15a87 = Plugin{ $name }No need to update or cannot be updated
msg-94b035f7 = No plugins need to be updated.
msg-0766d599 = Discover{ $res }plugins need to be updated
msg-bd5ab99c = Updating plugin{ $plugin_name }...
msg-e32912b8 = No matches found for '{ $query }'s plugin

### astrbot/dashboard/server.py

msg-e88807e2 = Route not found
msg-06151c57 = Missing API key
msg-88dca3cc = Invalid API key
msg-fd267dc8 = Insufficient API key scope
msg-076fb3a3 = Unauthorized
msg-6f214cc1 = Token expired
msg-5041dc95 = Token is invalid
msg-1241c883 = Check port{ $port }An error occurred:{ $e }
msg-7c3ba89d = Initialized random JWT secret for dashboard.
msg-a3adcb66 = WebUI has been disabled
msg-44832296 = Starting WebUI, listening address:{ $scheme }://{ $host }Text to translate:{ $port }
msg-3eed4a73 = Hint: WebUI will listen on all network interfaces, please note security. (You can modify the host by configuring dashboard.host in data/cmd_config.json)
msg-289a2fe8 = Error: Port{ $port }Occupied{ "\u000A" }Usage Information:{ "\u000A" }           { $process_info }{ "\u000A" }Please ensure:{ "\u000A" }1. No other AstrBot instances are currently running.{ "\u000A" }2. Port{ $port }Not occupied by other programs{ "\u000A" }3. To use other ports, please modify the configuration file.
msg-6d1dfba8 = Port{ $port }Occupied
msg-228fe31e = {"\u000A"} ✨✨✨{"\u000A"}  AstrBot v{$VERSION} WebUI started, visit at:{"\u000A"}{"\u000A"}
msg-3749e149 =    ➜  Local: {$scheme}://localhost:{$port}{"\u000A"}
msg-3c2a1175 =    ➜  Network: {$scheme}://{$ip}:{$port}{"\u000A"}
msg-d1ba29cb =    ➜  Default Username & Password: astrbot{"\u000A"} ✨✨✨{"\u000A"}
msg-d5182f70 = Configure dashboard.host in data/cmd_config.json for remote access.
msg-c0161c7c = { $display }
msg-ac4f2855 = dashboard.ssl.enable is true, cert_file and key_file must be configured.
msg-3e87aaf8 = SSL certificate file does not exist:{ $cert_path }
msg-5ccf0a9f = SSL private key file does not exist:{ $key_path }
msg-5e4aa3eb = SSL CA certificate file does not exist:{ $ca_path }
msg-cb049eb2 = AstrBot WebUI has been gracefully shut down.

### astrbot/dashboard/utils.py

msg-160bd44a = Missing required libraries for t-SNE visualization. Please install matplotlib and scikit-learn:{ e }
msg-aa3a3dbf = Knowledge base not found
msg-0e404ea3 = FAISS index does not exist:{ $index_path }
msg-8d92420c = Index is empty
msg-24c0450e = Extract{ $res }A vector for visualization...
msg-632d0acf = Starting t-SNE dimensionality reduction...
msg-61f0449f = Generating visual charts...
msg-4436ad2b = Error generating t-SNE visualization:{ $e }
msg-78b9c276 = { $res }

### astrbot/dashboard/routes/update.py

msg-a3503781 = Migration failed:{ $res }
msg-543d8e4d = Migration failed:{ $e }
msg-251a5f4a = Check for updates failed:{ $e }(Does not affect normal use except for project updates)
msg-aa6bff26 = /api/update/releases:{ $res }
msg-c5170c27 = Failed to download the management panel file:{ $e }.
msg-db715c26 = Updating dependencies...
msg-9a00f940 = Failed to update dependencies:{ $e }
msg-6f96e3ba = /api/update_project:{ $res }
msg-3217b509 = Failed to download management panel file:{ $e }
msg-9cff28cf = /api/update_dashboard:{ $res }
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-38e60adf = Missing or invalid parameter package.
msg-a1191473 = /api/update_pip:{ $res }

### astrbot/dashboard/routes/lang_route.py

msg-0d18aac8 = [LangRoute] lang:{ $lang }
msg-bf610e68 = lang is a required parameter.

### astrbot/dashboard/routes/auth.py

msg-ee9cf260 = For security purposes, please change the default password as soon as possible.
msg-87f936b8 = Username or password is incorrect
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-25562cd3 = Original password is incorrect
msg-d31087d2 = The new username and new password cannot both be empty.
msg-b512c27e = The new passwords entered twice do not match
msg-7b947d8b = JWT secret is not set in the cmd_config.

### astrbot/dashboard/routes/backup.py

msg-6920795d = Clean up expired upload sessions:{ $upload_id }
msg-3e96548d = Failed to clean up expired upload sessions:{ $e }
msg-259677a9 = Failed to clean up shard directory:{ $e }
msg-d7263882 = Failed to read backup manifest:{ $e }
msg-40f76598 = Skipping invalid backup file:{ $filename }
msg-18a49bfc = Failed to get backup list:{ $e }
msg-78b9c276 = { $res }
msg-6e08b5a5 = Failed to create backup:{ $e }
msg-9cce1032 = Background export task{ $task_id }Failed:{ $e }
msg-55927ac1 = Missing backup file
msg-374cab8a = Please upload a ZIP format backup file
msg-d53d6730 = Uploaded backup file saved:{ $unique_filename }(Original name:{ $res })
msg-98e64c7f = Upload backup file failed:{ $e }
msg-49c3b432 = Missing filename parameter
msg-df33d307 = Invalid file size
msg-162ad779 = Initialize multipart upload: upload_id={ $upload_id }, filename={ $unique_filename }, total_chunks={ $total_chunks }
msg-de676924 = Initialize multipart upload failed:{ $e }
msg-eecf877c = Missing required parameters
msg-f175c633 = Invalid shard index
msg-ad865497 = Missing shard data
msg-947c2d56 = The upload session does not exist or has expired.
msg-f3a464a5 = Shard index out of range
msg-7060da1d = Receiving chunks: upload_id={ $upload_id }, chunk={ $res }Text to be translated:{ $total_chunks }
msg-06c107c1 = Upload chunk failed:{ $e }
msg-f040b260 = Marked backup as upload source:{ $zip_path }
msg-559c10a8 = Failed to mark backup source:{ $e }
msg-d1d752ef = Missing upload_id parameter
msg-390ed49a = Shard is incomplete, missing:{ $res }...
msg-8029086a = Shard upload completed:{ $filename }, size={ $file_size }, chunks={ $total }
msg-4905dde5 = Failed to complete multipart upload:{ $e }
msg-b63394b1 = Cancel multipart upload:{ $upload_id }
msg-2b39da46 = Cancel upload failed:{ $e }
msg-f12b1f7a = Invalid file name
msg-44bb3b89 = Backup file does not exist:{ $filename }
msg-b005980b = Pre-check backup file failed:{ $e }
msg-65b7ede1 = Please confirm the import first. The import will clear and overwrite existing data, and this operation cannot be undone.
msg-b152e4bf = Import backup failed:{ $e }
msg-5e7f1683 = Background Import Task{ $task_id }Failure:{ $e }
msg-6906aa65 = Missing parameter task_id
msg-5ea3d72c = Cannot find the task
msg-f0901aef = Failed to get task progress:{ $e }
msg-8d23792b = Missing parameter filename
msg-4188ede6 = Missing parameter token
msg-0c708312 = Server configuration error
msg-cc228d62 = Token has expired, please refresh the page and try again.
msg-5041dc95 = Invalid token
msg-96283fc5 = Backup file does not exist
msg-00aacbf8 = Download backup failed:{ $e }
msg-3ea8e256 = Failed to delete backup:{ $e }
msg-e4a57714 = Missing parameter new_name
msg-436724bb = The new file name is invalid
msg-9f9d8558 = File name '{ $new_filename }Already exists
msg-a5fda312 = Backup file rename:{ $filename }->{ $new_filename }
msg-e7c82339 = Rename backup failed:{ $e }

### astrbot/dashboard/routes/command.py

msg-1d47363b = handler_full_name and enabled are both required.
msg-35374718 = handler_full_name and new_name are both required.
msg-f879f2f4 = handler_full_name and permission are both required.

### astrbot/dashboard/routes/subagent.py

msg-78b9c276 = { $res }
msg-eda47201 = Failed to retrieve subagent configuration:{ $e }
msg-3e5b1fe0 = Configuration must be a JSON object
msg-9f285dd3 = Failed to save subagent configuration:{ $e }
msg-665f4751 = Failed to get available tools:{ $e }

### astrbot/dashboard/routes/config.py

msg-680e7347 = Configuration items{ $path }{ $key }No type definition, skip validation
msg-ef2e5902 = Saving config, is_core={ $is_core }
msg-78b9c276 = { $res }
msg-acef166d = An exception occurred while validating the configuration:{ $e }
msg-42f62db0 = Format validation failed:{ $errors }
msg-3e668849 = Missing configuration data
msg-196b9b25 = Missing provider_source_id
msg-dbbbc375 = Provider source not found
msg-a77f69f4 = Missing original_id
msg-96f154c4 = Missing or incorrect configuration data
msg-c80b2c0f = Provider source ID '{ $res }' exists already, please try another ID.
msg-537b700b = Missing or incorrect routing table data
msg-b5079e61 = Failed to update routing table:{ $e }
msg-cf97d400 = Missing UMO or Configuration File ID
msg-2a05bc8d = Missing UMO
msg-7098aa3f = Failed to delete routing table entry:{ $e }
msg-902aedc3 = Missing configuration file ID
msg-b9026977 = abconf_id cannot be None
msg-acf0664a = Deletion failed
msg-59c93c1a = Failed to delete configuration file:{ $e }
msg-930442e2 = Update failed
msg-7375d4dc = Failed to update configuration file:{ $e }
msg-53a8fdb2 = Attempting to check provider:{ $res }(ID:{ $res_2 }, Type:{ $res_3 }, Model:{ $res_4 })
msg-8b0a48ee = Provider{ $res }(ID:{ $res_2 }) is available.
msg-7c7180a7 = Provider{ $res }(ID:{ $res_2 }) is unavailable. Error:{ $error_message }
msg-1298c229 = Traceback for{ $res }Text to be translated:{ "\u000A" }{ $res_2 }
msg-d7f9a42f = { $message }
msg-cd303a28 = API call: /config/provider/check_one id={ $provider_id }
msg-55b8107a = Provider with id '{ $provider_id }' not found in provider_manager.
msg-d1a98a9b = Provider with id '{ $provider_id }' not found
msg-cb9c402c = Missing parameter provider_type
msg-e092d4ee = Missing parameter provider_id
msg-1ff28fed = ID not found{ $provider_id }Provider
msg-92347c35 = Provider{ $provider_id }Type does not support retrieving model list
msg-d0845a10 = Missing parameter provider_config
msg-5657fea4 = provider_config is missing the type field
msg-09ed9dc7 = Provider adapter loading failed, please check provider type configuration or view server logs
msg-1cce1cd4 = Not applicable{ $provider_type }provider adapter
msg-8361e44d = Not found{ $provider_type }class
msg-4325087c = The provider is not of type EmbeddingProvider
msg-a9873ea4 = Detected{ $res }The embedding vector dimension is{ $dim }
msg-d170e384 = Failed to get embedding dimension:{ $e }
msg-abfeda72 = Missing parameter source_id
msg-0384f4c9 = ID not found for{ $provider_source_id }provider_source
msg-aec35bdb = provider_source is missing the type field
msg-cbb9d637 = Dynamic import of provider adapter failed:{ $e }
msg-468f64b3 = Provider{ $provider_type }Model list retrieval is not supported.
msg-cb07fc1c = Get provider_source{ $provider_source_id }Model List:{ $models }
msg-d2f6e16d = Failed to get model list:{ $e }
msg-25ea8a96 = Unsupported scope:{ $scope }
msg-23c8933f = Missing name or key parameter
msg-536e77ae = Plugin{ $name }not found or has no config
msg-1b6bc453 = Configuration item not found or not of file type
msg-fc0a457e = No files uploaded
msg-31c718d7 = Invalid name parameter
msg-e1edc16e = Missing name parameter
msg-8e634b35 = Invalid path parameter
msg-0b52a254 = Plugin{ $name }not found
msg-bff0e837 = Parameter error
msg-2f29d263 = Robot name cannot be modified
msg-1478800f = No corresponding platform found
msg-ca6133f7 = Missing parameter id
msg-1199c1f9 = Using cached logo token for platform{ $res }
msg-889a7de5 = Platform class not found for{ $res }
msg-317f359c = Logo token registered for platform{ $res }
msg-323ec1e2 = Platform{ $res }logo file not found:{ $logo_file_path }
msg-bc6d0bcf = Failed to import required modules for platform{ $res }Text to be translated:{ $e }
msg-b02b538d = File system error for platform{ $res }logo:{ $e }
msg-31123607 = Unexpected error registering logo for platform{ $res }Text to be translated:{ $e }
msg-af06ccab = Configuration file{ $conf_id }Not exist
msg-082a5585 = Plugin{ $plugin_name }Does not exist
msg-ca334960 = Plugin{ $plugin_name }No registration configuration

### astrbot/dashboard/routes/knowledge_base.py

msg-ce669289 = Upload document{ $res }Failed:{ $e }
msg-87e99c2d = Background upload task{ $task_id }Failed:{ $e }
msg-78b9c276 = { $res }
msg-d5355233 = Import documents{ $file_name }Failure:{ $e }
msg-5e7f1683 = Background import task{ $task_id }Failed:{ $e }
msg-e1949850 = Failed to retrieve knowledge base list:{ $e }
msg-299af36d = Knowledge base name cannot be empty
msg-faf380ec = Missing parameter embedding_provider_id
msg-9015b689 = Embedding model does not exist or is of the wrong type{ $res }Text to be translated:
msg-a63b3aa9 = Embedding vector dimensions do not match, actually{ $res }, however, the configuration is{ $res_2 }
msg-9b281e88 = Testing embedding model failed:{ $e }
msg-d3fb6072 = The reordering model does not exist.
msg-fbec0dfd = The reordering model returned an abnormal result.
msg-872feec8 = Test reordering model failed:{ $e }Please check the platform log output.
msg-a4ac0b9e = Failed to create knowledge base:{ $e }
msg-c8d487e9 = Missing parameter kb_id
msg-978b3c73 = Knowledge base does not exist
msg-2137a3e6 = Failed to retrieve knowledge base details:{ $e }
msg-e7cf9cfd = At least one update field must be provided
msg-d3d82c22 = Failed to update knowledge base:{ $e }
msg-5d5d4090 = Failed to delete knowledge base:{ $e }
msg-787a5dea = Failed to retrieve knowledge base statistics:{ $e }
msg-97a2d918 = Failed to get document list:{ $e }
msg-b170e0fa = Content-Type must be multipart/form-data
msg-5afbfa8e = Missing file
msg-6636fd31 = You can only upload up to 10 files.
msg-975f06d7 = Upload document failed:{ $e }
msg-35bacf60 = Missing parameter documents or format error
msg-6cc1edcd = Incorrect document format; must include file_name and chunks
msg-376d7d5f = chunks must be a list
msg-e7e2f311 = chunks must be a non-empty list of strings
msg-42315b8d = Failed to import document:{ $e }
msg-6906aa65 = Missing parameter task_id
msg-5ea3d72c = Task not found
msg-194def99 = Failed to get upload progress:{ $e }
msg-df6ec98e = Missing parameter doc_id
msg-7c3cfe22 = Document does not exist
msg-b54ab822 = Failed to retrieve document details:{ $e }
msg-0ef7f633 = Failed to delete document:{ $e }
msg-2fe40cbd = Missing parameter chunk_id
msg-fc13d42a = Failed to delete text block:{ $e }
msg-4ef8315b = Failed to retrieve block list:{ $e }
msg-b70a1816 = Missing parameter query
msg-82ee646e = Missing parameter kb_names or incorrect format
msg-07a61a9a = Failed to generate t-SNE visualization:{ $e }
msg-20a3b3f7 = Retrieval failed:{ $e }
msg-1b76f5ab = Missing parameter url
msg-5dc86dc6 = Failed to upload document from URL:{ $e }
msg-890b3dee = Background upload URL task{ $task_id }Failure:{ $e }

### astrbot/dashboard/routes/skills.py

msg-78b9c276 = { $res }
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-52430f2b = Missing file
msg-2ad598f3 = Only .zip files are supported
msg-a11f2e1c = Failed to remove temporary skill file:{ $temp_path }
msg-67367a6d = Missing skill name

### astrbot/dashboard/routes/live_chat.py

msg-40f242d5 = [Live Chat]{ $res }Start talking stamp={ $stamp }
msg-a168d76d = [Live Chat] stamp does not match or is not in speaking state:{ $stamp }vs{ $res }
msg-e01b2fea = [Live Chat] No audio frame data
msg-33856925 = [Live Chat] Audio file saved:{ $audio_path }, Size:{ $res }bytes
msg-9e9b7e59 = [Live Chat] Failed to assemble WAV file:{ $e }
msg-21430f56 = [Live Chat] Temporary files have been deleted:{ $res }
msg-6b4f88bc = [Live Chat] Failed to delete temporary files:{ $e }
msg-0849d043 = [Live Chat] WebSocket connection established:{ $username }
msg-5477338a = [Live Chat] WebSocket Error:{ $e }
msg-fdbfdba8 = [Live Chat] WebSocket connection closed:{ $username }
msg-7be90ac0 = [Live Chat] start_speaking missing stamp
msg-8215062a = [Live Chat] Failed to decode audio data:{ $e }
msg-438980ea = [Live Chat] end_speaking is missing stamp
msg-b35a375c = [Live Chat] User Interruption:{ $res }
msg-2c3e7bbc = [Live Chat] STT Provider Not Configured
msg-0582c8ba = [Live Chat] STT recognition result is empty
msg-57c2b539 = [Live Chat] STT result:{ $user_text }
msg-6b7628c6 = [Live Chat] User interruption detected
msg-2cab2269 = [Live Chat] Message ID mismatch:{ $result_message_id }!={ $message_id }
msg-74c2470e = [Live Chat] Failed to parse AgentStats:{ $e }
msg-4738a2b3 = [Live Chat] Failed to parse TTSStats:{ $e }
msg-944d5022 = [Live Chat] Starting audio stream playback
msg-009104d8 = [Live Chat] Bot reply completed:{ $bot_text }
msg-0c4c3051 = [Live Chat] Failed to process audio:{ $e }
msg-140caa36 = [Live Chat] Save Interrupted Messages:{ $interrupted_text }
msg-869f51ea = [Live Chat] User message:{ $user_text }(session:{ $res }, ts:{ $timestamp }Text to be translated:
msg-d26dee52 = [Live Chat] Bot Message (Interruption):{ $interrupted_text }(session:{ $res }, ts:{ $timestamp }Text to translate: )
msg-1377f378 = [Live Chat] Failed to record message:{ $e }

### astrbot/dashboard/routes/log.py

msg-5bf500c1 = Log SSE resend history error:{ $e }
msg-e4368397 = Log SSE connection error:{ $e }
msg-547abccb = Failed to fetch log history:{ $e }
msg-cb5d4ebb = Failed to get Trace settings:{ $e }
msg-7564d3b0 = Request data is empty
msg-d2a1cd76 = Failed to update Trace settings:{ $e }

### astrbot/dashboard/routes/conversation.py

msg-62392611 = Database query error:{ $e }{ "\u000A" }{ $res }
msg-b21b052b = Database query error:{ $e }
msg-10f72727 = { $error_msg }
msg-036e6190 = Failed to retrieve conversation list:{ $e }
msg-a16ba4b4 = Missing required parameters: user_id and cid
msg-9a1fcec9 = The conversation does not exist
msg-73a8a217 = Failed to retrieve conversation details:{ $e }{ "\u000A" }{ $res }
msg-976cd580 = Failed to retrieve conversation details:{ $e }
msg-c193b9c4 = Failed to update conversation information:{ $e }{ "\u000A" }{ $res }
msg-9f96c4ee = Failed to update conversation information:{ $e }
msg-e1cb0788 = The conversations parameter cannot be empty during batch deletion.
msg-38e3c4ba = Failed to delete conversation:{ $e }{ "\u000A" }{ $res }
msg-ebf0371a = Failed to delete conversation:{ $e }
msg-af54ee29 = Missing required parameter: history
msg-b72552c8 = history must be a valid JSON string or array
msg-fdf757f3 = Failed to update conversation history:{ $e }{ "\u000A" }{ $res }
msg-33762429 = Failed to update conversation history:{ $e }
msg-498f11f8 = Export list cannot be empty
msg-98aa3644 = Export conversation failed: user_id={ $user_id }, cid={ $cid }, error={ $e }
msg-ed77aa37 = No conversations were successfully exported.
msg-f07b18ee = Batch export conversations failed:{ $e }{ "\u000A" }{ $res }
msg-85dc73fa = Batch export conversations failed:{ $e }

### astrbot/dashboard/routes/cron.py

msg-fb5b419b = Cron manager not initialized
msg-78b9c276 = { $res }
msg-112659e5 = Failed to list jobs:{ $e }
msg-8bc87eb5 = Invalid payload
msg-29f616c2 = Session is required
msg-ae7c99a4 = run_at is required when run_once=true
msg-4bb8c206 = cron_expression is required when run_once=false
msg-13fbf01e = run_at must be ISO datetime
msg-da14d97a = Failed to create job:{ $e }
msg-804b6412 = Job not found
msg-94b2248d = Failed to update job:{ $e }
msg-42c0ee7a = Failed to delete job:{ $e }

### astrbot/dashboard/routes/tools.py

msg-78b9c276 = { $res }
msg-977490be = Failed to retrieve MCP server list:{ $e }
msg-50a07403 = Server name cannot be empty
msg-23d2bca3 = A valid server configuration must be provided
msg-31252516 = Server{ $name }Already exists
msg-20b8309f = Enable MCP Server{ $name }Timeout.
msg-fff3d0c7 = Enable MCP Server{ $name }Failed:{ $e }
msg-7f1f7921 = Failed to save configuration
msg-a7f06648 = Failed to add MCP server:{ $e }
msg-278dc41b = Server{ $old_name }Does not exist
msg-f0441f4b = Disable the MCP server before enabling{ $old_name }Timeout:{ $e }
msg-7c468a83 = Disable MCP server before enabling{ $old_name }Failed:{ $e }
msg-8a4c8128 = Stop the MCP server{ $old_name }Timeout.
msg-9ac9b2fc = Stop MCP Server{ $old_name }Failed:{ $e }
msg-b988392d = Failed to update MCP server:{ $e }
msg-c81030a7 = Server{ $name }Does not exist
msg-4cdbd30d = Deactivate MCP server{ $name }Timeout.
msg-1ed9a96e = Deactivate MCP Server{ $name }Failed:{ $e }
msg-a26f2c6a = Failed to delete MCP server:{ $e }
msg-bbc84cc5 = Invalid MCP server configuration
msg-aa0e3d0d = MCP server configuration cannot be empty
msg-d69cbcf2 = Only one MCP server configuration can be configured at a time.
msg-bd43f610 = Test MCP connection failed:{ $e }
msg-057a3970 = Failed to get tool list:{ $e }
msg-29415636 = Missing required parameters: name or action
msg-75d85dc1 = Failed to enable tool:{ $e }
msg-21a922b8 = Tools{ $tool_name }Does not exist or operation failed.
msg-20143f28 = Operation tool failed:{ $e }
msg-295ab1fe = Unknown:{ $provider_name }
msg-fe38e872 = Synchronization failed:{ $e }

### astrbot/dashboard/routes/chatui_project.py

msg-04827ead = Missing key: title
msg-34fccfbb = Missing key: project_id
msg-a7c08aee = Project{ $project_id }not found
msg-c52a1454 = Permission denied
msg-dbf41bfc = Missing key: session_id
msg-d922dfa3 = Session{ $session_id }not found

### astrbot/dashboard/routes/open_api.py

msg-e41d65d5 = Failed to create chat session %s: %s
msg-fc15cbcd = { $username_err }
msg-bc3b3977 = Invalid username
msg-2cd6e70f = { $ensure_session_err }
msg-53632573 = { $resolve_err }
msg-79b0c7cb = Failed to update chat config route for %s with %s: %s
msg-7c7a9f55 = Failed to update chat config route:{ $e }
msg-74bff366 = page and page_size must be integers
msg-1507569c = Message is empty
msg-1389e46a = message must be a string or list
msg-697561eb = message part must be an object
msg-2c4bf283 = reply part missing message_id
msg-60ddb927 = unsupported message part type:{ $part_type }
msg-cf310369 = attachment not found:{ $attachment_id }
msg-58e0b84a = { $part_type }part missing attachment_id
msg-e565c4b5 = file not found:{ $file_path }
msg-c6ec40ff = Message content is empty (reply only is not allowed)
msg-2b00f931 = Missing key: message
msg-a29d9adb = Missing key: umo
msg-4990e908 = Invalid umo:{ $e }
msg-45ac857c = Bot not found or not running for platform:{ $platform_id }
msg-ec0f0bd2 = Open API send_message failed:{ $e }
msg-d04109ab = Failed to send message:{ $e }

### astrbot/dashboard/routes/session_management.py

msg-e1949850 = Failed to fetch knowledge base list:{ $e }
msg-3cd6eb8c = Failed to fetch rule list:{ $e }
msg-363174ae = Missing required parameter: umo
msg-809e51d7 = Missing required parameter: rule_key
msg-ce203e7e = Unsupported rule key:{ $rule_key }
msg-2726ab30 = Failed to update conversation rules:{ $e }
msg-f021f9fb = Failed to delete session rule:{ $e }
msg-6bfa1fe5 = Missing required parameter: umos
msg-4ce0379e = The parameter umos must be an array.
msg-979c6e2f = Delete umo{ $umo }The rule failed:{ $e }
msg-77d2761d = Batch deletion of session rules failed:{ $e }
msg-6619322c = Failed to retrieve UMO list:{ $e }
msg-b944697c = Failed to retrieve session status list:{ $e }
msg-adba3c3b = At least one status to be modified must be specified.
msg-4a8eb7a6 = Please specify the group ID
msg-67f15ab7 = Group{ $group_id }Does not exist
msg-50fbcccb = No matching conversations found
msg-59714ede = Update{ $umo }Service status failed:{ $e }
msg-31640917 = Batch update service status failed:{ $e }
msg-4d83eb92 = Missing required parameters: provider_type, provider_id
msg-5f333041 = Unsupported provider_type:{ $provider_type }
msg-6fa017d7 = Update{ $umo }Provider failed:{ $e }
msg-07416020 = Batch update Provider failed:{ $e }
msg-94c745e6 = Failed to get group list:{ $e }
msg-fb7cf353 = Group name cannot be empty
msg-ae3fce8a = Failed to create group:{ $e }
msg-07de5ff3 = Group ID cannot be empty
msg-35b8a74f = Update group failed:{ $e }
msg-3d41a6fd = Failed to delete group:{ $e }

### astrbot/dashboard/routes/persona.py

msg-4a12aead = Failed to retrieve personality list:{ $e }{ "\u000A" }{ $res }
msg-c168407f = Failed to retrieve personality list:{ $e }
msg-63c6f414 = Missing required parameter: persona_id
msg-ce7da6f3 = Personality does not exist
msg-9c07774d = Failed to retrieve personality details:{ $e }{ "\u000A" }{ $res }
msg-ee3b44ad = Failed to retrieve personality details:{ $e }
msg-ad455c14 = Personality ID cannot be empty
msg-43037094 = System prompt cannot be empty
msg-ec9dda44 = The number of preset dialogues must be an even number (alternating between user and assistant).
msg-26b214d5 = Failed to create persona:{ $e }{ "\u000A" }{ $res }
msg-8913dfe6 = Failed to create personality:{ $e }
msg-3d94d18d = Failed to update persona:{ $e }{ "\u000A" }{ $res }
msg-f2cdfbb8 = Failed to update personality:{ $e }
msg-51d84afc = Failed to delete persona:{ $e }{ "\u000A" }{ $res }
msg-8314a263 = Failed to delete persona:{ $e }
msg-b8ecb8f9 = Failed to move personality:{ $e }{ "\u000A" }{ $res }
msg-ab0420e3 = Failed to move persona:{ $e }
msg-e5604a24 = Failed to get folder list:{ $e }{ "\u000A" }{ $res }
msg-4d7c7f4a = Failed to get folder list:{ $e }
msg-cf0ee4aa = Failed to retrieve folder tree:{ $e }{ "\u000A" }{ $res }
msg-bb515af0 = Failed to retrieve folder tree:{ $e }
msg-c92b4863 = Missing required parameter: folder_id
msg-77cdd6fa = Folder does not exist
msg-2d34652f = Failed to get folder details:{ $e }{ "\u000A" }{ $res }
msg-650ef096 = Failed to get folder details:{ $e }
msg-27c413df = Folder name cannot be empty
msg-b5866931 = Failed to create folder:{ $e }{ "\u000A" }{ $res }
msg-5e57f3b5 = Failed to create folder:{ $e }
msg-9bd8f820 = Failed to update folder:{ $e }{ "\u000A" }{ $res }
msg-1eada044 = Failed to update folder:{ $e }
msg-9cef0256 = Failed to delete folder:{ $e }{ "\u000A" }{ $res }
msg-22020727 = Failed to delete folder:{ $e }
msg-7a69fe08 = items cannot be empty
msg-e71ba5c2 = Each item must contain the id, type, and sort_order fields
msg-dfeb8320 = The type field must be 'persona' or 'folder'
msg-aec43ed3 = Failed to update sorting:{ $e }{ "\u000A" }{ $res }
msg-75ec4427 = Failed to update sorting:{ $e }

### astrbot/dashboard/routes/platform.py

msg-bcc64513 = Webhook UUID not found for{ $webhook_uuid }platform
msg-1478800f = No corresponding platform found
msg-378cb077 = Platform{ $res }Method webhook_callback not implemented
msg-2d797305 = Platform does not support unified Webhook mode
msg-83f8dedf = An error occurred while processing the webhook callback:{ $e }
msg-af91bc78 = Failed to process callback
msg-136a952f = Failed to get platform statistics:{ $e }
msg-60bb0722 = Failed to retrieve statistics:{ $e }

### astrbot/dashboard/routes/api_key.py

msg-8e0249fa = At least one valid scope is required
msg-1b79360d = Invalid scopes
msg-d6621696 = expires_in_days must be an integer
msg-33605d95 = expires_in_days must be greater than 0
msg-209030fe = Missing key: key_id
msg-24513a81 = API key not found

### astrbot/dashboard/routes/file.py

msg-78b9c276 = { $res }

### astrbot/dashboard/routes/chat.py

msg-a4a521ff = Missing key: filename
msg-c9746528 = Invalid file path
msg-3c2f6dee = File access error
msg-e5b19b36 = Missing key: attachment_id
msg-cfa38c4d = Attachment not found
msg-377a7406 = Missing key: file
msg-bae87336 = Failed to create attachment
msg-5c531303 = Missing JSON body
msg-1c3efd8f = Missing key: message or files
msg-04588d0f = Missing key: session_id or conversation_id
msg-c6ec40ff = Message content is empty (reply only is not allowed)
msg-2c3fdeb9 = Messages are both empty
msg-9bc95e22 = session_id is empty
msg-344a401b = [WebChat] User{ $username }Disconnect chat long connection.
msg-6b54abec = WebChat stream error:{ $e }
msg-53509ecb = webchat stream message_id mismatch
msg-1211e857 = [WebChat] User{ $username }Disconnect chat long connection.{ $e }
msg-be34e848 = Failed to extract web search refs:{ $e }
msg-80bbd0ff = WebChat stream unexpected error:{ $e }
msg-dbf41bfc = Missing key: session_id
msg-d922dfa3 = Session{ $session_id }not found
msg-c52a1454 = Permission denied
msg-9d7a8094 = Failed to delete UMO route %s during session cleanup: %s
msg-44c45099 = Failed to delete attachment file{ $res }Text to translate:{ $e }
msg-f033d8ea = Failed to get attachments:{ $e }
msg-e6f655bd = Failed to delete attachments:{ $e }
msg-a6ef3b67 = Missing key: display_name

### astrbot/dashboard/routes/t2i.py

msg-76cc0933 = Error in get_active_template
msg-5350f35b = Template not found
msg-d7b101c5 = Name and content are required.
msg-e910b6f3 = Template with this name already exists.
msg-18cfb637 = Content is required.
msg-2480cf2f = Template not found.
msg-9fe026f1 = Template name cannot be empty.
msg-eeefe1dc = Template '{ $name }does not exist, cannot be applied.
msg-0048e060 = Error in set_active_template
msg-8fde62dd = Error in reset_default_template

### astrbot/dashboard/routes/stat.py

msg-1198c327 = You are not permitted to do this operation in demo mode
msg-78b9c276 = { $res }
msg-0e5bb0b1 = proxy_url is required
msg-f0e0983e = Failed. Status code:{ $res }
msg-68e65093 = Error:{ $e }
msg-b5979fe8 = version parameter is required
msg-b88a1887 = Invalid version format
msg-8cb9bb6b = Path traversal attempt detected:{ $version }->{ $changelog_path }
msg-7616304c = Changelog for version{ $version }not found

### astrbot/dashboard/routes/plugin.py

msg-1198c327 = You are not permitted to do this operation in demo mode
msg-adce8d2f = Missing plugin directory name
msg-2f1b67fd = Overload failed:{ $err }
msg-71f9ea23 = /api/plugin/reload-failed:{ $res }
msg-27286c23 = /api/plugin/reload:{ $res }
msg-b33c0d61 = Cache MD5 matches, using cached plugin marketplace data.
msg-64b4a44c = Remote plugin market data is empty:{ $url }
msg-fdbffdca = Successfully retrieved remote plugin market data, including{ $res }plugins
msg-48c42bf8 = Request{ $url }Failed, status code:{ $res }
msg-6ac25100 = Request{ $url }Failed, error:{ $e }
msg-7e536821 = Failed to fetch remote plugin market data, using cached data
msg-d4b4c53a = Failed to fetch the plugin list, and no cached data is available
msg-37f59b88 = Failed to load cache MD5:{ $e }
msg-8048aa4c = Failed to retrieve remote MD5:{ $e }
msg-593eacfd = The cache file does not contain MD5 information.
msg-dedcd957 = Unable to retrieve remote MD5, will use cache
msg-21d7e754 = Plugin data MD5: Local={ $cached_md5 }, Remote={ $remote_md5 }, valid={ $is_valid }
msg-0faf4275 = Failed to check cache validity:{ $e }
msg-e26aa0a5 = Loading cache file:{ $cache_file }, Cache Time:{ $res }
msg-23d627a1 = Failed to load plugin marketplace cache:{ $e }
msg-22d12569 = Plugin market data has been cached to:{ $cache_file }, MD5:{ $md5 }
msg-478c99a9 = Failed to save plugin marketplace cache:{ $e }
msg-3838d540 = Failed to get plugin logo:{ $e }
msg-da442310 = Installing plugin{ $repo_url }
msg-e0abd541 = Install plugin{ $repo_url }Successful.
msg-78b9c276 = { $res }
msg-acfcd91e = Installing user uploaded plugin{ $res }
msg-48e05870 = Install plugin{ $res }Success
msg-8af56756 = 正在卸载插件{ $plugin_name }
msg-6d1235b6 = Uninstall plugin{ $plugin_name }Success
msg-7055316c = Updating plugin{ $plugin_name }
msg-d258c060 = Update plugin{ $plugin_name }Success.
msg-398370d5 = /api/plugin/update:{ $res }
msg-2d225636 = Plugin list cannot be empty
msg-32632e67 = Batch Update Plugin{ $name }
msg-08dd341c = /api/plugin/update-all: Update plugin{ $name }Failed:{ $res }
msg-cb230226 = Deactivate plugin{ $plugin_name }待翻译文本：
msg-abc710cd = /api/plugin/off:{ $res }
msg-06e2a068 = Enable plugin{ $plugin_name }.
msg-82c412e7 = /api/plugin/on:{ $res }
msg-77e5d67e = 正在获取插件{ $plugin_name }The content of the README file
msg-baed1b72 = Plugin name is empty
msg-773cca0a = Plugin name cannot be empty
msg-082a5585 = Plugin{ $plugin_name }Does not exist
msg-ba106e58 = Plugin{ $plugin_name }Directory does not exist
msg-e38e4370 = Unable to find plugin directory:{ $plugin_dir }
msg-df027f16 = Plugin not found{ $plugin_name }Directory
msg-5f304f4b = Plugin{ $plugin_name }No README file
msg-a3ed8739 = /api/plugin/readme:{ $res }
msg-2f9e2c11 = Failed to read README file:{ $e }
msg-dcbd593f = Fetching plugins{ $plugin_name }Update log
msg-ea5482da = /api/plugin/changelog:{ $res }
msg-8e27362e = Failed to read changelog:{ $e }
msg-0842bf8b = Plugin{ $plugin_name }No changelog file
msg-8e36313d = sources fields must be a list
msg-643e51e7 = /api/plugin/source/save:{ $res }

### astrbot/builtin_stars/session_controller/main.py

msg-b48bf3fe = LLM response failed:{ $e }

### astrbot/builtin_stars/builtin_commands/commands/setunset.py

msg-8b56b437 = Session{ $uid }Variable{ $key }Storage successful. Use /unset to remove.
msg-dfd31d9d = There is no such variable name. Format: /unset variable name.
msg-bf181241 = Session{ $uid }Variable{ $key }Removed successfully.

### astrbot/builtin_stars/builtin_commands/commands/provider.py

msg-b435fcdc = Provider reachability check failed: id=%s type=%s code=%s reason=%s
msg-f4cfd3ab = Provider reachability test in progress, please wait...
msg-ed8dcc22 = { $ret }
msg-f3d8988e = Please enter the serial number.
msg-284759bb = Invalid provider number.
msg-092d9956 = Successfully switched to{ $id_ }Text to be translated: .
msg-bf9eb668 = Invalid parameter.
msg-4cdd042d = No LLM providers found. Please configure first.
msg-cb218e86 = Model serial number error.
msg-1756f199 = Switched model successfully. Current provider: [{ $res }Current model: [{ $res_2 }]
msg-4d4f587f = Switch model to{ $res }.
msg-584ca956 = Key sequence number is incorrect.
msg-f52481b8 = Switch Key Unknown Error:{ $e }
msg-7a156524 = Switching Key successful.

### astrbot/builtin_stars/builtin_commands/commands/conversation.py

msg-63fe9607 = In{ $res }In this scenario, the reset command requires administrator privileges, you (ID{ $res_2 }) Not an administrator, unable to perform this operation.
msg-6f4bbe27 = Conversation reset successfully.
msg-4cdd042d = No LLM provider found. Please configure it first.
msg-69ed45be = Not currently in a conversation state, please use /switch to switch or /new to create.
msg-ed8dcc22 = { $ret }
msg-772ec1fa = Stop requested{ $stopped_count }A running task.
msg-8d42cd8a = No tasks are currently running in this session.
msg-efdfbe3e = { $THIRD_PARTY_AGENT_RUNNER_STR }The conversation list feature is currently not supported.
msg-492c2c02 = A new conversation has been created.
msg-c7dc838d = Switch to New Conversation: New Conversation({ $res })。
msg-6da01230 = Group Chat{ $session }Switched to new chat: New chat{ $res }).
msg-f356d65a = Please enter the group chat ID. /groupnew Group Chat ID.
msg-7e442185 = Type error, please enter a numeric conversation number.
msg-00dbe29c = Enter conversation number. /switch conversation number. /ls view conversations /new create conversation
msg-a848ccf6 = Dialog serial number error, please use /ls to view.
msg-1ec33cf6 = Switch to conversation:{ $title }Text to translate:{ $res })。
msg-68e5dd6c = Please enter a new conversation name.
msg-c8dd6158 = Conversation renamed successfully.
msg-1f1fa2f2 = Session is in a group chat, and independent sessions are not enabled, and you (ID{ $res }) is not an administrator and therefore does not have permission to delete the current conversation.
msg-6a1dc4b7 = Currently not in a conversation state, please /switch number to switch or /new to create.

### astrbot/builtin_stars/builtin_commands/commands/tts.py

msg-ef1b2145 = { $status_text }Text-to-speech for the current session. However, the TTS feature is not enabled in the configuration. Please go to the WebUI to enable it.
msg-deee9deb = { $status_text }Text-to-speech for the current session.

### astrbot/builtin_stars/builtin_commands/commands/llm.py

msg-72cd5f57 = { $status }LLM Chat Feature.

### astrbot/builtin_stars/builtin_commands/commands/persona.py

msg-4f52d0dd = The current conversation does not exist, please use /new to create a new conversation first.
msg-e092b97c = [Persona]{ "\u000A" }{ "\u000A" }- Persona Scenario List: `/persona list`{ "\u000A" }- Set personality scenario: `/persona personality`{ "\u000A" }- Persona scenario details: `/persona view persona`{ "\u000A" }- Cancel persona: `/persona unset`{ "\u000A" }{ "\u000A" }Default personality scenario:{ $res }{ "\u000A" }Current conversation{ $curr_cid_title }Personality scenario:{ $curr_persona_name }{ "\u000A" }{ "\u000A" }To configure persona scenarios, please go to the Admin Panel - Configuration page.{ "\u000A" }
msg-c046b6e4 = { $msg }
msg-99139ef8 = Please enter the personality scenario name
msg-a44c7ec0 = There is no conversation currently, unable to cancel persona.
msg-a90c75d4 = Personality cancellation successful.
msg-a712d71a = There is no conversation currently. Please start a conversation first or use /new to create one.
msg-4e4e746d = Settings successful. If you are switching to a different persona, please use /reset to clear the context to prevent the original persona's dialogue from affecting the current one.{ $force_warn_msg }
msg-ab60a2e7 = The persona scenario does not exist. Use /persona list to view all.

### astrbot/builtin_stars/builtin_commands/commands/t2i.py

msg-855d5cf3 = Text-to-image mode has been disabled.
msg-64da24f4 = Text-to-image mode is enabled.

### astrbot/builtin_stars/builtin_commands/commands/admin.py

msg-ad019976 = Usage: /op <id> to authorize an administrator; /deop <id> to remove administrator. Use /sid to get the ID.
msg-1235330f = Authorization successful.
msg-e78847e0 = Usage: /deop <id> to remove admin. ID can be obtained via /sid.
msg-012152c1 = Authorization canceled successfully.
msg-5e076026 = This user ID is not in the administrator list.
msg-7f8eedde = Usage: /wl <id> to add to the whitelist; /dwl <id> to remove from the whitelist. Use /sid to get your ID.
msg-de1b0a87 = Whitelist added successfully.
msg-59d6fcbe = Usage: /dwl <id> to remove from whitelist. Use /sid to get the ID.
msg-4638580f = Whitelist deletion successful.
msg-278fb868 = This SID is not in the whitelist.
msg-1dee5007 = Attempting to update the management panel...
msg-76bea66c = Management panel update completed.

### astrbot/builtin_stars/builtin_commands/commands/sid.py

msg-ed8dcc22 = { $ret }

### astrbot/builtin_stars/builtin_commands/commands/plugin.py

msg-9cae24f5 = { $plugin_list_info }
msg-3f3a6087 = Demo mode cannot disable plugins.
msg-90e17cd4 = /plugin off <plugin name> Disable plugin.
msg-d29d6d57 = Plugin{ $plugin_name }Disabled.
msg-f90bbe20 = Plugins cannot be enabled in demo mode.
msg-b897048f = /plugin on <plugin name> Enable plugin.
msg-ebfb93bb = Plugin{ $plugin_name }Enabled.
msg-9cd74a8d = Plugins cannot be installed in demo mode.
msg-d79ad78d = /plugin get <plugin repository address> install plugin
msg-4f293fe1 = Preparing to fetch from{ $plugin_repo }Install plugin.
msg-d40e7065 = Plugin installed successfully.
msg-feff82c6 = Plugin installation failed:{ $e }
msg-5bfe9d3d = /plugin help <plugin name> to view plugin information.
msg-02627a9b = Plugin not found.
msg-ed8dcc22 = { $ret }

### astrbot/builtin_stars/builtin_commands/commands/help.py

msg-c046b6e4 = { $msg }

### astrbot/builtin_stars/builtin_commands/commands/alter_cmd.py

msg-d7a36c19 = This command is used to set permissions for a command or a group of commands.{ "\u000A" }Format: /alter_cmd <cmd_name> <admin/member>{ "\u000A" }Example 1: /alter_cmd c1 admin sets c1 as an admin command{ "\u000A" }Example 2: /alter_cmd g1 c1 admin sets the c1 sub-command of the g1 command group as an administrator command.{ "\u000A" }/alter_cmd reset config opens reset permission configuration
msg-afe0fa58 = { $config_menu }
msg-0c85d498 = Scene number and permission type cannot be empty
msg-4e0afcd1 = Scene number must be a number between 1 and 3
msg-830d6eb8 = Permission type error, must be admin or member
msg-d1180ead = The reset command has been{ $res }Permissions set for the scenario{ $perm_type }
msg-8d9bc364 = Command type error, available types are admin, member
msg-1f2f65e0 = The command was not found
msg-cd271581 = 已将「{ $cmd_name }"{ $cmd_group_str }The permission level has been adjusted to{ $cmd_type }.

### astrbot/builtin_stars/web_searcher/main.py

msg-7f5fd92b = Detected legacy websearch_tavily_key (string format), automatically migrated to list format and saved.
msg-bed9def5 = web_searcher - scraping web:{ $res }To be translated text:{ $res_2 }
msg-8214760c = Bing search error:{ $e }, try the next one...
msg-8676b5aa = Search Bing failed
msg-3fb6d6ad = sogo search error:{ $e }
msg-fe9b336f = search sogo failed
msg-c991b022 = Error: Tavily API key is not configured in AstrBot.
msg-b4fbb4a9 = Tavily web search failed:{ $reason }, status:{ $res }
msg-6769aba9 = Error: Tavily web searcher does not return any results.
msg-b4e7334e = This command has been deprecated. Please enable or disable web search functionality in the WebUI.
msg-b1877974 = web_searcher - search_from_search_engine:{ $query }
msg-2360df6b = Error processing search result:{ $processed_result }
msg-359d0443 = Error: Baidu AI Search API key is not configured in AstrBot.
msg-94351632 = Successfully initialized Baidu AI Search MCP server.
msg-5a7207c1 = web_searcher - search_from_tavily:{ $query }
msg-b36134c9 = Error: Tavily API key is not configured in AstrBot.
msg-98ed69f4 = Error: url must be a non-empty string.
msg-51edd9ee = Error: BoCha API key is not configured in AstrBot.
msg-73964067 = BoCha web search failed:{ $reason }, status:{ $res }
msg-34417720 = web_searcher - search_from_bocha:{ $query }
msg-b798883b = Error: BoCha API key is not configured in AstrBot.
msg-22993708 = Cannot get Baidu AI Search MCP tool.
msg-6f8d62a4 = Cannot Initialize Baidu AI Search MCP Server:{ $e }

### astrbot/builtin_stars/web_searcher/engines/bing.py

msg-e3b4d1e9 = Bing search failed

### astrbot/builtin_stars/astrbot/main.py

msg-3df554a1 = Chat Enhancement err:{ $e }
msg-5bdf8f5c = { $e }
msg-bb6ff036 = No LLM provider found. Please configure first. Cannot actively reply.
msg-afa050be = 当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。
msg-9a6a6b2e = No conversation found, unable to initiate a reply.
msg-78b9c276 = { $res }
msg-b177e640 = Active reply failed:{ $e }
msg-24d2f380 = ltm:{ $e }

### astrbot/builtin_stars/astrbot/long_term_memory.py

msg-5bdf8f5c = { $e }
msg-8e11fa57 = No ID found for{ $image_caption_provider_id }Provider
msg-8ebaa397 = Provider type error{ $res }), unable to get image description
msg-30954f77 = Image URL is empty
msg-62de0c3e = Failed to get image description:{ $e }
msg-d0647999 = ltm |{ $res }|{ $final_message }
msg-133c1f1d = Recorded AI response:{ $res }To be translated text:{ $final_message }

### astrbot/i18n/ftl_translate.py

msg-547c9cc5 = No environment variable DEEPSEEK_API_KEY detected, please set it first.
msg-8654e4be = { "\u000A" }[Error] API call failed:{ $e }
msg-75f207ed = File not found:{ $ftl_path }
msg-dcfbbe82 = No messages found in{ $ftl_path }
msg-ccd5a28f = Total{ $res }Text, use{ $max_workers }Concurrent threads translation...
msg-00b24d69 = { "\u000A" }[Error] Translation failed, original text retained:{ $e }
msg-ebcdd595 = { "\u000A" }Translation completed, saved to{ $ftl_path }
msg-d6c66497 = Error: Please set the DEEPSEEK_API_KEY environment variable first.
msg-09486085 = For example: export DEEPSEEK_API_KEY='sk-xxxxxx'

### scripts/generate_changelog.py

msg-a79937ef = Warning: openai package not installed. Install it with: pip install openai
msg-090bfd36 = Warning: Failed to call LLM API:{ $e }
msg-a3ac9130 = Falling back to simple changelog generation...
msg-6f1011c5 = Latest tag:{ $latest_tag }
msg-8c7f64d7 = Error: No tags found in repository
msg-a89fa0eb = No commits found since{ $latest_tag }
msg-846ebecf = Found{ $res }commits since{ $latest_tag }
msg-9ad686af = Warning: Could not parse version from tag{ $latest_tag }
msg-f5d43a54 = Generating changelog for{ $version }...
msg-e54756e8 = { "\u000A" }✓ Changelog generated:{ $changelog_file }
msg-82be6c98 = { "\u000A" }Preview:
msg-321ac5b1 = { $changelog_content }

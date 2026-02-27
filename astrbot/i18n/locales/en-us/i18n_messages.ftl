
### main.py
msg-5e25709f = 请使用 Python3.10+ 运行本项目。
msg-afd0ab81 = 使用指定的 WebUI 目录: {$webui_dir}
msg-7765f00f = 指定的 WebUI 目录 {$webui_dir} 不存在，将使用默认逻辑。
msg-9af20e37 = WebUI 版本已是最新。
msg-9dd5c1d2 = 检测到 WebUI 版本 ({$v}) 与当前 AstrBot 版本 (v{$VERSION}) 不符。
msg-ec714d4e = 开始下载管理面板文件...高峰期（晚上）可能导致较慢的速度。如多次下载失败，请前往 https://github.com/AstrBotDevs/AstrBot/releases/latest 下载 dist.zip，并将其中的 dist 文件夹解压至 data 目录下。
msg-c5170c27 = 下载管理面板文件失败: {$e}。
msg-e1592ad1 = 管理面板下载完成。
msg-fe494da6 = {$logo_tmpl}

### astrbot/core/lang.py
msg-d103bc8e = Namespace must not be empty.
msg-f66527da = Namespace must not contain '.'.
msg-b3665aee = Locale directory does not exist: {$base_dir}
msg-3fe89e6a = No locale directories found under: {$base_dir}
msg-c79b2c75 = Namespace '{$namespace}' already exists. Set replace=True to overwrite.
msg-7db3fccf = Default namespace cannot be unregistered.
msg-3d066f64 = Namespace '{$namespace}' is not registered.

### astrbot/core/persona_mgr.py
msg-51a854e6 = 已加载 {$res} 个人格。
msg-1ea88f45 = Persona with ID {$persona_id} does not exist.
msg-28104dff = Persona with ID {$persona_id} already exists.
msg-08ecfd42 = {$res} 人格情景预设对话格式不对，条数应该为偶数。
msg-b6292b94 = 解析 Persona 配置失败：{$e}

### astrbot/core/initial_loader.py
msg-78b9c276 = {$res}
msg-58525c23 = 😭 初始化 AstrBot 失败：{$e} !!!
msg-002cc3e8 = 🌈 正在关闭 AstrBot...

### astrbot/core/log.py
msg-80a186b8 = Failed to add file sink: {$e}

### astrbot/core/astrbot_config_mgr.py
msg-7875e5bd = Config file {$conf_path} for UUID {$uuid_} does not exist, skipping.
msg-39c4fd49 = 不能删除默认配置文件
msg-cf7b8991 = 配置文件 {$conf_id} 不存在于映射中
msg-2aad13a4 = 已删除配置文件: {$conf_path}
msg-94c359ef = 删除配置文件 {$conf_path} 失败: {$e}
msg-44f0b770 = 成功删除配置文件 {$conf_id}
msg-737da44e = 不能更新默认配置文件的信息
msg-9d496709 = 成功更新配置文件 {$conf_id} 的信息

### astrbot/core/zip_updator.py
msg-24c90ff8 = 请求 {$url} 失败，状态码: {$res}, 内容: {$text}
msg-14726dd8 = 请求失败，状态码: {$res}
msg-fc3793c6 = 解析版本信息时发生异常: {$e}
msg-491135d9 = 解析版本信息失败
msg-03a72cb5 = 未找到合适的发布版本
msg-8bcbfcf0 = 正在下载更新 {$repo} ...
msg-ccc87294 = 正在从指定分支 {$branch} 下载 {$author}/{$repo}
msg-dfebcdc6 = 获取 {$author}/{$repo} 的 GitHub Releases 失败: {$e}，将尝试下载默认分支
msg-e327bc14 = 正在从默认分支下载 {$author}/{$repo}
msg-3cd3adfb = 检查到设置了镜像站，将使用镜像站下载 {$author}/{$repo} 仓库源码: {$release_url}
msg-1bffc0d7 = 无效的 GitHub URL
msg-0ba954db = 解压文件完成: {$zip_path}
msg-90ae0d15 = 删除临时更新文件: {$zip_path} 和 {$res}
msg-f8a43aa5 = 删除更新文件失败，可以手动删除 {$zip_path} 和 {$res}

### astrbot/core/file_token_service.py
msg-0e444e51 = 文件不存在: {$local_path} (原始输入: {$file_path})
msg-f61a5322 = 无效或过期的文件 token: {$file_token}
msg-73d3e179 = 文件不存在: {$file_path}

### astrbot/core/subagent_orchestrator.py
msg-5d950986 = subagent_orchestrator.agents must be a list
msg-29e3b482 = SubAgent persona %s not found, fallback to inline prompt.
msg-f425c9f0 = Registered subagent handoff tool: {$res}

### astrbot/core/astr_main_agent.py
msg-8dcf5caa = 未找到指定的提供商: %s。
msg-61d46ee5 = 选择的提供商类型无效(%s)，跳过 LLM 请求处理。
msg-496864bc = Error occurred while selecting provider: %s
msg-507853eb = 无法创建新的对话。
msg-66870b7e = Error occurred while retrieving knowledge base: %s
msg-36dc1409 = Moonshot AI API key for file extract is not set
msg-8534047e = Unsupported file extract provider: %s
msg-f2ea29f4 = Cannot get image caption because provider `{$provider_id}` is not exist.
msg-91a70615 = Cannot get image caption because provider `{$provider_id}` is not a valid Provider, it is {$res}.
msg-b1840df0 = Processing image caption with provider: %s
msg-089421fc = 处理图片描述失败: %s
msg-719d5e4d = No provider found for image captioning in quote.
msg-e16a974b = 处理引用图片失败: %s
msg-037dad2e = Group name display enabled but group object is None. Group ID: %s
msg-58b47bcd = 时区设置错误: %s, 使用本地时区
msg-938af433 = Provider %s does not support image, using placeholder.
msg-83d739f8 = Provider %s does not support tool_use, clearing tools.
msg-3dbad2d9 = sanitize_context_by_modalities applied: removed_image_blocks=%s, removed_tool_messages=%s, removed_tool_calls=%s
msg-4214b760 = Generated chatui title for session %s: %s
msg-cb6db56e = Unsupported llm_safety_mode strategy: %s.
msg-7ea2c5d3 = Shipyard sandbox configuration is incomplete.
msg-9248b273 = 未找到指定的上下文压缩模型 %s，将跳过压缩。
msg-16fe8ea5 = 指定的上下文压缩模型 %s 不是对话模型，将跳过压缩。
msg-c6c9d989 = fallback_chat_models setting is not a list, skip fallback providers.
msg-614aebad = Fallback chat provider `%s` not found, skip.
msg-1a2e87dd = Fallback chat provider `%s` is invalid type: %s, skip.
msg-ee979399 = 未找到任何对话模型（提供商），跳过 LLM 请求处理。
msg-7a7b4529 = Skip quoted fallback images due to limit=%d for umo=%s
msg-46bcda31 = Truncate quoted fallback images for umo=%s, reply_id=%s from %d to %d
msg-cbceb923 = Failed to resolve fallback quoted images for umo=%s, reply_id=%s: %s
msg-31483e80 = Error occurred while applying file extract: %s

### astrbot/core/umop_config_router.py
msg-dedcfded = umop keys must be strings in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all
msg-8e3a16f3 = umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all

### astrbot/core/event_bus.py
msg-da466871 = PipelineScheduler not found for id: {$res}, event ignored.
msg-7eccffa5 = [{$conf_name}] [{$res}({$res_2})] {$res_3}/{$res_4}: {$res_5}
msg-88bc26f2 = [{$conf_name}] [{$res}({$res_2})] {$res_3}: {$res_4}

### astrbot/core/astr_agent_tool_exec.py
msg-e5f2fb34 = Background task {$task_id} failed: {$e}
msg-c54b2335 = Background handoff {$task_id} ({$res}) failed: {$e}
msg-8c2fe51d = Failed to build main agent for background task {$tool_name}.
msg-c6d4e4a6 = background task agent got no response
msg-0b3711f1 = Event must be provided for local function tools.
msg-8c19e27a = Tool must have a valid handler or override 'run' method.
msg-24053a5f = Tool 直接发送消息失败: {$e}
msg-f940b51e = tool {$res} execution timeout after {$res_2} seconds.
msg-7e22fc8e = 未知的方法名: {$method_name}
msg-c285315c = Tool execution ValueError: {$e}
msg-41366b74 = Tool handler parameter mismatch, please check the handler definition. Handler parameters: {$handler_param_str}
msg-e8cadf8e = Tool execution error: {$e}. Traceback: {$trace_}
msg-d7b4aa84 = Previous Error: {$trace_}

### astrbot/core/astr_agent_run_util.py
msg-6b326889 = Agent reached max steps ({$max_step}), forcing a final response.
msg-bb15e9c7 = {$status_msg}
msg-78b9c276 = {$res}
msg-9c246298 = Error in on_agent_done hook
msg-34f164d4 = {$err_msg}
msg-6d9553b2 = [Live Agent] 使用流式 TTS（原生支持 get_audio_stream）
msg-becf71bf = [Live Agent] 使用 TTS（{$res} 使用 get_audio，将按句子分块生成音频）
msg-21723afb = [Live Agent] 运行时发生错误: {$e}
msg-ca1bf0d7 = 发送 TTS 统计信息失败: {$e}
msg-5ace3d96 = [Live Agent Feeder] 分句: {$temp_buffer}
msg-bc1826ea = [Live Agent Feeder] Error: {$e}
msg-a92774c9 = [Live TTS Stream] Error: {$e}
msg-d7b3bbae = [Live TTS Simulated] Error processing text '{$res}...': {$e}
msg-035bca5f = [Live TTS Simulated] Critical Error: {$e}

### astrbot/core/astr_main_agent_resources.py
msg-509829d8 = Downloaded file from sandbox: {$path} -> {$local_path}
msg-b462b60d = Failed to check/download file from sandbox: {$e}
msg-0b3144f1 = [知识库] 会话 {$umo} 已被配置为不使用知识库
msg-97e13f98 = [知识库] 知识库不存在或未加载: {$kb_id}
msg-312d09c7 = [知识库] 会话 {$umo} 配置的以下知识库无效: {$invalid_kb_ids}
msg-42b0e9f8 = [知识库] 使用会话级配置，知识库数量: {$res}
msg-08167007 = [知识库] 使用全局配置，知识库数量: {$res}
msg-a00becc3 = [知识库] 开始检索知识库，数量: {$res}, top_k={$top_k}
msg-199e71b7 = [知识库] 为会话 {$umo} 注入了 {$res} 条相关知识块

### astrbot/core/conversation_mgr.py
msg-86f404dd = 会话删除回调执行失败 (session: {$unified_msg_origin}): {$e}
msg-57dcc41f = Conversation with id {$cid} not found

### astrbot/core/updator.py
msg-e3d42a3b = 正在终止 {$res} 个子进程。
msg-e7edc4a4 = 正在终止子进程 {$res}
msg-37bea42d = 子进程 {$res} 没有被正常终止, 正在强行杀死。
msg-cc6d9588 = 重启失败（{$executable}, {$e}），请尝试手动重启。
msg-0e4439d8 = 不支持更新此方式启动的AstrBot
msg-3f39a942 = 当前已经是最新版本。
msg-c7bdf215 = 未找到版本号为 {$version} 的更新文件。
msg-92e46ecc = commit hash 长度不正确，应为 40
msg-71c01b1c = 准备更新至指定版本的 AstrBot Core: {$version}
msg-d3a0e13d = 下载 AstrBot Core 更新文件完成，正在执行解压...

### astrbot/core/core_lifecycle.py
msg-9967ec8b = Using proxy: {$proxy_config}
msg-5a29b73d = HTTP proxy cleared
msg-fafb87ce = Subagent orchestrator init failed: {$e}
msg-f7861f86 = AstrBot migration failed: {$e}
msg-78b9c276 = {$res}
msg-967606fd = ------- 任务 {$res} 发生错误: {$e}
msg-a2cd77f3 = |    {$line}
msg-1f686eeb = -------
msg-9556d279 = AstrBot 启动完成。
msg-daaf690b = hook(on_astrbot_loaded) -> {$res} - {$res_2}
msg-4719cb33 = 插件 {$res} 未被正常终止 {$e}, 可能会导致资源泄露等问题。
msg-c3bbfa1d = 任务 {$res} 发生错误: {$e}
msg-af06ccab = 配置文件 {$conf_id} 不存在

### astrbot/core/pipeline/context_utils.py
msg-49f260d3 = 处理函数参数不匹配，请检查 handler 的定义。
msg-d7b4aa84 = Previous Error: {$trace_}
msg-eb8619cb = hook({$res}) -> {$res_2} - {$res_3}
msg-78b9c276 = {$res}
msg-add19f94 = {$res} - {$res_2} 终止了事件传播。

### astrbot/core/pipeline/__init__.py
msg-1c9fc93d = module {$__name__} has no attribute {$name}

### astrbot/core/pipeline/scheduler.py
msg-c240d574 = 阶段 {$res} 已终止事件传播。
msg-609a1ac5 = pipeline 执行完毕。

### astrbot/core/pipeline/rate_limit_check/stage.py
msg-18092978 = 会话 {$session_id} 被限流。根据限流策略，此会话处理将被暂停 {$stall_duration} 秒。
msg-4962387a = 会话 {$session_id} 被限流。根据限流策略，此请求已被丢弃，直到限额于 {$stall_duration} 秒后重置。

### astrbot/core/pipeline/whitelist_check/stage.py
msg-8282c664 = 会话 ID {$res} 不在会话白名单中，已终止事件传播。请在配置文件中添加该会话 ID 到白名单。

### astrbot/core/pipeline/process_stage/follow_up.py
msg-df881b01 = Captured follow-up message for active agent run, umo=%s, order_seq=%s

### astrbot/core/pipeline/process_stage/method/agent_request.py
msg-3267978a = 识别 LLM 聊天额外唤醒前缀 {$res} 以机器人唤醒前缀 {$bwp} 开头，已自动去除。
msg-97a4d573 = This pipeline does not enable AI capability, skip processing.
msg-f1a11d2b = The session {$res} has disabled AI capability, skipping processing.

### astrbot/core/pipeline/process_stage/method/star_request.py
msg-f0144031 = Cannot find plugin for given handler module path: {$res}
msg-1e8939dd = plugin -> {$res} - {$res_2}
msg-6be73b5e = {$traceback_text}
msg-d919bd27 = Star {$res} handle error: {$e}
msg-ed8dcc22 = {$ret}

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py
msg-60493581 = Unsupported tool_schema_mode: %s, fallback to skills_like
msg-9cdb2b6e = skip llm request: empty message and no provider_request
msg-e461e5af = ready to request llm provider
msg-be33dd11 = Follow-up ticket already consumed, stopping processing. umo=%s, seq=%s
msg-abd5ccbc = acquired session lock for llm request
msg-f9d617d7 = Provider API base %s is blocked due to security reasons. Please use another ai provider.
msg-3247374d = [Internal Agent] 检测到 Live Mode，启用 TTS 处理
msg-dae92399 = [Live Mode] TTS Provider 未配置，将使用普通流式模式
msg-1b1af61e = Error occurred while processing agent: {$e}
msg-ea02b899 = Error occurred while processing agent request: {$e}
msg-ee7e792b = LLM 响应为空，不保存记录。

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/third_party.py
msg-5e551baf = Third party agent runner error: {$e}
msg-34f164d4 = {$err_msg}
msg-f9d76893 = 没有填写 Agent Runner 提供商 ID，请前往配置页面配置。
msg-0f856470 = Agent Runner 提供商 {$res} 配置不存在，请前往配置页面修改配置。
msg-b3f25c81 = Unsupported third party agent runner type: {$res}
msg-6c63eb68 = Agent Runner 未返回最终结果。

### astrbot/core/pipeline/result_decorate/stage.py
msg-7ec898fd = hook(on_decorating_result) -> {$res} - {$res_2}
msg-5e27dae6 = 启用流式输出时，依赖发送消息前事件钩子的插件可能无法正常工作
msg-caaaec29 = hook(on_decorating_result) -> {$res} - {$res_2} 将消息结果清空。
msg-78b9c276 = {$res}
msg-add19f94 = {$res} - {$res_2} 终止了事件传播。
msg-813a44bb = 流式输出已启用，跳过结果装饰阶段
msg-891aa43a = 分段回复正则表达式错误，使用默认分段方式: {$res}
msg-82bb9025 = 会话 {$res} 未配置文本转语音模型。
msg-fb1c757a = TTS 请求: {$res}
msg-06341d25 = TTS 结果: {$audio_path}
msg-2057f670 = 由于 TTS 音频文件未找到，消息段转语音失败: {$res}
msg-f26725cf = 已注册：{$url}
msg-47716aec = TTS 失败，使用文本发送。
msg-ffe054a9 = 文本转图片失败，使用文本发送。
msg-06c1aedc = 文本转图片耗时超过了 3 秒，如果觉得很慢可以使用 /t2i 关闭文本转图片模式。

### astrbot/core/pipeline/waking_check/stage.py
msg-df815938 = enabled_plugins_name: {$enabled_plugins_name}
msg-51182733 = 插件 {$res}: {$e}
msg-e0dcf0b8 = 您(ID: {$res})的权限不足以使用此指令。通过 /sid 获取 ID 并请管理员添加。
msg-a3c3706f = 触发 {$res} 时, 用户(ID={$res_2}) 权限不足。

### astrbot/core/pipeline/session_status_check/stage.py
msg-f9aba737 = 会话 {$res} 已被关闭，已终止事件传播。

### astrbot/core/pipeline/respond/stage.py
msg-59539c6e = 解析分段回复的间隔时间失败。{$e}
msg-4ddee754 = 分段回复间隔时间：{$res}
msg-5e2371a9 = Prepare to send - {$res}/{$res_2}: {$res_3}
msg-df92ac24 = async_stream 为空，跳过发送。
msg-858b0e4f = 应用流式输出({$res})
msg-22c7a672 = 消息为空，跳过发送阶段
msg-e6ab7a25 = 空内容检查异常: {$e}
msg-b29b99c1 = 实际消息链为空, 跳过发送阶段。header_chain: {$header_comps}, actual_chain: {$res}
msg-842df577 = 发送消息链失败: chain = {$res}, error = {$e}
msg-f35465cf = 消息链全为 Reply 和 At 消息段, 跳过发送阶段。chain: {$res}
msg-784e8a67 = 发送消息链失败: chain = {$chain}, error = {$e}

### astrbot/core/pipeline/content_safety_check/stage.py
msg-c733275f = 你的消息或者大模型的响应中包含不适当的内容，已被屏蔽。
msg-46c80f28 = 内容安全检查不通过，原因：{$info}

### astrbot/core/pipeline/content_safety_check/strategies/strategy.py
msg-27a700e0 = 使用百度内容审核应该先 pip install baidu-aip

### astrbot/core/pipeline/preprocess_stage/stage.py
msg-7b9074fa = {$platform} 预回应表情发送失败: {$e}
msg-43f1b4ed = 路径映射: {$url} -> {$res}
msg-9549187d = 会话 {$res} 未配置语音转文本模型。
msg-5bdf8f5c = {$e}
msg-ad90e19e = 重试中: {$res}/{$retry}
msg-78b9c276 = {$res}
msg-4f3245bf = 语音转文本失败: {$e}

### astrbot/core/config/astrbot_config.py
msg-e0a69978 = 不受支持的配置类型 {$res}。支持的类型有：{$res_2}
msg-b9583fc9 = 检查到配置项 {$path_} 不存在，已插入默认值 {$value}
msg-ee26e40e = 检查到配置项 {$path_} 不存在，将从当前配置中删除
msg-2d7497a5 = 检查到配置项 {$path} 的子项顺序不一致，已重新排序
msg-5fdad937 = 检查到配置项顺序不一致，已重新排序
msg-555373b0 = 没有找到 Key: '{$key}'

### astrbot/core/platform/register.py
msg-eecf0aa8 = 平台适配器 {$adapter_name} 已经注册过了，可能发生了适配器命名冲突。
msg-614a55eb = 平台适配器 {$adapter_name} 已注册
msg-bb06a88d = 平台适配器 {$res} 已注销 (来自模块 {$res_2})

### astrbot/core/platform/platform.py
msg-30fc9871 = 平台 {$res} 未实现统一 Webhook 模式

### astrbot/core/platform/astr_message_event.py
msg-b593f13f = Failed to convert message type {$res} to MessageType. Falling back to FRIEND_MESSAGE.
msg-98bb33b7 = 清除 {$res} 的额外信息: {$res_2}
msg-0def44e2 = {$result}
msg-8e7dc862 = {$text}

### astrbot/core/platform/manager.py
msg-464b7ab7 = 终止平台适配器失败: client_id=%s, error=%s
msg-78b9c276 = {$res}
msg-563a0a74 = 初始化 {$platform} 平台适配器失败: {$e}
msg-8432d24e = 平台 ID %r 包含非法字符 ':' 或 '!'，已替换为 %r。
msg-31361418 = 平台 ID {$platform_id} 不能为空，跳过加载该平台适配器。
msg-e395bbcc = 载入 {$res}({$res_2}) 平台适配器 ...
msg-b4b29344 = 加载平台适配器 {$res} 失败，原因：{$e}。请检查依赖库是否安装。提示：可以在 管理面板->平台日志->安装Pip库 中安装依赖库。
msg-18f0e1fe = 加载平台适配器 {$res} 失败，原因：{$e}。
msg-2636a882 = 未找到适用于 {$res}({$res_2}) 平台适配器，请检查是否已经安装或者名称填写错误
msg-c4a38b85 = hook(on_platform_loaded) -> {$res} - {$res_2}
msg-967606fd = ------- 任务 {$res} 发生错误: {$e}
msg-a2cd77f3 = |    {$line}
msg-1f686eeb = -------
msg-38723ea8 = 正在尝试终止 {$platform_id} 平台适配器 ...
msg-63f684c6 = 可能未完全移除 {$platform_id} 平台适配器
msg-136a952f = 获取平台统计信息失败: {$e}

### astrbot/core/platform/sources/dingtalk/dingtalk_adapter.py
msg-c81e728d = 2
msg-d6371313 = dingtalk: {$res}
msg-a1c8b5b1 = 钉钉私聊会话缺少 staff_id 映射，回退使用 session_id 作为 userId 发送
msg-2abb842f = 保存钉钉会话映射失败: {$e}
msg-46988861 = 下载钉钉文件失败: {$res}, {$res_2}
msg-ba9e1288 = 通过 dingtalk_stream 获取 access_token 失败: {$e}
msg-835b1ce6 = 获取钉钉机器人 access_token 失败: {$res}, {$res_2}
msg-331fcb1f = 读取钉钉 staff_id 映射失败: {$e}
msg-ba183a34 = 钉钉群消息发送失败: access_token 为空
msg-b8aaa69b = 钉钉群消息发送失败: {$res}, {$res_2}
msg-cfb35bf5 = 钉钉私聊消息发送失败: access_token 为空
msg-7553c219 = 钉钉私聊消息发送失败: {$res}, {$res_2}
msg-5ab2d58d = 清理临时文件失败: {$file_path}, {$e}
msg-c0c40912 = 钉钉语音转 OGG 失败，回退 AMR: {$e}
msg-21c73eca = 钉钉媒体上传失败: access_token 为空
msg-24e3054f = 钉钉媒体上传失败: {$res}, {$res_2}
msg-34d0a11d = 钉钉媒体上传失败: {$data}
msg-3b0d4fb5 = 钉钉语音发送失败: {$e}
msg-7187f424 = 钉钉视频发送失败: {$e}
msg-e40cc45f = 钉钉私聊回复失败: 缺少 sender_staff_id
msg-be63618a = 钉钉适配器已被关闭
msg-0ab22b13 = 钉钉机器人启动失败: {$e}

### astrbot/core/platform/sources/dingtalk/dingtalk_event.py
msg-eaa1f3e4 = 钉钉消息发送失败: 缺少 adapter

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py
msg-41a3e59d = 正在登录到 QQ 官方机器人...
msg-66040e15 = 已登录 QQ 官方机器人账号: {$res}
msg-6ed59b60 = 收到 qq_official_webhook 回调: {$msg}
msg-ad355b59 = {$signed}
msg-1f6260e4 = _parser unknown event %s.
msg-cef08b17 = 将在 {$res}:{$res_2} 端口启动 QQ 官方机器人 webhook 适配器。

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_adapter.py
msg-3803e307 = [QQOfficialWebhook] No cached msg_id for session: %s, skip send_by_session
msg-08fd28cf = [QQOfficialWebhook] Unsupported message type for send_by_session: %s
msg-6fa95bb3 = Exception occurred during QQOfficialWebhook server shutdown: {$exc}
msg-6f83eea0 = QQ 机器人官方 API 适配器已经被优雅地关闭

### astrbot/core/platform/sources/discord/discord_platform_event.py
msg-0056366b = [Discord] 解析消息链时失败: {$e}
msg-fa0a9e40 = [Discord] 尝试发送空消息，已忽略。
msg-5ccebf9a = [Discord] 频道 {$res} 不是可发送消息的类型
msg-1550c1eb = [Discord] 发送消息时发生未知错误: {$e}
msg-7857133d = [Discord] 无法获取频道 {$res}
msg-050aa8d6 = [Discord] 开始处理 Image 组件: {$i}
msg-57c802ef = [Discord] Image 组件没有 file 属性: {$i}
msg-f2bea7ac = [Discord] 处理 URL 图片: {$file_content}
msg-c3eae1f1 = [Discord] 处理 File URI: {$file_content}
msg-6201da92 = [Discord] 图片文件不存在: {$path}
msg-2a6f0cd4 = [Discord] 处理 Base64 URI
msg-b589c643 = [Discord] 尝试作为裸 Base64 处理
msg-41dd4b8f = [Discord] 裸 Base64 解码失败，作为本地路径处理: {$file_content}
msg-f59778a1 = [Discord] 处理图片时发生未知严重错误: {$file_info}
msg-85665612 = [Discord] 获取文件失败，路径不存在: {$file_path_str}
msg-e55956fb = [Discord] 获取文件失败: {$res}
msg-56cc0d48 = [Discord] 处理文件失败: {$res}, 错误: {$e}
msg-c0705d4e = [Discord] 忽略了不支持的消息组件: {$res}
msg-0417d127 = [Discord] 消息内容超过2000字符，将被截断。
msg-6277510f = [Discord] 添加反应失败: {$e}

### astrbot/core/platform/sources/discord/client.py
msg-940888cb = [Discord] 客户端未正确加载用户信息 (self.user is None)
msg-9a3c1925 = [Discord] 已作为 {$res} (ID: {$res_2}) 登录
msg-30c1f1c8 = [Discord] 客户端已准备就绪。
msg-d8c03bdf = [Discord] on_ready_once_callback 执行失败: {$e}
msg-c9601653 = Bot is not ready: self.user is None
msg-4b017a7c = Interaction received without a valid user
msg-3067bdce = [Discord] 收到原始消息 from {$res}: {$res_2}

### astrbot/core/platform/sources/discord/discord_platform_adapter.py
msg-7ea23347 = [Discord] 客户端未就绪 (self.client.user is None)，无法发送消息
msg-ff6611ce = [Discord] Invalid channel ID format: {$channel_id_str}
msg-5e4e5d63 = [Discord] Can't get channel info for {$channel_id_str}, will guess message type.
msg-32d4751b = [Discord] 收到消息: {$message_data}
msg-8296c994 = [Discord] Bot Token 未配置。请在配置文件中正确设置 token。
msg-170b31df = [Discord] 登录失败。请检查你的 Bot Token 是否正确。
msg-6678fbd3 = [Discord] 与 Discord 的连接已关闭。
msg-cd8c35d2 = [Discord] 适配器运行时发生意外错误: {$e}
msg-4df30f1d = [Discord] 客户端未就绪 (self.client.user is None)，无法处理消息
msg-f7803502 = [Discord] 收到非 Message 类型的消息: {$res}，已忽略。
msg-134e70e9 = [Discord] 正在终止适配器... (step 1: cancel polling task)
msg-5c01a092 = [Discord] polling_task 已取消。
msg-77f8ca59 = [Discord] polling_task 取消异常: {$e}
msg-528b6618 = [Discord] 正在清理已注册的斜杠指令... (step 2)
msg-d0b832e6 = [Discord] 指令清理完成。
msg-43383f5e = [Discord] 清理指令时发生错误: {$e}
msg-b960ed33 = [Discord] 正在关闭 Discord 客户端... (step 3)
msg-5e58f8a2 = [Discord] 客户端关闭异常: {$e}
msg-d1271bf1 = [Discord] 适配器已终止。
msg-c374da7a = [Discord] 开始收集并注册斜杠指令...
msg-a6d37e4d = [Discord] 准备同步 {$res} 个指令: {$res_2}
msg-dbcaf095 = [Discord] 没有发现可注册的指令。
msg-09209f2f = [Discord] 指令同步完成。
msg-a95055fd = [Discord] 回调函数触发: {$cmd_name}
msg-55b13b1e = [Discord] 回调函数参数: {$ctx}
msg-79f72e4e = [Discord] 回调函数参数: {$params}
msg-22add467 = [Discord] 斜杠指令 '{$cmd_name}' 被触发。 原始参数: '{$params}'. 构建的指令字符串: '{$message_str_for_filter}'
msg-ccffc74a = [Discord] 指令 '{$cmd_name}' defer 失败: {$e}
msg-13402a28 = [Discord] 跳过不符合规范的指令: {$cmd_name}

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py
msg-859d480d = Handle request message failed: {$e}
msg-6fb672e1 = Handle notice message failed: {$e}
msg-cf4687a3 = Handle group message failed: {$e}
msg-3a9853e3 = Handle private message failed: {$e}
msg-ec06dc3d = aiocqhttp(OneBot v11) 适配器已连接。
msg-1304a54d = [aiocqhttp] RawMessage {$event}
msg-93cbb9fa = {$err}
msg-a4487a03 = 回复消息失败: {$e}
msg-48bc7bff = guessing lagrange
msg-6ab145a1 = 获取文件失败: {$ret}
msg-457454d7 = 获取文件失败: {$e}，此消息段将被忽略。
msg-7a299806 = 无法从回复消息数据构造 Event 对象: {$reply_event_data}
msg-e6633a51 = 获取引用消息失败: {$e}。
msg-6e99cb8d = 获取 @ 用户信息失败: {$e}，此消息段将被忽略。
msg-cf15fd40 = 不支持的消息段类型，已忽略: {$t}, data={$res}
msg-45d126ad = 消息段解析失败: type={$t}, data={$res}. {$e}
msg-394a20ae = aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port，将使用默认值：http://0.0.0.0:6199
msg-7414707c = aiocqhttp 适配器已被关闭

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py
msg-0db8227d = 无法发送消息：缺少有效的数字 session_id({$session_id}) 或 event({$event})

### astrbot/core/platform/sources/lark/server.py
msg-2f3bccf1 = 未配置 encrypt_key，无法解密事件
msg-e77104e2 = [Lark Webhook] 收到 challenge 验证请求: {$challenge}
msg-34b24fa1 = [Lark Webhook] 解析请求体失败: {$e}
msg-ec0fe13e = [Lark Webhook] 请求体为空
msg-f69ebbdb = [Lark Webhook] 签名验证失败
msg-7ece4036 = [Lark Webhook] 解密后的事件: {$event_data}
msg-f2cb4b46 = [Lark Webhook] 解密事件失败: {$e}
msg-ef9f8906 = [Lark Webhook] Verification Token 不匹配。
msg-bedb2071 = [Lark Webhook] 处理事件回调失败: {$e}

### astrbot/core/platform/sources/lark/lark_event.py
msg-eefbe737 = [Lark] API Client im 模块未初始化
msg-a21f93fa = [Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空
msg-f456e468 = [Lark] 发送飞书消息失败({$res}): {$res_2}
msg-1eb66d14 = [Lark] 文件不存在: {$path}
msg-1df39b24 = [Lark] API Client im 模块未初始化，无法上传文件
msg-2ee721dd = [Lark] 无法上传文件({$res}): {$res_2}
msg-a04abf78 = [Lark] 上传文件成功但未返回数据(data is None)
msg-959e78a4 = [Lark] 文件上传成功: {$file_key}
msg-901a2f60 = [Lark] 无法打开或上传文件: {$e}
msg-13065327 = [Lark] 图片路径为空，无法上传
msg-37245892 = [Lark] 无法打开图片文件: {$e}
msg-ad63bf53 = [Lark] API Client im 模块未初始化，无法上传图片
msg-ef90038b = 无法上传飞书图片({$res}): {$res_2}
msg-d2065832 = [Lark] 上传图片成功但未返回数据(data is None)
msg-dbb635c2 = {$image_key}
msg-d4810504 = [Lark] 检测到文件组件，将单独发送
msg-45556717 = [Lark] 检测到音频组件，将单独发送
msg-959070b5 = [Lark] 检测到视频组件，将单独发送
msg-4e2aa152 = 飞书 暂时不支持消息段: {$res}
msg-20d7c64b = [Lark] 无法获取音频文件路径: {$e}
msg-2f6f35e6 = [Lark] 音频文件不存在: {$original_audio_path}
msg-528b968d = [Lark] 音频格式转换失败，将尝试直接上传: {$e}
msg-fbc7efb9 = [Lark] 已删除转换后的音频文件: {$converted_audio_path}
msg-09840299 = [Lark] 删除转换后的音频文件失败: {$e}
msg-e073ff1c = [Lark] 无法获取视频文件路径: {$e}
msg-47e52913 = [Lark] 视频文件不存在: {$original_video_path}
msg-85ded1eb = [Lark] 视频格式转换失败，将尝试直接上传: {$e}
msg-b3bee05d = [Lark] 已删除转换后的视频文件: {$converted_video_path}
msg-775153f6 = [Lark] 删除转换后的视频文件失败: {$e}
msg-45038ba7 = [Lark] API Client im 模块未初始化，无法发送表情
msg-8d475b01 = 发送飞书表情回应失败({$res}): {$res_2}

### astrbot/core/platform/sources/lark/lark_adapter.py
msg-06ce76eb = 未设置飞书机器人名称，@ 机器人可能得不到回复。
msg-eefbe737 = [Lark] API Client im 模块未初始化
msg-236bcaad = [Lark] 下载消息资源失败 type={$resource_type}, key={$file_key}, code={$res}, msg={$res_2}
msg-ef9a61fe = [Lark] 消息资源响应中不包含文件流: {$file_key}
msg-7b69a8d4 = [Lark] 图片消息缺少 message_id
msg-59f1694d = [Lark] 富文本视频消息缺少 message_id
msg-af8f391d = [Lark] 文件消息缺少 message_id
msg-d4080b76 = [Lark] 文件消息缺少 file_key
msg-ab21318a = [Lark] 音频消息缺少 message_id
msg-9ec2c30a = [Lark] 音频消息缺少 file_key
msg-0fa9ed18 = [Lark] 视频消息缺少 message_id
msg-ae884c5c = [Lark] 视频消息缺少 file_key
msg-dac98a62 = [Lark] 获取引用消息失败 id={$parent_message_id}, code={$res}, msg={$res_2}
msg-7ee9f7dc = [Lark] 引用消息响应为空 id={$parent_message_id}
msg-2b3b2db9 = [Lark] 解析引用消息内容失败 id={$quoted_message_id}
msg-c5d54255 = [Lark] 收到空事件(event.event is None)
msg-82f041c4 = [Lark] 事件中没有消息体(message is None)
msg-206c3506 = [Lark] 消息内容为空
msg-876aa1d2 = [Lark] 解析消息内容失败: {$res}
msg-514230f3 = [Lark] 消息内容不是 JSON Object: {$res}
msg-0898cf8b = [Lark] 解析消息内容: {$content_json_b}
msg-6a8bc661 = [Lark] 消息缺少 message_id
msg-26554571 = [Lark] 消息发送者信息不完整
msg-007d863a = [Lark Webhook] 跳过重复事件: {$event_id}
msg-6ce17e71 = [Lark Webhook] 未处理的事件类型: {$event_type}
msg-8689a644 = [Lark Webhook] 处理事件失败: {$e}
msg-20688453 = [Lark] Webhook 模式已启用，但 webhook_server 未初始化
msg-f46171bc = [Lark] Webhook 模式已启用，但未配置 webhook_uuid
msg-dd90a367 = 飞书(Lark) 适配器已关闭

### astrbot/core/platform/sources/wecom/wecom_event.py
msg-e164c137 = 未找到微信客服发送消息方法。
msg-c114425e = 微信客服上传图片失败: {$e}
msg-a90bc15d = 微信客服上传图片返回: {$response}
msg-38298880 = 微信客服上传语音失败: {$e}
msg-3aee0caa = 微信客服上传语音返回: {$response}
msg-15e6381b = 删除临时音频文件失败: {$e}
msg-a79ae417 = 微信客服上传文件失败: {$e}
msg-374455ef = 微信客服上传文件返回: {$response}
msg-a2a133e4 = 微信客服上传视频失败: {$e}
msg-2732fffd = 微信客服上传视频返回: {$response}
msg-60815f02 = 还没实现这个消息类型的发送逻辑: {$res}。
msg-9913aa52 = 企业微信上传图片失败: {$e}
msg-9e90ba91 = 企业微信上传图片返回: {$response}
msg-232af016 = 企业微信上传语音失败: {$e}
msg-e5b8829d = 企业微信上传语音返回: {$response}
msg-f68671d7 = 企业微信上传文件失败: {$e}
msg-8cdcc397 = 企业微信上传文件返回: {$response}
msg-4f3e15f5 = 企业微信上传视频失败: {$e}
msg-4e9aceea = 企业微信上传视频返回: {$response}

### astrbot/core/platform/sources/wecom/wecom_adapter.py
msg-d4bbf9cb = 验证请求有效性: {$res}
msg-f8694a8a = 验证请求有效性成功。
msg-8f4cda74 = 验证请求有效性失败，签名异常，请检查配置。
msg-46d3feb9 = 解密失败，签名异常，请检查配置。
msg-4d1dfce4 = 解析成功: {$msg}
msg-a98efa4b = 将在 {$res}:{$res_2} 端口启动 企业微信 适配器。
msg-a616d9ce = 企业微信客服模式不支持 send_by_session 主动发送。
msg-5d01d7b9 = send_by_session 失败：无法为会话 {$res} 推断 agent_id。
msg-3f05613d = 获取到微信客服列表: {$acc_list}
msg-8fd19bd9 = 获取微信客服失败，open_kfid 为空。
msg-5900d9b6 = Found open_kfid: {$open_kfid}
msg-391119b8 = 请打开以下链接，在微信扫码以获取客服微信: https://api.cl2wm.cn/api/qrcode/code?text={$kf_url}
msg-5bdf8f5c = {$e}
msg-93c9125e = 转换音频失败: {$e}。如果没有安装 ffmpeg 请先安装。
msg-b2f7d1dc = 暂未实现的事件: {$res}
msg-61480a61 = abm: {$abm}
msg-42431e46 = 未实现的微信客服消息事件: {$msg}
msg-fbca491d = 企业微信 适配器已被关闭

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_event.py
msg-fa7f7afc = split plain into {$res} chunks for passive reply. Message not sent.
msg-59231e07 = 微信公众平台上传图片失败: {$e}
msg-d3968fc5 = 微信公众平台上传图片返回: {$response}
msg-7834b934 = 微信公众平台上传语音失败: {$e}
msg-4901d769 = 微信公众平台上传语音返回: {$response}
msg-15e6381b = 删除临时音频文件失败: {$e}
msg-60815f02 = 还没实现这个消息类型的发送逻辑: {$res}。

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_adapter.py
msg-d4bbf9cb = 验证请求有效性: {$res}
msg-b2edb1b2 = 未知的响应，请检查回调地址是否填写正确。
msg-f8694a8a = 验证请求有效性成功。
msg-8f4cda74 = 验证请求有效性失败，签名异常，请检查配置。
msg-46d3feb9 = 解密失败，签名异常，请检查配置。
msg-e23d8bff = 解析失败。msg为None。
msg-4d1dfce4 = 解析成功: {$msg}
msg-193d9d7a = 用户消息缓冲状态: user={$from_user} state={$state}
msg-57a3c1b2 = wx buffer hit on trigger: user={$from_user}
msg-bed995d9 = wx buffer hit on retry window: user={$from_user}
msg-3a94b6ab = wx finished message sending in passive window: user={$from_user} msg_id={$msg_id} 
msg-50c4b253 = wx finished message sending in passive window but not final: user={$from_user} msg_id={$msg_id} 
msg-7d8b62e7 = wx finished in window but not final; return placeholder: user={$from_user} msg_id={$msg_id} 
msg-2b9b8aed = wx task failed in passive window
msg-7bdf4941 = wx passive window timeout: user={$from_user} msg_id={$msg_id}
msg-98489949 = wx trigger while thinking: user={$from_user}
msg-01d0bbeb = wx new trigger: user={$from_user} msg_id={$msg_id}
msg-52bb36cd = wx start task: user={$from_user} msg_id={$msg_id} preview={$preview}
msg-ec9fd2ed = wx buffer hit immediately: user={$from_user}
msg-61c91fb9 = wx not finished in first window; return placeholder: user={$from_user} msg_id={$msg_id} 
msg-35604bba = wx task failed in first window
msg-e56c4a28 = wx first window timeout: user={$from_user} msg_id={$msg_id}
msg-e163be40 = 将在 {$res}:{$res_2} 端口启动 微信公众平台 适配器。
msg-c1740a04 = duplicate message id checked: {$res}
msg-04718b37 = Got future result: {$result}
msg-296e66c1 = callback 处理消息超时: message_id={$res}
msg-eb718c92 = 转换消息时出现异常: {$e}
msg-93c9125e = 转换音频失败: {$e}。如果没有安装 ffmpeg 请先安装。
msg-b2f7d1dc = 暂未实现的事件: {$res}
msg-61480a61 = abm: {$abm}
msg-2e7e0187 = 用户消息未找到缓冲状态，无法处理消息: user={$res} message_id={$res_2}
msg-84312903 = 微信公众平台 适配器已被关闭

### astrbot/core/platform/sources/misskey/misskey_adapter.py
msg-7bacee77 = [Misskey] 配置不完整，无法启动
msg-99cdf3d3 = [Misskey] 已连接用户: {$res} (ID: {$res_2})
msg-5579c974 = [Misskey] 获取用户信息失败: {$e}
msg-d9547102 = [Misskey] API 客户端未初始化
msg-341b0aa0 = [Misskey] WebSocket 已连接 (尝试 #{$connection_attempts})
msg-c77d157b = [Misskey] 聊天频道已订阅
msg-a0c5edc0 = [Misskey] WebSocket 连接失败 (尝试 #{$connection_attempts})
msg-1958faa8 = [Misskey] WebSocket 异常 (尝试 #{$connection_attempts}): {$e}
msg-1b47382d = [Misskey] {$sleep_time}秒后重连 (下次尝试 #{$res})
msg-a10a224d = [Misskey] 收到通知事件: type={$notification_type}, user_id={$res}
msg-7f0abf4a = [Misskey] 处理贴文提及: {$res}...
msg-2da7cdf5 = [Misskey] 处理通知失败: {$e}
msg-6c21d412 = [Misskey] 收到聊天事件: sender_id={$sender_id}, room_id={$room_id}, is_self={$res}
msg-68269731 = [Misskey] 检查群聊消息: '{$raw_text}', 机器人用户名: '{$res}'
msg-585aa62b = [Misskey] 处理群聊消息: {$res}...
msg-426c7874 = [Misskey] 处理私聊消息: {$res}...
msg-f5aff493 = [Misskey] 处理聊天消息失败: {$e}
msg-ea465183 = [Misskey] 收到未处理事件: type={$event_type}, channel={$res}
msg-8b69eb93 = [Misskey] 消息内容为空且无文件组件，跳过发送
msg-9ba9c4e5 = [Misskey] 已清理临时文件: {$local_path}
msg-91af500e = [Misskey] 文件数量超过限制 ({$res} > {$MAX_FILE_UPLOAD_COUNT})，只上传前{$MAX_FILE_UPLOAD_COUNT}个文件
msg-9746d7f5 = [Misskey] 并发上传过程中出现异常，继续发送文本
msg-d6dc928c = [Misskey] 聊天消息只支持单个文件，忽略其余 {$res} 个文件
msg-af584ae8 = [Misskey] 解析可见性: visibility={$visibility}, visible_user_ids={$visible_user_ids}, session_id={$session_id}, user_id_for_cache={$user_id_for_cache}
msg-1a176905 = [Misskey] 发送消息失败: {$e}

### astrbot/core/platform/sources/misskey/misskey_api.py
msg-fab20f57 = aiohttp and websockets are required for Misskey API. Please install them with: pip install aiohttp websockets
msg-f2eea8e1 = [Misskey WebSocket] 已连接
msg-5efd11a2 = [Misskey WebSocket] 重新订阅 {$channel_type} 失败: {$e}
msg-b70e2176 = [Misskey WebSocket] 连接失败: {$e}
msg-b9f3ee06 = [Misskey WebSocket] 连接已断开
msg-7cd98e54 = WebSocket 未连接
msg-43566304 = [Misskey WebSocket] 无法解析消息: {$e}
msg-e617e390 = [Misskey WebSocket] 处理消息失败: {$e}
msg-c60715cf = [Misskey WebSocket] 连接意外关闭: {$e}
msg-da9a2a17 = [Misskey WebSocket] 连接已关闭 (代码: {$res}, 原因: {$res_2})
msg-bbf6a42e = [Misskey WebSocket] 握手失败: {$e}
msg-254f0237 = [Misskey WebSocket] 监听消息失败: {$e}
msg-49f7e90e = {$channel_summary}
msg-630a4832 = [Misskey WebSocket] 频道消息: {$channel_id}, 事件类型: {$event_type}
msg-0dc61a4d = [Misskey WebSocket] 使用处理器: {$handler_key}
msg-012666fc = [Misskey WebSocket] 使用事件处理器: {$event_type}
msg-e202168a = [Misskey WebSocket] 未找到处理器: {$handler_key} 或 {$event_type}
msg-a397eef1 = [Misskey WebSocket] 直接消息处理器: {$message_type}
msg-a5f12225 = [Misskey WebSocket] 未处理的消息类型: {$message_type}
msg-ad61d480 = [Misskey API] {$func_name} 重试 {$max_retries} 次后仍失败: {$e}
msg-7de2ca49 = [Misskey API] {$func_name} 第 {$attempt} 次重试失败: {$e}，{$sleep_time}s后重试
msg-f5aecf37 = [Misskey API] {$func_name} 遇到不可重试异常: {$e}
msg-e5852be5 = [Misskey API] 客户端已关闭
msg-21fc185c = [Misskey API] 请求参数错误: {$endpoint} (HTTP {$status})
msg-5b106def = Bad request for {$endpoint}
msg-28afff67 = [Misskey API] 未授权访问: {$endpoint} (HTTP {$status})
msg-e12f2d28 = Unauthorized access for {$endpoint}
msg-beda662d = [Misskey API] 访问被禁止: {$endpoint} (HTTP {$status})
msg-795ca227 = Forbidden access for {$endpoint}
msg-5c6ba873 = [Misskey API] 资源不存在: {$endpoint} (HTTP {$status})
msg-74f2bac2 = Resource not found for {$endpoint}
msg-9ceafe4c = [Misskey API] 请求体过大: {$endpoint} (HTTP {$status})
msg-3e336b73 = Request entity too large for {$endpoint}
msg-a47067de = [Misskey API] 请求频率限制: {$endpoint} (HTTP {$status})
msg-901dc2da = Rate limit exceeded for {$endpoint}
msg-2bea8c2e = [Misskey API] 服务器内部错误: {$endpoint} (HTTP {$status})
msg-ae8d3725 = Internal server error for {$endpoint}
msg-7b028462 = [Misskey API] 网关错误: {$endpoint} (HTTP {$status})
msg-978414ef = Bad gateway for {$endpoint}
msg-50895a69 = [Misskey API] 服务不可用: {$endpoint} (HTTP {$status})
msg-62adff89 = Service unavailable for {$endpoint}
msg-1cf15497 = [Misskey API] 网关超时: {$endpoint} (HTTP {$status})
msg-a8a2578d = Gateway timeout for {$endpoint}
msg-c012110a = [Misskey API] 未知错误: {$endpoint} (HTTP {$status})
msg-dc96bbb8 = HTTP {$status} for {$endpoint}
msg-4c7598b6 = [Misskey API] 获取到 {$res} 条新通知
msg-851a2a54 = [Misskey API] 请求成功: {$endpoint}
msg-5f5609b6 = [Misskey API] 响应格式错误: {$e}
msg-c8f7bbeb = Invalid JSON response
msg-82748b31 = [Misskey API] 请求失败: {$endpoint} - HTTP {$res}, 响应: {$error_text}
msg-c6de3320 = [Misskey API] 请求失败: {$endpoint} - HTTP {$res}
msg-affb19a7 = [Misskey API] HTTP 请求错误: {$e}
msg-9f1286b3 = HTTP request failed: {$e}
msg-44f91be2 = [Misskey API] 发帖成功: {$note_id}
msg-fbafd3db = No file path provided for upload
msg-872d8419 = [Misskey API] 本地文件不存在: {$file_path}
msg-37186dea = File not found: {$file_path}
msg-65ef68e0 = [Misskey API] 本地文件上传成功: {$filename} -> {$file_id}
msg-0951db67 = [Misskey API] 文件上传网络错误: {$e}
msg-e3a322f5 = Upload failed: {$e}
msg-f28772b9 = No MD5 hash provided for find-by-hash
msg-25e566ef = [Misskey API] find-by-hash 请求: md5={$md5_hash}
msg-a036a942 = [Misskey API] find-by-hash 响应: 找到 {$res} 个文件
msg-ea3581d5 = [Misskey API] 根据哈希查找文件失败: {$e}
msg-1d2a84ff = No name provided for find
msg-f25e28b4 = [Misskey API] find 请求: name={$name}, folder_id={$folder_id}
msg-cd43861a = [Misskey API] find 响应: 找到 {$res} 个文件
msg-05cd55ef = [Misskey API] 根据名称查找文件失败: {$e}
msg-c01052a4 = [Misskey API] 列表文件请求: limit={$limit}, folder_id={$folder_id}, type={$type}
msg-7c81620d = [Misskey API] 列表文件响应: 找到 {$res} 个文件
msg-a187a089 = [Misskey API] 列表文件失败: {$e}
msg-9e776259 = No existing session available
msg-de18c220 = URL不能为空
msg-25b15b61 = [Misskey API] SSL 验证下载失败: {$ssl_error}，重试不验证 SSL
msg-b6cbeef6 = [Misskey API] 本地上传成功: {$res}
msg-a4a898e2 = [Misskey API] 本地上传失败: {$e}
msg-46b7ea4b = [Misskey API] 聊天消息发送成功: {$message_id}
msg-32f71df4 = [Misskey API] 房间消息发送成功: {$message_id}
msg-7829f3b3 = [Misskey API] 聊天消息响应格式异常: {$res}
msg-d74c86a1 = [Misskey API] 提及通知响应格式异常: {$res}
msg-65ccb697 = 消息内容不能为空：需要文本或媒体文件
msg-b6afb123 = [Misskey API] URL媒体上传成功: {$res}
msg-4e62bcdc = [Misskey API] URL媒体上传失败: {$url}
msg-71cc9d61 = [Misskey API] URL媒体处理失败 {$url}: {$e}
msg-75890c2b = [Misskey API] 本地文件上传成功: {$res}
msg-024d0ed5 = [Misskey API] 本地文件上传失败: {$file_path}
msg-f1fcb5e1 = [Misskey API] 本地文件处理失败 {$file_path}: {$e}
msg-1ee80a6b = 不支持的消息类型: {$message_type}

### astrbot/core/platform/sources/misskey/misskey_event.py
msg-85cb7d49 = [MisskeyEvent] send 方法被调用，消息链包含 {$res} 个组件
msg-252c2fca = [MisskeyEvent] 检查适配器方法: hasattr(self.client, 'send_by_session') = {$res}
msg-44d7a060 = [MisskeyEvent] 调用适配器的 send_by_session 方法
msg-b6e08872 = [MisskeyEvent] 内容为空，跳过发送
msg-8cfebc9c = [MisskeyEvent] 创建新帖子
msg-ed0d2ed5 = [MisskeyEvent] 发送失败: {$e}

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_webhook.py
msg-a5c90267 = 消息推送 webhook URL 不能为空
msg-76bfb25b = 消息推送 webhook URL 缺少 key 参数
msg-3545eb07 = Webhook 请求失败: HTTP {$res}, {$text}
msg-758dfe0d = Webhook 返回错误: {$res} {$res_2}
msg-c056646b = 企业微信消息推送成功: %s
msg-73d3e179 = 文件不存在: {$file_path}
msg-774a1821 = 上传媒体失败: HTTP {$res}, {$text}
msg-6ff016a4 = 上传媒体失败: {$res} {$res_2}
msg-0e8252d1 = 上传媒体失败: 返回缺少 media_id
msg-9dbc2296 = 文件消息缺少有效文件路径，已跳过: %s
msg-2e567c36 = 清理临时语音文件失败 %s: %s
msg-e99c4df9 = 企业微信消息推送暂不支持组件类型 %s，已跳过

### astrbot/core/platform/sources/wecom_ai_bot/WXBizJsonMsgCrypt.py
msg-5bdf8f5c = {$e}
msg-fe69e232 = receiveid not match
msg-00b71c27 = signature not match
msg-5cfb5c20 = {$signature}

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_event.py
msg-e44e77b0 = 图片数据为空，跳过
msg-30d116ed = 处理图片消息失败: %s
msg-31b11295 = [WecomAI] 不支持的消息组件类型: {$res}, 跳过

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_adapter.py
msg-277cdd37 = 企业微信消息推送 webhook 配置无效: %s
msg-2102fede = 处理队列消息时发生异常: {$e}
msg-d4ea688d = 消息类型未知，忽略: {$message_data}
msg-15ba426f = 处理消息时发生异常: %s
msg-740911ab = Stream already finished, returning end message: {$stream_id}
msg-9fdbafe9 = Cannot find back queue for stream_id: {$stream_id}
msg-7a52ca2b = No new messages in back queue for stream_id: {$stream_id}
msg-9ffb59fb = Aggregated content: {$latest_plain_content}, image: {$res}, finish: {$finish}
msg-de9ff585 = Stream message sent successfully, stream_id: {$stream_id}
msg-558310b9 = 消息加密失败
msg-251652f9 = 处理欢迎消息时发生异常: %s
msg-480c5dac = [WecomAI] 消息已入队: {$stream_id}
msg-f595dd6e = 处理加密图片失败: {$result}
msg-e8beeb3d = WecomAIAdapter: {$res}
msg-6f8ad811 = 主动消息发送失败: 未配置企业微信消息推送 Webhook URL，请前往配置添加。session_id=%s
msg-84439b09 = 企业微信消息推送失败(session=%s): %s
msg-f70f5008 = 启动企业微信智能机器人适配器，监听 %s:%d
msg-87616945 = 企业微信智能机器人适配器正在关闭...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_api.py
msg-86f6ae9f = 消息解密失败，错误码: {$ret}
msg-45ad825c = 解密成功，消息内容: {$message_data}
msg-84c476a7 = JSON 解析失败: {$e}, 原始消息: {$decrypted_msg}
msg-c0d8c5f9 = 解密消息为空
msg-a08bcfc7 = 解密过程发生异常: {$e}
msg-4dfaa613 = 消息加密失败，错误码: {$ret}
msg-6e566b12 = 消息加密成功
msg-39bf8dba = 加密过程发生异常: {$e}
msg-fa5be7c5 = URL 验证失败，错误码: {$ret}
msg-813a4e4e = URL 验证成功
msg-65ce0d23 = URL 验证发生异常: {$e}
msg-b1aa892f = 开始下载加密图片: {$image_url}
msg-10f72727 = {$error_msg}
msg-70123a82 = 图片下载成功，大小: {$res} 字节
msg-85d2dba1 = AES 密钥不能为空
msg-67c4fcea = 无效的 AES 密钥长度: 应为 32 字节
msg-bde4bb57 = 无效的填充长度 (大于32字节)
msg-63c22912 = 图片解密成功，解密后大小: {$res} 字节
msg-6ea489f0 = 文本消息解析失败
msg-eb12d147 = 图片消息解析失败
msg-ab1157ff = 流消息解析失败
msg-e7e945d1 = 混合消息解析失败
msg-06ada9dd = 事件消息解析失败

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_server.py
msg-adaee66c = URL 验证参数缺失
msg-742e0b43 = 收到企业微信智能机器人 WebHook URL 验证请求。
msg-f86c030c = 消息回调参数缺失
msg-cce4e44c = 收到消息回调，msg_signature={$msg_signature}, timestamp={$timestamp}, nonce={$nonce}
msg-7f018a3c = 消息解密失败，错误码: %d
msg-9d42e548 = 消息处理器执行异常: %s
msg-15ba426f = 处理消息时发生异常: %s
msg-5bf7dffa = 启动企业微信智能机器人服务器，监听 %s:%d
msg-445921d5 = 服务器运行异常: %s
msg-3269840c = 企业微信智能机器人服务器正在关闭...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_queue_mgr.py
msg-8be03d44 = [WecomAI] 创建输入队列: {$session_id}
msg-9804296a = [WecomAI] 创建输出队列: {$session_id}
msg-bdf0fb78 = [WecomAI] 移除输出队列: {$session_id}
msg-40f6bb7b = [WecomAI] 移除待处理响应: {$session_id}
msg-fbb807cd = [WecomAI] 标记流已结束: {$session_id}
msg-9d7f5627 = [WecomAI] 移除输入队列: {$session_id}
msg-7637ed00 = [WecomAI] 设置待处理响应: {$session_id}
msg-5329c49b = [WecomAI] 清理过期响应及队列: {$session_id}
msg-09f098ea = [WecomAI] 为会话启动监听器: {$session_id}
msg-c55856d6 = 处理会话 {$session_id} 消息时发生错误: {$e}

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_utils.py
msg-14d01778 = JSON 解析失败: {$e}, 原始字符串: {$json_str}
msg-df346cf5 = 开始下载加密图片: %s
msg-cb266fb3 = 图片下载成功，大小: %d 字节
msg-10f72727 = {$error_msg}
msg-1d91d2bb = AES密钥不能为空
msg-bb32bedd = 无效的AES密钥长度: 应为32字节
msg-bde4bb57 = 无效的填充长度 (大于32字节)
msg-3cf2120e = 图片解密成功，解密后大小: %d 字节
msg-3f8ca8aa = 图片已转换为base64编码，编码后长度: %d

### astrbot/core/platform/sources/line/line_api.py
msg-06e3f874 = [LINE] %s message failed: status=%s body=%s
msg-1478c917 = [LINE] %s message request failed: %s
msg-39941f06 = [LINE] get content retry failed: message_id=%s status=%s body=%s
msg-1fe70511 = [LINE] get content failed: message_id=%s status=%s body=%s

### astrbot/core/platform/sources/line/line_event.py
msg-4068a191 = [LINE] resolve image url failed: %s
msg-2233b256 = [LINE] resolve record url failed: %s
msg-a7455817 = [LINE] resolve record duration failed: %s
msg-9d0fee66 = [LINE] resolve video url failed: %s
msg-3b8ea946 = [LINE] resolve video cover failed: %s
msg-aea2081a = [LINE] generate video preview failed: %s
msg-af426b7e = [LINE] resolve file url failed: %s
msg-fe44c12d = [LINE] resolve file size failed: %s
msg-d6443173 = [LINE] message count exceeds 5, extra segments will be dropped.

### astrbot/core/platform/sources/line/line_adapter.py
msg-68539775 = LINE 适配器需要 channel_access_token 和 channel_secret。
msg-30c67081 = [LINE] webhook_uuid 为空，统一 Webhook 可能无法接收消息。
msg-64e92929 = [LINE] invalid webhook signature
msg-71bc0b77 = [LINE] invalid webhook body: %s
msg-8c7d9bab = [LINE] duplicate event skipped: %s

### astrbot/core/platform/sources/telegram/tg_event.py
msg-7757f090 = [Telegram] 发送 chat action 失败: {$e}
msg-80b075a3 = User privacy settings prevent receiving voice messages, falling back to sending an audio file. To enable voice messages, go to Telegram Settings → Privacy and Security → Voice Messages → set to 'Everyone'.
msg-20665ad1 = MarkdownV2 send failed: {$e}. Using plain text instead.
msg-323cb67c = [Telegram] 添加反应失败: {$e}
msg-abe7fc3d = 编辑消息失败(streaming-break): {$e}
msg-f7d40103 = 不支持的消息类型: {$res}
msg-d4b50a96 = 编辑消息失败(streaming): {$e}
msg-2701a78f = 发送消息失败(streaming): {$e}
msg-2a8ecebd = Markdown转换失败，使用普通文本: {$e}

### astrbot/core/platform/sources/telegram/tg_adapter.py
msg-cb53f79a = Telegram base url: {$res}
msg-e6b6040f = Telegram Updater is not initialized. Cannot start polling.
msg-2c4b186e = Telegram Platform Adapter is running.
msg-908d0414 = 向 Telegram 注册指令时发生错误: {$e}
msg-d2dfe45e = 命令名 '{$cmd_name}' 重复注册，将使用首次注册的定义: '{$res}'
msg-63bdfab8 = Received a start command without an effective chat, skipping /start reply.
msg-03a27b01 = Telegram message: {$res}
msg-e47b4bb4 = Received an update without a message.
msg-c97401c6 = [Telegram] Received a message without a from_user.
msg-f5c839ee = Telegram document file_path is None, cannot save the file {$file_name}.
msg-dca991a9 = Telegram video file_path is None, cannot save the file {$file_name}.
msg-56fb2950 = Create media group cache: {$media_group_id}
msg-0de2d4b5 = Add message to media group {$media_group_id}, currently has {$res} items.
msg-9e5069e9 = Media group {$media_group_id} has reached max wait time ({$elapsed}s >= {$res}s), processing immediately.
msg-9156b9d6 = Scheduled media group {$media_group_id} to be processed in {$delay} seconds (already waited {$elapsed}s)
msg-2849c882 = Media group {$media_group_id} not found in cache
msg-c75b2163 = Media group {$media_group_id} is empty
msg-0a3626c1 = Processing media group {$media_group_id}, total {$res} items
msg-2842e389 = Failed to convert the first message of media group {$media_group_id}
msg-32fbf7c1 = Added {$res} components to media group {$media_group_id}
msg-23bae28a = Telegram adapter has been closed.
msg-e46e7740 = Error occurred while closing Telegram adapter: {$e}

### astrbot/core/platform/sources/slack/client.py
msg-1d6b68b9 = Slack request signature verification failed
msg-53ef18c3 = Received Slack event: {$event_data}
msg-58488af6 = 处理 Slack 事件时出错: {$e}
msg-477be979 = Slack Webhook 服务器启动中，监听 {$res}:{$res_2}{$res_3}...
msg-639fee6c = Slack Webhook 服务器已停止
msg-a238d798 = Socket client is not initialized
msg-4e6de580 = 处理 Socket Mode 事件时出错: {$e}
msg-5bb71de9 = Slack Socket Mode 客户端启动中...
msg-f79ed37f = Slack Socket Mode 客户端已停止

### astrbot/core/platform/sources/slack/slack_adapter.py
msg-c34657ff = Slack bot_token 是必需的
msg-64f8a45d = Socket Mode 需要 app_token
msg-a2aba1a7 = Webhook Mode 需要 signing_secret
msg-40e00bd4 = Slack 发送消息失败: {$e}
msg-56c1d0a3 = [slack] RawMessage {$event}
msg-855510b4 = Failed to download slack file: {$res} {$res_2}
msg-04ab2fae = 下载文件失败: {$res}
msg-79ed7e65 = Slack auth test OK. Bot ID: {$res}
msg-ec27746a = Slack 适配器 (Socket Mode) 启动中...
msg-34222d3a = Slack 适配器 (Webhook Mode) 启动中，监听 {$res}:{$res_2}{$res_3}...
msg-6d8110d2 = 不支持的连接模式: {$res}，请使用 'socket' 或 'webhook'
msg-d71e7f36 = Slack 适配器已被关闭

### astrbot/core/platform/sources/slack/slack_event.py
msg-b233107c = Slack file upload failed: {$res}
msg-596945d1 = Slack file upload response: {$response}

### astrbot/core/platform/sources/satori/satori_adapter.py
msg-ab7db6d9 = Satori WebSocket 连接关闭: {$e}
msg-4ef42cd1 = Satori WebSocket 连接失败: {$e}
msg-b50d159b = 达到最大重试次数 ({$max_retries})，停止重试
msg-89de477c = Satori 适配器正在连接到 WebSocket: {$res}
msg-cfa5b059 = Satori 适配器 HTTP API 地址: {$res}
msg-d534864b = 无效的WebSocket URL: {$res}
msg-a110f9f7 = WebSocket URL必须以ws://或wss://开头: {$res}
msg-bf43ccb6 = Satori 处理消息异常: {$e}
msg-89081a1a = Satori WebSocket 连接异常: {$e}
msg-5c04bfcd = Satori WebSocket 关闭异常: {$e}
msg-b67bcee0 = WebSocket连接未建立
msg-89ea8b76 = WebSocket连接已关闭
msg-4c8a40e3 = 发送 IDENTIFY 信令时连接关闭: {$e}
msg-05a6b99d = 发送 IDENTIFY 信令失败: {$e}
msg-c9b1b774 = Satori WebSocket 发送心跳失败: {$e}
msg-61edb4f3 = 心跳任务异常: {$e}
msg-7db44899 = Satori 连接成功 - Bot {$res}: platform={$platform}, user_id={$user_id}, user_name={$user_name}
msg-01564612 = 解析 WebSocket 消息失败: {$e}, 消息内容: {$message}
msg-3a1657ea = 处理 WebSocket 消息异常: {$e}
msg-dc6b459c = 处理事件失败: {$e}
msg-6524f582 = 解析<quote>标签时发生错误: {$e}, 错误内容: {$content}
msg-3be535c3 = 转换 Satori 消息失败: {$e}
msg-be17caf1 = XML解析失败，使用正则提取: {$e}
msg-f6f41d74 = 提取<quote>标签时发生错误: {$e}
msg-ca6dca7f = 转换引用消息失败: {$e}
msg-cd3b067e = 解析 Satori 元素时发生解析错误: {$e}, 错误内容: {$content}
msg-03071274 = 解析 Satori 元素时发生未知错误: {$e}
msg-775cd5c0 = HTTP session 未初始化
msg-e354c8d1 = Satori HTTP 请求异常: {$e}

### astrbot/core/platform/sources/satori/satori_event.py
msg-c063ab8a = Satori 消息发送异常: {$e}
msg-9bc42a8d = Satori 消息发送失败
msg-dbf77ca2 = 图片转换为base64失败: {$e}
msg-8b6100fb = Satori 流式消息发送异常: {$e}
msg-3c16c45c = 语音转换为base64失败: {$e}
msg-66994127 = 视频文件转换失败: {$e}
msg-30943570 = 转换消息组件失败: {$e}
msg-3e8181fc = 转换转发节点失败: {$e}
msg-d626f831 = 转换合并转发消息失败: {$e}

### astrbot/core/platform/sources/webchat/webchat_queue_mgr.py
msg-4af4f885 = Started listener for conversation: {$conversation_id}
msg-10237240 = Error processing message from conversation {$conversation_id}: {$e}

### astrbot/core/platform/sources/webchat/webchat_adapter.py
msg-9406158c = WebChatAdapter: {$res}

### astrbot/core/platform/sources/webchat/webchat_event.py
msg-6b37adcd = webchat 忽略: {$res}

### astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py
msg-8af45ba1 = QQ 机器人官方 API 适配器不支持 send_by_session
msg-8ebd1249 = Unknown message type: {$message_type}
msg-c165744d = QQ 官方机器人接口 适配器已被优雅地关闭

### astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py
msg-28a74d9d = [QQOfficial] Skip botpy FormData patch.
msg-c0b123f6 = 发送流式消息时出错: {$e}
msg-05d6bba5 = [QQOfficial] 不支持的消息源类型: {$res}
msg-e5339577 = [QQOfficial] GroupMessage 缺少 group_openid
msg-71275806 = Message sent to C2C: {$ret}
msg-040e7942 = [QQOfficial] markdown 发送被拒绝，回退到 content 模式重试。
msg-9000f8f7 = Invalid upload parameters
msg-d72cffe7 = Failed to upload image, response is not dict: {$result}
msg-5944a27c = 上传文件响应格式错误: {$result}
msg-1e513ee5 = 上传请求错误: {$e}
msg-f1f1733c = Failed to post c2c message, response is not dict: {$result}
msg-9b8f9f70 = Unsupported image file format
msg-24eb302a = 转换音频格式时出错：音频时长不大于0
msg-b49e55f9 = 处理语音时出错: {$e}
msg-6e716579 = qq_official 忽略 {$res}

### astrbot/core/provider/provider.py
msg-e6f0c96f = Provider type {$provider_type_name} not registered
msg-c7953e3f = 批次 {$batch_idx} 处理失败，已重试 {$max_retries} 次: {$e}
msg-10f72727 = {$error_msg}
msg-7ff71721 = Rerank provider test failed, no results returned

### astrbot/core/provider/register.py
msg-19ddffc0 = 检测到大模型提供商适配器 {$provider_type_name} 已经注册，可能发生了大模型提供商适配器类型命名冲突。
msg-7e134b0d = 服务提供商 Provider {$provider_type_name} 已注册

### astrbot/core/provider/func_tool_manager.py
msg-0c42a4d9 = 添加函数调用工具: {$name}
msg-e8fdbb8c = 未找到 MCP 服务配置文件，已创建默认配置文件 {$mcp_json_file}
msg-cf8aed84 = 收到 MCP 客户端 {$name} 终止信号
msg-3d7bcc64 = 初始化 MCP 客户端 {$name} 失败
msg-1b190842 = MCP server {$name} list tools response: {$tools_res}
msg-6dc4f652 = 已连接 MCP 服务 {$name}, Tools: {$tool_names}
msg-a44aa4f2 = 清空 MCP 客户端资源 {$name}: {$e}。
msg-e9c96c53 = 已关闭 MCP 服务 {$name}
msg-10f72727 = {$error_msg}
msg-85f156e0 = testing MCP server connection with config: {$config}
msg-93c54ce0 = Cleaning up MCP client after testing connection.
msg-368450ee = 此函数调用工具所属的插件 {$res} 已被禁用，请先在管理面板启用再激活此工具。
msg-4ffa2135 = 加载 MCP 配置失败: {$e}
msg-a486ac39 = 保存 MCP 配置失败: {$e}
msg-58dfdfe7 = 从 ModelScope 同步了 {$synced_count} 个 MCP 服务器
msg-75f1222f = 没有找到可用的 ModelScope MCP 服务器
msg-c9f6cb1d = ModelScope API 请求失败: HTTP {$res}
msg-c8ebb4f7 = 网络连接错误: {$e}
msg-0ac6970f = 同步 ModelScope MCP 服务器时发生错误: {$e}

### astrbot/core/provider/entities.py
msg-7fc6f623 = 图片 {$image_url} 得到的结果为空，将忽略。

### astrbot/core/provider/manager.py
msg-9e1a7f1f = 提供商 {$provider_id} 不存在，无法设置。
msg-5fda2049 = Unknown provider type: {$provider_type}
msg-a5cb19c6 = 没有找到 ID 为 {$provider_id} 的提供商，这可能是由于您修改了提供商（模型）ID 导致的。
msg-78b9c276 = {$res}
msg-5bdf8f5c = {$e}
msg-b734a1f4 = Provider {$provider_id} 配置项 key[{$idx}] 使用环境变量 {$env_key} 但未设置。
msg-664b3329 = Provider {$res} is disabled, skipping
msg-f43f8022 = 载入 {$res}({$res_2}) 服务提供商 ...
msg-edd4aefe = 加载 {$res}({$res_2}) 提供商适配器失败：{$e}。可能是因为有未安装的依赖。
msg-78e514a1 = 加载 {$res}({$res_2}) 提供商适配器失败：{$e}。未知原因
msg-4636f83c = 未找到适用于 {$res}({$res_2}) 的提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。
msg-e9c6c4a2 = 无法找到 {$res} 的类
msg-f705cf50 = Provider class {$cls_type} is not a subclass of STTProvider
msg-d20620aa = 已选择 {$res}({$res_2}) 作为当前语音转文本提供商适配器。
msg-afbe5661 = Provider class {$cls_type} is not a subclass of TTSProvider
msg-74d437ed = 已选择 {$res}({$res_2}) 作为当前文本转语音提供商适配器。
msg-08cd85c9 = Provider class {$cls_type} is not a subclass of Provider
msg-16a2b8e0 = 已选择 {$res}({$res_2}) 作为当前提供商适配器。
msg-0e1707e7 = Provider class {$cls_type} is not a subclass of EmbeddingProvider
msg-821d06e0 = Provider class {$cls_type} is not a subclass of RerankProvider
msg-14c35664 = 未知的提供商类型：{$res}
msg-186fd5c6 = 实例化 {$res}({$res_2}) 提供商适配器失败：{$e}
msg-ede02a99 = providers in user's config: {$config_ids}
msg-95dc4227 = 自动选择 {$res} 作为当前提供商适配器。
msg-a6187bac = 自动选择 {$res} 作为当前语音转文本提供商适配器。
msg-bf28f7e2 = 自动选择 {$res} 作为当前文本转语音提供商适配器。
msg-dba10c27 = 终止 {$provider_id} 提供商适配器({$res}, {$res_2}, {$res_3}) ...
msg-9d9d9765 = {$provider_id} 提供商适配器已终止({$res}, {$res_2}, {$res_3})
msg-925bb70a = Provider {$target_prov_ids} 已从配置中删除。
msg-a1657092 = New provider config must have an 'id' field
msg-1486c653 = Provider ID {$npid} already exists
msg-f9fc1545 = Provider ID {$origin_provider_id} not found
msg-4e2c657c = Error while disabling MCP servers

### astrbot/core/provider/sources/gemini_embedding_source.py
msg-173efb0e = [Gemini Embedding] 使用代理: {$proxy}
msg-58a99789 = Gemini Embedding API请求失败: {$res}
msg-5c4ea38e = Gemini Embedding API批量请求失败: {$res}

### astrbot/core/provider/sources/bailian_rerank_source.py
msg-dc1a9e6e = 阿里云百炼 API Key 不能为空。
msg-f7079f37 = AstrBot 百炼 Rerank 初始化完成。模型: {$res}
msg-5b6d35ce = 百炼 API 错误: {$res} – {$res_2}
msg-d600c5e2 = 百炼 Rerank 返回空结果: {$data}
msg-d3312319 = 结果 {$idx} 缺少 relevance_score，使用默认值 0.0
msg-2855fb44 = 解析结果 {$idx} 时出错: {$e}, result={$result}
msg-392f26e8 = 百炼 Rerank 消耗 Token: {$tokens}
msg-595e0cf9 = 百炼 Rerank 客户端会话已关闭，返回空结果
msg-d0388210 = 文档列表为空，返回空结果
msg-44d6cc76 = 查询文本为空，返回空结果
msg-bd8b942a = 文档数量({$res})超过限制(500)，将截断前500个文档
msg-0dc3bca4 = 百炼 Rerank 请求: query='{$res}...', 文档数量={$res_2}
msg-4a9f4ee3 = 百炼 Rerank 成功返回 {$res} 个结果
msg-fa301307 = 百炼 Rerank 网络请求失败: {$e}
msg-10f72727 = {$error_msg}
msg-9879e226 = 百炼 Rerank 处理失败: {$e}
msg-4f15074c = 关闭 百炼 Rerank 客户端会话
msg-d01b1b0f = 关闭 百炼 Rerank 客户端时出错: {$e}

### astrbot/core/provider/sources/edge_tts_source.py
msg-f4ab0713 = pyffmpeg 转换失败: {$e}, 尝试使用 ffmpeg 命令行进行转换
msg-ddc3594a = [EdgeTTS] FFmpeg 标准输出: {$res}
msg-1b8c0a83 = FFmpeg错误输出: {$res}
msg-1e980a68 = [EdgeTTS] 返回值(0代表成功): {$res}
msg-c39d210c = 生成的WAV文件不存在或为空
msg-57f60837 = FFmpeg 转换失败: {$res}
msg-ca94a42a = FFmpeg 转换失败: {$e}
msg-be660d63 = 音频生成失败: {$e}

### astrbot/core/provider/sources/whisper_api_source.py
msg-28cbbf07 = 文件不存在: {$audio_url}
msg-b335b8db = Converting silk file to wav using tencent_silk_to_wav...
msg-68b5660f = Converting amr file to wav using convert_to_pcm_wav...
msg-cad3735e = Failed to remove temp file {$audio_url}: {$e}

### astrbot/core/provider/sources/gemini_source.py
msg-1474947f = [Gemini] 使用代理: {$proxy}
msg-e2a81024 = 检测到 Key 异常({$res})，正在尝试更换 API Key 重试... 当前 Key: {$res_2}...
msg-0d388dae = 检测到 Key 异常({$res})，且已没有可用的 Key。 当前 Key: {$res_2}...
msg-1465290c = 达到了 Gemini 速率限制, 请稍后再试...
msg-7e9c01ca = 流式输出不支持图片模态，已自动降级为文本模态
msg-89bac423 = 代码执行工具与搜索工具互斥，已忽略搜索工具
msg-301cf76e = 代码执行工具与URL上下文工具互斥，已忽略URL上下文工具
msg-356e7b28 = 当前 SDK 版本不支持 URL 上下文工具，已忽略该设置，请升级 google-genai 包
msg-7d4e7d48 = gemini-2.0-lite 不支持代码执行、搜索工具和URL上下文，将忽略这些设置
msg-cc5c666f = 已启用原生工具，函数工具将被忽略
msg-aa7c77a5 = Invalid thinking level: {$thinking_level}, using HIGH
msg-59e1e769 = 文本内容为空，已添加空格占位
msg-34c5c910 = Failed to decode google gemini thinking signature: {$e}
msg-a2357584 = assistant 角色的消息内容为空，已添加空格占位
msg-f627f75d = 检测到启用Gemini原生工具，且上下文中存在函数调用，建议使用 /reset 重置上下文
msg-cb743183 = 收到的 candidate.content 为空: {$candidate}
msg-34b367fc = API 返回的 candidate.content 为空。
msg-73541852 = 模型生成内容未通过 Gemini 平台的安全检查
msg-ae3cdcea = 模型生成内容违反 Gemini 平台政策
msg-5d8f1711 = 收到的 candidate.content.parts 为空: {$candidate}
msg-57847bd5 = API 返回的 candidate.content.parts 为空。
msg-a56c85e4 = genai result: {$result}
msg-42fc0767 = 请求失败, 返回的 candidates 为空: {$result}
msg-faf3a0dd = 请求失败, 返回的 candidates 为空。
msg-cd690916 = 温度参数已超过最大值2，仍然发生recitation
msg-632e23d7 = 发生了recitation，正在提高温度至{$temperature}重试...
msg-41ff84bc = {$model} 不支持 system prompt，已自动去除(影响人格设置)
msg-ef9512f7 = {$model} 不支持函数调用，已自动去除
msg-fde41b1d = {$model} 不支持多模态输出，降级为文本模态
msg-4e168d67 = 收到的 chunk 中 candidates 为空: {$chunk}
msg-11af7d46 = 收到的 chunk 中 content 为空: {$chunk}
msg-8836d4a2 = 请求失败。
msg-757d3828 = 获取模型列表失败: {$res}
msg-7fc6f623 = 图片 {$image_url} 得到的结果为空，将忽略。
msg-0b041916 = 不支持的额外内容块类型: {$res}

### astrbot/core/provider/sources/gsvi_tts_source.py
msg-520e410f = GSVI TTS API 请求失败，状态码: {$res}，错误: {$error_text}

### astrbot/core/provider/sources/anthropic_source.py
msg-d6b1df6e = Failed to parse image data URI: {$res}...
msg-6c2c0426 = Unsupported image URL format for Anthropic: {$res}...
msg-999f7680 = completion: {$completion}
msg-8d2c43ec = API 返回的 completion 为空。
msg-26140afc = Anthropic API 返回的 completion 无法解析：{$completion}。
msg-8e4c8c24 = 工具调用参数 JSON 解析失败: {$tool_info}
msg-7fc6f623 = 图片 {$image_url} 得到的结果为空，将忽略。
msg-0b041916 = 不支持的额外内容块类型: {$res}

### astrbot/core/provider/sources/openai_source.py
msg-bbb399f6 = 检测到图片请求失败（%s），已移除图片并重试（保留文本内容）。
msg-d6f6a3c2 = 获取模型列表失败：{$e}
msg-1f850e09 = API 返回的 completion 类型错误：{$res}: {$completion}。
msg-999f7680 = completion: {$completion}
msg-844635f7 = Unexpected dict format content: {$raw_content}
msg-8d2c43ec = API 返回的 completion 为空。
msg-87d75331 = {$completion_text}
msg-0614efaf = 工具集未提供
msg-c46f067a = API 返回的 completion 由于内容安全过滤被拒绝(非 AstrBot)。
msg-647f0002 = API 返回的 completion 无法解析：{$completion}。
msg-5cc50a15 = API 调用过于频繁，尝试使用其他 Key 重试。当前 Key: {$res}
msg-c4e639eb = 上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数: {$res}
msg-5f8be4fb = {$res} 不支持函数工具调用，已自动去除，不影响使用。
msg-45591836 = 疑似该模型不支持函数调用工具调用。请输入 /tool off_all
msg-6e47d22a = API 调用失败，重试 {$max_retries} 次仍然失败。
msg-974e7484 = 未知错误
msg-7fc6f623 = 图片 {$image_url} 得到的结果为空，将忽略。
msg-0b041916 = 不支持的额外内容块类型: {$res}

### astrbot/core/provider/sources/gemini_tts_source.py
msg-29fe386a = [Gemini TTS] 使用代理: {$proxy}
msg-012edfe1 = No audio content returned from Gemini TTS API.

### astrbot/core/provider/sources/genie_tts.py
msg-583dd8a6 = Please install genie_tts first.
msg-935222b4 = Failed to load character {$res}: {$e}
msg-a6886f9e = Genie TTS did not save to file.
msg-e3587d60 = Genie TTS generation failed: {$e}
msg-3303e3a8 = Genie TTS failed to generate audio for: {$text}
msg-1cfe1af1 = Genie TTS stream error: {$e}

### astrbot/core/provider/sources/dashscope_tts.py
msg-f23d2372 = Dashscope TTS model is not configured.
msg-74a7cc0a = Audio synthesis failed, returned empty content. The model may not be supported or the service is unavailable.
msg-bc8619d3 = dashscope SDK missing MultiModalConversation. Please upgrade the dashscope package to use Qwen TTS models.
msg-95bbf71e = No voice specified for Qwen TTS model, using default 'Cherry'.
msg-3c35d2d0 = Audio synthesis failed for model '{$model}'. {$response}
msg-16dc3b00 = Failed to decode base64 audio data.
msg-26603085 = Failed to download audio from URL {$url}: {$e}
msg-78b9c276 = {$res}

### astrbot/core/provider/sources/whisper_selfhosted_source.py
msg-27fda50a = 下载或者加载 Whisper 模型中，这可能需要一些时间 ...
msg-4e70f563 = Whisper 模型加载完成。
msg-28cbbf07 = 文件不存在: {$audio_url}
msg-d98780e5 = Converting silk file to wav ...
msg-e3e1215c = Whisper 模型未初始化

### astrbot/core/provider/sources/openai_tts_api_source.py
msg-d7084760 = [OpenAI TTS] 使用代理: {$proxy}

### astrbot/core/provider/sources/xinference_rerank_source.py
msg-1ec1e6e4 = Xinference Rerank: Using API key for authentication.
msg-7bcb6e1b = Xinference Rerank: No API key provided.
msg-b0d1e564 = Model '{$res}' is already running with UID: {$uid}
msg-16965859 = Launching {$res} model...
msg-7b1dfdd3 = Model launched.
msg-3fc7310e = Model '{$res}' is not running and auto-launch is disabled. Provider will not be available.
msg-15f19a42 = Failed to initialize Xinference model: {$e}
msg-01af1651 = Xinference initialization failed with exception: {$e}
msg-2607cc7a = Xinference rerank model is not initialized.
msg-3d28173b = Rerank API response: {$response}
msg-4c63e1bd = Rerank API returned an empty list. Original response: {$response}
msg-cac71506 = Xinference rerank failed: {$e}
msg-4135cf72 = Xinference rerank failed with exception: {$e}
msg-ea2b36d0 = Closing Xinference rerank client...
msg-633a269f = Failed to close Xinference client: {$e}

### astrbot/core/provider/sources/minimax_tts_api_source.py
msg-77c88c8a = Failed to parse JSON data from SSE message
msg-7873b87b = MiniMax TTS API请求失败: {$e}

### astrbot/core/provider/sources/azure_tts_source.py
msg-93d9b5cf = [Azure TTS] 使用代理: {$res}
msg-9eea5bcb = Client not initialized. Please use 'async with' context.
msg-fd53d21d = 时间同步失败
msg-77890ac4 = OTTS请求失败: {$e}
msg-c6ec6ec7 = OTTS未返回音频文件
msg-5ad71900 = 无效的Azure订阅密钥
msg-6416da27 = [Azure TTS Native] 使用代理: {$res}
msg-15c55ed8 = 无效的other[...]格式，应形如 other[{...}]
msg-90b31925 = 缺少OTTS参数: {$res}
msg-10f72727 = {$error_msg}
msg-60b044ea = 配置错误: 缺少必要参数 {$e}
msg-5c7dee08 = 订阅密钥格式无效，应为32位字母数字或other[...]格式

### astrbot/core/provider/sources/openai_embedding_source.py
msg-cecb2fbc = [OpenAI Embedding] 使用代理: {$proxy}

### astrbot/core/provider/sources/vllm_rerank_source.py
msg-6f160342 = Rerank API 返回了空的列表数据。原始响应: {$response_data}

### astrbot/core/provider/sources/xinference_stt_provider.py
msg-4e31e089 = Xinference STT: Using API key for authentication.
msg-e291704e = Xinference STT: No API key provided.
msg-b0d1e564 = Model '{$res}' is already running with UID: {$uid}
msg-16965859 = Launching {$res} model...
msg-7b1dfdd3 = Model launched.
msg-3fc7310e = Model '{$res}' is not running and auto-launch is disabled. Provider will not be available.
msg-15f19a42 = Failed to initialize Xinference model: {$e}
msg-01af1651 = Xinference initialization failed with exception: {$e}
msg-42ed8558 = Xinference STT model is not initialized.
msg-bbc43272 = Failed to download audio from {$audio_url}, status: {$res}
msg-f4e53d3d = File not found: {$audio_url}
msg-ebab7cac = Audio bytes are empty.
msg-7fd63838 = Audio requires conversion ({$conversion_type}), using temporary files...
msg-d03c4ede = Converting silk to wav ...
msg-79486689 = Converting amr to wav ...
msg-c4305a5b = Xinference STT result: {$text}
msg-d4241bd5 = Xinference STT transcription failed with status {$res}: {$error_text}
msg-8efe4ef1 = Xinference STT failed: {$e}
msg-b1554c7c = Xinference STT failed with exception: {$e}
msg-9d33941a = Removed temporary file: {$temp_file}
msg-7dc5bc44 = Failed to remove temporary file {$temp_file}: {$e}
msg-31904a1c = Closing Xinference STT client...
msg-633a269f = Failed to close Xinference client: {$e}

### astrbot/core/provider/sources/fishaudio_tts_api_source.py
msg-c785baf0 = [FishAudio TTS] 使用代理: {$res}
msg-822bce1c = 无效的FishAudio参考模型ID: '{$res}'. 请确保ID是32位十六进制字符串（例如: 626bb6d3f3364c9cbc3aa6a67300a664）。您可以从 https://fish.audio/zh-CN/discovery 获取有效的模型ID。
msg-5956263b = Fish Audio API请求失败: 状态码 {$res}, 响应内容: {$error_text}

### astrbot/core/provider/sources/gsv_selfhosted_source.py
msg-5fb63f61 = [GSV TTS] 初始化完成
msg-e0c38c5b = [GSV TTS] 初始化失败：{$e}
msg-4d57bc4f = [GSV TTS] Provider HTTP session is not ready or closed.
msg-2a4a0819 = [GSV TTS] 请求地址：{$endpoint}，参数：{$params}
msg-5fdee1da = [GSV TTS] Request to {$endpoint} failed with status {$res}: {$error_text}
msg-3a51c2c5 = [GSV TTS] 请求 {$endpoint} 第 {$res} 次失败：{$e}，重试中...
msg-49c1c17a = [GSV TTS] 请求 {$endpoint} 最终失败：{$e}
msg-1beb6249 = [GSV TTS] 成功设置 GPT 模型路径：{$res}
msg-17f1a087 = [GSV TTS] GPT 模型路径未配置，将使用内置 GPT 模型
msg-ddeb915f = [GSV TTS] 成功设置 SoVITS 模型路径：{$res}
msg-bee5c961 = [GSV TTS] SoVITS 模型路径未配置，将使用内置 SoVITS 模型
msg-423edb93 = [GSV TTS] 设置模型路径时发生网络错误：{$e}
msg-7d3c79cb = [GSV TTS] 设置模型路径时发生未知错误：{$e}
msg-d084916a = [GSV TTS] TTS 文本不能为空
msg-fa20c883 = [GSV TTS] 正在调用语音合成接口，参数：{$params}
msg-a7fc38eb = [GSV TTS] 合成失败，输入文本：{$text}，错误信息：{$result}
msg-a49cb96b = [GSV TTS] Session 已关闭

### astrbot/core/provider/sources/volcengine_tts.py
msg-4b55f021 = 请求头: {$headers}
msg-d252d96d = 请求 URL: {$res}
msg-72e07cfd = 请求体: {$res}...
msg-fb8cdd69 = 响应状态码: {$res}
msg-4c62e457 = 响应内容: {$res}...
msg-1477973b = 火山引擎 TTS API 返回错误: {$error_msg}
msg-75401c15 = 火山引擎 TTS API 请求失败: {$res}, {$response_text}
msg-a29cc73d = 火山引擎 TTS 异常详情: {$error_details}
msg-01433007 = 火山引擎 TTS 异常: {$e}

### astrbot/core/provider/sources/sensevoice_selfhosted_source.py
msg-ee0daf96 = 下载或者加载 SenseVoice 模型中，这可能需要一些时间 ...
msg-cd6da7e9 = SenseVoice 模型加载完成。
msg-28cbbf07 = 文件不存在: {$audio_url}
msg-d98780e5 = Converting silk file to wav ...
msg-4e8f1d05 = SenseVoice识别到的文案：{$res}
msg-55668aa2 = 未能提取到情绪信息
msg-0cdbac9b = 处理音频文件时出错: {$e}

### astrbot/core/message/components.py
msg-afb10076 = not a valid url
msg-fe4c33a0 = not a valid file: {$res}
msg-24d98e13 = 未配置 callback_api_base，文件服务不可用
msg-a5c69cc9 = 已注册：{$callback_host}/api/file/{$token}
msg-3cddc5ef = download failed: {$url}
msg-1921aa47 = not a valid file: {$url}
msg-2ee3827c = Generated video file callback link: {$payload_file}
msg-32f4fc78 = No valid file or URL provided
msg-36375f4c = 不可以在异步上下文中同步等待下载! 这个警告通常发生于某些逻辑试图通过 <File>.file 获取文件消息段的文件内容。请使用 await get_file() 代替直接获取 <File>.file 字段
msg-4a987754 = 文件下载失败: {$e}
msg-7c1935ee = Download failed: No URL provided in File component.
msg-35bb8d53 = Generated file callback link: {$payload_file}

### astrbot/core/utils/metrics.py
msg-314258f2 = 保存指标到数据库失败: {$e}

### astrbot/core/utils/trace.py
msg-fffce1b9 = [trace] {$payload}
msg-78b9c276 = {$res}

### astrbot/core/utils/webhook_utils.py
msg-64c7ddcf = 获取 callback_api_base 失败: {$e}
msg-9b5d1bb1 = 获取 dashboard 端口失败: {$e}
msg-3db149ad = 获取 dashboard SSL 配置失败: {$e}
msg-3739eec9 = {$display_log}

### astrbot/core/utils/path_util.py
msg-cf211d0f = 路径映射规则错误: {$mapping}
msg-ecea161e = 路径映射: {$url} -> {$srcPath}

### astrbot/core/utils/media_utils.py
msg-2f697658 = [Media Utils] 获取媒体时长: {$duration_ms}ms
msg-52dfbc26 = [Media Utils] 无法获取媒体文件时长: {$file_path}
msg-486d493a = [Media Utils] ffprobe未安装或不在PATH中，无法获取媒体时长。请安装ffmpeg: https://ffmpeg.org/
msg-0f9c647b = [Media Utils] 获取媒体时长时出错: {$e}
msg-aff4c5f8 = [Media Utils] 已清理失败的opus输出文件: {$output_path}
msg-82427384 = [Media Utils] 清理失败的opus输出文件时出错: {$e}
msg-215a0cfc = [Media Utils] ffmpeg转换音频失败: {$error_msg}
msg-8cce258e = ffmpeg conversion failed: {$error_msg}
msg-f0cfcb92 = [Media Utils] 音频转换成功: {$audio_path} -> {$output_path}
msg-ead1395b = [Media Utils] ffmpeg未安装或不在PATH中，无法转换音频格式。请安装ffmpeg: https://ffmpeg.org/
msg-5df3a5ee = ffmpeg not found
msg-6322d4d2 = [Media Utils] 转换音频格式时出错: {$e}
msg-e125b1a5 = [Media Utils] 已清理失败的{$output_format}输出文件: {$output_path}
msg-5cf417e3 = [Media Utils] 清理失败的{$output_format}输出文件时出错: {$e}
msg-3766cbb8 = [Media Utils] ffmpeg转换视频失败: {$error_msg}
msg-77f68449 = [Media Utils] 视频转换成功: {$video_path} -> {$output_path}
msg-3fb20b91 = [Media Utils] ffmpeg未安装或不在PATH中，无法转换视频格式。请安装ffmpeg: https://ffmpeg.org/
msg-696c4a46 = [Media Utils] 转换视频格式时出错: {$e}
msg-98cc8fb8 = [Media Utils] 清理失败的音频输出文件时出错: {$e}
msg-3c27d5e8 = [Media Utils] 清理失败的视频封面文件时出错: {$e}
msg-072774ab = ffmpeg extract cover failed: {$error_msg}

### astrbot/core/utils/session_waiter.py
msg-0c977996 = 等待超时
msg-ac406437 = session_filter 必须是 SessionFilter

### astrbot/core/utils/history_saver.py
msg-fb7718cb = Failed to parse conversation history: %s

### astrbot/core/utils/io.py
msg-665b0191 = SSL certificate verification failed for {$url}. Disabling SSL verification (CERT_NONE) as a fallback. This is insecure and exposes the application to man-in-the-middle attacks. Please investigate and resolve certificate issues.
msg-04ab2fae = 下载文件失败: {$res}
msg-63dacf99 = 文件大小: {$res} KB | 文件地址: {$url}
msg-14c3d0bb = \r下载进度: {$res} 速度: {$speed} KB/s
msg-4e4ee68e = SSL 证书验证失败，已关闭 SSL 验证（不安全，仅用于临时下载）。请检查目标服务器的证书配置。
msg-5a3beefb = SSL certificate verification failed for {$url}. Falling back to unverified connection (CERT_NONE). This is insecure and exposes the application to man-in-the-middle attacks. Please investigate certificate issues with the remote server.
msg-315e5ed6 = 准备下载指定发行版本的 AstrBot WebUI 文件: {$dashboard_release_url}
msg-c709cf82 = 准备下载指定版本的 AstrBot WebUI: {$url}

### astrbot/core/utils/shared_preferences.py
msg-9a1e6a9a = scope_id and key cannot be None when getting a specific preference.

### astrbot/core/utils/migra_helper.py
msg-497ddf83 = Migration for third party agent runner configs failed: {$e}
msg-78b9c276 = {$res}
msg-e21f1509 = Migrating provider {$res} to new structure
msg-dd3339e6 = Provider-source structure migration completed
msg-1cb6c174 = Migration from version 4.5 to 4.6 failed: {$e}
msg-a899acc6 = Migration for webchat session failed: {$e}
msg-b9c52817 = Migration for token_usage column failed: {$e}
msg-d9660ff5 = Migration for provider-source structure failed: {$e}

### astrbot/core/utils/temp_dir_cleaner.py
msg-752c7cc8 = Invalid {$res}={$configured}, fallback to {$res_2}MB.
msg-b1fc3643 = Skip temp file {$path} due to stat error: {$e}
msg-5e61f6b7 = Failed to delete temp file {$res}: {$e}
msg-391449f0 = Temp dir exceeded limit ({$total_size} > {$limit}). Removed {$removed_files} files, released {$released} bytes (target {$target_release} bytes).
msg-aaf1e12a = TempDirCleaner started. interval={$res}s cleanup_ratio={$res_2}
msg-e6170717 = TempDirCleaner run failed: {$e}
msg-0fc33fbc = TempDirCleaner stopped.

### astrbot/core/utils/tencent_record_helper.py
msg-377ae139 = pilk 模块未安装，请前往管理面板->平台日志->安装pip库 安装 pilk 这个库
msg-f4ab0713 = pyffmpeg 转换失败: {$e}, 尝试使用 ffmpeg 命令行进行转换
msg-33c88889 = [FFmpeg] stdout: {$res}
msg-2470430c = [FFmpeg] stderr: {$res}
msg-1321d5f7 = [FFmpeg] return code: {$res}
msg-c39d210c = 生成的WAV文件不存在或为空
msg-6e04bdb8 = 未安装 pilk: pip install pilk

### astrbot/core/utils/pip_installer.py
msg-aa9e40b8 = pip module is unavailable (sys.executable={$res}, frozen={$res_2}, ASTRBOT_DESKTOP_CLIENT={$res_3})
msg-560f11f2 = 读取依赖文件失败，跳过冲突检测: %s
msg-91ae1d17 = 读取 site-packages 元数据失败，使用回退模块名: %s
msg-c815b9dc = {$conflict_message}
msg-e8d4b617 = Loaded %s from plugin site-packages: %s
msg-4ef5d900 = Recovered dependency %s while preferring %s from plugin site-packages.
msg-0bf22754 = Module %s not found in plugin site-packages: %s
msg-76a41595 = Failed to prefer module %s from plugin site-packages: %s
msg-3d4de966 = Failed to patch pip distlib finder for loader %s (%s): %s
msg-117d9cf4 = Distlib finder patch did not take effect for loader %s (%s).
msg-b7975236 = Patched pip distlib finder for frozen loader: %s (%s)
msg-b1fa741c = Skip patching distlib finder because _finder_registry is unavailable.
msg-4ef0e609 = Skip patching distlib finder because register API is unavailable.
msg-b8c741dc = Pip 包管理器: pip {$res}
msg-6b72a960 = 安装失败，错误码：{$result_code}
msg-c8325399 = {$line}

### astrbot/core/utils/llm_metadata.py
msg-d6535d03 = Successfully fetched metadata for {$res} LLMs.
msg-8cceaeb0 = Failed to fetch LLM metadata: {$e}

### astrbot/core/utils/network_utils.py
msg-54b8fda8 = [{$provider_label}] 网络/代理连接失败 ({$error_type})。代理地址: {$effective_proxy}，错误: {$error}
msg-ea7c80f1 = [{$provider_label}] 网络连接失败 ({$error_type})。错误: {$error}
msg-f8c8a73c = [{$provider_label}] 使用代理: {$proxy}

### astrbot/core/utils/t2i/renderer.py
msg-4225607b = Failed to render image via AstrBot API: {$e}. Falling back to local rendering.

### astrbot/core/utils/t2i/local_strategy.py
msg-94a58a1e = 无法加载任何字体
msg-d5c7d255 = Failed to load image: HTTP {$res}
msg-7d59d0a0 = Failed to load image: {$e}

### astrbot/core/utils/t2i/template_manager.py
msg-47d72ff5 = 模板名称包含非法字符。
msg-d1b2131b = 模板不存在。
msg-dde05b0f = 同名模板已存在。
msg-0aa209bf = 用户模板不存在，无法删除。

### astrbot/core/utils/t2i/network_strategy.py
msg-be0eeaa7 = Successfully got {$res} official T2I endpoints.
msg-3bee02f4 = Failed to get official endpoints: {$e}
msg-829d3c71 = HTTP {$res}
msg-05fb621f = Endpoint {$endpoint} failed: {$e}, trying next...
msg-9a836926 = All endpoints failed: {$last_exception}

### astrbot/core/utils/quoted_message/extractor.py
msg-24049c48 = quoted_message_parser: stop fetching nested forward messages after %d hops

### astrbot/core/utils/quoted_message/onebot_client.py
msg-062923e6 = quoted_message_parser: action %s failed with params %s: %s
msg-f33f59d5 = quoted_message_parser: all attempts failed for action %s, last_params=%s, error=%s

### astrbot/core/utils/quoted_message/image_resolver.py
msg-94224a01 = quoted_message_parser: skip non-image local path ref=%s
msg-3e6c0d14 = quoted_message_parser: failed to resolve quoted image ref=%s after %d actions

### astrbot/core/agent/tool_image_cache.py
msg-45da4af7 = ToolImageCache initialized, cache dir: {$res}
msg-017bde96 = Saved tool image to: {$file_path}
msg-29398f55 = Failed to save tool image: {$e}
msg-128aa08a = Failed to read cached image {$file_path}: {$e}
msg-3c111d1f = Error during cache cleanup: {$e}
msg-eeb1b849 = Cleaned up {$cleaned} expired cached images

### astrbot/core/agent/message.py
msg-d38656d7 = {$invalid_subclass_error_msg}
msg-42d5a315 = Cannot validate {$value} as ContentPart
msg-ffc376d0 = content is required unless role='assistant' and tool_calls is not None

### astrbot/core/agent/mcp_client.py
msg-6a61ca88 = Warning: Missing 'mcp' dependency, MCP services will be unavailable.
msg-45995cdb = Warning: Missing 'mcp' dependency or MCP library version too old, Streamable HTTP connection unavailable.
msg-2866b896 = MCP connection config missing transport or type field
msg-3bf7776b = MCP Server {$name} Error: {$msg}
msg-10f72727 = {$error_msg}
msg-19c9b509 = MCP Client is not initialized
msg-5b9b4918 = MCP Client {$res} is already reconnecting, skipping
msg-c1008866 = Cannot reconnect: missing connection configuration
msg-7c3fe178 = Attempting to reconnect to MCP server {$res}...
msg-783f3b85 = Successfully reconnected to MCP server {$res}
msg-da7361ff = Failed to reconnect to MCP server {$res}: {$e}
msg-c0fd612e = MCP session is not available for MCP function tools.
msg-8236c58c = MCP tool {$tool_name} call failed (ClosedResourceError), attempting to reconnect...
msg-044046ec = Error closing current exit stack: {$e}

### astrbot/core/agent/tool.py
msg-983bc802 = FunctionTool.call() must be implemented by subclasses or set a handler.

### astrbot/core/agent/context/compressor.py
msg-6c75531b = Failed to generate summary: {$e}

### astrbot/core/agent/context/manager.py
msg-59241964 = Error during context processing: {$e}
msg-a0d672dc = Compress triggered, starting compression...
msg-e6ef66f0 = Compress completed. {$prev_tokens} -> {$tokens_after_summary} tokens, compression rate: {$compress_rate}%.
msg-3fe644eb = Context still exceeds max tokens after compression, applying halving truncation...

### astrbot/core/agent/runners/tool_loop_agent_runner.py
msg-960ef181 = Switched from %s to fallback chat provider: %s
msg-4f999913 = Chat Model %s returns error response, trying fallback to next provider.
msg-c042095f = Chat Model %s request error: %s
msg-81b2aeae = {$tag} RunCtx.messages -> [{$res}] {$res_2}
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook: {$e}
msg-61de315c = Agent execution was requested to stop by user.
msg-8eb53be3 = Error in on_agent_done hook: {$e}
msg-508d6d17 = LLM 响应错误: {$res}
msg-ed80313d = LLM returned empty assistant message with no tool calls.
msg-970947ae = Appended {$res} cached image(s) to context for LLM review
msg-6b326889 = Agent reached max steps ({$max_step}), forcing a final response.
msg-948ea4b7 = Agent 使用工具: {$res}
msg-a27ad3d1 = 使用工具：{$func_tool_name}，参数：{$func_tool_args}
msg-812ad241 = 未找到指定的工具: {$func_tool_name}，将跳过。
msg-20b4f143 = 工具 {$func_tool_name} 期望的参数: {$res}
msg-78f6833c = 工具 {$func_tool_name} 忽略非期望参数: {$ignored_params}
msg-2b523f8c = Error in on_tool_start hook: {$e}
msg-ec868b73 = {$func_tool_name} 没有返回值，或者已将结果直接发送给用户。
msg-6b61e4f1 = Tool 返回了不支持的类型: {$res}。
msg-34c13e02 = Error in on_tool_end hook: {$e}
msg-78b9c276 = {$res}
msg-a1493b6d = Tool `{$func_tool_name}` Result: {$last_tcr_content}

### astrbot/core/agent/runners/base.py
msg-24eb2b08 = Agent state transition: {$res} -> {$new_state}

### astrbot/core/agent/runners/dashscope/dashscope_agent_runner.py
msg-dc1a9e6e = 阿里云百炼 API Key 不能为空。
msg-c492cbbc = 阿里云百炼 APP ID 不能为空。
msg-bcc8e027 = 阿里云百炼 APP 类型不能为空。
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook: {$e}
msg-e3af4efd = 阿里云百炼请求失败：{$res}
msg-fccf5004 = dashscope stream chunk: {$chunk}
msg-100d7d7e = 阿里云百炼请求失败: request_id={$res}, code={$res_2}, message={$res_3}, 请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code
msg-10f72727 = {$error_msg}
msg-e8615101 = {$chunk_text}
msg-dfb132c4 = {$ref_text}
msg-8eb53be3 = Error in on_agent_done hook: {$e}
msg-650b47e1 = 阿里云百炼暂不支持图片输入，将自动忽略图片内容。

### astrbot/core/agent/runners/coze/coze_agent_runner.py
msg-448549b0 = Coze API Key 不能为空。
msg-b88724b0 = Coze Bot ID 不能为空。
msg-ea5a135a = Coze API Base URL 格式不正确，必须以 http:// 或 https:// 开头。
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook: {$e}
msg-5aa3eb1c = Coze 请求失败：{$res}
msg-333354c6 = 处理上下文图片失败: {$e}
msg-2d9e1c08 = 处理图片失败 {$url}: {$e}
msg-1f50979d = {$content}
msg-6fe5588b = Coze message completed
msg-d2802f3b = Coze chat completed
msg-ba4afcda = Coze 出现错误: {$error_code} - {$error_msg}
msg-ee300f25 = Coze 未返回任何内容
msg-8eb53be3 = Error in on_agent_done hook: {$e}
msg-034c1858 = [Coze] 使用缓存的 file_id: {$file_id}
msg-475d8a41 = [Coze] 图片上传成功并缓存，file_id: {$file_id}
msg-696dad99 = 处理图片失败 {$image_url}: {$e}
msg-7793a347 = 处理图片失败: {$e}

### astrbot/core/agent/runners/coze/coze_api_client.py
msg-76f97104 = Coze API 认证失败，请检查 API Key 是否正确
msg-3653b652 = 文件上传响应状态: {$res}, 内容: {$response_text}
msg-13fe060c = 文件上传失败，状态码: {$res}, 响应: {$response_text}
msg-5604b862 = 文件上传响应解析失败: {$response_text}
msg-c0373c50 = 文件上传失败: {$res}
msg-010e4299 = [Coze] 图片上传成功，file_id: {$file_id}
msg-719f13cb = 文件上传超时
msg-121c11fb = 文件上传失败: {$e}
msg-f6101892 = 下载图片失败，状态码: {$res}
msg-c09c56c9 = 下载图片失败 {$image_url}: {$e}
msg-15211c7c = 下载图片失败: {$e}
msg-2245219f = Coze chat_messages payload: {$payload}, params: {$params}
msg-d8fd415c = Coze API 流式请求失败，状态码: {$res}
msg-f5cc7604 = Coze API 流式请求超时 ({$timeout}秒)
msg-30c0a9d6 = Coze API 流式请求失败: {$e}
msg-11509aba = Coze API 请求失败，状态码: {$res}
msg-002af11d = Coze API 返回非JSON格式
msg-c0b8fc7c = Coze API 请求超时
msg-a68a33fa = Coze API 请求失败: {$e}
msg-c26e068e = 获取Coze消息列表失败: {$e}
msg-5bc0a49d = Uploaded file_id: {$file_id}
msg-7c08bdaf = Event: {$event}

### astrbot/core/agent/runners/dify/dify_api_client.py
msg-cd6cd7ac = Drop invalid dify json data: {$res}
msg-3654a12d = chat_messages payload: {$payload}
msg-8e865c52 = Dify /chat-messages 接口请求失败：{$res}. {$text}
msg-2d7534b8 = workflow_run payload: {$payload}
msg-89918ba5 = Dify /workflows/run 接口请求失败：{$res}. {$text}
msg-8bf17938 = file_path 和 file_data 不能同时为 None
msg-b6ee8f38 = Dify 文件上传失败：{$res}. {$text}

### astrbot/core/agent/runners/dify/dify_agent_runner.py
msg-55333301 = Request is not set. Please call reset() first.
msg-d3b77736 = Error in on_agent_begin hook: {$e}
msg-0d493427 = Dify 请求失败：{$res}
msg-fe594f21 = Dify 上传图片响应：{$file_response}
msg-3534b306 = 上传图片后得到未知的 Dify 响应：{$file_response}，图片将忽略。
msg-08441fdf = 上传图片失败：{$e}
msg-3972f693 = dify resp chunk: {$chunk}
msg-6c74267b = Dify message end
msg-1ce260ba = Dify 出现错误：{$chunk}
msg-a12417dd = Dify 出现错误 status: {$res} message: {$res_2}
msg-f8530ee9 = dify workflow resp chunk: {$chunk}
msg-386a282e = Dify 工作流(ID: {$res})开始运行。
msg-0bc1299b = Dify 工作流节点(ID: {$res} Title: {$res_2})运行结束。
msg-5cf24248 = Dify 工作流(ID: {$res})运行结束
msg-e2c2159f = Dify 工作流结果：{$chunk}
msg-4fa60ef1 = Dify 工作流出现错误：{$res}
msg-1f786836 = Dify 工作流的输出不包含指定的键名：{$res}
msg-c4a70ffb = 未知的 Dify API 类型：{$res}
msg-51d321fd = Dify 请求结果为空，请查看 Debug 日志。
msg-8eb53be3 = Error in on_agent_done hook: {$e}

### astrbot/core/star/session_plugin_manager.py
msg-16cc2a7a = 插件 {$res} 在会话 {$session_id} 中被禁用，跳过处理器 {$res_2}

### astrbot/core/star/star_manager.py
msg-bfa28c02 = 未安装 watchfiles，无法实现插件的热重载。
msg-f8e1c445 = 插件热重载监视任务异常: {$e}
msg-78b9c276 = {$res}
msg-28aeca68 = 检测到文件变化: {$changes}
msg-aeec7738 = 检测到插件 {$plugin_name} 文件变化，正在重载...
msg-4f989555 = 插件 {$d} 未找到 main.py 或者 {$d}.py，跳过。
msg-74b32804 = 正在安装插件 {$p} 所需的依赖库: {$pth}
msg-936edfca = 更新插件 {$p} 的依赖失败。Code: {$e}
msg-ebd47311 = 插件 {$root_dir_name} 导入失败，尝试从已安装依赖恢复: {$import_exc}
msg-1b6e94f1 = 插件 {$root_dir_name} 已从 site-packages 恢复依赖，跳过重新安装。
msg-81b7c9b9 = 插件 {$root_dir_name} 已安装依赖恢复失败，将重新安装依赖: {$recover_exc}
msg-22fde75d = 插件不存在。
msg-3a307a9e = 插件元数据信息不完整。name, desc, version, author 是必须的字段。
msg-55e089d5 = 删除模块 {$key}
msg-64de1322 = 删除模块 {$module_name}
msg-66823424 = 模块 {$module_name} 未载入
msg-45c8df8d = 清除了插件{$dir_name}中的{$key}模块
msg-f7d9aa9b = 清理处理器: {$res}
msg-3c492aa6 = 清理工具: {$res}
msg-e0002829 = 插件 {$res} 未被正常终止: {$e}, 可能会导致该插件运行不正常。
msg-0fe27735 = 正在载入插件 {$root_dir_name} ...
msg-b2ec4801 = {$error_trace}
msg-db351291 = 插件 {$root_dir_name} 导入失败。原因：{$e}
msg-a3db5f45 = 失败插件依旧在插件列表中，正在清理...
msg-58c66a56 = 插件 {$root_dir_name} 元数据载入失败: {$e}。使用默认元数据。
msg-da764b29 = {$metadata}
msg-17cd7b7d = 插件 {$res} 已被禁用。
msg-4baf6814 = 插件 {$path} 未通过装饰器注册。尝试通过旧版本方式载入。
msg-840994d1 = 无法找到插件 {$plugin_dir_path} 的元数据。
msg-944ffff1 = 插入权限过滤器 {$cmd_type} 到 {$res} 的 {$res_2} 方法。
msg-64edd12c = hook(on_plugin_loaded) -> {$res} - {$res_2}
msg-db49f7a1 = ----- 插件 {$root_dir_name} 载入失败 -----
msg-26039659 = | {$line}
msg-4292f44d = ----------------------------------
msg-d2048afe = 同步指令配置失败: {$e}
msg-df515dec = 已清理安装失败的插件目录: {$plugin_path}
msg-1f2aa1a9 = 清理安装失败插件目录失败: {$plugin_path}，原因: {$e}
msg-1e947210 = 已清理安装失败插件配置: {$plugin_config_path}
msg-7374541f = 清理安装失败插件配置失败: {$plugin_config_path}，原因: {$e}
msg-e871b08f = 读取插件 {$dir_name} 的 README.md 文件失败: {$e}
msg-70ca4592 = 该插件是 AstrBot 保留插件，无法卸载。
msg-e247422b = 插件 {$plugin_name} 未被正常终止 {$e}, 可能会导致资源泄露等问题。
msg-0c25dbf4 = 插件 {$plugin_name} 数据不完整，无法卸载。
msg-d6f8142c = 移除插件成功，但是删除插件文件夹失败: {$e}。您可以手动删除该文件夹，位于 addons/plugins/ 下。
msg-6313500c = 已删除插件 {$plugin_name} 的配置文件
msg-f0f01b67 = 删除插件配置文件失败: {$e}
msg-c4008b30 = 已删除插件 {$plugin_name} 的持久化数据 (plugin_data)
msg-88d1ee05 = 删除插件持久化数据失败 (plugin_data): {$e}
msg-ba805469 = 已删除插件 {$plugin_name} 的持久化数据 (plugins_data)
msg-cf6eb821 = 删除插件持久化数据失败 (plugins_data): {$e}
msg-e1853811 = 移除了插件 {$plugin_name} 的处理函数 {$res} ({$res_2})
msg-95b20050 = 移除了插件 {$plugin_name} 的平台适配器 {$adapter_name}
msg-9f248e88 = 该插件是 AstrBot 保留插件，无法更新。
msg-ff435883 = 正在终止插件 {$res} ...
msg-355187b7 = 插件 {$res} 未被激活，不需要终止，跳过。
msg-4369864f = hook(on_plugin_unloaded) -> {$res} - {$res_2}
msg-1b95e855 = 插件 {$plugin_name} 不存在。
msg-c1bc6cd6 = 检测到插件 {$res} 已安装，正在终止旧插件...
msg-4f3271db = 检测到同名插件 {$res} 存在于不同目录 {$res_2}，正在终止...
msg-d247fc54 = 读取新插件 metadata.yaml 失败，跳过同名检查: {$e}
msg-0f8947f8 = 删除插件压缩包失败: {$e}

### astrbot/core/star/session_llm_manager.py
msg-7b90d0e9 = 会话 {$session_id} 的TTS状态已更新为: {$res}

### astrbot/core/star/config.py
msg-c2189e8d = namespace 不能为空。
msg-97f66907 = namespace 不能以 internal_ 开头。
msg-09179604 = key 只支持 str 类型。
msg-1163e4f1 = value 只支持 str, int, float, bool, list 类型。
msg-ed0f93e4 = 配置文件 {$namespace}.json 不存在。
msg-e3b5cdfb = 配置项 {$key} 不存在。

### astrbot/core/star/star_tools.py
msg-397b7bf9 = StarTools not initialized
msg-ca30e638 = 未找到适配器: AiocqhttpAdapter
msg-77ca0ccb = 不支持的平台: {$platform}
msg-3ed67eb2 = 无法获取调用者模块信息
msg-e77ccce6 = 无法获取模块 {$res} 的元数据信息
msg-76ac38ee = 无法获取插件名称
msg-751bfd23 = 无法创建目录 {$data_dir}：权限不足
msg-68979283 = 无法创建目录 {$data_dir}：{$e}

### astrbot/core/star/context.py
msg-60eb9e43 = Provider {$chat_provider_id} not found
msg-da70a6fb = Agent did not produce a final LLM response
msg-141151fe = Provider not found
msg-a5cb19c6 = 没有找到 ID 为 {$provider_id} 的提供商，这可能是由于您修改了提供商（模型）ID 导致的。
msg-2a44300b = 该会话来源的对话模型（提供商）的类型不正确: {$res}
msg-37c286ea = 返回的 Provider 不是 TTSProvider 类型
msg-ff775f3b = 返回的 Provider 不是 STTProvider 类型
msg-fd8c8295 = cannot find platform for session {$res}, message not sent
msg-2b806a28 = plugin(module_path {$module_path}) added LLM tool: {$res}

### astrbot/core/star/updator.py
msg-66be72ec = 插件 {$res} 没有指定仓库地址。
msg-7a29adea = 插件 {$res} 的根目录名未指定。
msg-99a86f88 = 正在更新插件，路径: {$plugin_path}，仓库地址: {$repo_url}
msg-df2c7e1b = 删除旧版本插件 {$plugin_path} 文件夹失败: {$e}，使用覆盖安装。
msg-b3471491 = 正在解压压缩包: {$zip_path}
msg-7197ad11 = 删除临时文件: {$zip_path} 和 {$res}
msg-f8a43aa5 = 删除更新文件失败，可以手动删除 {$zip_path} 和 {$res}

### astrbot/core/star/command_management.py
msg-011581bb = 指定的处理函数不存在或不是指令。
msg-a0c37004 = 指令名不能为空。
msg-ae8b2307 = 指令名 '{$candidate_full}' 已被其他指令占用。
msg-247926a7 = 别名 '{$alias_full}' 已被其他指令占用。
msg-dbd19a23 = 权限类型必须为 admin 或 member。
msg-9388ea1e = 未找到指令所属插件
msg-0dd9b70d = 解析指令处理函数 {$res} 失败，跳过该指令。原因: {$e}

### astrbot/core/star/base.py
msg-57019272 = get_config() failed: {$e}

### astrbot/core/star/register/star.py
msg-64619f8e = The 'register_star' decorator is deprecated and will be removed in a future version.

### astrbot/core/star/register/star_handler.py
msg-7ff2d46e = 注册指令{$command_name} 的子指令时未提供 sub_command 参数。
msg-b68436e1 = 注册裸指令时未提供 command_name 参数。
msg-1c183df2 = {$command_group_name} 指令组的子指令组 sub_command 未指定
msg-9210c7e8 = 根指令组的名称未指定
msg-678858e7 = 注册指令组失败。
msg-6c3915e0 = LLM 函数工具 {$res}_{$llm_tool_name} 的参数 {$res_2} 缺少类型注释。
msg-1255c964 = LLM 函数工具 {$res}_{$llm_tool_name} 不支持的参数类型：{$res_2}

### astrbot/core/star/filter/command.py
msg-995944c2 = 参数 '{$param_name}' (GreedyStr) 必须是最后一个参数。
msg-04dbdc3a = 必要参数缺失。该指令完整参数: {$res}
msg-bda71712 = 参数 {$param_name} 必须是布尔值（true/false, yes/no, 1/0）。
msg-a9afddbf = 参数 {$param_name} 类型错误。完整参数: {$res}

### astrbot/core/star/filter/custom_filter.py
msg-8f3eeb6e = Operands must be subclasses of CustomFilter.
msg-732ada95 = CustomFilter class can only operate with other CustomFilter.
msg-51c0c77d = CustomFilter lass can only operate with other CustomFilter.

### astrbot/core/db/vec_db/faiss_impl/document_storage.py
msg-c2dc1d2b = Database connection is not initialized, returning empty result
msg-51fa7426 = Database connection is not initialized, skipping delete operation
msg-43d1f69f = Database connection is not initialized, returning 0

### astrbot/core/db/vec_db/faiss_impl/embedding_storage.py
msg-8e5fe535 = faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。
msg-9aa7b941 = 向量维度不匹配, 期望: {$res}, 实际: {$res_2}

### astrbot/core/db/vec_db/faiss_impl/vec_db.py
msg-9f9765dc = Generating embeddings for {$res} contents...
msg-385bc50a = Generated embeddings for {$res} contents in {$res_2} seconds.

### astrbot/core/db/migration/migra_token_usage.py
msg-c3e53a4f = 开始执行数据库迁移（添加 conversations.token_usage 列）...
msg-ccbd0a41 = token_usage 列已存在，跳过迁移
msg-39f60232 = token_usage 列添加成功
msg-4f9d3876 = token_usage 迁移完成
msg-91571aaf = 迁移过程中发生错误: {$e}

### astrbot/core/db/migration/migra_3_to_4.py
msg-7805b529 = 迁移 {$total_cnt} 条旧的会话数据到新的表中...
msg-6f232b73 = 进度: {$progress}% ({$res}/{$total_cnt})
msg-6b1def31 = 未找到该条旧会话对应的具体数据: {$conversation}, 跳过。
msg-b008c93f = 迁移旧会话 {$res} 失败: {$e}
msg-6ac6313b = 成功迁移 {$total_cnt} 条旧的会话数据到新表。
msg-6b72e89b = 迁移旧平台数据，offset_sec: {$offset_sec} 秒。
msg-bdc90b84 = 迁移 {$res} 条旧的平台数据到新的表中...
msg-e6caca5c = 没有找到旧平台数据，跳过迁移。
msg-1e824a79 = 进度: {$progress}% ({$res}/{$total_buckets})
msg-813384e2 = 迁移平台统计数据失败: {$platform_id}, {$platform_type}, 时间戳: {$bucket_end}
msg-27ab191d = 成功迁移 {$res} 条旧的平台数据到新表。
msg-8e6280ed = 迁移 {$total_cnt} 条旧的 WebChat 会话数据到新的表中...
msg-cad66fe1 = 迁移旧 WebChat 会话 {$res} 失败
msg-63748a46 = 成功迁移 {$total_cnt} 条旧的 WebChat 会话数据到新表。
msg-dfc93fa4 = 迁移 {$total_personas} 个 Persona 配置到新表中...
msg-ff85e45c = 进度: {$progress}% ({$res}/{$total_personas})
msg-c346311e = 迁移 Persona {$res}({$res_2}...) 到新表成功。
msg-b6292b94 = 解析 Persona 配置失败：{$e}
msg-90e5039e = 迁移全局偏好设置 {$key} 成功，值: {$value}
msg-d538da1c = 迁移会话 {$umo} 的对话数据到新表成功，平台 ID: {$platform_id}
msg-ee03c001 = 迁移会话 {$umo} 的对话数据失败: {$e}
msg-5c4339cd = 迁移会话 {$umo} 的服务配置到新表成功，平台 ID: {$platform_id}
msg-4ce2a0b2 = 迁移会话 {$umo} 的服务配置失败: {$e}
msg-2e62dab9 = 迁移会话 {$umo} 的变量失败: {$e}
msg-afbf819e = 迁移会话 {$umo} 的提供商偏好到新表成功，平台 ID: {$platform_id}
msg-959bb068 = 迁移会话 {$umo} 的提供商偏好失败: {$e}

### astrbot/core/db/migration/helper.py
msg-a48f4752 = 开始执行数据库迁移...
msg-45e31e8e = 数据库迁移完成。

### astrbot/core/db/migration/migra_45_to_46.py
msg-782b01c1 = migrate_45_to_46: abconf_data is not a dict (type={$res}). Value: {$abconf_data}
msg-49e09620 = Starting migration from version 4.5 to 4.6
msg-791b79f8 = Migration from version 45 to 46 completed successfully

### astrbot/core/db/migration/migra_webchat_session.py
msg-53fad3d0 = 开始执行数据库迁移（WebChat 会话迁移）...
msg-7674efb0 = 没有找到需要迁移的 WebChat 数据
msg-139e39ee = 找到 {$res} 个 WebChat 会话需要迁移
msg-cf287e58 = 会话 {$session_id} 已存在，跳过
msg-062c72fa = WebChat 会话迁移完成！成功迁移: {$res}, 跳过: {$skipped_count}
msg-a516cc9f = 没有新会话需要迁移
msg-91571aaf = 迁移过程中发生错误: {$e}

### astrbot/core/knowledge_base/kb_helper.py
msg-7b3dc642 =   - LLM call failed on attempt {$res}/{$res_2}. Error: {$res_3}
msg-4ba9530f =   - Failed to process chunk after {$res} attempts. Using original text.
msg-77670a3a = 知识库 {$res} 未配置 Embedding Provider
msg-8e9eb3f9 = 无法找到 ID 为 {$res} 的 Embedding Provider
msg-3e426806 = 无法找到 ID 为 {$res} 的 Rerank Provider
msg-6e780e1e = 使用预分块文本进行上传，共 {$res} 个块。
msg-f4b82f18 = 当未提供 pre_chunked_text 时，file_content 不能为空。
msg-975f06d7 = 上传文档失败: {$e}
msg-969b17ca = 清理多媒体文件失败 {$media_path}: {$me}
msg-18d25e55 = 无法找到 ID 为 {$doc_id} 的文档
msg-f5d7c34c = Error: Tavily API key is not configured in provider_settings.
msg-975d88e0 = Failed to extract content from URL {$url}: {$e}
msg-cfe431b3 = No content extracted from URL: {$url}
msg-e7f5f836 = 内容清洗后未提取到有效文本。请尝试关闭内容清洗功能，或更换更高性能的LLM模型后重试。
msg-693aa5c5 = 内容清洗未启用，使用指定参数进行分块: chunk_size={$chunk_size}, chunk_overlap={$chunk_overlap}
msg-947d8f46 = 启用了内容清洗，但未提供 cleaning_provider_id，跳过清洗并使用默认分块。
msg-31963d3f = 无法找到 ID 为 {$cleaning_provider_id} 的 LLM Provider 或类型不正确
msg-82728272 = 初步分块完成，生成 {$res} 个块用于修复。
msg-6fa5fdca = 块 {$i} 处理异常: {$res}. 回退到原始块。
msg-6780e950 = 文本修复完成: {$res} 个原始块 -> {$res_2} 个最终块。
msg-79056c76 = 使用 Provider '{$cleaning_provider_id}' 清洗内容失败: {$e}

### astrbot/core/knowledge_base/kb_mgr.py
msg-98bfa670 = 正在初始化知识库模块...
msg-7da7ae15 = 知识库模块导入失败: {$e}
msg-842a3c65 = 请确保已安装所需依赖: pypdf, aiofiles, Pillow, rank-bm25
msg-c9e943f7 = 知识库模块初始化失败: {$e}
msg-78b9c276 = {$res}
msg-9349e112 = KnowledgeBase database initialized: {$DB_PATH}
msg-7605893e = 创建知识库时必须提供embedding_provider_id
msg-0b632cbd = 知识库名称 '{$kb_name}' 已存在
msg-ca30330f = 关闭知识库 {$kb_id} 失败: {$e}
msg-00262e1f = 关闭知识库元数据数据库失败: {$e}
msg-3fc9ef0b = Knowledge base with id {$kb_id} not found.

### astrbot/core/knowledge_base/kb_db_sqlite.py
msg-b850e5d8 = 知识库数据库已关闭: {$res}

### astrbot/core/knowledge_base/parsers/util.py
msg-398b3580 = 暂时不支持的文件格式: {$ext}

### astrbot/core/knowledge_base/parsers/url_parser.py
msg-2de85bf5 = Error: Tavily API keys are not configured.
msg-98ed69f4 = Error: url must be a non-empty string.
msg-7b14cdb7 = Tavily web extraction failed: {$reason}, status: {$res}
msg-cfe431b3 = No content extracted from URL: {$url}
msg-b0897365 = Failed to fetch URL {$url}: {$e}
msg-975d88e0 = Failed to extract content from URL {$url}: {$e}

### astrbot/core/knowledge_base/parsers/text_parser.py
msg-70cbd40d = 无法解码文件: {$file_name}

### astrbot/core/knowledge_base/chunking/recursive.py
msg-21db456a = chunk_size must be greater than 0
msg-c0656f4e = chunk_overlap must be non-negative
msg-82bd199c = chunk_overlap must be less than chunk_size

### astrbot/core/knowledge_base/retrieval/manager.py
msg-fcc0dde2 = 知识库 ID {$kb_id} 实例未找到, 已跳过该知识库的检索
msg-320cfcff = Dense retrieval across {$res} bases took {$res_2}s and returned {$res_3} results.
msg-90ffcfc8 = Sparse retrieval across {$res} bases took {$res_2}s and returned {$res_3} results.
msg-12bcf404 = Rank fusion took {$res}s and returned {$res_2} results.
msg-28c084bc = vec_db for kb_id {$kb_id} is not FaissVecDB
msg-cc0230a3 = 知识库 {$kb_id} 稠密检索失败: {$e}

### astrbot/core/skills/skill_manager.py
msg-ed9670ad = Zip file not found: {$zip_path}
msg-73f9cf65 = Uploaded file is not a valid zip archive.
msg-69eb5f95 = Zip archive is empty.
msg-9e9abb4c = {$top_dirs}
msg-20b8533f = Zip archive must contain a single top-level folder.
msg-1db1caf7 = Invalid skill folder name.
msg-d7814054 = Zip archive contains absolute paths.
msg-179bd10e = Zip archive contains invalid relative paths.
msg-90f2904e = Zip archive contains unexpected top-level entries.
msg-95775a4d = SKILL.md not found in the skill folder.
msg-a4117c0b = Skill folder not found after extraction.
msg-94041ef2 = Skill already exists.

### astrbot/core/backup/importer.py
msg-c046b6e4 = {$msg}
msg-0e6f1f5d = 开始从 {$zip_path} 导入备份
msg-2bf97ca0 = 备份导入完成: {$res}
msg-e67dda98 = 备份文件缺少版本信息
msg-8f871d9f = 版本差异警告: {$res}
msg-2d6da12a = 已清空表 {$table_name}
msg-7d21b23a = 清空表 {$table_name} 失败: {$e}
msg-ab0f09db = 已清空知识库表 {$table_name}
msg-7bcdfaee = 清空知识库表 {$table_name} 失败: {$e}
msg-43f008f1 = 清理知识库 {$kb_id} 失败: {$e}
msg-985cae66 = 未知的表: {$table_name}
msg-dfa8b605 = 导入记录到 {$table_name} 失败: {$e}
msg-89a2120c = 导入表 {$table_name}: {$count} 条记录
msg-f1dec753 = 导入知识库记录到 {$table_name} 失败: {$e}
msg-9807bcd8 = 导入文档块失败: {$e}
msg-98a66293 = 导入附件 {$name} 失败: {$e}
msg-39f2325f = 备份版本不支持目录备份，跳过目录导入
msg-689050b6 = 已备份现有目录 {$target_dir} 到 {$backup_path}
msg-d51b3536 = 导入目录 {$dir_name}: {$file_count} 个文件

### astrbot/core/backup/exporter.py
msg-c7ed7177 = 开始导出备份到 {$zip_path}
msg-8099b694 = 备份导出完成: {$zip_path}
msg-75a4910d = 备份导出失败: {$e}
msg-2821fc92 = 导出表 {$table_name}: {$res} 条记录
msg-52b7c242 = 导出表 {$table_name} 失败: {$e}
msg-56310830 = 导出知识库表 {$table_name}: {$res} 条记录
msg-f4e8f57e = 导出知识库表 {$table_name} 失败: {$e}
msg-8e4ddd12 = 导出知识库文档失败: {$e}
msg-c1960618 = 导出 FAISS 索引: {$archive_path}
msg-314bf920 = 导出 FAISS 索引失败: {$e}
msg-528757b2 = 导出知识库媒体文件失败: {$e}
msg-d89d6dfe = 目录不存在，跳过: {$full_path}
msg-94527edd = 导出文件 {$file_path} 失败: {$e}
msg-cb773e24 = 导出目录 {$dir_name}: {$file_count} 个文件, {$total_size} 字节
msg-ae929510 = 导出目录 {$dir_path} 失败: {$e}
msg-93e331d2 = 导出附件失败: {$e}

### astrbot/core/computer/computer_client.py
msg-7cb974b8 = Uploading skills bundle to sandbox...
msg-130cf3e3 = Failed to upload skills bundle to sandbox.
msg-99188d69 = Failed to remove temp skills zip: {$zip_path}
msg-3f3c81da = Unknown booter type: {$booter_type}
msg-e20cc33a = Error booting sandbox for session {$session_id}: {$e}

### astrbot/core/computer/tools/fs.py
msg-99ab0efe = Upload result: {$result}
msg-bca9d578 = File {$local_path} uploaded to sandbox at {$file_path}
msg-da21a6a5 = Error uploading file {$local_path}: {$e}
msg-93476abb = File {$remote_path} downloaded from sandbox to {$local_path}
msg-079c5972 = Error sending file message: {$e}
msg-ce35bb2c = Error downloading file {$remote_path}: {$e}

### astrbot/core/computer/booters/local.py
msg-487d0c91 = Path is outside the allowed computer roots.
msg-e5eb5377 = Blocked unsafe shell command.
msg-9e1e117f = Local computer booter initialized for session: {$session_id}
msg-2d7f95de = Local computer booter shutdown complete.
msg-82a45196 = LocalBooter does not support upload_file operation. Use shell instead.
msg-0457524a = LocalBooter does not support download_file operation. Use shell instead.

### astrbot/core/computer/booters/shipyard.py
msg-b03115b0 = Got sandbox ship: {$res} for session: {$session_id}
msg-c5ce8bde = Error checking Shipyard sandbox availability: {$e}

### astrbot/core/computer/booters/boxlite.py
msg-019c4d18 = Failed to exec operation: {$res} {$error_text}
msg-b135b7bd = Failed to upload file: {$e}
msg-873ed1c8 = File not found: {$path}
msg-f58ceec6 = Unexpected error uploading file: {$e}
msg-900ab999 = Checking health for sandbox {$ship_id} on {$res}...
msg-2a50d6f3 = Sandbox {$ship_id} is healthy
msg-fbdbe32f = Booting(Boxlite) for session: {$session_id}, this may take a while...
msg-b1f13f5f = Boxlite booter started for session: {$session_id}
msg-e93d0c30 = Shutting down Boxlite booter for ship: {$res}
msg-6deea473 = Boxlite booter for ship: {$res} stopped

### astrbot/core/cron/manager.py
msg-724e64a9 = Skip scheduling basic cron job %s due to missing handler.
msg-78ef135f = Invalid timezone %s for cron job %s, fallback to system.
msg-e71c28d3 = run_once job missing run_at timestamp
msg-dd46e69f = Failed to schedule cron job {$res}: {$e}
msg-aa2e4688 = Unknown cron job type: {$res}
msg-186627d9 = Cron job {$job_id} failed: {$e}
msg-cb955de0 = Basic cron job handler not found for {$res}
msg-2029c4b2 = ActiveAgentCronJob missing session.
msg-6babddc9 = Invalid session for cron job: {$e}
msg-865a2b07 = Failed to build main agent for cron job.
msg-27c9c6b3 = Cron job agent got no response

### astrbot/utils/http_ssl_common.py
msg-7957c9b6 = Failed to load certifi CA bundle into SSL context; falling back to system trust store only: %s

### astrbot/cli/__main__.py
msg-fe494da6 = {$logo_tmpl}
msg-c8b2ff67 = Welcome to AstrBot CLI!
msg-d79e1ff9 = AstrBot CLI version: {$__version__}
msg-78b9c276 = {$res}
msg-14dd710d = Unknown command: {$command_name}

### astrbot/cli/utils/basic.py
msg-f4e0fd7b = 未安装管理面板
msg-2d090cc3 = 正在安装管理面板...
msg-2eeb67e0 = 管理面板安装完成
msg-9c727dca = 管理面板已是最新版本
msg-11b49913 = 管理面板版本: {$version}
msg-f0b6145e = 下载管理面板失败: {$e}
msg-9504d173 = 初始化管理面板目录...
msg-699e2509 = 管理面板初始化完成

### astrbot/cli/utils/plugin.py
msg-e327bc14 = 正在从默认分支下载 {$author}/{$repo}
msg-c804f59f = 获取 release 信息失败: {$e}，将直接使用提供的 URL
msg-aa398bd5 = master 分支不存在，尝试下载 main 分支
msg-5587d9fb = 读取 {$yaml_path} 失败: {$e}
msg-8dbce791 = 获取在线插件列表失败: {$e}
msg-6999155d = 插件 {$plugin_name} 未安装，无法更新
msg-fa5e129a = 正在从 {$repo_url} {$res}插件 {$plugin_name}...
msg-9ac1f4db = 插件 {$plugin_name} {$res}成功
msg-b9c719ae = {$res}插件 {$plugin_name} 时出错: {$e}

### astrbot/cli/commands/cmd_conf.py
msg-635b8763 = 日志级别必须是 DEBUG/INFO/WARNING/ERROR/CRITICAL 之一
msg-ebc250dc = 端口必须在 1-65535 范围内
msg-6ec400b6 = 端口必须是数字
msg-0b62b5ce = 用户名不能为空
msg-89b5d3d5 = 密码不能为空
msg-92e7c8ad = 无效的时区: {$value}，请使用有效的IANA时区名称
msg-e470e37d = 回调接口基址必须以 http:// 或 https:// 开头
msg-6b615721 = {$root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init
msg-f74c517c = 配置文件解析失败: {$e}
msg-d7c58bcc = 配置路径冲突: {$res} 不是字典
msg-e16816cc = 不支持的配置项: {$key}
msg-e9cce750 = 配置已更新: {$key}
msg-1ed565aa =   原值: ********
msg-1bf9569a =   新值: ********
msg-f2a20ab3 =   原值: {$old_value}
msg-0c104905 =   新值: {$validated_value}
msg-ea9b4e2c = 未知的配置项: {$key}
msg-4450e3b1 = 设置配置失败: {$e}
msg-ba464bee = {$key}: {$value}
msg-72aab576 = 获取配置失败: {$e}
msg-c1693d1d = 当前配置:
msg-50be9b74 =   {$key}: {$value}

### astrbot/cli/commands/cmd_init.py
msg-a90a250e = Current Directory: {$astrbot_root}
msg-4deda62e = 如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的数据目录。
msg-3319bf71 = Created {$dot_astrbot}
msg-7054f44f = {$res}: {$path}
msg-b19edc8a = Initializing AstrBot...
msg-eebc39e3 = 无法获取锁文件，请检查是否有其他实例正在运行
msg-e16da80f = 初始化失败: {$e}

### astrbot/cli/commands/cmd_run.py
msg-41ecc632 = {$astrbot_root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init
msg-0ccaca23 = 启用插件自动重载
msg-220914e7 = AstrBot 已关闭...
msg-eebc39e3 = 无法获取锁文件，请检查是否有其他实例正在运行
msg-85f241d3 = 运行时出现错误: {$e}{"\u000A"}{$res}

### astrbot/cli/commands/cmd_plug.py
msg-cbd8802b = {$base}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init
msg-78b9c276 = {$res}
msg-83664fcf = {$val} {$val} {$val} {$val} {$val}
msg-56f3f0bf = {$res} {$res_2} {$res_3} {$res_4} {$desc}
msg-1d802ff2 = 插件 {$name} 已存在
msg-a7be9d23 = 版本号必须为 x.y 或 x.y.z 格式
msg-4d81299b = 仓库地址必须以 http 开头
msg-93289755 = 下载插件模板...
msg-b21682dd = 重写插件信息...
msg-bffc8bfa = 插件 {$name} 创建成功
msg-08eae1e3 = 未安装任何插件
msg-1a021bf4 = 未找到可安装的插件 {$name}，可能是不存在或已安装
msg-c120bafd = 插件 {$name} 不存在或未安装
msg-63da4867 = 插件 {$name} 已卸载
msg-e4925708 = 卸载插件 {$name} 失败: {$e}
msg-f4d15a87 = 插件 {$name} 不需要更新或无法更新
msg-94b035f7 = 没有需要更新的插件
msg-0766d599 = 发现 {$res} 个插件需要更新
msg-bd5ab99c = 正在更新插件 {$plugin_name}...
msg-e32912b8 = 未找到匹配 '{$query}' 的插件

### astrbot/dashboard/server.py
msg-e88807e2 = 未找到该路由
msg-06151c57 = Missing API key
msg-88dca3cc = Invalid API key
msg-fd267dc8 = Insufficient API key scope
msg-076fb3a3 = 未授权
msg-6f214cc1 = Token 过期
msg-5041dc95 = Token 无效
msg-1241c883 = 检查端口 {$port} 时发生错误: {$e}
msg-7c3ba89d = Initialized random JWT secret for dashboard.
msg-a3adcb66 = WebUI 已被禁用
msg-44832296 = 正在启动 WebUI, 监听地址: {$scheme}://{$host}:{$port}
msg-3eed4a73 = 提示: WebUI 将监听所有网络接口，请注意安全。（可在 data/cmd_config.json 中配置 dashboard.host 以修改 host）
msg-289a2fe8 = 错误：端口 {$port} 已被占用{"\u000A"}占用信息: {"\u000A"}           {$process_info}{"\u000A"}请确保：{"\u000A"}1. 没有其他 AstrBot 实例正在运行{"\u000A"}2. 端口 {$port} 没有被其他程序占用{"\u000A"}3. 如需使用其他端口，请修改配置文件
msg-6d1dfba8 = 端口 {$port} 已被占用
msg-c0161c7c = {$display}
msg-ac4f2855 = dashboard.ssl.enable 为 true 时，必须配置 cert_file 和 key_file。
msg-3e87aaf8 = SSL 证书文件不存在: {$cert_path}
msg-5ccf0a9f = SSL 私钥文件不存在: {$key_path}
msg-5e4aa3eb = SSL CA 证书文件不存在: {$ca_path}
msg-cb049eb2 = AstrBot WebUI 已经被优雅地关闭

### astrbot/dashboard/utils.py
msg-160bd44a = 缺少必要的库以生成 t-SNE 可视化。请安装 matplotlib 和 scikit-learn: {e}
msg-aa3a3dbf = 未找到知识库
msg-0e404ea3 = FAISS 索引不存在: {$index_path}
msg-8d92420c = 索引为空
msg-24c0450e = 提取 {$res} 个向量用于可视化...
msg-632d0acf = 开始 t-SNE 降维...
msg-61f0449f = 生成可视化图表...
msg-4436ad2b = 生成 t-SNE 可视化时出错: {$e}
msg-78b9c276 = {$res}

### astrbot/dashboard/routes/update.py
msg-a3503781 = 迁移失败: {$res}
msg-543d8e4d = 迁移失败: {$e}
msg-251a5f4a = 检查更新失败: {$e} (不影响除项目更新外的正常使用)
msg-aa6bff26 = /api/update/releases: {$res}
msg-c5170c27 = 下载管理面板文件失败: {$e}。
msg-db715c26 = 更新依赖中...
msg-9a00f940 = 更新依赖失败: {$e}
msg-6f96e3ba = /api/update_project: {$res}
msg-3217b509 = 下载管理面板文件失败: {$e}
msg-9cff28cf = /api/update_dashboard: {$res}
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-38e60adf = 缺少参数 package 或不合法。
msg-a1191473 = /api/update_pip: {$res}

### astrbot/dashboard/routes/lang_route.py
msg-0d18aac8 = [LangRoute] lang:{$lang}
msg-bf610e68 = lang 为必填参数。

### astrbot/dashboard/routes/auth.py
msg-ee9cf260 = 为了保证安全，请尽快修改默认密码。
msg-87f936b8 = 用户名或密码错误
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-25562cd3 = 原密码错误
msg-d31087d2 = 新用户名和新密码不能同时为空
msg-b512c27e = 两次输入的新密码不一致
msg-7b947d8b = JWT secret is not set in the cmd_config.

### astrbot/dashboard/routes/backup.py
msg-6920795d = 清理过期的上传会话: {$upload_id}
msg-3e96548d = 清理过期上传会话失败: {$e}
msg-259677a9 = 清理分片目录失败: {$e}
msg-d7263882 = 读取备份 manifest 失败: {$e}
msg-40f76598 = 跳过无效备份文件: {$filename}
msg-18a49bfc = 获取备份列表失败: {$e}
msg-78b9c276 = {$res}
msg-6e08b5a5 = 创建备份失败: {$e}
msg-9cce1032 = 后台导出任务 {$task_id} 失败: {$e}
msg-55927ac1 = 缺少备份文件
msg-374cab8a = 请上传 ZIP 格式的备份文件
msg-d53d6730 = 上传的备份文件已保存: {$unique_filename} (原始名称: {$res})
msg-98e64c7f = 上传备份文件失败: {$e}
msg-49c3b432 = 缺少 filename 参数
msg-df33d307 = 无效的文件大小
msg-162ad779 = 初始化分片上传: upload_id={$upload_id}, filename={$unique_filename}, total_chunks={$total_chunks}
msg-de676924 = 初始化分片上传失败: {$e}
msg-eecf877c = 缺少必要参数
msg-f175c633 = 无效的分片索引
msg-ad865497 = 缺少分片数据
msg-947c2d56 = 上传会话不存在或已过期
msg-f3a464a5 = 分片索引超出范围
msg-7060da1d = 接收分片: upload_id={$upload_id}, chunk={$res}/{$total_chunks}
msg-06c107c1 = 上传分片失败: {$e}
msg-f040b260 = 已标记备份为上传来源: {$zip_path}
msg-559c10a8 = 标记备份来源失败: {$e}
msg-d1d752ef = 缺少 upload_id 参数
msg-390ed49a = 分片不完整，缺少: {$res}...
msg-8029086a = 分片上传完成: {$filename}, size={$file_size}, chunks={$total}
msg-4905dde5 = 完成分片上传失败: {$e}
msg-b63394b1 = 取消分片上传: {$upload_id}
msg-2b39da46 = 取消上传失败: {$e}
msg-f12b1f7a = 无效的文件名
msg-44bb3b89 = 备份文件不存在: {$filename}
msg-b005980b = 预检查备份文件失败: {$e}
msg-65b7ede1 = 请先确认导入。导入将会清空并覆盖现有数据，此操作不可撤销。
msg-b152e4bf = 导入备份失败: {$e}
msg-5e7f1683 = 后台导入任务 {$task_id} 失败: {$e}
msg-6906aa65 = 缺少参数 task_id
msg-5ea3d72c = 找不到该任务
msg-f0901aef = 获取任务进度失败: {$e}
msg-8d23792b = 缺少参数 filename
msg-4188ede6 = 缺少参数 token
msg-0c708312 = 服务器配置错误
msg-cc228d62 = Token 已过期，请刷新页面后重试
msg-5041dc95 = Token 无效
msg-96283fc5 = 备份文件不存在
msg-00aacbf8 = 下载备份失败: {$e}
msg-3ea8e256 = 删除备份失败: {$e}
msg-e4a57714 = 缺少参数 new_name
msg-436724bb = 新文件名无效
msg-9f9d8558 = 文件名 '{$new_filename}' 已存在
msg-a5fda312 = 备份文件重命名: {$filename} -> {$new_filename}
msg-e7c82339 = 重命名备份失败: {$e}

### astrbot/dashboard/routes/command.py
msg-1d47363b = handler_full_name 与 enabled 均为必填。
msg-35374718 = handler_full_name 与 new_name 均为必填。
msg-f879f2f4 = handler_full_name 与 permission 均为必填。

### astrbot/dashboard/routes/subagent.py
msg-78b9c276 = {$res}
msg-eda47201 = 获取 subagent 配置失败: {$e}
msg-3e5b1fe0 = 配置必须为 JSON 对象
msg-9f285dd3 = 保存 subagent 配置失败: {$e}
msg-665f4751 = 获取可用工具失败: {$e}

### astrbot/dashboard/routes/config.py
msg-680e7347 = 配置项 {$path}{$key} 没有类型定义, 跳过校验
msg-ef2e5902 = Saving config, is_core={$is_core}
msg-78b9c276 = {$res}
msg-acef166d = 验证配置时出现异常: {$e}
msg-42f62db0 = 格式校验未通过: {$errors}
msg-3e668849 = 缺少配置数据
msg-196b9b25 = 缺少 provider_source_id
msg-dbbbc375 = 未找到对应的 provider source
msg-a77f69f4 = 缺少 original_id
msg-96f154c4 = 缺少或错误的配置数据
msg-c80b2c0f = Provider source ID '{$res}' exists already, please try another ID.
msg-537b700b = 缺少或错误的路由表数据
msg-b5079e61 = 更新路由表失败: {$e}
msg-cf97d400 = 缺少 UMO 或配置文件 ID
msg-2a05bc8d = 缺少 UMO
msg-7098aa3f = 删除路由表项失败: {$e}
msg-902aedc3 = 缺少配置文件 ID
msg-b9026977 = abconf_id cannot be None
msg-acf0664a = 删除失败
msg-59c93c1a = 删除配置文件失败: {$e}
msg-930442e2 = 更新失败
msg-7375d4dc = 更新配置文件失败: {$e}
msg-53a8fdb2 = Attempting to check provider: {$res} (ID: {$res_2}, Type: {$res_3}, Model: {$res_4})
msg-8b0a48ee = Provider {$res} (ID: {$res_2}) is available.
msg-7c7180a7 = Provider {$res} (ID: {$res_2}) is unavailable. Error: {$error_message}
msg-1298c229 = Traceback for {$res}:{"\u000A"}{$res_2}
msg-d7f9a42f = {$message}
msg-cd303a28 = API call: /config/provider/check_one id={$provider_id}
msg-55b8107a = Provider with id '{$provider_id}' not found in provider_manager.
msg-d1a98a9b = Provider with id '{$provider_id}' not found
msg-cb9c402c = 缺少参数 provider_type
msg-e092d4ee = 缺少参数 provider_id
msg-1ff28fed = 未找到 ID 为 {$provider_id} 的提供商
msg-92347c35 = 提供商 {$provider_id} 类型不支持获取模型列表
msg-d0845a10 = 缺少参数 provider_config
msg-5657fea4 = provider_config 缺少 type 字段
msg-09ed9dc7 = 提供商适配器加载失败，请检查提供商类型配置或查看服务端日志
msg-1cce1cd4 = 未找到适用于 {$provider_type} 的提供商适配器
msg-8361e44d = 无法找到 {$provider_type} 的类
msg-4325087c = 提供商不是 EmbeddingProvider 类型
msg-a9873ea4 = 检测到 {$res} 的嵌入向量维度为 {$dim}
msg-d170e384 = 获取嵌入维度失败: {$e}
msg-abfeda72 = 缺少参数 source_id
msg-0384f4c9 = 未找到 ID 为 {$provider_source_id} 的 provider_source
msg-aec35bdb = provider_source 缺少 type 字段
msg-cbb9d637 = 动态导入提供商适配器失败: {$e}
msg-468f64b3 = 提供商 {$provider_type} 不支持获取模型列表
msg-cb07fc1c = 获取到 provider_source {$provider_source_id} 的模型列表: {$models}
msg-d2f6e16d = 获取模型列表失败: {$e}
msg-25ea8a96 = Unsupported scope: {$scope}
msg-23c8933f = Missing name or key parameter
msg-536e77ae = Plugin {$name} not found or has no config
msg-1b6bc453 = Config item not found or not file type
msg-fc0a457e = No files uploaded
msg-31c718d7 = Invalid name parameter
msg-e1edc16e = Missing name parameter
msg-8e634b35 = Invalid path parameter
msg-0b52a254 = Plugin {$name} not found
msg-bff0e837 = 参数错误
msg-2f29d263 = 机器人名称不允许修改
msg-1478800f = 未找到对应平台
msg-ca6133f7 = 缺少参数 id
msg-1199c1f9 = Using cached logo token for platform {$res}
msg-889a7de5 = Platform class not found for {$res}
msg-317f359c = Logo token registered for platform {$res}
msg-323ec1e2 = Platform {$res} logo file not found: {$logo_file_path}
msg-bc6d0bcf = Failed to import required modules for platform {$res}: {$e}
msg-b02b538d = File system error for platform {$res} logo: {$e}
msg-31123607 = Unexpected error registering logo for platform {$res}: {$e}
msg-af06ccab = 配置文件 {$conf_id} 不存在
msg-082a5585 = 插件 {$plugin_name} 不存在
msg-ca334960 = 插件 {$plugin_name} 没有注册配置

### astrbot/dashboard/routes/knowledge_base.py
msg-ce669289 = 上传文档 {$res} 失败: {$e}
msg-87e99c2d = 后台上传任务 {$task_id} 失败: {$e}
msg-78b9c276 = {$res}
msg-d5355233 = 导入文档 {$file_name} 失败: {$e}
msg-5e7f1683 = 后台导入任务 {$task_id} 失败: {$e}
msg-e1949850 = 获取知识库列表失败: {$e}
msg-299af36d = 知识库名称不能为空
msg-faf380ec = 缺少参数 embedding_provider_id
msg-9015b689 = 嵌入模型不存在或类型错误({$res})
msg-a63b3aa9 = 嵌入向量维度不匹配，实际是 {$res}，然而配置是 {$res_2}
msg-9b281e88 = 测试嵌入模型失败: {$e}
msg-d3fb6072 = 重排序模型不存在
msg-fbec0dfd = 重排序模型返回结果异常
msg-872feec8 = 测试重排序模型失败: {$e}，请检查平台日志输出。
msg-a4ac0b9e = 创建知识库失败: {$e}
msg-c8d487e9 = 缺少参数 kb_id
msg-978b3c73 = 知识库不存在
msg-2137a3e6 = 获取知识库详情失败: {$e}
msg-e7cf9cfd = 至少需要提供一个更新字段
msg-d3d82c22 = 更新知识库失败: {$e}
msg-5d5d4090 = 删除知识库失败: {$e}
msg-787a5dea = 获取知识库统计失败: {$e}
msg-97a2d918 = 获取文档列表失败: {$e}
msg-b170e0fa = Content-Type 须为 multipart/form-data
msg-5afbfa8e = 缺少文件
msg-6636fd31 = 最多只能上传10个文件
msg-975f06d7 = 上传文档失败: {$e}
msg-35bacf60 = 缺少参数 documents 或格式错误
msg-6cc1edcd = 文档格式错误，必须包含 file_name 和 chunks
msg-376d7d5f = chunks 必须是列表
msg-e7e2f311 = chunks 必须是非空字符串列表
msg-42315b8d = 导入文档失败: {$e}
msg-6906aa65 = 缺少参数 task_id
msg-5ea3d72c = 找不到该任务
msg-194def99 = 获取上传进度失败: {$e}
msg-df6ec98e = 缺少参数 doc_id
msg-7c3cfe22 = 文档不存在
msg-b54ab822 = 获取文档详情失败: {$e}
msg-0ef7f633 = 删除文档失败: {$e}
msg-2fe40cbd = 缺少参数 chunk_id
msg-fc13d42a = 删除文本块失败: {$e}
msg-4ef8315b = 获取块列表失败: {$e}
msg-b70a1816 = 缺少参数 query
msg-82ee646e = 缺少参数 kb_names 或格式错误
msg-07a61a9a = 生成 t-SNE 可视化失败: {$e}
msg-20a3b3f7 = 检索失败: {$e}
msg-1b76f5ab = 缺少参数 url
msg-5dc86dc6 = 从URL上传文档失败: {$e}
msg-890b3dee = 后台上传URL任务 {$task_id} 失败: {$e}

### astrbot/dashboard/routes/skills.py
msg-78b9c276 = {$res}
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-52430f2b = Missing file
msg-2ad598f3 = Only .zip files are supported
msg-a11f2e1c = Failed to remove temp skill file: {$temp_path}
msg-67367a6d = Missing skill name

### astrbot/dashboard/routes/live_chat.py
msg-40f242d5 = [Live Chat] {$res} 开始说话 stamp={$stamp}
msg-a168d76d = [Live Chat] stamp 不匹配或未在说话状态: {$stamp} vs {$res}
msg-e01b2fea = [Live Chat] 没有音频帧数据
msg-33856925 = [Live Chat] 音频文件已保存: {$audio_path}, 大小: {$res} bytes
msg-9e9b7e59 = [Live Chat] 组装 WAV 文件失败: {$e}
msg-21430f56 = [Live Chat] 已删除临时文件: {$res}
msg-6b4f88bc = [Live Chat] 删除临时文件失败: {$e}
msg-0849d043 = [Live Chat] WebSocket 连接建立: {$username}
msg-5477338a = [Live Chat] WebSocket 错误: {$e}
msg-fdbfdba8 = [Live Chat] WebSocket 连接关闭: {$username}
msg-7be90ac0 = [Live Chat] start_speaking 缺少 stamp
msg-8215062a = [Live Chat] 解码音频数据失败: {$e}
msg-438980ea = [Live Chat] end_speaking 缺少 stamp
msg-b35a375c = [Live Chat] 用户打断: {$res}
msg-2c3e7bbc = [Live Chat] STT Provider 未配置
msg-0582c8ba = [Live Chat] STT 识别结果为空
msg-57c2b539 = [Live Chat] STT 结果: {$user_text}
msg-6b7628c6 = [Live Chat] 检测到用户打断
msg-2cab2269 = [Live Chat] 消息 ID 不匹配: {$result_message_id} != {$message_id}
msg-74c2470e = [Live Chat] 解析 AgentStats 失败: {$e}
msg-4738a2b3 = [Live Chat] 解析 TTSStats 失败: {$e}
msg-944d5022 = [Live Chat] 开始播放音频流
msg-009104d8 = [Live Chat] Bot 回复完成: {$bot_text}
msg-0c4c3051 = [Live Chat] 处理音频失败: {$e}
msg-140caa36 = [Live Chat] 保存打断消息: {$interrupted_text}
msg-869f51ea = [Live Chat] 用户消息: {$user_text} (session: {$res}, ts: {$timestamp})
msg-d26dee52 = [Live Chat] Bot 消息（打断）: {$interrupted_text} (session: {$res}, ts: {$timestamp})
msg-1377f378 = [Live Chat] 记录消息失败: {$e}

### astrbot/dashboard/routes/log.py
msg-5bf500c1 = Log SSE 补发历史错误: {$e}
msg-e4368397 = Log SSE 连接错误: {$e}
msg-547abccb = 获取日志历史失败: {$e}
msg-cb5d4ebb = 获取 Trace 设置失败: {$e}
msg-7564d3b0 = 请求数据为空
msg-d2a1cd76 = 更新 Trace 设置失败: {$e}

### astrbot/dashboard/routes/conversation.py
msg-62392611 = 数据库查询出错: {$e}{"\u000A"}{$res}
msg-b21b052b = 数据库查询出错: {$e}
msg-10f72727 = {$error_msg}
msg-036e6190 = 获取对话列表失败: {$e}
msg-a16ba4b4 = 缺少必要参数: user_id 和 cid
msg-9a1fcec9 = 对话不存在
msg-73a8a217 = 获取对话详情失败: {$e}{"\u000A"}{$res}
msg-976cd580 = 获取对话详情失败: {$e}
msg-c193b9c4 = 更新对话信息失败: {$e}{"\u000A"}{$res}
msg-9f96c4ee = 更新对话信息失败: {$e}
msg-e1cb0788 = 批量删除时conversations参数不能为空
msg-38e3c4ba = 删除对话失败: {$e}{"\u000A"}{$res}
msg-ebf0371a = 删除对话失败: {$e}
msg-af54ee29 = 缺少必要参数: history
msg-b72552c8 = history 必须是有效的 JSON 字符串或数组
msg-fdf757f3 = 更新对话历史失败: {$e}{"\u000A"}{$res}
msg-33762429 = 更新对话历史失败: {$e}
msg-498f11f8 = 导出列表不能为空
msg-98aa3644 = 导出对话失败: user_id={$user_id}, cid={$cid}, error={$e}
msg-ed77aa37 = 没有成功导出任何对话
msg-f07b18ee = 批量导出对话失败: {$e}{"\u000A"}{$res}
msg-85dc73fa = 批量导出对话失败: {$e}

### astrbot/dashboard/routes/cron.py
msg-fb5b419b = Cron manager not initialized
msg-78b9c276 = {$res}
msg-112659e5 = Failed to list jobs: {$e}
msg-8bc87eb5 = Invalid payload
msg-29f616c2 = session is required
msg-ae7c99a4 = run_at is required when run_once=true
msg-4bb8c206 = cron_expression is required when run_once=false
msg-13fbf01e = run_at must be ISO datetime
msg-da14d97a = Failed to create job: {$e}
msg-804b6412 = Job not found
msg-94b2248d = Failed to update job: {$e}
msg-42c0ee7a = Failed to delete job: {$e}

### astrbot/dashboard/routes/tools.py
msg-78b9c276 = {$res}
msg-977490be = 获取 MCP 服务器列表失败: {$e}
msg-50a07403 = 服务器名称不能为空
msg-23d2bca3 = 必须提供有效的服务器配置
msg-31252516 = 服务器 {$name} 已存在
msg-20b8309f = 启用 MCP 服务器 {$name} 超时。
msg-fff3d0c7 = 启用 MCP 服务器 {$name} 失败: {$e}
msg-7f1f7921 = 保存配置失败
msg-a7f06648 = 添加 MCP 服务器失败: {$e}
msg-278dc41b = 服务器 {$old_name} 不存在
msg-f0441f4b = 启用前停用 MCP 服务器时 {$old_name} 超时: {$e}
msg-7c468a83 = 启用前停用 MCP 服务器时 {$old_name} 失败: {$e}
msg-8a4c8128 = 停用 MCP 服务器 {$old_name} 超时。
msg-9ac9b2fc = 停用 MCP 服务器 {$old_name} 失败: {$e}
msg-b988392d = 更新 MCP 服务器失败: {$e}
msg-c81030a7 = 服务器 {$name} 不存在
msg-4cdbd30d = 停用 MCP 服务器 {$name} 超时。
msg-1ed9a96e = 停用 MCP 服务器 {$name} 失败: {$e}
msg-a26f2c6a = 删除 MCP 服务器失败: {$e}
msg-bbc84cc5 = 无效的 MCP 服务器配置
msg-aa0e3d0d = MCP 服务器配置不能为空
msg-d69cbcf2 = 一次只能配置一个 MCP 服务器配置
msg-bd43f610 = 测试 MCP 连接失败: {$e}
msg-057a3970 = 获取工具列表失败: {$e}
msg-29415636 = 缺少必要参数: name 或 action
msg-75d85dc1 = 启用工具失败: {$e}
msg-21a922b8 = 工具 {$tool_name} 不存在或操作失败。
msg-20143f28 = 操作工具失败: {$e}
msg-295ab1fe = 未知: {$provider_name}
msg-fe38e872 = 同步失败: {$e}

### astrbot/dashboard/routes/chatui_project.py
msg-04827ead = Missing key: title
msg-34fccfbb = Missing key: project_id
msg-a7c08aee = Project {$project_id} not found
msg-c52a1454 = Permission denied
msg-dbf41bfc = Missing key: session_id
msg-d922dfa3 = Session {$session_id} not found

### astrbot/dashboard/routes/open_api.py
msg-e41d65d5 = Failed to create chat session %s: %s
msg-fc15cbcd = {$username_err}
msg-bc3b3977 = Invalid username
msg-2cd6e70f = {$ensure_session_err}
msg-53632573 = {$resolve_err}
msg-79b0c7cb = Failed to update chat config route for %s with %s: %s
msg-7c7a9f55 = Failed to update chat config route: {$e}
msg-74bff366 = page and page_size must be integers
msg-1507569c = Message is empty
msg-1389e46a = message must be a string or list
msg-697561eb = message part must be an object
msg-2c4bf283 = reply part missing message_id
msg-60ddb927 = unsupported message part type: {$part_type}
msg-cf310369 = attachment not found: {$attachment_id}
msg-58e0b84a = {$part_type} part missing attachment_id
msg-e565c4b5 = file not found: {$file_path}
msg-c6ec40ff = Message content is empty (reply only is not allowed)
msg-2b00f931 = Missing key: message
msg-a29d9adb = Missing key: umo
msg-4990e908 = Invalid umo: {$e}
msg-45ac857c = Bot not found or not running for platform: {$platform_id}
msg-ec0f0bd2 = Open API send_message failed: {$e}
msg-d04109ab = Failed to send message: {$e}

### astrbot/dashboard/routes/session_management.py
msg-e1949850 = 获取知识库列表失败: {$e}
msg-3cd6eb8c = 获取规则列表失败: {$e}
msg-363174ae = 缺少必要参数: umo
msg-809e51d7 = 缺少必要参数: rule_key
msg-ce203e7e = 不支持的规则键: {$rule_key}
msg-2726ab30 = 更新会话规则失败: {$e}
msg-f021f9fb = 删除会话规则失败: {$e}
msg-6bfa1fe5 = 缺少必要参数: umos
msg-4ce0379e = 参数 umos 必须是数组
msg-979c6e2f = 删除 umo {$umo} 的规则失败: {$e}
msg-77d2761d = 批量删除会话规则失败: {$e}
msg-6619322c = 获取 UMO 列表失败: {$e}
msg-b944697c = 获取会话状态列表失败: {$e}
msg-adba3c3b = 至少需要指定一个要修改的状态
msg-4a8eb7a6 = 请指定分组 ID
msg-67f15ab7 = 分组 '{$group_id}' 不存在
msg-50fbcccb = 没有找到符合条件的会话
msg-59714ede = 更新 {$umo} 服务状态失败: {$e}
msg-31640917 = 批量更新服务状态失败: {$e}
msg-4d83eb92 = 缺少必要参数: provider_type, provider_id
msg-5f333041 = 不支持的 provider_type: {$provider_type}
msg-6fa017d7 = 更新 {$umo} Provider 失败: {$e}
msg-07416020 = 批量更新 Provider 失败: {$e}
msg-94c745e6 = 获取分组列表失败: {$e}
msg-fb7cf353 = 分组名称不能为空
msg-ae3fce8a = 创建分组失败: {$e}
msg-07de5ff3 = 分组 ID 不能为空
msg-35b8a74f = 更新分组失败: {$e}
msg-3d41a6fd = 删除分组失败: {$e}

### astrbot/dashboard/routes/persona.py
msg-4a12aead = 获取人格列表失败: {$e}{"\u000A"}{$res}
msg-c168407f = 获取人格列表失败: {$e}
msg-63c6f414 = 缺少必要参数: persona_id
msg-ce7da6f3 = 人格不存在
msg-9c07774d = 获取人格详情失败: {$e}{"\u000A"}{$res}
msg-ee3b44ad = 获取人格详情失败: {$e}
msg-ad455c14 = 人格ID不能为空
msg-43037094 = 系统提示词不能为空
msg-ec9dda44 = 预设对话数量必须为偶数（用户和助手轮流对话）
msg-26b214d5 = 创建人格失败: {$e}{"\u000A"}{$res}
msg-8913dfe6 = 创建人格失败: {$e}
msg-3d94d18d = 更新人格失败: {$e}{"\u000A"}{$res}
msg-f2cdfbb8 = 更新人格失败: {$e}
msg-51d84afc = 删除人格失败: {$e}{"\u000A"}{$res}
msg-8314a263 = 删除人格失败: {$e}
msg-b8ecb8f9 = 移动人格失败: {$e}{"\u000A"}{$res}
msg-ab0420e3 = 移动人格失败: {$e}
msg-e5604a24 = 获取文件夹列表失败: {$e}{"\u000A"}{$res}
msg-4d7c7f4a = 获取文件夹列表失败: {$e}
msg-cf0ee4aa = 获取文件夹树失败: {$e}{"\u000A"}{$res}
msg-bb515af0 = 获取文件夹树失败: {$e}
msg-c92b4863 = 缺少必要参数: folder_id
msg-77cdd6fa = 文件夹不存在
msg-2d34652f = 获取文件夹详情失败: {$e}{"\u000A"}{$res}
msg-650ef096 = 获取文件夹详情失败: {$e}
msg-27c413df = 文件夹名称不能为空
msg-b5866931 = 创建文件夹失败: {$e}{"\u000A"}{$res}
msg-5e57f3b5 = 创建文件夹失败: {$e}
msg-9bd8f820 = 更新文件夹失败: {$e}{"\u000A"}{$res}
msg-1eada044 = 更新文件夹失败: {$e}
msg-9cef0256 = 删除文件夹失败: {$e}{"\u000A"}{$res}
msg-22020727 = 删除文件夹失败: {$e}
msg-7a69fe08 = items 不能为空
msg-e71ba5c2 = 每个 item 必须包含 id, type, sort_order 字段
msg-dfeb8320 = type 字段必须是 'persona' 或 'folder'
msg-aec43ed3 = 更新排序失败: {$e}{"\u000A"}{$res}
msg-75ec4427 = 更新排序失败: {$e}

### astrbot/dashboard/routes/platform.py
msg-bcc64513 = 未找到 webhook_uuid 为 {$webhook_uuid} 的平台
msg-1478800f = 未找到对应平台
msg-378cb077 = 平台 {$res} 未实现 webhook_callback 方法
msg-2d797305 = 平台未支持统一 Webhook 模式
msg-83f8dedf = 处理 webhook 回调时发生错误: {$e}
msg-af91bc78 = 处理回调失败
msg-136a952f = 获取平台统计信息失败: {$e}
msg-60bb0722 = 获取统计信息失败: {$e}

### astrbot/dashboard/routes/api_key.py
msg-8e0249fa = At least one valid scope is required
msg-1b79360d = Invalid scopes
msg-d6621696 = expires_in_days must be an integer
msg-33605d95 = expires_in_days must be greater than 0
msg-209030fe = Missing key: key_id
msg-24513a81 = API key not found

### astrbot/dashboard/routes/file.py
msg-78b9c276 = {$res}

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
msg-2c3fdeb9 = Message are both empty
msg-9bc95e22 = session_id is empty
msg-344a401b = [WebChat] 用户 {$username} 断开聊天长连接。
msg-6b54abec = WebChat stream error: {$e}
msg-53509ecb = webchat stream message_id mismatch
msg-1211e857 = [WebChat] 用户 {$username} 断开聊天长连接。 {$e}
msg-be34e848 = Failed to extract web search refs: {$e}
msg-80bbd0ff = WebChat stream unexpected error: {$e}
msg-dbf41bfc = Missing key: session_id
msg-d922dfa3 = Session {$session_id} not found
msg-c52a1454 = Permission denied
msg-9d7a8094 = Failed to delete UMO route %s during session cleanup: %s
msg-44c45099 = Failed to delete attachment file {$res}: {$e}
msg-f033d8ea = Failed to get attachments: {$e}
msg-e6f655bd = Failed to delete attachments: {$e}
msg-a6ef3b67 = Missing key: display_name

### astrbot/dashboard/routes/t2i.py
msg-76cc0933 = Error in get_active_template
msg-5350f35b = Template not found
msg-d7b101c5 = Name and content are required.
msg-e910b6f3 = Template with this name already exists.
msg-18cfb637 = Content is required.
msg-2480cf2f = Template not found.
msg-9fe026f1 = 模板名称(name)不能为空。
msg-eeefe1dc = 模板 '{$name}' 不存在，无法应用。
msg-0048e060 = Error in set_active_template
msg-8fde62dd = Error in reset_default_template

### astrbot/dashboard/routes/stat.py
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-78b9c276 = {$res}
msg-0e5bb0b1 = proxy_url is required
msg-f0e0983e = Failed. Status code: {$res}
msg-68e65093 = Error: {$e}
msg-b5979fe8 = version parameter is required
msg-b88a1887 = Invalid version format
msg-8cb9bb6b = Path traversal attempt detected: {$version} -> {$changelog_path}
msg-7616304c = Changelog for version {$version} not found

### astrbot/dashboard/routes/plugin.py
msg-1198c327 = You are not permitted to do this operation in demo mode
msg-adce8d2f = 缺少插件目录名
msg-2f1b67fd = 重载失败: {$err}
msg-71f9ea23 = /api/plugin/reload-failed: {$res}
msg-27286c23 = /api/plugin/reload: {$res}
msg-b33c0d61 = 缓存MD5匹配，使用缓存的插件市场数据
msg-64b4a44c = 远程插件市场数据为空: {$url}
msg-fdbffdca = 成功获取远程插件市场数据，包含 {$res} 个插件
msg-48c42bf8 = 请求 {$url} 失败，状态码：{$res}
msg-6ac25100 = 请求 {$url} 失败，错误：{$e}
msg-7e536821 = 远程插件市场数据获取失败，使用缓存数据
msg-d4b4c53a = 获取插件列表失败，且没有可用的缓存数据
msg-37f59b88 = 加载缓存MD5失败: {$e}
msg-8048aa4c = 获取远程MD5失败: {$e}
msg-593eacfd = 缓存文件中没有MD5信息
msg-dedcd957 = 无法获取远程MD5，将使用缓存
msg-21d7e754 = 插件数据MD5: 本地={$cached_md5}, 远程={$remote_md5}, 有效={$is_valid}
msg-0faf4275 = 检查缓存有效性失败: {$e}
msg-e26aa0a5 = 加载缓存文件: {$cache_file}, 缓存时间: {$res}
msg-23d627a1 = 加载插件市场缓存失败: {$e}
msg-22d12569 = 插件市场数据已缓存到: {$cache_file}, MD5: {$md5}
msg-478c99a9 = 保存插件市场缓存失败: {$e}
msg-3838d540 = 获取插件 Logo 失败: {$e}
msg-da442310 = 正在安装插件 {$repo_url}
msg-e0abd541 = 安装插件 {$repo_url} 成功。
msg-78b9c276 = {$res}
msg-acfcd91e = 正在安装用户上传的插件 {$res}
msg-48e05870 = 安装插件 {$res} 成功
msg-8af56756 = 正在卸载插件 {$plugin_name}
msg-6d1235b6 = 卸载插件 {$plugin_name} 成功
msg-7055316c = 正在更新插件 {$plugin_name}
msg-d258c060 = 更新插件 {$plugin_name} 成功。
msg-398370d5 = /api/plugin/update: {$res}
msg-2d225636 = 插件列表不能为空
msg-32632e67 = 批量更新插件 {$name}
msg-08dd341c = /api/plugin/update-all: 更新插件 {$name} 失败: {$res}
msg-cb230226 = 停用插件 {$plugin_name} 。
msg-abc710cd = /api/plugin/off: {$res}
msg-06e2a068 = 启用插件 {$plugin_name} 。
msg-82c412e7 = /api/plugin/on: {$res}
msg-77e5d67e = 正在获取插件 {$plugin_name} 的README文件内容
msg-baed1b72 = 插件名称为空
msg-773cca0a = 插件名称不能为空
msg-082a5585 = 插件 {$plugin_name} 不存在
msg-ba106e58 = 插件 {$plugin_name} 目录不存在
msg-e38e4370 = 无法找到插件目录: {$plugin_dir}
msg-df027f16 = 无法找到插件 {$plugin_name} 的目录
msg-5f304f4b = 插件 {$plugin_name} 没有README文件
msg-a3ed8739 = /api/plugin/readme: {$res}
msg-2f9e2c11 = 读取README文件失败: {$e}
msg-dcbd593f = 正在获取插件 {$plugin_name} 的更新日志
msg-ea5482da = /api/plugin/changelog: {$res}
msg-8e27362e = 读取更新日志失败: {$e}
msg-0842bf8b = 插件 {$plugin_name} 没有更新日志文件
msg-8e36313d = sources fields must be a list
msg-643e51e7 = /api/plugin/source/save: {$res}

### astrbot/builtin_stars/session_controller/main.py
msg-b48bf3fe = LLM response failed: {$e}

### astrbot/builtin_stars/builtin_commands/commands/setunset.py
msg-8b56b437 = 会话 {$uid} 变量 {$key} 存储成功。使用 /unset 移除。
msg-dfd31d9d = 没有那个变量名。格式 /unset 变量名。
msg-bf181241 = 会话 {$uid} 变量 {$key} 移除成功。

### astrbot/builtin_stars/builtin_commands/commands/provider.py
msg-b435fcdc = Provider reachability check failed: id=%s type=%s code=%s reason=%s
msg-f4cfd3ab = 正在进行提供商可达性测试，请稍候...
msg-ed8dcc22 = {$ret}
msg-f3d8988e = 请输入序号。
msg-284759bb = 无效的提供商序号。
msg-092d9956 = 成功切换到 {$id_}。
msg-bf9eb668 = 无效的参数。
msg-4cdd042d = 未找到任何 LLM 提供商。请先配置。
msg-cb218e86 = 模型序号错误。
msg-1756f199 = 切换模型成功。当前提供商: [{$res}] 当前模型: [{$res_2}]
msg-4d4f587f = 切换模型到 {$res}。
msg-584ca956 = Key 序号错误。
msg-f52481b8 = 切换 Key 未知错误: {$e}
msg-7a156524 = 切换 Key 成功。

### astrbot/builtin_stars/builtin_commands/commands/conversation.py
msg-63fe9607 = 在{$res}场景下，reset命令需要管理员权限，您 (ID {$res_2}) 不是管理员，无法执行此操作。
msg-6f4bbe27 = 重置对话成功。
msg-4cdd042d = 未找到任何 LLM 提供商。请先配置。
msg-69ed45be = 当前未处于对话状态，请 /switch 切换或者 /new 创建。
msg-ed8dcc22 = {$ret}
msg-772ec1fa = 已请求停止 {$stopped_count} 个运行中的任务。
msg-8d42cd8a = 当前会话没有运行中的任务。
msg-efdfbe3e = {$THIRD_PARTY_AGENT_RUNNER_STR} 对话列表功能暂不支持。
msg-492c2c02 = 已创建新对话。
msg-c7dc838d = 切换到新对话: 新对话({$res})。
msg-6da01230 = 群聊 {$session} 已切换到新对话: 新对话({$res})。
msg-f356d65a = 请输入群聊 ID。/groupnew 群聊ID。
msg-7e442185 = 类型错误，请输入数字对话序号。
msg-00dbe29c = 请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话
msg-a848ccf6 = 对话序号错误，请使用 /ls 查看
msg-1ec33cf6 = 切换到对话: {$title}({$res})。
msg-68e5dd6c = 请输入新的对话名称。
msg-c8dd6158 = 重命名对话成功。
msg-1f1fa2f2 = 会话处于群聊，并且未开启独立会话，并且您 (ID {$res}) 不是管理员，因此没有权限删除当前对话。
msg-6a1dc4b7 = 当前未处于对话状态，请 /switch 序号 切换或 /new 创建。

### astrbot/builtin_stars/builtin_commands/commands/tts.py
msg-ef1b2145 = {$status_text}当前会话的文本转语音。但 TTS 功能在配置中未启用，请前往 WebUI 开启。
msg-deee9deb = {$status_text}当前会话的文本转语音。

### astrbot/builtin_stars/builtin_commands/commands/llm.py
msg-72cd5f57 = {$status} LLM 聊天功能。

### astrbot/builtin_stars/builtin_commands/commands/persona.py
msg-4f52d0dd = 当前对话不存在，请先使用 /new 新建一个对话。
msg-e092b97c = [Persona]{"\u000A"}{"\u000A"}- 人格情景列表: `/persona list`{"\u000A"}- 设置人格情景: `/persona 人格`{"\u000A"}- 人格情景详细信息: `/persona view 人格`{"\u000A"}- 取消人格: `/persona unset`{"\u000A"}{"\u000A"}默认人格情景: {$res}{"\u000A"}当前对话 {$curr_cid_title} 的人格情景: {$curr_persona_name}{"\u000A"}{"\u000A"}配置人格情景请前往管理面板-配置页{"\u000A"}
msg-c046b6e4 = {$msg}
msg-99139ef8 = 请输入人格情景名
msg-a44c7ec0 = 当前没有对话，无法取消人格。
msg-a90c75d4 = 取消人格成功。
msg-a712d71a = 当前没有对话，请先开始对话或使用 /new 创建一个对话。
msg-4e4e746d = 设置成功。如果您正在切换到不同的人格，请注意使用 /reset 来清空上下文，防止原人格对话影响现人格。{$force_warn_msg}
msg-ab60a2e7 = 不存在该人格情景。使用 /persona list 查看所有。

### astrbot/builtin_stars/builtin_commands/commands/t2i.py
msg-855d5cf3 = 已关闭文本转图片模式。
msg-64da24f4 = 已开启文本转图片模式。

### astrbot/builtin_stars/builtin_commands/commands/admin.py
msg-ad019976 = 使用方法: /op <id> 授权管理员；/deop <id> 取消管理员。可通过 /sid 获取 ID。
msg-1235330f = 授权成功。
msg-e78847e0 = 使用方法: /deop <id> 取消管理员。可通过 /sid 获取 ID。
msg-012152c1 = 取消授权成功。
msg-5e076026 = 此用户 ID 不在管理员名单内。
msg-7f8eedde = 使用方法: /wl <id> 添加白名单；/dwl <id> 删除白名单。可通过 /sid 获取 ID。
msg-de1b0a87 = 添加白名单成功。
msg-59d6fcbe = 使用方法: /dwl <id> 删除白名单。可通过 /sid 获取 ID。
msg-4638580f = 删除白名单成功。
msg-278fb868 = 此 SID 不在白名单内。
msg-1dee5007 = 正在尝试更新管理面板...
msg-76bea66c = 管理面板更新完成。

### astrbot/builtin_stars/builtin_commands/commands/sid.py
msg-ed8dcc22 = {$ret}

### astrbot/builtin_stars/builtin_commands/commands/plugin.py
msg-9cae24f5 = {$plugin_list_info}
msg-3f3a6087 = 演示模式下无法禁用插件。
msg-90e17cd4 = /plugin off <插件名> 禁用插件。
msg-d29d6d57 = 插件 {$plugin_name} 已禁用。
msg-f90bbe20 = 演示模式下无法启用插件。
msg-b897048f = /plugin on <插件名> 启用插件。
msg-ebfb93bb = 插件 {$plugin_name} 已启用。
msg-9cd74a8d = 演示模式下无法安装插件。
msg-d79ad78d = /plugin get <插件仓库地址> 安装插件
msg-4f293fe1 = 准备从 {$plugin_repo} 安装插件。
msg-d40e7065 = 安装插件成功。
msg-feff82c6 = 安装插件失败: {$e}
msg-5bfe9d3d = /plugin help <插件名> 查看插件信息。
msg-02627a9b = 未找到此插件。
msg-ed8dcc22 = {$ret}

### astrbot/builtin_stars/builtin_commands/commands/help.py
msg-c046b6e4 = {$msg}

### astrbot/builtin_stars/builtin_commands/commands/alter_cmd.py
msg-d7a36c19 = 该指令用于设置指令或指令组的权限。{"\u000A"}格式: /alter_cmd <cmd_name> <admin/member>{"\u000A"}例1: /alter_cmd c1 admin 将 c1 设为管理员指令{"\u000A"}例2: /alter_cmd g1 c1 admin 将 g1 指令组的 c1 子指令设为管理员指令{"\u000A"}/alter_cmd reset config 打开 reset 权限配置
msg-afe0fa58 = {$config_menu}
msg-0c85d498 = 场景编号和权限类型不能为空
msg-4e0afcd1 = 场景编号必须是 1-3 之间的数字
msg-830d6eb8 = 权限类型错误，只能是 admin 或 member
msg-d1180ead = 已将 reset 命令在{$res}场景下的权限设为{$perm_type}
msg-8d9bc364 = 指令类型错误，可选类型有 admin, member
msg-1f2f65e0 = 未找到该指令
msg-cd271581 = 已将「{$cmd_name}」{$cmd_group_str} 的权限级别调整为 {$cmd_type}。

### astrbot/builtin_stars/web_searcher/main.py
msg-7f5fd92b = 检测到旧版 websearch_tavily_key (字符串格式)，自动迁移为列表格式并保存。
msg-bed9def5 = web_searcher - scraping web: {$res} - {$res_2}
msg-8214760c = bing search error: {$e}, try the next one...
msg-8676b5aa = search bing failed
msg-3fb6d6ad = sogo search error: {$e}
msg-fe9b336f = search sogo failed
msg-c991b022 = 错误：Tavily API密钥未在AstrBot中配置。
msg-b4fbb4a9 = Tavily web search failed: {$reason}, status: {$res}
msg-6769aba9 = Error: Tavily web searcher does not return any results.
msg-b4e7334e = 此指令已经被废弃，请在 WebUI 中开启或关闭网页搜索功能。
msg-b1877974 = web_searcher - search_from_search_engine: {$query}
msg-2360df6b = Error processing search result: {$processed_result}
msg-359d0443 = Error: Baidu AI Search API key is not configured in AstrBot.
msg-94351632 = Successfully initialized Baidu AI Search MCP server.
msg-5a7207c1 = web_searcher - search_from_tavily: {$query}
msg-b36134c9 = Error: Tavily API key is not configured in AstrBot.
msg-98ed69f4 = Error: url must be a non-empty string.
msg-51edd9ee = 错误：BoCha API密钥未在AstrBot中配置。
msg-73964067 = BoCha web search failed: {$reason}, status: {$res}
msg-34417720 = web_searcher - search_from_bocha: {$query}
msg-b798883b = Error: BoCha API key is not configured in AstrBot.
msg-22993708 = Cannot get Baidu AI Search MCP tool.
msg-6f8d62a4 = Cannot Initialize Baidu AI Search MCP Server: {$e}

### astrbot/builtin_stars/web_searcher/engines/bing.py
msg-e3b4d1e9 = Bing search failed

### astrbot/builtin_stars/astrbot/main.py
msg-3df554a1 = 聊天增强 err: {$e}
msg-5bdf8f5c = {$e}
msg-bb6ff036 = 未找到任何 LLM 提供商。请先配置。无法主动回复
msg-afa050be = 当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。
msg-9a6a6b2e = 未找到对话，无法主动回复
msg-78b9c276 = {$res}
msg-b177e640 = 主动回复失败: {$e}
msg-24d2f380 = ltm: {$e}

### astrbot/builtin_stars/astrbot/long_term_memory.py
msg-5bdf8f5c = {$e}
msg-8e11fa57 = 没有找到 ID 为 {$image_caption_provider_id} 的提供商
msg-8ebaa397 = 提供商类型错误({$res})，无法获取图片描述
msg-30954f77 = 图片 URL 为空
msg-62de0c3e = 获取图片描述失败: {$e}
msg-d0647999 = ltm | {$res} | {$final_message}
msg-133c1f1d = Recorded AI response: {$res} | {$final_message}

### astrbot/i18n/ftl_translate.py
msg-547c9cc5 = 未检测到环境变量 DEEPSEEK_API_KEY，请先设置。
msg-8654e4be = {"\u000A"}[Error] API 调用失败: {$e}
msg-75f207ed = File not found: {$ftl_path}
msg-dcfbbe82 = No messages found in {$ftl_path}
msg-ccd5a28f = 共 {$res} 条文本，使用 {$max_workers} 个并发线程翻译...
msg-00b24d69 = {"\u000A"}[Error] 翻译失败，保留原文: {$e}
msg-ebcdd595 = {"\u000A"}翻译完成，已保存到 {$ftl_path}
msg-d6c66497 = 错误: 请先设置 DEEPSEEK_API_KEY 环境变量。
msg-09486085 = 例如: export DEEPSEEK_API_KEY='sk-xxxxxx'

### scripts/generate_changelog.py
msg-a79937ef = Warning: openai package not installed. Install it with: pip install openai
msg-090bfd36 = Warning: Failed to call LLM API: {$e}
msg-a3ac9130 = Falling back to simple changelog generation...
msg-6f1011c5 = Latest tag: {$latest_tag}
msg-8c7f64d7 = Error: No tags found in repository
msg-a89fa0eb = No commits found since {$latest_tag}
msg-846ebecf = Found {$res} commits since {$latest_tag}
msg-9ad686af = Warning: Could not parse version from tag {$latest_tag}
msg-f5d43a54 = Generating changelog for {$version}...
msg-e54756e8 = {"\u000A"}✓ Changelog generated: {$changelog_file}
msg-82be6c98 = {"\u000A"}Preview:
msg-321ac5b1 = {$changelog_content}
### astr_agent_run_util.py
agent-max-steps-reached = Agent 已达到最大步数限制 ({$max_step})，强制返回最终响应。
agent-tool-call = 🔨 调用工具: {$tool_name}
agent-tool-call-unknown = 🔨 调用工具...
agent-request-failed = {"\u000A"}{"\u000A"}AstrBot 请求失败。{"\u000A"}错误类型: {$error_type}{"\u000A"}错误信息: {$error_message}{"\u000A"}{"\u000A"}请在平台日志查看和分享错误详情。{"\u000A"}
agent-error-in-hook = on_agent_done 钩子执行错误
live-agent-stream-tts = [Live Agent] 使用流式 TTS（原生支持 get_audio_stream）
live-agent-tts-info = [Live Agent] 使用 TTS（{$provider_type} {"\u000A"}使用 get_audio，将按句子分块生成音频）
live-agent-runtime-error = [Live Agent] 运行时发生错误: {$error}
live-agent-feeder-error = [Live Agent Feeder] 错误: {$error}
live-tts-stream-error = [Live TTS Stream] 错误: {$error}
live-tts-simulated-error = [Live TTS Simulated] 处理文本 '{$text_preview}...' 时出错: {$error}
live-tts-simulated-critical = [Live TTS Simulated] 严重错误: {$error}
tts-stats-send-failed = 发送 TTS 统计信息失败: {$error}
live-agent-feeder-sentence = [Live Agent Feeder] 分句: {$sentence}

### astr_agent_tool_exec.py
background-task-failed = 后台任务 {$task_id} 失败: {$error}
background-task-build-failed = 为后台任务构建主代理失败。
background-task-no-response = 后台任务代理未返回响应
tool-send-message-failed = 工具直接发送消息失败: {$error}，追踪信息: {$traceback}
tool-execution-timeout = 工具 {$tool_name} 执行超时，已超过 {$timeout} 秒。
tool-execution-value-error = 工具执行值错误: {$error}
tool-parameter-mismatch = 工具处理函数参数不匹配，请检查处理函数定义。处理函数参数: {$handler_param_str}
tool-execution-error = 工具执行错误: {$error}。追踪信息: {$traceback}
unknown-method-name = 未知的方法名: {$method_name}
previous-error = 先前错误: {$traceback}

### zip_updator.py
repo-request-failed = 请求 {$url} 失败，状态码: {$status_code}, 内容: {$content}
repo-parse-error = 解析版本信息时发生异常: {$error}
repo-parse-failed = 解析版本信息失败
repo-no-suitable-release = 未找到合适的发布版本
repo-downloading-update = 正在下载更新 {$repo} ...
repo-downloading-branch = 正在从指定分支 {$branch} 下载 {$author}/{$repo}
repo-fetch-releases-failed = 获取 {$author}/{$repo} 的 GitHub Releases 失败: {$error}，将尝试下载默认分支
repo-downloading-default = 正在从默认分支下载 {$author}/{$repo}
repo-using-mirror = 检查到设置了镜像站，将使用镜像站下载 {$author}/{$repo} 仓库源码: {$url}
repo-unzip-complete = 解压文件完成: {$zip_path}
repo-delete-temp = 删除临时更新文件: {$zip_path} 和 {$temp_dir}
repo-delete-failed = 删除更新文件失败，可以手动删除 {$zip_path} 和 {$temp_dir}
repo-invalid-url = 无效的 GitHub URL
repo-request-failed-exception = 请求失败，状态码: {$status_code}
release-info = 版本: {$version} | 发布于: {$published_at}

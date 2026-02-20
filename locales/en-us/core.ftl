### astr_agent_run_util.py
agent-max-steps-reached = Agent reached max steps ({$max_step}), forcing a final response.
agent-tool-call = 🔨 Calling tool: {$tool_name}
agent-tool-call-unknown = 🔨 Calling tool...
agent-request-failed = {"\u000A"}{"\u000A"}AstrBot request failed.{"\u000A"}Error type: {$error_type}{"\u000A"}Error message: {$error_message}{"\u000A"}{"\u000A"}Please check the platform logs for error details.{"\u000A"}
agent-error-in-hook = Error in on_agent_done hook
live-agent-stream-tts = [Live Agent] Using streaming TTS (native get_audio_stream support)
live-agent-tts-info = [Live Agent] Using TTS ({$provider_type} using get_audio, will generate audio sentence by sentence)
live-agent-runtime-error = [Live Agent] Runtime error: {$error}
live-agent-feeder-error = [Live Agent Feeder] Error: {$error}
live-tts-stream-error = [Live TTS Stream] Error: {$error}
live-tts-simulated-error = [Live TTS Simulated] Error processing text '{$text_preview}...': {$error}
live-tts-simulated-critical = [Live TTS Simulated] Critical Error: {$error}
tts-stats-send-failed = Failed to send TTS statistics: {$error}
live-agent-feeder-sentence = [Live Agent Feeder] Sentence: {$sentence}

### astr_agent_tool_exec.py
background-task-failed = Background task {$task_id} failed: {$error}
background-task-build-failed = Failed to build main agent for background task job.
background-task-no-response = background task agent got no response
tool-send-message-failed = Tool failed to send message directly: {$error}, traceback: {$traceback}
tool-execution-timeout = tool {$tool_name} execution timeout after {$timeout} seconds.
tool-execution-value-error = Tool execution ValueError: {$error}
tool-parameter-mismatch = Tool handler parameter mismatch, please check the handler definition. Handler parameters: {$handler_param_str}
tool-execution-error = Tool execution error: {$error}. Traceback: {$traceback}
unknown-method-name = Unknown method name: {$method_name}
previous-error = Previous Error: {$traceback}

### zip_updator.py
repo-request-failed = Request {$url} failed, status code: {$status_code}, content: {$content}
repo-parse-error = An exception occurred while parsing version information: {$error}
repo-parse-failed = Failed to parse version information
repo-no-suitable-release = No suitable release version found
repo-downloading-update = Downloading update {$repo} ...
repo-downloading-branch = Downloading {$author}/{$repo} from specified branch {$branch}
repo-fetch-releases-failed = Failed to fetch {$author}/{$repo} GitHub Releases: {$error}, will try to download default branch
repo-downloading-default = Downloading {$author}/{$repo} from default branch
repo-using-mirror = Mirror detected, will use mirror to download {$author}/{$repo} repository source code: {$url}
repo-unzip-complete = Unzip completed: {$zip_path}
repo-delete-temp = Deleting temporary update files: {$zip_path} and {$temp_dir}
repo-delete-failed = Failed to delete update files, you can manually delete {$zip_path} and {$temp_dir}
repo-invalid-url = Invalid GitHub URL
repo-request-failed-exception = Request failed, status code: {$status_code}
release-info = Version: {$version} | Published at: {$published_at}

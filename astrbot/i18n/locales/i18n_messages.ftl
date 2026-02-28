### main.py

msg-5e25709f = 请使用 Python 3.10 或更高版本运行本项目。
msg-afd0ab81 = 使用指定的 WebUI 目录：{ $webui_dir }
msg-7765f00f = 指定的 WebUI 目录{ $webui_dir }不存在，将使用默认逻辑。
msg-9af20e37 = WebUI 版本已是最新。
msg-9dd5c1d2 = 检测到 WebUI 版本 ({ $v }) 与当前 AstrBot 版本 (v{ $VERSION }) 不匹配。
msg-ec714d4e = 开始下载管理面板文件...高峰期（晚上）可能导致较慢的速度。如多次下载失败，请前往 https://github.com/AstrBotDevs/AstrBot/releases/latest 下载 dist.zip，并将其中的 dist 文件夹解压至 data 目录下。
msg-c5170c27 = 下载管理面板文件失败：{ $e }。
msg-e1592ad1 = 管理面板下载完成。
msg-fe494da6 = { $logo_tmpl }

### astrbot\builtin_stars\astrbot\long_term_memory.py

msg-5bdf8f5c = { $e }
msg-8e11fa57 = 未找到 ID 为{ $image_caption_provider_id }提供商
msg-8ebaa397 = 提供商类型错误({ $res }无法获取图片描述
msg-30954f77 = 图片 URL 为空
msg-62de0c3e = 获取图片描述失败:{ $e }
msg-d0647999 = ltm |{ $res }|{ $final_message }
msg-133c1f1d = 已记录的AI响应：{ $res }|{ $final_message }

### astrbot\builtin_stars\astrbot\main.py

msg-3df554a1 = 聊天增强错误：{ $e }
msg-5bdf8f5c = { $e }
msg-bb6ff036 = 未找到任何 LLM 提供商。请先进行配置。无法主动回复。
msg-afa050be = 当前未处于对话状态，无法主动回复，请确保 平台设置->会话隔离(unique_session) 未开启，并使用 /switch 序号 切换或者 /new 创建一个会话。
msg-9a6a6b2e = 未找到对话，无法主动回复。
msg-78b9c276 = { $res }
msg-b177e640 = 主动回复失败:{ $e }
msg-24d2f380 = 长期记忆：{ $e }

### astrbot\builtin_stars\builtin_commands\commands\admin.py

msg-ad019976 = 使用方法：/op <id> 授予管理员权限；/deop <id> 取消管理员权限。使用 /sid 获取您的 ID。
msg-1235330f = 授权成功。
msg-e78847e0 = 使用方法：/deop <id> 用于取消管理员权限。可通过 /sid 获取 ID。
msg-012152c1 = 取消授权成功。
msg-5e076026 = 此用户 ID 不在管理员名单内。
msg-7f8eedde = 使用方法：/wl <id> 添加白名单；/dwl <id> 删除白名单。可通过 /sid 获取 ID。
msg-de1b0a87 = 白名单添加成功。
msg-59d6fcbe = 使用方法：/dwl <id> 可从白名单中移除。使用 /sid 获取 ID。
msg-4638580f = 白名单删除成功。
msg-278fb868 = 此 SID 不在白名单内。
msg-1dee5007 = 正在尝试更新管理面板...
msg-76bea66c = 管理面板更新完成。

### astrbot\builtin_stars\builtin_commands\commands\alter_cmd.py

msg-d7a36c19 =
    该指令用于设置指令或指令组的权限。  
    格式: /alter_cmd <cmd_name> <admin/member>  
    例1: /alter_cmd c1 admin 将 c1 设为管理员指令  
    例2: /alter_cmd g1 c1 admin 将 g1 指令组中的 c1 子指令设为管理员指令  
    /alter_cmd reset config 打开 reset 权限配置
msg-afe0fa58 = { $config_menu }
msg-0c85d498 = 场景编号和权限类型不能为空。
msg-4e0afcd1 = 场景编号必须是 1 到 3 之间的数字。
msg-830d6eb8 = 权限类型错误，只能是 admin 或 member。
msg-d1180ead = 已将 reset 命令在{ $res }场景下的权限设置{ $perm_type }
msg-8d9bc364 = 指令类型错误，可选类型有 admin, member
msg-1f2f65e0 = 未找到该指令
msg-cd271581 = 已将「{ $cmd_name }」{ $cmd_group_str }权限级别已调整为{ $cmd_type }。

### astrbot\builtin_stars\builtin_commands\commands\conversation.py

msg-63fe9607 = 在{ $res }在此场景下，重置命令需要管理员权限，您（ID{ $res_2 }) 不是管理员，无法执行此操作。
msg-6f4bbe27 = 对话已成功重置。
msg-4cdd042d = 未找到任何 LLM 提供商。请先进行配置。
msg-69ed45be = 当前未处于对话状态，请使用 /switch 切换或 /new 创建。
msg-ed8dcc22 = { $ret }
msg-772ec1fa = 已请求停止{ $stopped_count }一个运行中的任务。
msg-8d42cd8a = 当前会话没有运行中的任务。
msg-efdfbe3e = { $THIRD_PARTY_AGENT_RUNNER_STR }对话列表功能暂不支持。
msg-492c2c02 = 已创建新对话。
msg-c7dc838d = 切换到新对话: 新对话({ $res })。
msg-6da01230 = 群聊{ $session }已切换到新对话: 新对话({ $res })。
msg-f356d65a = 请输入群聊 ID。/groupnew 群聊ID。
msg-7e442185 = 类型错误，请输入数字对话序号。
msg-00dbe29c = 请输入对话序号。/switch 对话序号。/ls 查看对话 /new 新建对话
msg-a848ccf6 = 对话序号错误，请使用 /ls 查看。
msg-1ec33cf6 = 切换到对话:{ $title }({ $res })。
msg-68e5dd6c = 请输入新的对话名称。
msg-c8dd6158 = 对话重命名成功。
msg-1f1fa2f2 = 会话处于群聊状态，且未开启独立会话，同时您（ID{ $res }非管理员，因此无权删除当前对话。
msg-6a1dc4b7 = 当前未处于对话状态，请使用 /switch 序号 切换或 /new 创建。

### astrbot\builtin_stars\builtin_commands\commands\help.py

msg-c046b6e4 = { $msg }

### astrbot\builtin_stars\builtin_commands\commands\llm.py

msg-72cd5f57 = { $status }LLM 聊天功能。

### astrbot\builtin_stars\builtin_commands\commands\persona.py

msg-4f52d0dd = 当前对话不存在，请先使用 /new 新建一个对话。
msg-e092b97c = [角色设定]
    
    - 角色情景列表: `/persona list`
    - 设置角色情景: `/persona 角色`
    - 角色情景详细信息: `/persona view 角色`
    - 取消角色: `/persona unset`
    
    默认角色情景:{ $res }当前对话{ $curr_cid_title }人格情景：{ $curr_persona_name }配置人格情景请前往管理面板-配置页
msg-c046b6e4 = { $msg }
msg-99139ef8 = 请输入人格情景名称
msg-a44c7ec0 = 当前没有进行中的对话，无法取消人格。
msg-a90c75d4 = 人格取消成功。
msg-a712d71a = 当前没有对话，请先开始对话或使用 /new 创建一个对话。
msg-4e4e746d = 设置成功。如果您正在切换到不同的人格，请使用 /reset 来清空上下文，以防原人格的对话影响现人格。{ $force_warn_msg }
msg-ab60a2e7 = 该人格情景不存在。使用 /persona list 查看所有可用情景。

### astrbot\builtin_stars\builtin_commands\commands\plugin.py

msg-9cae24f5 = { $plugin_list_info }
msg-3f3a6087 = 演示模式下无法禁用插件。
msg-90e17cd4 = /plugin off <插件名> 禁用插件。
msg-d29d6d57 = 插件{ $plugin_name }已禁用。
msg-f90bbe20 = 演示模式下无法启用插件。
msg-b897048f = /plugin on <插件名> 启用插件。
msg-ebfb93bb = 插件{ $plugin_name }已启用。
msg-9cd74a8d = 演示模式下无法安装插件。
msg-d79ad78d = /plugin get <插件仓库地址> 安装插件
msg-4f293fe1 = 准备从{ $plugin_repo }安装插件。
msg-d40e7065 = 插件安装成功。
msg-feff82c6 = 安装插件失败:{ $e }
msg-5bfe9d3d = /plugin help <插件名> 查看插件信息。
msg-02627a9b = 未找到此插件。
msg-ed8dcc22 = { $ret }

### astrbot\builtin_stars\builtin_commands\commands\provider.py

msg-7717d729 = 提供方可达性检查失败：id={ $res }类型={ $res_2 }代码={ $err_code }原因={ $err_reason }
msg-f4cfd3ab = 正在测试提供商可达性，请稍候...
msg-ed8dcc22 = { $ret }
msg-f3d8988e = 请输入序号。
msg-284759bb = 无效的提供商序号。
msg-092d9956 = 成功切换到{ $id_ }。
msg-bf9eb668 = 无效的参数。
msg-4cdd042d = 未找到任何 LLM 提供商。请先进行配置。
msg-cb218e86 = 模型序号错误。
msg-1756f199 = 模型切换成功。当前提供商：[{ $res }当前模型:{ $res_2 }]
msg-4d4f587f = 切换模型至{ $res }。
msg-584ca956 = 密钥序号错误。
msg-f52481b8 = 切换密钥时发生未知错误：{ $e }
msg-7a156524 = 密钥切换成功。

### astrbot\builtin_stars\builtin_commands\commands\setunset.py

msg-8b56b437 = Session{ $uid }variable{ $key }存储成功。使用 /unset 移除。
msg-dfd31d9d = 该变量名不存在。格式：/unset 变量名。
msg-bf181241 = Session{ $uid }variable{ $key }移除成功。

### astrbot\builtin_stars\builtin_commands\commands\sid.py

msg-ed8dcc22 = { $ret }

### astrbot\builtin_stars\builtin_commands\commands\t2i.py

msg-855d5cf3 = 文本转图片模式已关闭。
msg-64da24f4 = 文本转图片模式已开启。

### astrbot\builtin_stars\builtin_commands\commands\tts.py

msg-ef1b2145 = { $status_text }当前会话的文本转语音。但 TTS 功能在配置中未启用，请前往 WebUI 开启。
msg-deee9deb = { $status_text }当前会话的文本转语音。

### astrbot\builtin_stars\session_controller\main.py

msg-b48bf3fe = LLM响应失败：{ $e }

### astrbot\builtin_stars\web_searcher\main.py

msg-7f5fd92b = 检测到旧版 websearch_tavily_key（字符串格式），已自动迁移为列表格式并保存。
msg-bed9def5 = web_searcher - 正在抓取网页：{ $res }-{ $res_2 }
msg-8214760c = 必应搜索错误：{ $e }，试试下一个...
msg-8676b5aa = 搜索必应失败
msg-3fb6d6ad = 搜狗搜索错误：{ $e }
msg-fe9b336f = 搜索搜狗失败
msg-c991b022 = 错误：Tavily API密钥未在AstrBot中配置。
msg-b4fbb4a9 = Tavily 网络搜索失败：{ $reason }，状态：{ $res }
msg-6769aba9 = 错误：Tavily 网络搜索器未返回任何结果。
msg-b4e7334e = 此指令已被废弃，请在 WebUI 中开启或关闭网页搜索功能。
msg-b1877974 = 网络搜索器 - 从搜索引擎搜索：{ $query }
msg-2360df6b = 处理搜索结果时出错：{ $processed_result }
msg-359d0443 = 错误：AstrBot 中未配置百度 AI 搜索 API 密钥。
msg-94351632 = 已成功初始化百度AI搜索MCP服务器。
msg-5a7207c1 = 网络搜索器 - 从Tavily搜索：{ $query }
msg-b36134c9 = 错误：AstrBot 中未配置 Tavily API 密钥。
msg-98ed69f4 = 错误：URL 必须为非空字符串。
msg-51edd9ee = 错误：BoCha API密钥未在AstrBot中配置。
msg-73964067 = BoCha网页搜索失败：{ $reason }，状态：{ $res }
msg-34417720 = 网络搜索器 - 从博查搜索：{ $query }
msg-b798883b = 错误：AstrBot 中未配置 BoCha API 密钥。
msg-22993708 = 无法获取百度AI搜索MCP工具。
msg-6f8d62a4 = 无法初始化百度AI搜索MCP服务器：{ $e }

### astrbot\builtin_stars\web_searcher\engines\bing.py

msg-e3b4d1e9 = 必应搜索失败

### astrbot\cli\__main__.py

msg-fe494da6 = { $logo_tmpl }
msg-c8b2ff67 = 欢迎使用 AstrBot 命令行界面！
msg-78b9c276 = { $res }
msg-14dd710d = 未知命令：{ $command_name }

### astrbot\cli\commands\cmd_conf.py

msg-635b8763 = 日志级别必须是 DEBUG、INFO、WARNING、ERROR 或 CRITICAL 之一。
msg-ebc250dc = 端口必须在 1-65535 范围内。
msg-6ec400b6 = 端口必须是数字
msg-0b62b5ce = 用户名不能为空
msg-89b5d3d5 = 密码不能为空
msg-92e7c8ad = 无效的时区:{ $value }请使用有效的IANA时区名称
msg-e470e37d = 回调接口基址必须以 http:// 或 https:// 开头
msg-6b615721 = { $root }不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init。
msg-f74c517c = 配置文件解析失败：{ $e }
msg-d7c58bcc = 配置路径冲突：{ $res }不是字典
msg-e16816cc = 不支持的配置项：{ $key }
msg-e9cce750 = 配置已更新：{ $key }
msg-1ed565aa = 原始值: ********
msg-1bf9569a = 新值: ********
msg-f2a20ab3 = 原值:{ $old_value }
msg-0c104905 = 新值:{ $validated_value }
msg-ea9b4e2c = 未知的配置项：{ $key }
msg-4450e3b1 = 设置配置失败:{ $e }
msg-ba464bee = { $key }：{ $value }
msg-72aab576 = 获取配置失败:{ $e }
msg-c1693d1d = 当前配置:
msg-50be9b74 = { $key }：{ $value }

### astrbot\cli\commands\cmd_init.py

msg-a90a250e = 当前目录：{ $astrbot_root }
msg-4deda62e = 如果你确认这是 Astrbot 根目录，你需要在当前目录下创建一个 .astrbot 文件，以将该目录标记为 AstrBot 的数据目录。
msg-3319bf71 = 已创建{ $dot_astrbot }
msg-7054f44f = { $res }：{ $path }
msg-b19edc8a = 正在初始化AstrBot...
msg-eebc39e3 = 无法获取锁文件，请检查是否有其他实例正在运行。
msg-e16da80f = 初始化失败:{ $e }

### astrbot\cli\commands\cmd_plug.py

msg-cbd8802b = { $base }不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init。
msg-78b9c276 = { $res }
msg-83664fcf = { $val } { $val } { $val } { $val } { $val }
msg-56f3f0bf = { $res } { $res_2 } { $res_3 } { $res_4 } { $desc }
msg-1d802ff2 = 插件{ $name }已存在
msg-a7be9d23 = 版本号必须采用 x.y 或 x.y.z 格式。
msg-4d81299b = 仓库地址必须以 http 开头
msg-93289755 = 正在下载插件模板...
msg-b21682dd = 正在重写插件信息...
msg-bffc8bfa = 插件{ $name }创建成功
msg-08eae1e3 = 未安装任何插件
msg-1a021bf4 = 未找到可安装的插件{ $name }可能不存在或已安装
msg-c120bafd = 插件{ $name }不存在或未安装
msg-63da4867 = 插件{ $name }已卸载
msg-e4925708 = 卸载插件{ $name }失败:{ $e }
msg-f4d15a87 = 插件{ $name }无需更新或无法更新
msg-94b035f7 = 没有需要更新的插件。
msg-0766d599 = 发现{ $res }一个插件需要更新。
msg-bd5ab99c = 正在更新插件{ $plugin_name }...
msg-e32912b8 = 未找到匹配项 '{ $query }' 的插件

### astrbot\cli\commands\cmd_run.py

msg-41ecc632 = { $astrbot_root }不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init。
msg-0ccaca23 = 启用插件自动重载
msg-220914e7 = AstrBot 已关闭...
msg-eebc39e3 = 无法获取锁文件，请检查是否有其他实例正在运行。
msg-85f241d3 = 运行时出现错误：{ $e }：{ $res }

### astrbot\cli\utils\basic.py

msg-f4e0fd7b = 管理面板未安装
msg-2d090cc3 = 正在安装管理面板...
msg-2eeb67e0 = 管理面板安装完成
msg-9c727dca = 管理面板已是最新版本。
msg-11b49913 = 管理面板版本：{ $version }
msg-f0b6145e = 下载管理面板失败:{ $e }
msg-9504d173 = 正在初始化管理面板目录...
msg-699e2509 = 管理面板初始化完成

### astrbot\cli\utils\plugin.py

msg-e327bc14 = 正在从默认分支下载{ $author }/{ $repo }
msg-c804f59f = 获取 release 信息失败:{ $e }，将直接使用提供的 URL
msg-aa398bd5 = master 分支不存在，尝试下载 main 分支
msg-5587d9fb = 读取{ $yaml_path }失败:{ $e }
msg-8dbce791 = 获取在线插件列表失败:{ $e }
msg-6999155d = 插件{ $plugin_name }未安装，无法更新
msg-fa5e129a = 正在从{ $repo_url } { $res }插件{ $plugin_name }...
msg-9ac1f4db = 插件{ $plugin_name } { $res }成功
msg-b9c719ae = { $res }插件{ $plugin_name }时出错:{ $e }

### astrbot\core\astrbot_config_mgr.py

msg-7875e5bd = 配置文件{ $conf_path }用于UUID{ $uuid_ }不存在，跳过。
msg-39c4fd49 = 无法删除默认配置文件
msg-cf7b8991 = 配置文件{ $conf_id }不存在于映射中
msg-2aad13a4 = 已删除配置文件:{ $conf_path }
msg-94c359ef = 删除配置文件{ $conf_path }失败:{ $e }
msg-44f0b770 = 配置文件已成功删除{ $conf_id }
msg-737da44e = 无法更新默认配置文件中的信息。
msg-9d496709 = 配置文件更新成功{ $conf_id }信息

### astrbot\core\astr_agent_run_util.py

msg-6b326889 = 代理已达到最大步数（{ $max_step }强制最终响应。
msg-bb15e9c7 = { $status_msg }
msg-78b9c276 = { $res }
msg-9c246298 = 代理完成钩子中发生错误
msg-34f164d4 = { $err_msg }
msg-6d9553b2 = [在线客服] 使用流式 TTS（原生支持 get_audio_stream）
msg-becf71bf = [在线客服] 使用 TTS（{ $res }使用 get_audio，将按句子分块生成音频）
msg-21723afb = [在线客服] 运行时发生错误：{ $e }
msg-ca1bf0d7 = 发送 TTS 统计信息失败：{ $e }
msg-5ace3d96 = [实时客服信息源] 分句:{ $temp_buffer }
msg-bc1826ea = [实时客服信息推送器] 错误：{ $e }
msg-a92774c9 = [实时TTS流] 错误：{ $e }
msg-d7b3bbae = [实时TTS模拟] 处理文本时出错 '{ $res }...'{ $e }
msg-035bca5f = [实时TTS模拟] 严重错误：{ $e }

### astrbot\core\astr_agent_tool_exec.py

msg-e5f2fb34 = 后台任务{ $task_id }失败：{ $e }
msg-c54b2335 = 后台交接{ $task_id }({ $res }) 失败：{ $e }
msg-8c2fe51d = 构建后台任务主代理失败{ $tool_name }.
msg-c6d4e4a6 = 后台任务代理未收到响应
msg-0b3711f1 = 本地函数工具必须提供事件。
msg-8c19e27a = 工具必须具有有效的处理程序或重写'run'方法。
msg-24053a5f = 工具直接发送消息失败：{ $e }
msg-f940b51e = 工具{ $res }执行超时{ $res_2 }秒。
msg-7e22fc8e = 未知的方法名：{ $method_name }
msg-c285315c = 工具执行值错误：{ $e }
msg-41366b74 = 工具处理器参数不匹配，请检查处理器定义。处理器参数：{ $handler_param_str }
msg-e8cadf8e = 工具执行错误：{ $e }. 回溯：{ $trace_ }
msg-d7b4aa84 = 先前错误：{ $trace_ }

### astrbot\core\astr_main_agent.py

msg-3d3f3df8 = 未找到指定的提供商:{ $sel_provider }。
msg-23d02c04 = 选择的提供商类型无效。{ $res })，跳过 LLM 请求处理。
msg-97d98ea8 = 选择提供程序时发生错误：{ $exc }
msg-507853eb = 无法创建新的对话。
msg-24bd9273 = 检索知识库时发生错误：{ $exc }
msg-36dc1409 = Moonshot AI 文件提取 API 密钥未设置
msg-b41a7a58 = 不支持的文件提取提供程序：{ $res }
msg-f2ea29f4 = 无法获取图片描述，因为提供者 `{ $provider_id }` 不存在。
msg-91a70615 = 无法获取图片描述，因为提供者 `{ $provider_id }` 不是一个有效的 Provider。{ $res }.
msg-6097bd34 = 正在使用提供商处理图像描述：{ $provider_id }
msg-7f5e3367 = 处理图片描述失败：{ $exc }
msg-719d5e4d = 引用中未找到图像描述提供程序。
msg-633f992f = 处理引用图片失败：{ $exc }
msg-1891edf8 = 组名显示已启用但群组对象为空。群组ID：{ $res }
msg-7d93dc13 = 时区设置错误：{ $exc }, 使用本地时区
msg-09eb6259 = 提供商{ $provider }不支持图像，使用占位符。
msg-f57d475e = 提供商{ $provider }不支持工具使用，正在清除工具。
msg-2e3df24a = sanitize_context_by_modalities 已应用：removed_image_blocks={ $removed_image_blocks }已移除工具消息={ $removed_tool_messages }已移除工具调用={ $removed_tool_calls }
msg-5becd564 = 为会话生成的聊天界面标题{ $chatui_session_id }：{ $title }
msg-d8cff4db = 不支持的 llm_safety_mode 策略：{ $res }.
msg-7ea2c5d3 = 船坞沙箱配置不完整。
msg-8271b0d7 = 未找到指定的上下文压缩模型。{ $res }，将跳过压缩。
msg-bf48c713 = 指定的上下文压缩模型{ $res }非对话模型，将跳过压缩。
msg-c6c9d989 = fallback_chat_models 设置不是列表，跳过备用提供程序。
msg-c48173dd = 备用聊天服务提供商{ $fallback_id }` 未找到，跳过。
msg-88fd7233 = 备用聊天服务提供商{ $fallback_id }` 是无效类型：{ $res }，跳过。
msg-ee979399 = 未找到任何对话模型（提供商），跳过 LLM 请求处理。
msg-d003c63c = 跳过带引号的备用图像，因为 limit={ $res }对于 umo={ $res_2 }
msg-65bb0f30 = 为umo=截断引用的回退图像{ $res }，reply_id={ $res_2 }从{ $res_3 }到{ $remaining_limit }
msg-617040f3 = 无法为 umo= 解析回退引用图像{ $res }，reply_id={ $res_2 }：{ $exc }
msg-d4c7199d = 应用文件提取时发生错误：{ $exc }

### astrbot\core\astr_main_agent_resources.py

msg-509829d8 = 从沙箱下载的文件：{ $path }->{ $local_path }
msg-b462b60d = 无法从沙箱中检查/下载文件：{ $e }
msg-0b3144f1 = [知识库] 会话{ $umo }已配置为不使用知识库
msg-97e13f98 = [知识库] 知识库不存在或未加载：{ $kb_id }
msg-312d09c7 = [知识库] 会话{ $umo }以下配置的知识库无效：{ $invalid_kb_ids }
msg-42b0e9f8 = [知识库] 使用会话级配置，知识库数量：{ $res }
msg-08167007 = [知识库] 使用全局配置，知识库数量：{ $res }
msg-a00becc3 = [知识库] 开始检索知识库，数量：{ $res }, top_k={ $top_k }
msg-199e71b7 = [知识库] 用于会话{ $umo }已注入{ $res }相关知识点

### astrbot\core\conversation_mgr.py

msg-86f404dd = 会话删除回调执行失败 (session:{ $unified_msg_origin }):{ $e }
msg-57dcc41f = 会话 ID{ $cid }未找到

### astrbot\core\core_lifecycle.py

msg-9967ec8b = 使用代理：{ $proxy_config }
msg-5a29b73d = HTTP代理已清除
msg-fafb87ce = 子代理编排器初始化失败：{ $e }
msg-f7861f86 = AstrBot迁移失败：{ $e }
msg-78b9c276 = { $res }
msg-967606fd = ------- 任务{ $res }发生错误:{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = -------
msg-9556d279 = AstrBot 启动完成。
msg-daaf690b = 钩子（当_astrbot_加载完成时） ->{ $res }-{ $res_2 }
msg-4719cb33 = 插件{ $res }未正常终止{ $e }可能导致资源泄露等问题。
msg-c3bbfa1d = 任务{ $res }发生错误:{ $e }
msg-af06ccab = 配置文件{ $conf_id }不存在

### astrbot\core\event_bus.py

msg-da466871 = 未找到对应ID的PipelineScheduler：{ $res }事件已忽略。
msg-7eccffa5 = [{ $conf_name }] [{ $res }({ $res_2 })]{ $res_3 }/{ $res_4 }：{ $res_5 }
msg-88bc26f2 = [{ $conf_name }] [{ $res }({ $res_2 })]{ $res_3 }：{ $res_4 }

### astrbot\core\file_token_service.py

msg-0e444e51 = 文件不存在:{ $local_path }(原始输入:{ $file_path })
msg-f61a5322 = 无效或过期的文件令牌：{ $file_token }
msg-73d3e179 = 文件不存在:{ $file_path }

### astrbot\core\initial_loader.py

msg-78b9c276 = { $res }
msg-58525c23 = 😭 初始化 AstrBot 失败：{ $e }!!!
msg-002cc3e8 = 正在关闭 AstrBot...

### astrbot\core\log.py

msg-80a186b8 = 添加文件接收器失败：{ $e }

### astrbot\core\persona_mgr.py

msg-51a854e6 = 已加载{ $res }人格。
msg-1ea88f45 = ID为{$session_id}的用户角色{ $persona_id }不存在。
msg-28104dff = ID为{$session_id}的用户角色{ $persona_id }已存在。
msg-08ecfd42 = { $res }人格情景预设对话格式不正确，条目数应为偶数。
msg-b6292b94 = 解析 Persona 配置失败：{ $e }

### astrbot\core\subagent_orchestrator.py

msg-5d950986 = subagent_orchestrator.agents 必须是一个列表
msg-4867eefb = 子代理角色{ $persona_id }未找到，回退至内联提示。
msg-f425c9f0 = 已注册子代理交接工具：{ $res }

### astrbot\core\umop_config_router.py

msg-dedcfded = umop键必须是格式为[platform_id]:[message_type]:[session_id]的字符串，支持使用通配符*或留空表示全部。
msg-8e3a16f3 = umop 必须是格式为 [platform_id]:[message_type]:[session_id] 的字符串，可使用通配符 * 或留空表示全部

### astrbot\core\updator.py

msg-e3d42a3b = 正在终止{ $res }子进程。
msg-e7edc4a4 = 正在终止子进程{ $res }
msg-37bea42d = 子进程{ $res }未正常终止，正在强制终止。
msg-cc6d9588 = 重启失败（{ $executable },{ $e }请尝试手动重启。
msg-0e4439d8 = 通过此方式启动的AstrBot不支持更新。
msg-3f39a942 = 当前已经是最新版本。
msg-c7bdf215 = 未找到版本号{ $version }更新文件。
msg-92e46ecc = 提交哈希长度不正确，应为 40 位。
msg-71c01b1c = 准备更新至指定版本的 AstrBot Core:{ $version }
msg-d3a0e13d = AstrBot Core 更新文件下载完成，正在解压...

### astrbot\core\zip_updator.py

msg-24c90ff8 = Request{ $url }失败，状态码：{ $res }, 内容:{ $text }
msg-14726dd8 = 请求失败，状态码：{ $res }
msg-fc3793c6 = 解析版本信息时发生异常:{ $e }
msg-491135d9 = 解析版本信息失败
msg-03a72cb5 = 未找到合适的发布版本
msg-8bcbfcf0 = 正在下载更新{ $repo }...
msg-ccc87294 = 正在从指定分支获取{ $branch }下载{ $author }/{ $repo }
msg-dfebcdc6 = 获取{ $author }/{ $repo }GitHub Releases 失败：{ $e }，将尝试下载默认分支
msg-e327bc14 = 正在从默认分支下载{ $author }/{ $repo }
msg-3cd3adfb = 检测到已设置镜像站，将使用镜像站进行下载。{ $author }/{ $repo }仓库源码:{ $release_url }
msg-1bffc0d7 = 无效的 GitHub URL
msg-0ba954db = 文件解压完成：{ $zip_path }
msg-90ae0d15 = 删除临时更新文件:{ $zip_path }和{ $res }
msg-f8a43aa5 = 删除更新文件失败，可以手动删除。{ $zip_path }和{ $res }

### astrbot\core\agent\mcp_client.py

msg-6a61ca88 = 警告：缺少 'mcp' 依赖项，MCP 服务将不可用。
msg-45995cdb = 警告：缺少 'mcp' 依赖项或 MCP 库版本过旧，无法使用流式 HTTP 连接。
msg-2866b896 = MCP连接配置缺少传输或类型字段
msg-3bf7776b = MCP服务器{ $name }错误：{ $msg }
msg-10f72727 = { $error_msg }
msg-19c9b509 = MCP客户端未初始化
msg-5b9b4918 = MCP 客户端{ $res }正在重新连接，跳过
msg-c1008866 = 无法重新连接：缺少连接配置
msg-7c3fe178 = 正在尝试重新连接到 MCP 服务器{ $res }...
msg-783f3b85 = 已成功重新连接到MCP服务器{ $res }
msg-da7361ff = 无法重新连接到MCP服务器{ $res }：{ $e }
msg-c0fd612e = MCP会话不适用于MCP功能工具。
msg-8236c58c = MCP工具{ $tool_name }调用失败（ClosedResourceError），正在尝试重新连接...
msg-044046ec = 关闭当前退出栈时出错：{ $e }

### astrbot\core\agent\message.py

msg-d38656d7 = { $invalid_subclass_error_msg }
msg-42d5a315 = 无法验证{ $value }作为ContentPart
msg-ffc376d0 = 内容为必填项，除非角色为'assistant'且工具调用不为空。

### astrbot\core\agent\tool.py

msg-983bc802 = FunctionTool.call() 必须由子类实现或设置处理程序。

### astrbot\core\agent\tool_image_cache.py

msg-45da4af7 = ToolImageCache 已初始化，缓存目录：{ $res }
msg-017bde96 = 已保存工具镜像至：{ $file_path }
msg-29398f55 = 保存工具镜像失败：{ $e }
msg-128aa08a = 无法读取缓存的图像{ $file_path }：{ $e }
msg-3c111d1f = 缓存清理过程中出现错误：{ $e }
msg-eeb1b849 = 已清理{ $cleaned }过期的缓存图像

### astrbot\core\agent\context\compressor.py

msg-6c75531b = 生成摘要失败：{ $e }

### astrbot\core\agent\context\manager.py

msg-59241964 = 上下文处理期间发生错误：{ $e }
msg-a0d672dc = 压缩已触发，正在开始压缩...
msg-e6ef66f0 = 压缩完成。{ $prev_tokens }->{ $tokens_after_summary }令牌，压缩率：{ $compress_rate }%。
msg-3fe644eb = 上下文在压缩后仍超出最大令牌数，正在应用减半截断处理...

### astrbot\core\agent\runners\base.py

msg-24eb2b08 = 代理状态转换：{ $res }->{ $new_state }

### astrbot\core\agent\runners\tool_loop_agent_runner.py

msg-ec018aef = 已切换自{ $res }回退至聊天服务提供商：{ $candidate_id }
msg-24b29511 = 聊天模型{ $candidate_id }返回错误响应，正在尝试切换到下一个提供程序。
msg-9af066fa = 聊天模型{ $candidate_id }请求错误：{ $exc }
msg-81b2aeae = { $tag }RunCtx.messages -> [{ $res }]{ $res_2 }
msg-55333301 = 请求未设置。请先调用 reset() 方法。
msg-d3b77736 = 代理开始钩子中发生错误：{ $e }
msg-61de315c = 用户请求停止代理执行。
msg-8eb53be3 = on_agent_done 钩子中发生错误：{ $e }
msg-508d6d17 = LLM 响应错误：{ $res }
msg-ed80313d = 大语言模型返回了空的助手消息，未包含任何工具调用。
msg-970947ae = 已附加{ $res }缓存图像至上下文以供LLM审查
msg-6b326889 = 代理已达到最大步数（{ $max_step }强制最终响应。
msg-948ea4b7 = Agent 使用工具:{ $res }
msg-a27ad3d1 = 使用工具：{ $func_tool_name }，参数：{ $func_tool_args }
msg-812ad241 = 未找到指定的工具:{ $func_tool_name }，将跳过。
msg-20b4f143 = 工具{ $func_tool_name }期望的参数：{ $res }
msg-78f6833c = 工具{ $func_tool_name }忽略非期望参数:{ $ignored_params }
msg-2b523f8c = 工具启动钩子中发生错误：{ $e }
msg-ec868b73 = { $func_tool_name }无返回值，或结果已直接发送给用户。
msg-6b61e4f1 = 工具返回了不支持的类型：{ $res }。
msg-34c13e02 = 工具结束钩子中发生错误：{ $e }
msg-78b9c276 = { $res }
msg-a1493b6d = 工具{ $func_tool_name }结果：{ $last_tcr_content }

### astrbot\core\agent\runners\coze\coze_agent_runner.py

msg-448549b0 = Coze API Key 不能为空。
msg-b88724b0 = Coze Bot ID 不能为空。
msg-ea5a135a = Coze API 基础 URL 格式不正确，必须以 http:// 或 https:// 开头。
msg-55333301 = 请求未设置。请先调用 reset() 方法。
msg-d3b77736 = 代理开始钩子中发生错误：{ $e }
msg-5aa3eb1c = Coze 请求失败：{ $res }
msg-333354c6 = 处理上下文图片失败：{ $e }
msg-2d9e1c08 = 图片处理失败{ $url }：{ $e }
msg-1f50979d = { $content }
msg-6fe5588b = Coze 消息已处理完成
msg-d2802f3b = Coze 聊天已完成
msg-ba4afcda = Coze 出现错误：{ $error_code }-{ $error_msg }
msg-ee300f25 = Coze 未返回任何内容
msg-8eb53be3 = on_agent_done 钩子中发生错误：{ $e }
msg-034c1858 = [Coze] 使用缓存的 file_id:{ $file_id }
msg-475d8a41 = [Coze] 图片上传成功并缓存，file_id:{ $file_id }
msg-696dad99 = 图片处理失败{ $image_url }：{ $e }
msg-7793a347 = 图片处理失败：{ $e }

### astrbot\core\agent\runners\coze\coze_api_client.py

msg-76f97104 = Coze API 认证失败，请检查 API Key 是否正确
msg-3653b652 = 文件上传响应状态：{ $res }, 内容:{ $response_text }
msg-13fe060c = 文件上传失败，状态码：{ $res }, 响应:{ $response_text }
msg-5604b862 = 文件上传响应解析失败:{ $response_text }
msg-c0373c50 = 文件上传失败：{ $res }
msg-010e4299 = [Coze] 图片上传成功，file_id:{ $file_id }
msg-719f13cb = 文件上传超时
msg-121c11fb = 文件上传失败：{ $e }
msg-f6101892 = 下载图片失败，状态码：{ $res }
msg-c09c56c9 = 图片下载失败{ $image_url }：{ $e }
msg-15211c7c = 图片下载失败：{ $e }
msg-2245219f = Coze 聊天消息负载：{ $payload }参数：{ $params }
msg-d8fd415c = Coze API 流式请求失败，状态码：{ $res }
msg-f5cc7604 = Coze API 流式请求超时{ $timeout }秒)
msg-30c0a9d6 = Coze API 流式请求失败：{ $e }
msg-11509aba = Coze API 请求失败，状态码：{ $res }
msg-002af11d = Coze API 返回非JSON格式
msg-c0b8fc7c = Coze API 请求超时
msg-a68a33fa = Coze API 请求失败：{ $e }
msg-c26e068e = 获取Coze消息列表失败：{ $e }
msg-5bc0a49d = 已上传文件ID：{ $file_id }
msg-7c08bdaf = 事件：{ $event }

### astrbot\core\agent\runners\dashscope\dashscope_agent_runner.py

msg-dc1a9e6e = 阿里云百炼 API Key 不能为空。
msg-c492cbbc = 阿里云百炼 APP ID 不能为空。
msg-bcc8e027 = 阿里云百炼的APP类型不能为空。
msg-55333301 = 请求未设置。请先调用 reset() 方法。
msg-d3b77736 = 代理开始钩子中发生错误：{ $e }
msg-e3af4efd = 阿里云百炼请求失败：{ $res }
msg-fccf5004 = dashscope 流式数据块：{ $chunk }
msg-100d7d7e = 阿里云百炼请求失败: request_id={ $res }，代码={ $res_2 }，消息={ $res_3 }请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code
msg-10f72727 = { $error_msg }
msg-e8615101 = { $chunk_text }
msg-dfb132c4 = { $ref_text }
msg-8eb53be3 = on_agent_done 钩子中发生错误：{ $e }
msg-650b47e1 = 阿里云百炼暂不支持图片输入，将自动忽略图片内容。

### astrbot\core\agent\runners\dify\dify_agent_runner.py

msg-55333301 = 请求未设置。请先调用 reset() 方法。
msg-d3b77736 = 代理开始钩子中发生错误：{ $e }
msg-0d493427 = Dify 请求失败：{ $res }
msg-fe594f21 = Dify 图片上传响应：{ $file_response }
msg-3534b306 = 上传图片后收到未知的 Dify 响应：{ $file_response }图片将被忽略。
msg-08441fdf = 图片上传失败：{ $e }
msg-3972f693 = dify 响应块：{ $chunk }
msg-6c74267b = Dify 消息结束
msg-1ce260ba = Dify 出现错误：{ $chunk }
msg-a12417dd = Dify 出现错误状态：{ $res }消息：{ $res_2 }
msg-f8530ee9 = dify 工作流响应块：{ $chunk }
msg-386a282e = Dify 工作流(ID:{ $res }) 开始运行。
msg-0bc1299b = Dify 工作流节点(ID:{ $res }标题：{ $res_2 }) 运行结束。
msg-5cf24248 = Dify 工作流(ID:{ $res }) 运行结束
msg-e2c2159f = Dify 工作流结果：{ $chunk }
msg-4fa60ef1 = Dify 工作流出现错误：{ $res }
msg-1f786836 = Dify 工作流的输出不包含指定的键名：{ $res }
msg-c4a70ffb = 未知的 Dify API 类型：{ $res }
msg-51d321fd = Dify 请求结果为空，请查看 Debug 日志。
msg-8eb53be3 = on_agent_done 钩子中发生错误：{ $e }

### astrbot\core\agent\runners\dify\dify_api_client.py

msg-cd6cd7ac = 丢弃无效的 dify JSON 数据：{ $res }
msg-3654a12d = 聊天消息负载：{ $payload }
msg-8e865c52 = Dify /chat-messages 接口请求失败：{ $res }.{ $text }
msg-2d7534b8 = workflow_run 负载：{ $payload }
msg-89918ba5 = Dify /workflows/run 接口请求失败：{ $res }.{ $text }
msg-8bf17938 = file_path 和 file_data 不能同时为 None
msg-b6ee8f38 = Dify 文件上传失败：{ $res }.{ $text }

### astrbot\core\backup\exporter.py

msg-c7ed7177 = 开始导出备份到{ $zip_path }
msg-8099b694 = 备份导出完成:{ $zip_path }
msg-75a4910d = 备份导出失败：{ $e }
msg-2821fc92 = 导出表{ $table_name }：{ $res }1条记录
msg-52b7c242 = 导出表{ $table_name }失败:{ $e }
msg-56310830 = 导出知识库表{ $table_name }：{ $res }1条记录
msg-f4e8f57e = 导出知识库表{ $table_name }失败:{ $e }
msg-8e4ddd12 = 导出知识库文档失败：{ $e }
msg-c1960618 = 导出 FAISS 索引：{ $archive_path }
msg-314bf920 = 导出 FAISS 索引失败：{ $e }
msg-528757b2 = 导出知识库媒体文件失败：{ $e }
msg-d89d6dfe = 目录不存在，跳过:{ $full_path }
msg-94527edd = 导出文件{ $file_path }失败:{ $e }
msg-cb773e24 = 导出目录{ $dir_name }：{ $file_count }一个文件。{ $total_size }字节
msg-ae929510 = 导出目录{ $dir_path }失败:{ $e }
msg-93e331d2 = 导出附件失败：{ $e }

### astrbot\core\backup\importer.py

msg-c046b6e4 = { $msg }
msg-0e6f1f5d = 开始从{ $zip_path }导入备份
msg-2bf97ca0 = 备份导入完成:{ $res }
msg-e67dda98 = 备份文件缺少版本信息。
msg-8f871d9f = 版本差异警告:{ $res }
msg-2d6da12a = 表已清空{ $table_name }
msg-7d21b23a = 清空表{ $table_name }失败:{ $e }
msg-ab0f09db = 知识库表已清空。{ $table_name }
msg-7bcdfaee = 清空知识库表{ $table_name }失败:{ $e }
msg-43f008f1 = 清理知识库{ $kb_id }失败:{ $e }
msg-985cae66 = 未知的表:{ $table_name }
msg-dfa8b605 = 导入记录到{ $table_name }失败:{ $e }
msg-89a2120c = 导入表{ $table_name }：{ $count }1条记录
msg-f1dec753 = 导入知识库记录到{ $table_name }失败:{ $e }
msg-9807bcd8 = 导入文档块失败:{ $e }
msg-98a66293 = 导入附件{ $name }失败:{ $e }
msg-39f2325f = 备份版本不支持目录备份，跳过目录导入。
msg-689050b6 = 现有目录已备份{ $target_dir }到{ $backup_path }
msg-d51b3536 = 导入目录{ $dir_name }：{ $file_count }一个文件

### astrbot\core\computer\computer_client.py

msg-7cb974b8 = 正在将技能包上传至沙箱...
msg-130cf3e3 = 技能包上传至沙箱失败。
msg-99188d69 = 无法删除临时技能压缩包：{ $zip_path }
msg-3f3c81da = 未知的引导程序类型：{ $booter_type }
msg-e20cc33a = 会话沙箱启动错误{ $session_id }：{ $e }

### astrbot\core\computer\booters\boxlite.py

msg-019c4d18 = 执行操作失败：{ $res } { $error_text }
msg-b135b7bd = 文件上传失败：{ $e }
msg-873ed1c8 = 文件未找到：{ $path }
msg-f58ceec6 = 上传文件时出现意外错误：{ $e }
msg-900ab999 = 检查沙箱运行状况{ $ship_id }开启{ $res }...
msg-2a50d6f3 = 沙盒{ $ship_id }是健康的
msg-fbdbe32f = 正在启动(Boxlite)会话：{ $session_id }这可能需要一些时间...
msg-b1f13f5f = Boxlite 启动器已为会话启动：{ $session_id }
msg-e93d0c30 = 正在关闭舰船Boxlite启动器：{ $res }
msg-6deea473 = Boxlite 启动器用于船舶：{ $res }已停止

### astrbot\core\computer\booters\local.py

msg-487d0c91 = 路径超出了允许的计算机根目录范围。
msg-e5eb5377 = 已阻止不安全的Shell命令。
msg-9e1e117f = 本地计算机启动器已为会话初始化：{ $session_id }
msg-2d7f95de = 本地计算机启动器关闭完成。
msg-82a45196 = LocalBooter不支持upload_file操作。请改用shell。
msg-0457524a = LocalBooter不支持download_file操作。请改用shell。

### astrbot\core\computer\booters\shipyard.py

msg-b03115b0 = 已获取沙箱环境：{ $res }对于会话：{ $session_id }
msg-c5ce8bde = 检查Shipyard沙箱可用性时出错：{ $e }

### astrbot\core\computer\tools\fs.py

msg-99ab0efe = 上传结果：{ $result }
msg-bca9d578 = 文件{ $local_path }已上传至沙箱环境{ $file_path }
msg-da21a6a5 = 文件上传错误{ $local_path }：{ $e }
msg-93476abb = 文件{ $remote_path }已从沙箱下载至{ $local_path }
msg-079c5972 = 发送文件消息时出错：{ $e }
msg-ce35bb2c = 文件下载错误{ $remote_path }：{ $e }

### astrbot\core\config\astrbot_config.py

msg-e0a69978 = 不支持的配置类型{ $res }支持的类型包括：{ $res_2 }
msg-b9583fc9 = 检测到配置项{ $path_ }不存在，已插入默认值{ $value }
msg-ee26e40e = 检测到配置项{ $path_ }不存在，将从当前配置中删除。
msg-2d7497a5 = 检测到配置项{ $path }子项顺序不一致，已重新排序。
msg-5fdad937 = 检测到配置项顺序不一致，已重新排序。
msg-555373b0 = 未找到键：'{ $key }'

### astrbot\core\cron\manager.py

msg-2a752c91 = 跳过基础定时任务的调度{ $res }由于缺少处理程序。
msg-d5c33112 = 无效时区{ $res }用于定时任务{ $res_2 }回退到系统。
msg-e71c28d3 = 一次性任务缺少运行时间戳
msg-dd46e69f = 无法调度定时任务{ $res }：{ $e }
msg-aa2e4688 = 未知的定时任务类型：{ $res }
msg-186627d9 = 定时任务{ $job_id }失败：{ $e }
msg-cb955de0 = 基础cron任务处理器未找到{ $res }
msg-2029c4b2 = ActiveAgentCronJob 缺少会话。
msg-6babddc9 = 定时任务会话无效：{ $e }
msg-865a2b07 = 构建定时任务主代理失败。
msg-27c9c6b3 = Cron作业代理未收到响应

### astrbot\core\db\migration\helper.py

msg-a48f4752 = 开始执行数据库迁移...
msg-45e31e8e = 数据库迁移完成。

### astrbot\core\db\migration\migra_3_to_4.py

msg-7805b529 = 迁移{ $total_cnt }将旧的会话数据迁移到新的表中...
msg-6f232b73 = 进度：{ $progress }% ({ $res }/{ $total_cnt })
msg-6b1def31 = 未找到该条旧会话对应的具体数据：{ $conversation }跳过。
msg-b008c93f = 迁移旧会话{ $res }失败:{ $e }
msg-6ac6313b = 成功迁移{ $total_cnt }将旧的会话数据迁移到新表。
msg-6b72e89b = 迁移旧平台数据，offset_sec:{ $offset_sec }秒。
msg-bdc90b84 = 迁移{ $res }将旧平台数据迁移至新表...
msg-e6caca5c = 未找到旧平台数据，跳过迁移。
msg-1e824a79 = 进度：{ $progress }% ({ $res }/{ $total_buckets })
msg-813384e2 = 迁移平台统计数据失败：{ $platform_id },{ $platform_type }时间戳:{ $bucket_end }
msg-27ab191d = 成功迁移{ $res }将旧平台数据迁移至新表。
msg-8e6280ed = 迁移{ $total_cnt }将旧的 WebChat 会话数据迁移到新表中...
msg-cad66fe1 = 迁移旧版 WebChat 会话{ $res }失败
msg-63748a46 = 成功迁移{ $total_cnt }将旧的 WebChat 会话数据迁移到新表。
msg-dfc93fa4 = 迁移{ $total_personas }正在将 Persona 配置迁移到新表...
msg-ff85e45c = 进度：{ $progress }% ({ $res }/{ $total_personas })
msg-c346311e = 迁移 Persona{ $res }({ $res_2 }...) 到新表成功。
msg-b6292b94 = 解析 Persona 配置失败：{ $e }
msg-90e5039e = 迁移全局偏好设置{ $key }成功，值:{ $value }
msg-d538da1c = 迁移会话{ $umo }对话数据已成功迁移至新表，平台 ID:{ $platform_id }
msg-ee03c001 = 迁移会话{ $umo }对话数据失败:{ $e }
msg-5c4339cd = 迁移会话{ $umo }服务配置已成功迁移至新表，平台 ID:{ $platform_id }
msg-4ce2a0b2 = 迁移会话{ $umo }服务配置失败：{ $e }
msg-2e62dab9 = 迁移会话{ $umo }变量失败:{ $e }
msg-afbf819e = 迁移会话{ $umo }提供商偏好已成功迁移至新表，平台ID：{ $platform_id }
msg-959bb068 = 迁移会话{ $umo }提供商偏好设置失败：{ $e }

### astrbot\core\db\migration\migra_45_to_46.py

msg-782b01c1 = migrate_45_to_46: abconf_data 不是字典类型 (type={ $res }). 值：{ $abconf_data }
msg-49e09620 = 开始从版本4.5迁移至4.6
msg-791b79f8 = 从版本45到版本46的迁移已成功完成

### astrbot\core\db\migration\migra_token_usage.py

msg-c3e53a4f = 开始执行数据库迁移（添加 conversations.token_usage 列）...
msg-ccbd0a41 = token_usage 列已存在，跳过迁移
msg-39f60232 = token_usage 列添加成功
msg-4f9d3876 = token_usage 迁移完成
msg-91571aaf = 迁移过程中发生错误：{ $e }

### astrbot\core\db\migration\migra_webchat_session.py

msg-53fad3d0 = 开始执行数据库迁移（WebChat 会话迁移）...
msg-7674efb0 = 未找到需要迁移的 WebChat 数据。
msg-139e39ee = 找到{ $res }WebChat 会话需要迁移。
msg-cf287e58 = Session{ $session_id }已存在，跳过
msg-062c72fa = WebChat 会话迁移完成！成功迁移：{ $res }, 跳过:{ $skipped_count }
msg-a516cc9f = 没有新会话需要迁移。
msg-91571aaf = 迁移过程中发生错误：{ $e }

### astrbot\core\db\vec_db\faiss_impl\document_storage.py

msg-c2dc1d2b = 数据库连接未初始化，返回空结果
msg-51fa7426 = 数据库连接未初始化，跳过删除操作
msg-43d1f69f = 数据库连接未初始化，返回0

### astrbot\core\db\vec_db\faiss_impl\embedding_storage.py

msg-8e5fe535 = faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。
msg-9aa7b941 = 向量维度不匹配，预期应为：{ $res }, 实际:{ $res_2 }

### astrbot\core\db\vec_db\faiss_impl\vec_db.py

msg-9f9765dc = 正在生成嵌入向量{ $res }内容...
msg-385bc50a = 已生成嵌入向量{ $res }内容{ $res_2 }秒。

### astrbot\core\knowledge_base\kb_db_sqlite.py

msg-b850e5d8 = 知识库数据库已关闭:{ $res }

### astrbot\core\knowledge_base\kb_helper.py

msg-7b3dc642 = - 第{$attempt}次尝试时LLM调用失败{ $res }/{ $res_2 }错误：{ $res_3 }
msg-4ba9530f = - 处理分片失败，在{ $res }次尝试之后。使用原始文本。
msg-77670a3a = 知识库{ $res }未配置 Embedding Provider
msg-8e9eb3f9 = 无法找到 ID{ $res }嵌入提供程序
msg-3e426806 = 无法找到 ID{ $res }的重新排序提供程序
msg-6e780e1e = 使用预分块文本进行上传，共{ $res }一个块。
msg-f4b82f18 = 当未提供 pre_chunked_text 时，file_content 不能为空。
msg-975f06d7 = 上传文档失败：{ $e }
msg-969b17ca = 清理多媒体文件失败{ $media_path }：{ $me }
msg-18d25e55 = 无法找到 ID{ $doc_id }文档
msg-f5d7c34c = 错误：Tavily API 密钥未在 provider_settings 中配置。
msg-975d88e0 = 无法从URL提取内容{ $url }：{ $e }
msg-cfe431b3 = 未从URL提取到内容：{ $url }
msg-e7f5f836 = 内容清洗后未提取到有效文本。请尝试关闭内容清洗功能，或更换更高性能的LLM模型后重试。
msg-693aa5c5 = 内容清洗未启用，使用指定参数进行分块: chunk_size={ $chunk_size }，块重叠={ $chunk_overlap }
msg-947d8f46 = 已启用内容清洗，但未提供 cleaning_provider_id，跳过清洗并使用默认分块。
msg-31963d3f = 无法找到 ID{ $cleaning_provider_id }LLM Provider 或类型不正确
msg-82728272 = 初步分块完成，正在生成{ $res }此块用于修复。
msg-6fa5fdca = 块{ $i }处理异常：{ $res }回退到原始块。
msg-6780e950 = 文本修复完成。{ $res }原始块 ->{ $res_2 }最终块。
msg-79056c76 = 使用 Provider '{ $cleaning_provider_id }内容清洗失败：{ $e }

### astrbot\core\knowledge_base\kb_mgr.py

msg-98bfa670 = 正在初始化知识库模块...
msg-7da7ae15 = 知识库模块导入失败:{ $e }
msg-842a3c65 = 请确保已安装所需依赖：pypdf、aiofiles、Pillow、rank-bm25。
msg-c9e943f7 = 知识库模块初始化失败:{ $e }
msg-78b9c276 = { $res }
msg-9349e112 = 知识库数据库已初始化：{ $DB_PATH }
msg-7605893e = 创建知识库时必须提供embedding_provider_id。
msg-0b632cbd = 知识库名称{ $kb_name }' 已存在
msg-ca30330f = 知识库已关闭{ $kb_id }失败:{ $e }
msg-00262e1f = 关闭知识库元数据数据库失败:{ $e }
msg-3fc9ef0b = 知识库ID为{ $kb_id }未找到。

### astrbot\core\knowledge_base\chunking\recursive.py

msg-21db456a = 块大小必须大于0
msg-c0656f4e = 块重叠必须为非负数
msg-82bd199c = 块重叠量必须小于块大小

### astrbot\core\knowledge_base\parsers\text_parser.py

msg-70cbd40d = 无法解码文件：{ $file_name }

### astrbot\core\knowledge_base\parsers\url_parser.py

msg-2de85bf5 = 错误：Tavily API 密钥未配置。
msg-98ed69f4 = 错误：URL 必须为非空字符串。
msg-7b14cdb7 = Tavily 网页提取失败：{ $reason }，状态：{ $res }
msg-cfe431b3 = 未从URL提取到内容：{ $url }
msg-b0897365 = 获取URL失败{ $url }：{ $e }
msg-975d88e0 = 无法从URL提取内容{ $url }：{ $e }

### astrbot\core\knowledge_base\parsers\util.py

msg-398b3580 = 暂时不支持的文件格式:{ $ext }

### astrbot\core\knowledge_base\retrieval\manager.py

msg-fcc0dde2 = 知识库 ID{ $kb_id }实例未找到，已跳过该知识库的检索。
msg-320cfcff = 密集检索跨越{ $res }基础已获取{ $res_2 }并返回{ $res_3 }结果。
msg-90ffcfc8 = 跨稀疏检索{ $res }基础已获取{ $res_2 }并返回{ $res_3 }结果。
msg-12bcf404 = 排名融合耗时{ $res }并返回{ $res_2 }结果。
msg-28c084bc = 知识库ID的向量数据库{ $kb_id }不是FaissVecDB
msg-cc0230a3 = 知识库{ $kb_id }稠密检索失败：{ $e }

### astrbot\core\message\components.py

msg-afb10076 = 不是有效的URL
msg-fe4c33a0 = 不是有效的文件：{ $res }
msg-24d98e13 = 未配置 callback_api_base，文件服务不可用
msg-a5c69cc9 = 已注册：{ $callback_host }/api/文件/{ $token }
msg-3cddc5ef = 下载失败：{ $url }
msg-1921aa47 = 不是有效的文件：{ $url }
msg-2ee3827c = 生成的视频文件回调链接：{ $payload_file }
msg-32f4fc78 = 未提供有效的文件或URL
msg-36375f4c = 禁止在异步上下文中同步等待下载！此警告通常出现在某些逻辑尝试通过 <File>.file 获取文件消息段的内容时。请使用 await get_file() 替代直接访问 <File>.file 字段。
msg-4a987754 = 文件下载失败:{ $e }
msg-7c1935ee = 下载失败：文件组件中未提供URL。
msg-35bb8d53 = 生成文件回调链接：{ $payload_file }

### astrbot\core\pipeline\context_utils.py

msg-49f260d3 = 处理函数参数不匹配，请检查 handler 的定义。
msg-d7b4aa84 = 先前错误：{ $trace_ }
msg-eb8619cb = 钩子({ $res }) ->{ $res_2 }-{ $res_3 }
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }已停止事件传播。

### astrbot\core\pipeline\scheduler.py

msg-c240d574 = Phase{ $res }事件传播已终止。
msg-609a1ac5 = 流水线执行完毕。

### astrbot\core\pipeline\__init__.py


### astrbot\core\pipeline\content_safety_check\stage.py

msg-c733275f = 您的消息或大模型的回复包含不当内容，已被屏蔽。
msg-46c80f28 = 内容安全检查未通过，原因：{ $info }

### astrbot\core\pipeline\content_safety_check\strategies\strategy.py

msg-27a700e0 = 使用百度内容审核前，应先执行 pip install baidu-aip。

### astrbot\core\pipeline\preprocess_stage\stage.py

msg-7b9074fa = { $platform }预响应表情发送失败：{ $e }
msg-43f1b4ed = 路径映射：{ $url }->{ $res }
msg-9549187d = Session{ $res }未配置语音转文本模型。
msg-5bdf8f5c = { $e }
msg-ad90e19e = 重试中:{ $res }/{ $retry }
msg-78b9c276 = { $res }
msg-4f3245bf = 语音转文本失败:{ $e }

### astrbot\core\pipeline\process_stage\follow_up.py

msg-12767505 = 已捕获活动代理运行的后续消息，umo={ $res }, order_seq={ $order_seq }

### astrbot\core\pipeline\process_stage\method\agent_request.py

msg-3267978a = 识别 LLM 聊天额外唤醒前缀{ $res }机器人唤醒前缀{ $bwp }开头，已自动去除。
msg-97a4d573 = 此流水线未启用AI功能，跳过处理。
msg-f1a11d2b = 会话{ $res }已禁用AI功能，跳过处理。

### astrbot\core\pipeline\process_stage\method\star_request.py

msg-f0144031 = 无法找到给定处理器模块路径的插件：{ $res }
msg-1e8939dd = 插件 ->{ $res }-{ $res_2 }
msg-6be73b5e = { $traceback_text }
msg-d919bd27 = 星{ $res }处理错误：{ $e }
msg-ed8dcc22 = { $ret }

### astrbot\core\pipeline\process_stage\method\agent_sub_stages\internal.py

msg-73bf9e45 = 不支持的 tool_schema_mode：{ $res }，回退到 skills_like
msg-9cdb2b6e = 跳过LLM请求：消息为空且无提供者请求
msg-e461e5af = 准备请求LLM服务提供商
msg-4d2645f7 = 后续工单已处理完毕，停止处理。umo={ $res }，序列={ $res_2 }
msg-abd5ccbc = 已获取LLM请求的会话锁
msg-abc0d82d = 提供者API基础{ $api_base }由于安全原因，访问已被阻止。请使用其他AI服务提供商。
msg-3247374d = [内部代理] 检测到实时模式，启用 TTS 处理
msg-dae92399 = [实时模式] TTS 提供商未配置，将使用普通流式模式
msg-1b1af61e = 处理代理时发生错误：{ $e }
msg-ea02b899 = 处理代理请求时发生错误：{ $e }
msg-ee7e792b = LLM 响应为空，不保存记录。

### astrbot\core\pipeline\process_stage\method\agent_sub_stages\third_party.py

msg-5e551baf = 第三方代理运行器错误：{ $e }
msg-34f164d4 = { $err_msg }
msg-f9d76893 = 未填写 Agent Runner 提供商 ID，请前往配置页面进行配置。
msg-0f856470 = Agent Runner 提供商{ $res }配置不存在，请前往配置页面修改配置。
msg-b3f25c81 = 不支持的第三方代理运行器类型：{ $res }
msg-6c63eb68 = Agent Runner 未返回最终结果。

### astrbot\core\pipeline\rate_limit_check\stage.py

msg-18092978 = Session{ $session_id }被限流。根据限流策略，此会话处理将被暂停。{ $stall_duration }秒。
msg-4962387a = Session{ $session_id }被限流。根据限流策略，此请求已被丢弃，直到配额于{ $stall_duration }秒后重置。

### astrbot\core\pipeline\respond\stage.py

msg-59539c6e = 解析分段回复的间隔时间失败。{ $e }
msg-4ddee754 = 分段回复间隔时间：{ $res }
msg-5e2371a9 = 准备发送 -{ $res }/{ $res_2 }：{ $res_3 }
msg-df92ac24 = async_stream 为空，跳过发送。
msg-858b0e4f = 应用流式输出({ $res })
msg-22c7a672 = 消息为空，跳过发送阶段
msg-e6ab7a25 = 空内容检查异常:{ $e }
msg-b29b99c1 = 实际消息链为空，跳过发送阶段。header_chain:{ $header_comps }，实际链：{ $res }
msg-842df577 = 发送消息链失败: chain ={ $res }，错误 ={ $e }
msg-f35465cf = 消息链仅包含 Reply 和 At 消息段，跳过发送阶段。chain:{ $res }
msg-784e8a67 = 发送消息链失败: chain ={ $chain }，错误 ={ $e }

### astrbot\core\pipeline\result_decorate\stage.py

msg-7ec898fd = hook(on_decorating_result) ->{ $res }-{ $res_2 }
msg-5e27dae6 = 启用流式输出时，依赖发送消息前事件钩子的插件可能无法正常工作。
msg-caaaec29 = hook(on_decorating_result) ->{ $res }-{ $res_2 }清空消息结果。
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }已停止事件传播。
msg-813a44bb = 流式输出已启用，跳过结果装饰阶段。
msg-891aa43a = 分段回复正则表达式错误，使用默认分段方式：{ $res }
msg-82bb9025 = Session{ $res }未配置文本转语音模型。
msg-fb1c757a = TTS 请求:{ $res }
msg-06341d25 = TTS 结果:{ $audio_path }
msg-2057f670 = 由于 TTS 音频文件未找到，消息段转语音失败:{ $res }
msg-f26725cf = 已注册：{ $url }
msg-47716aec = TTS 失败，使用文本发送。
msg-ffe054a9 = 文本转图片失败，使用文本发送。
msg-06c1aedc = 文本转图片耗时超过3秒，若感觉较慢可使用 /t2i 关闭文本转图片模式。

### astrbot\core\pipeline\session_status_check\stage.py

msg-f9aba737 = Session{ $res }已关闭，事件传播已终止。

### astrbot\core\pipeline\waking_check\stage.py

msg-df815938 = 已启用的插件名称：{ $enabled_plugins_name }
msg-51182733 = 插件{ $res }：{ $e }
msg-e0dcf0b8 = 您的ID：{ $res }权限不足，无法使用此指令。请通过 /sid 获取 ID 并联系管理员添加权限。
msg-a3c3706f = 触发{ $res }当用户(ID={ $res_2 }权限不足。

### astrbot\core\pipeline\whitelist_check\stage.py

msg-8282c664 = Session ID{ $res }不在会话白名单中，已终止事件传播。请在配置文件中添加该会话 ID 到白名单。

### astrbot\core\platform\astr_message_event.py

msg-b593f13f = 无法转换消息类型{ $res }回退至 FRIEND_MESSAGE。
msg-98bb33b7 = 清除{ $res }Additional information:{ $res_2 }
msg-0def44e2 = { $result }
msg-8e7dc862 = { $text }

### astrbot\core\platform\manager.py

msg-61bd87ae = 终止平台适配器失败: client_id={ $client_id }，错误={ $e }
msg-78b9c276 = { $res }
msg-563a0a74 = 初始化{ $platform }平台适配器失败：{ $e }
msg-3398495c = 平台 ID{ $platform_id }包含非法字符 ':' 或 '!'，已替换为{ $sanitized_id }。
msg-31361418 = 平台 ID{ $platform_id }不能为空，跳过加载此平台适配器。
msg-e395bbcc = 载入{ $res }({ $res_2 }) 平台适配器 ...
msg-b4b29344 = 正在加载平台适配器{ $res }失败，原因：{ $e }请检查依赖库是否安装。提示：可在管理面板->平台日志->安装Pip库中安装依赖库。
msg-18f0e1fe = 正在加载平台适配器{ $res }失败，原因：{ $e }。
msg-2636a882 = 未找到适用于{ $res }({ $res_2 }平台适配器，请检查是否已安装或名称填写是否正确。
msg-c4a38b85 = hook(on_platform_loaded) ->{ $res }-{ $res_2 }
msg-967606fd = ------- 任务{ $res }发生错误:{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = -------
msg-38723ea8 = 正在尝试终止{ $platform_id }平台适配器 ...
msg-63f684c6 = 可能未完全移除{ $platform_id }平台适配器
msg-136a952f = 获取平台统计信息失败：{ $e }

### astrbot\core\platform\platform.py

msg-30fc9871 = 平台{ $res }未实现统一 Webhook 模式

### astrbot\core\platform\register.py

msg-eecf0aa8 = 平台适配器{ $adapter_name }已注册，可能存在适配器命名冲突。
msg-614a55eb = 平台适配器{ $adapter_name }已注册
msg-bb06a88d = 平台适配器{ $res }已注销 (来自模块{ $res_2 })

### astrbot\core\platform\sources\aiocqhttp\aiocqhttp_message_event.py

msg-0db8227d = 无法发送消息：缺少有效的数字 session_id{ $session_id }) 或 event({ $event })

### astrbot\core\platform\sources\aiocqhttp\aiocqhttp_platform_adapter.py

msg-859d480d = 处理请求消息失败：{ $e }
msg-6fb672e1 = 处理通知消息失败：{ $e }
msg-cf4687a3 = 处理群组消息失败：{ $e }
msg-3a9853e3 = 处理私信失败：{ $e }
msg-ec06dc3d = aiocqhttp(OneBot v11) 适配器已连接。
msg-1304a54d = [aiocqhttp] 原始消息{ $event }
msg-93cbb9fa = { $err }
msg-a4487a03 = 回复消息失败：{ $e }
msg-48bc7bff = 猜测拉格朗日
msg-6ab145a1 = 获取文件失败:{ $ret }
msg-457454d7 = 获取文件失败:{ $e }此消息段将被忽略。
msg-7a299806 = 无法从回复消息数据构造 Event 对象：{ $reply_event_data }
msg-e6633a51 = Failed to retrieve quoted message:{ $e }。
msg-6e99cb8d = 获取 @ 用户信息失败:{ $e }此消息段将被忽略。
msg-cf15fd40 = 不支持的消息段类型，已忽略:{ $t }，数据={ $res }
msg-45d126ad = 消息段解析失败: type={ $t }，数据={ $res }.{ $e }
msg-394a20ae = aiocqhttp: 未配置 ws_reverse_host 或 ws_reverse_port，将使用默认值：http://0.0.0.0:6199
msg-7414707c = aiocqhttp 适配器已被关闭

### astrbot\core\platform\sources\dingtalk\dingtalk_adapter.py

msg-c81e728d = 2
msg-d6371313 = 钉钉：{ $res }
msg-a1c8b5b1 = 钉钉私聊会话缺少 staff_id 映射，回退使用 session_id 作为 userId 进行发送。
msg-2abb842f = 钉钉会话映射保存失败：{ $e }
msg-46988861 = 钉钉文件下载失败：{ $res },{ $res_2 }
msg-ba9e1288 = 通过 dingtalk_stream 获取 access_token 失败：{ $e }
msg-835b1ce6 = 获取钉钉机器人 access_token 失败：{ $res },{ $res_2 }
msg-331fcb1f = 读取钉钉 staff_id 映射失败：{ $e }
msg-ba183a34 = 钉钉群消息发送失败：access_token 为空
msg-b8aaa69b = 钉钉群消息发送失败:{ $res },{ $res_2 }
msg-cfb35bf5 = 钉钉私聊消息发送失败：access_token 为空
msg-7553c219 = 钉钉私聊消息发送失败：{ $res },{ $res_2 }
msg-5ab2d58d = 清理临时文件失败：{ $file_path },{ $e }
msg-c0c40912 = 钉钉语音转OGG失败，回退至AMR：{ $e }
msg-21c73eca = 钉钉媒体上传失败：access_token 为空
msg-24e3054f = 钉钉媒体上传失败：{ $res },{ $res_2 }
msg-34d0a11d = 钉钉媒体上传失败：{ $data }
msg-3b0d4fb5 = 钉钉语音消息发送失败：{ $e }
msg-7187f424 = 钉钉视频发送失败：{ $e }
msg-e40cc45f = 钉钉私聊回复失败：缺少发送者员工ID
msg-be63618a = 钉钉适配器已关闭。
msg-0ab22b13 = 钉钉机器人启动失败：{ $e }

### astrbot\core\platform\sources\dingtalk\dingtalk_event.py

msg-eaa1f3e4 = 钉钉消息发送失败：缺少适配器

### astrbot\core\platform\sources\discord\client.py

msg-940888cb = [Discord] 客户端未能正确加载用户信息 (self.user 为 None)
msg-9a3c1925 = [Discord] 已作为{ $res }(ID:{ $res_2 }登录
msg-30c1f1c8 = [Discord] 客户端已准备就绪。
msg-d8c03bdf = [Discord] on_ready_once_callback 执行失败:{ $e }
msg-c9601653 = 机器人未就绪：self.user 为 None
msg-4b017a7c = 收到无有效用户的交互
msg-3067bdce = [Discord] 收到原始消息 来自{ $res }：{ $res_2 }

### astrbot\core\platform\sources\discord\discord_platform_adapter.py

msg-7ea23347 = [Discord] 客户端未就绪 (self.client.user 为 None)，无法发送消息
msg-ff6611ce = [Discord] 频道ID格式无效：{ $channel_id_str }
msg-5e4e5d63 = [Discord] 无法获取频道信息{ $channel_id_str }将猜测消息类型。
msg-32d4751b = [Discord] 收到消息:{ $message_data }
msg-8296c994 = [Discord] 机器人令牌未配置。请在配置文件中正确设置令牌。
msg-170b31df = [Discord] 登录失败。请检查你的 Bot Token 是否正确。
msg-6678fbd3 = [Discord] 与 Discord 的连接已关闭。
msg-cd8c35d2 = [Discord] 适配器运行时发生意外错误：{ $e }
msg-4df30f1d = [Discord] 客户端未就绪 (self.client.user 为 None)，无法处理消息
msg-f7803502 = [Discord] 收到非 Message 类型的消息:{ $res }，已忽略。
msg-134e70e9 = [Discord] 正在终止适配器... (步骤1：取消轮询任务)
msg-5c01a092 = [Discord] polling_task 已取消。
msg-77f8ca59 = [Discord] polling_task 取消异常:{ $e }
msg-528b6618 = [Discord] 正在清理已注册的斜杠指令... (步骤 2)
msg-d0b832e6 = [Discord] 指令清理完成。
msg-43383f5e = [Discord] 清理指令时发生错误:{ $e }
msg-b960ed33 = [Discord] 正在关闭 Discord 客户端... (步骤 3)
msg-5e58f8a2 = [Discord] 客户端关闭异常:{ $e }
msg-d1271bf1 = [Discord] 适配器已终止。
msg-c374da7a = [Discord] 开始收集并注册斜杠指令...
msg-a6d37e4d = [Discord] 准备同步{ $res }一个指令：{ $res_2 }
msg-dbcaf095 = [Discord] 未找到可注册的指令。
msg-09209f2f = [Discord] 指令同步完成。
msg-a95055fd = [Discord] 回调函数触发:{ $cmd_name }
msg-55b13b1e = [Discord] 回调函数参数:{ $ctx }
msg-79f72e4e = [Discord] 回调函数参数:{ $params }
msg-22add467 = [Discord] 斜杠命令 '{ $cmd_name }' 被触发。 原始参数: '{ $params }'. 构建的指令字符串: '{ $message_str_for_filter }'
msg-ccffc74a = [Discord] 指令 '{ $cmd_name }'defer' 失败：{ $e }
msg-13402a28 = [Discord] 跳过不符合规范的指令:{ $cmd_name }

### astrbot\core\platform\sources\discord\discord_platform_event.py

msg-0056366b = [Discord] 解析消息链时失败：{ $e }
msg-fa0a9e40 = [Discord] 尝试发送空消息，已忽略。
msg-5ccebf9a = [Discord] 频道{ $res }不是可发送消息的类型
msg-1550c1eb = [Discord] 发送消息时发生未知错误：{ $e }
msg-7857133d = [Discord] 无法获取频道{ $res }
msg-050aa8d6 = [Discord] 开始处理 Image 组件:{ $i }
msg-57c802ef = [Discord] Image 组件缺少 file 属性:{ $i }
msg-f2bea7ac = [Discord] 处理 URL 图片:{ $file_content }
msg-c3eae1f1 = [Discord] 正在处理文件URI：{ $file_content }
msg-6201da92 = [Discord] 图片文件不存在：{ $path }
msg-2a6f0cd4 = [Discord] 处理 Base64 URI
msg-b589c643 = [Discord] 尝试作为裸 Base64 处理
msg-41dd4b8f = [Discord] 裸 Base64 解码失败，作为本地路径处理：{ $file_content }
msg-f59778a1 = [Discord] 处理图片时发生未知严重错误：{ $file_info }
msg-85665612 = [Discord] 获取文件失败，路径不存在：{ $file_path_str }
msg-e55956fb = [Discord] 获取文件失败:{ $res }
msg-56cc0d48 = [Discord] 处理文件失败:{ $res }错误:{ $e }
msg-c0705d4e = [Discord] 忽略了不支持的消息组件：{ $res }
msg-0417d127 = [Discord] 消息内容超过2000字符，将被截断。
msg-6277510f = [Discord] 添加反应失败：{ $e }

### astrbot\core\platform\sources\lark\lark_adapter.py

msg-06ce76eb = 未设置飞书机器人名称，@机器人可能无法收到回复。
msg-eefbe737 = [Lark] API Client im 模块未初始化
msg-236bcaad = [Lark] 下载消息资源失败 type={ $resource_type }，键={ $file_key }，代码={ $res }, 消息={ $res_2 }
msg-ef9a61fe = [Lark] 消息资源响应中不包含文件流：{ $file_key }
msg-7b69a8d4 = [Lark] 图片消息缺少 message_id
msg-59f1694d = [Lark] 富文本视频消息缺少 message_id
msg-af8f391d = [Lark] 文件消息缺少 message_id
msg-d4080b76 = [Lark] 文件消息缺少 file_key
msg-ab21318a = [Lark] 音频消息缺少 message_id
msg-9ec2c30a = [Lark] 音频消息缺少 file_key
msg-0fa9ed18 = [Lark] 视频消息缺少 message_id
msg-ae884c5c = [Lark] 视频消息缺少 file_key
msg-dac98a62 = [Lark] 获取引用消息失败 id={ $parent_message_id }，代码={ $res }, 消息={ $res_2 }
msg-7ee9f7dc = [Lark] 引用消息响应为空 id={ $parent_message_id }
msg-2b3b2db9 = [Lark] 解析引用消息内容失败 id={ $quoted_message_id }
msg-c5d54255 = [Lark] 收到空事件(event.event is None)
msg-82f041c4 = [Lark] 事件中没有消息体(message is None)
msg-206c3506 = [Lark] 消息内容为空
msg-876aa1d2 = [Lark] 解析消息内容失败:{ $res }
msg-514230f3 = [Lark] 消息内容不是 JSON 对象：{ $res }
msg-0898cf8b = [Lark] 解析消息内容:{ $content_json_b }
msg-6a8bc661 = [Lark] 消息缺少 message_id
msg-26554571 = [Lark] 消息发送者信息不完整
msg-007d863a = [Lark Webhook] 跳过重复事件：{ $event_id }
msg-6ce17e71 = [Lark Webhook] 未处理的事件类型:{ $event_type }
msg-8689a644 = [Lark Webhook] 处理事件失败:{ $e }
msg-20688453 = [Lark] Webhook 模式已启用，但 webhook_server 未初始化
msg-f46171bc = [Lark] Webhook 模式已启用，但未配置 webhook_uuid
msg-dd90a367 = 飞书(Lark) 适配器已关闭

### astrbot\core\platform\sources\lark\lark_event.py

msg-eefbe737 = [Lark] API Client im 模块未初始化
msg-a21f93fa = [Lark] 主动发送消息时，receive_id 和 receive_id_type 不能为空
msg-f456e468 = [Lark] 发送飞书消息失败({ $res }):{ $res_2 }
msg-1eb66d14 = [Lark] 文件不存在:{ $path }
msg-1df39b24 = [Lark] API Client im 模块未初始化，无法上传文件
msg-2ee721dd = [Lark] 无法上传文件({ $res }):{ $res_2 }
msg-a04abf78 = [Lark] 文件上传成功但未返回数据（data 为 None）
msg-959e78a4 = [Lark] 文件上传成功:{ $file_key }
msg-901a2f60 = [Lark] 无法打开或上传文件：{ $e }
msg-13065327 = [Lark] 图片路径为空，无法上传
msg-37245892 = [Lark] 无法打开图片文件：{ $e }
msg-ad63bf53 = [Lark] API Client im 模块未初始化，无法上传图片
msg-ef90038b = 无法上传飞书图片({ $res }):{ $res_2 }
msg-d2065832 = [Lark] 图片上传成功但未返回数据（data 为 None）
msg-dbb635c2 = { $image_key }
msg-d4810504 = [Lark] 检测到文件组件，将单独发送
msg-45556717 = [Lark] 检测到音频组件，将单独发送
msg-959070b5 = [Lark] 检测到视频组件，将单独发送
msg-4e2aa152 = 飞书 暂时不支持消息段:{ $res }
msg-20d7c64b = [Lark] 无法获取音频文件路径：{ $e }
msg-2f6f35e6 = [Lark] 音频文件不存在：{ $original_audio_path }
msg-528b968d = [Lark] 音频格式转换失败，将尝试直接上传：{ $e }
msg-fbc7efb9 = [Lark] 已删除转换后的音频文件：{ $converted_audio_path }
msg-09840299 = [Lark] 删除转换后的音频文件失败：{ $e }
msg-e073ff1c = [Lark] 无法获取视频文件路径：{ $e }
msg-47e52913 = [Lark] 视频文件不存在:{ $original_video_path }
msg-85ded1eb = [Lark] 视频格式转换失败，将尝试直接上传：{ $e }
msg-b3bee05d = [Lark] 已删除转换后的视频文件：{ $converted_video_path }
msg-775153f6 = [Lark] 删除转换后的视频文件失败：{ $e }
msg-45038ba7 = [Lark] API Client im 模块未初始化，无法发送表情
msg-8d475b01 = 发送飞书表情回应失败{ $res }):{ $res_2 }

### astrbot\core\platform\sources\lark\server.py

msg-2f3bccf1 = 未配置 encrypt_key，无法解密事件
msg-e77104e2 = [Lark Webhook] 收到 challenge 验证请求:{ $challenge }
msg-34b24fa1 = [Lark Webhook] 解析请求体失败:{ $e }
msg-ec0fe13e = [Lark Webhook] 请求体为空
msg-f69ebbdb = [Lark Webhook] 签名验证失败
msg-7ece4036 = [Lark Webhook] 解密后的事件:{ $event_data }
msg-f2cb4b46 = [Lark Webhook] 解密事件失败:{ $e }
msg-ef9f8906 = [Lark Webhook] 验证令牌不匹配。
msg-bedb2071 = [Lark Webhook] 处理事件回调失败:{ $e }

### astrbot\core\platform\sources\line\line_adapter.py

msg-68539775 = LINE适配器需要channel_access_token和channel_secret。
msg-30c67081 = [LINE] webhook_uuid 为空，统一 Webhook 可能无法接收消息。
msg-64e92929 = [LINE] 无效的 webhook 签名
msg-321afd59 = [LINE] 无效的 webhook 请求体：{ $e }
msg-1079248e = [LINE] 重复事件已跳过：{ $event_id }

### astrbot\core\platform\sources\line\line_api.py

msg-dc6656f8 = [LINE]{ $op_name }消息发送失败：状态={ $res }正文={ $body }
msg-10996a43 = [LINE]{ $op_name }消息请求失败：{ $e }
msg-5aa92977 = [LINE] 获取内容重试失败：message_id={ $message_id }状态={ $res }正文={ $body }
msg-cf700d79 = [LINE] 获取内容失败：message_id={ $message_id }状态={ $res }正文={ $body }

### astrbot\core\platform\sources\line\line_event.py

msg-a491ddd0 = [LINE] 解析图片URL失败：{ $e }
msg-ca47546c = [LINE] 解析记录URL失败：{ $e }
msg-616e5840 = [LINE] 解析记录时长失败：{ $e }
msg-c953a061 = [LINE] 解析视频链接失败：{ $e }
msg-19078257 = [LINE] 解析视频封面失败：{ $e }
msg-eccdecff = [LINE] 生成视频预览失败：{ $e }
msg-b833dc32 = [LINE] 解析文件URL失败：{ $e }
msg-60290793 = [LINE] 解析文件大小失败：{ $e }
msg-d6443173 = [LINE] 消息数量超过5条，超出部分将被丢弃。

### astrbot\core\platform\sources\misskey\misskey_adapter.py

msg-7bacee77 = [Misskey] 配置不完整，无法启动
msg-99cdf3d3 = [Misskey] 已连接用户：{ $res }(ID:{ $res_2 })
msg-5579c974 = [Misskey] 获取用户信息失败：{ $e }
msg-d9547102 = [Misskey] API 客户端未初始化
msg-341b0aa0 = [Misskey] WebSocket 已连接 (尝试 #{ $connection_attempts })
msg-c77d157b = [Misskey] 聊天频道已订阅
msg-a0c5edc0 = [Misskey] WebSocket 连接失败 (尝试 #{ $connection_attempts })
msg-1958faa8 = [Misskey] WebSocket 异常 (尝试 #{ $connection_attempts }):{ $e }
msg-1b47382d = [Misskey]{ $sleep_time }秒后重连 (下次尝试 #{ $res })
msg-a10a224d = [Misskey] 收到通知事件: type={ $notification_type }用户ID={ $res }
msg-7f0abf4a = [Misskey] 处理贴文提及:{ $res }...
msg-2da7cdf5 = [Misskey] 处理通知失败:{ $e }
msg-6c21d412 = [Misskey] 收到聊天事件: sender_id={ $sender_id }，room_id={ $room_id }，is_self={ $res }
msg-68269731 = [Misskey] 检查群聊消息: '{ $raw_text }', 机器人用户名: '{ $res }'
msg-585aa62b = [Misskey] 处理群聊消息：{ $res }...
msg-426c7874 = [Misskey] 处理私聊消息：{ $res }...
msg-f5aff493 = [Misskey] 处理聊天消息失败：{ $e }
msg-ea465183 = [Misskey] 收到未处理事件: type={ $event_type }，通道={ $res }
msg-8b69eb93 = [Misskey] 消息内容为空且无文件附件，跳过发送
msg-9ba9c4e5 = [Misskey] 已清理临时文件：{ $local_path }
msg-91af500e = [Misskey] 文件数量超过限制 ({ $res }>{ $MAX_FILE_UPLOAD_COUNT }), 仅上传第一个{ $MAX_FILE_UPLOAD_COUNT }一个文件
msg-9746d7f5 = [Misskey] 并发上传过程中出现异常，继续发送文本
msg-d6dc928c = [Misskey] 聊天消息仅支持单个文件，已忽略其余{ $res }一个文件
msg-af584ae8 = [Misskey] 解析可见性: visibility={ $visibility }, visible_user_ids={ $visible_user_ids }, session_id={ $session_id }, user_id_for_cache={ $user_id_for_cache }
msg-1a176905 = [Misskey] 消息发送失败：{ $e }

### astrbot\core\platform\sources\misskey\misskey_api.py

msg-fab20f57 = Misskey API 需要 aiohttp 和 websockets。请使用以下命令安装：pip install aiohttp websockets
msg-f2eea8e1 = [Misskey WebSocket] 已连接
msg-5efd11a2 = [Misskey WebSocket] 重新订阅{ $channel_type }失败:{ $e }
msg-b70e2176 = [Misskey WebSocket] 连接失败：{ $e }
msg-b9f3ee06 = [Misskey WebSocket] 连接已断开
msg-7cd98e54 = WebSocket 未连接
msg-43566304 = [Misskey WebSocket] 无法解析消息：{ $e }
msg-e617e390 = [Misskey WebSocket] 处理消息失败:{ $e }
msg-c60715cf = [Misskey WebSocket] 连接意外关闭：{ $e }
msg-da9a2a17 = [Misskey WebSocket] 连接已关闭 (代码:{ $res }, 原因:{ $res_2 })
msg-bbf6a42e = [Misskey WebSocket] 握手失败:{ $e }
msg-254f0237 = [Misskey WebSocket] 监听消息失败:{ $e }
msg-49f7e90e = { $channel_summary }
msg-630a4832 = [Misskey WebSocket] 频道消息:{ $channel_id }事件类型:{ $event_type }
msg-0dc61a4d = [Misskey WebSocket] 使用处理器:{ $handler_key }
msg-012666fc = [Misskey WebSocket] 使用事件处理器：{ $event_type }
msg-e202168a = [Misskey WebSocket] 未找到处理器:{ $handler_key }或{ $event_type }
msg-a397eef1 = [Misskey WebSocket] 直接消息处理器：{ $message_type }
msg-a5f12225 = [Misskey WebSocket] 未处理的消息类型:{ $message_type }
msg-ad61d480 = [Misskey API]{ $func_name }重试{ $max_retries }后续尝试仍然失败：{ $e }
msg-7de2ca49 = [Misskey API]{ $func_name }第{ $attempt }重试失败:{ $e }，{ $sleep_time }请稍后重试
msg-f5aecf37 = [Misskey API]{ $func_name }遇到不可重试异常:{ $e }
msg-e5852be5 = [Misskey API] 客户端已关闭
msg-21fc185c = [Misskey API] 请求参数错误：{ $endpoint }(HTTP{ $status })
msg-5b106def = 错误请求{ $endpoint }
msg-28afff67 = [Misskey API] 未授权访问：{ $endpoint }(HTTP{ $status })
msg-e12f2d28 = 未经授权的访问{ $endpoint }
msg-beda662d = [Misskey API] 访问被禁止：{ $endpoint }(HTTP{ $status })
msg-795ca227 = 禁止访问{ $endpoint }
msg-5c6ba873 = [Misskey API] 资源不存在:{ $endpoint }(HTTP{ $status })
msg-74f2bac2 = 资源未找到{ $endpoint }
msg-9ceafe4c = [Misskey API] 请求体过大：{ $endpoint }(HTTP{ $status })
msg-3e336b73 = 请求实体过大{ $endpoint }
msg-a47067de = [Misskey API] 请求频率限制：{ $endpoint }(HTTP{ $status })
msg-901dc2da = 请求频率超限{ $endpoint }
msg-2bea8c2e = [Misskey API] 服务器内部错误：{ $endpoint }(HTTP{ $status })
msg-ae8d3725 = 内部服务器错误{ $endpoint }
msg-7b028462 = [Misskey API] 网关错误：{ $endpoint }(HTTP{ $status })
msg-978414ef = 网关错误{ $endpoint }
msg-50895a69 = [Misskey API] 服务不可用：{ $endpoint }(HTTP{ $status })
msg-62adff89 = 服务不可用{ $endpoint }
msg-1cf15497 = [Misskey API] 网关超时：{ $endpoint }(HTTP{ $status })
msg-a8a2578d = 网关超时{ $endpoint }
msg-c012110a = [Misskey API] 未知错误：{ $endpoint }(HTTP{ $status })
msg-dc96bbb8 = HTTP{ $status }对于{ $endpoint }
msg-4c7598b6 = [Misskey API] 已获取{ $res }一条新通知
msg-851a2a54 = [Misskey API] 请求成功：{ $endpoint }
msg-5f5609b6 = [Misskey API] 响应格式错误：{ $e }
msg-c8f7bbeb = 无效的JSON响应
msg-82748b31 = [Misskey API] 请求失败：{ $endpoint }- HTTP{ $res }, 响应:{ $error_text }
msg-c6de3320 = [Misskey API] 请求失败：{ $endpoint }- HTTP{ $res }
msg-affb19a7 = [Misskey API] HTTP 请求错误：{ $e }
msg-9f1286b3 = HTTP请求失败：{ $e }
msg-44f91be2 = [Misskey API] 发帖成功:{ $note_id }
msg-fbafd3db = 未提供上传文件路径
msg-872d8419 = [Misskey API] 本地文件不存在：{ $file_path }
msg-37186dea = 文件未找到：{ $file_path }
msg-65ef68e0 = [Misskey API] 本地文件上传成功：{ $filename }->{ $file_id }
msg-0951db67 = [Misskey API] 文件上传网络错误：{ $e }
msg-e3a322f5 = 上传失败：{ $e }
msg-f28772b9 = 未提供用于按哈希查找的 MD5 哈希值
msg-25e566ef = [Misskey API] find-by-hash 请求: md5={ $md5_hash }
msg-a036a942 = [Misskey API] find-by-hash 响应: 找到{ $res }一个文件
msg-ea3581d5 = [Misskey API] 根据哈希查找文件失败:{ $e }
msg-1d2a84ff = 未提供查找名称
msg-f25e28b4 = [Misskey API] find 请求: name={ $name }文件夹ID={ $folder_id }
msg-cd43861a = [Misskey API] find 响应: 找到{ $res }一个文件
msg-05cd55ef = [Misskey API] 根据名称查找文件失败:{ $e }
msg-c01052a4 = [Misskey API] 列表文件请求: limit={ $limit }文件夹ID={ $folder_id }，类型={ $type }
msg-7c81620d = [Misskey API] 列表文件响应: 找到{ $res }一个文件
msg-a187a089 = [Misskey API] 列表文件失败：{ $e }
msg-9e776259 = 无可用会话
msg-de18c220 = URL不能为空
msg-25b15b61 = [Misskey API] SSL 验证下载失败：{ $ssl_error }，重试不验证 SSL
msg-b6cbeef6 = [Misskey API] 本地上传成功：{ $res }
msg-a4a898e2 = [Misskey API] 本地上传失败：{ $e }
msg-46b7ea4b = [Misskey API] 聊天消息发送成功：{ $message_id }
msg-32f71df4 = [Misskey API] 房间消息发送成功：{ $message_id }
msg-7829f3b3 = [Misskey API] 聊天消息响应格式异常:{ $res }
msg-d74c86a1 = [Misskey API] 提及通知响应格式异常：{ $res }
msg-65ccb697 = 消息内容不能为空：需要文本或媒体文件。
msg-b6afb123 = [Misskey API] URL媒体上传成功：{ $res }
msg-4e62bcdc = [Misskey API] URL媒体上传失败：{ $url }
msg-71cc9d61 = [Misskey API] URL媒体处理失败{ $url }：{ $e }
msg-75890c2b = [Misskey API] 本地文件上传成功：{ $res }
msg-024d0ed5 = [Misskey API] 本地文件上传失败：{ $file_path }
msg-f1fcb5e1 = [Misskey API] 本地文件处理失败{ $file_path }：{ $e }
msg-1ee80a6b = 不支持的消息类型:{ $message_type }

### astrbot\core\platform\sources\misskey\misskey_event.py

msg-85cb7d49 = [MisskeyEvent] send 方法被调用，消息链包含{ $res }一个组件
msg-252c2fca = [MisskeyEvent] 检查适配器方法: hasattr(self.client, 'send_by_session') ={ $res }
msg-44d7a060 = [MisskeyEvent] 调用适配器的 send_by_session 方法
msg-b6e08872 = [MisskeyEvent] 内容为空，跳过发送
msg-8cfebc9c = [Misskey事件] 创建新帖子
msg-ed0d2ed5 = [MisskeyEvent] 发送失败：{ $e }

### astrbot\core\platform\sources\qqofficial\qqofficial_message_event.py

msg-28a74d9d = [QQ官方] 跳过 botpy 的 FormData 补丁。
msg-c0b123f6 = 发送流式消息时出错:{ $e }
msg-05d6bba5 = [QQOfficial] 不支持的消息源类型:{ $res }
msg-e5339577 = [QQOfficial] GroupMessage 缺少 group_openid
msg-71275806 = 消息已发送至C2C：{ $ret }
msg-040e7942 = [QQ官方] markdown 发送被拒绝，已回退到 content 模式重试。
msg-9000f8f7 = 无效的上传参数
msg-d72cffe7 = 上传图片失败，响应不是字典类型：{ $result }
msg-5944a27c = 上传文件响应格式错误：{ $result }
msg-1e513ee5 = 上传请求错误：{ $e }
msg-f1f1733c = 发布C2C消息失败，响应不是字典类型：{ $result }
msg-9b8f9f70 = 不支持的图像文件格式
msg-24eb302a = 转换音频格式时出错：音频时长不大于0
msg-b49e55f9 = 处理语音时出错:{ $e }
msg-6e716579 = qq_official 忽略{ $res }

### astrbot\core\platform\sources\qqofficial\qqofficial_platform_adapter.py

msg-8af45ba1 = QQ 机器人官方 API 适配器不支持 send_by_session
msg-8ebd1249 = 未知消息类型：{ $message_type }
msg-c165744d = QQ 官方机器人接口适配器已优雅关闭。

### astrbot\core\platform\sources\qqofficial_webhook\qo_webhook_adapter.py

msg-6721010c = [QQ官方Webhook] 会话无缓存的 msg_id：{ $res }，跳过 send_by_session
msg-296dfcad = [QQ官方Webhook] 通过会话发送不支持的消息类型：{ $res }
msg-6fa95bb3 = QQ官方Webhook服务器关闭期间发生异常：{ $exc }
msg-6f83eea0 = QQ 机器人官方 API 适配器已优雅关闭。

### astrbot\core\platform\sources\qqofficial_webhook\qo_webhook_server.py

msg-41a3e59d = 正在登录到 QQ 官方机器人...
msg-66040e15 = 已登录 QQ 官方机器人账号：{ $res }
msg-6ed59b60 = 收到 qq_official_webhook 回调：{ $msg }
msg-ad355b59 = { $signed }
msg-4bf0bff8 = _解析器未知事件{ $event }.
msg-cef08b17 = 将在{ $res }：{ $res_2 }端口启动 QQ 官方机器人 webhook 适配器。

### astrbot\core\platform\sources\satori\satori_adapter.py

msg-ab7db6d9 = Satori WebSocket 连接已关闭：{ $e }
msg-4ef42cd1 = Satori WebSocket 连接失败：{ $e }
msg-b50d159b = 达到最大重试次数 ({ $max_retries }), 停止重试
msg-89de477c = Satori 适配器正在连接到 WebSocket：{ $res }
msg-cfa5b059 = Satori 适配器 HTTP API 地址:{ $res }
msg-d534864b = 无效的WebSocket URL：{ $res }
msg-a110f9f7 = WebSocket URL必须以ws://或wss://开头。{ $res }
msg-bf43ccb6 = Satori 处理消息异常：{ $e }
msg-89081a1a = Satori WebSocket 连接异常：{ $e }
msg-5c04bfcd = Satori WebSocket 关闭异常：{ $e }
msg-b67bcee0 = WebSocket连接未建立
msg-89ea8b76 = WebSocket连接已关闭
msg-4c8a40e3 = IDENTIFY 信令发送时连接已关闭。{ $e }
msg-05a6b99d = 发送 IDENTIFY 信令失败:{ $e }
msg-c9b1b774 = Satori WebSocket 心跳发送失败：{ $e }
msg-61edb4f3 = 心跳任务异常:{ $e }
msg-7db44899 = Satori 连接成功 - 机器人{ $res }平台={ $platform }用户ID={ $user_id }, 用户名={ $user_name }
msg-01564612 = 解析 WebSocket 消息失败:{ $e }消息内容：{ $message }
msg-3a1657ea = 处理 WebSocket 消息异常:{ $e }
msg-dc6b459c = 处理事件失败：{ $e }
msg-6524f582 = 解析<quote>标签时发生错误:{ $e }, 错误内容:{ $content }
msg-3be535c3 = 转换 Satori 消息失败：{ $e }
msg-be17caf1 = XML解析失败，使用正则提取：{ $e }
msg-f6f41d74 = 提取<quote>标签时发生错误:{ $e }
msg-ca6dca7f = 转换引用消息失败：{ $e }
msg-cd3b067e = 解析 Satori 元素时发生解析错误:{ $e }, 错误内容:{ $content }
msg-03071274 = 解析 Satori 元素时发生未知错误:{ $e }
msg-775cd5c0 = HTTP会话未初始化
msg-e354c8d1 = Satori HTTP 请求异常：{ $e }

### astrbot\core\platform\sources\satori\satori_event.py

msg-c063ab8a = Satori 消息发送异常：{ $e }
msg-9bc42a8d = Satori 消息发送失败
msg-dbf77ca2 = 图片转换为base64失败:{ $e }
msg-8b6100fb = Satori 流式消息发送异常：{ $e }
msg-3c16c45c = 语音转换为base64失败:{ $e }
msg-66994127 = 视频文件转换失败：{ $e }
msg-30943570 = 转换消息组件失败：{ $e }
msg-3e8181fc = 转换转发节点失败：{ $e }
msg-d626f831 = 转换合并转发消息失败：{ $e }

### astrbot\core\platform\sources\slack\client.py

msg-1d6b68b9 = Slack 请求签名验证失败
msg-53ef18c3 = 收到Slack事件：{ $event_data }
msg-58488af6 = 处理 Slack 事件时出错:{ $e }
msg-477be979 = Slack Webhook 服务器启动中，监听{ $res }：{ $res_2 }{ $res_3 }...
msg-639fee6c = Slack Webhook 服务器已停止
msg-a238d798 = Socket客户端未初始化
msg-4e6de580 = 处理 Socket Mode 事件时出错:{ $e }
msg-5bb71de9 = Slack Socket Mode 客户端启动中...
msg-f79ed37f = Slack Socket Mode 客户端已停止

### astrbot\core\platform\sources\slack\slack_adapter.py

msg-c34657ff = Slack bot_token 是必需的
msg-64f8a45d = Socket 模式需要应用令牌
msg-a2aba1a7 = Webhook 模式需要签名密钥
msg-40e00bd4 = Slack 发送消息失败：{ $e }
msg-56c1d0a3 = [slack] 原始消息{ $event }
msg-855510b4 = 无法下载Slack文件：{ $res } { $res_2 }
msg-04ab2fae = 下载文件失败:{ $res }
msg-79ed7e65 = Slack 认证测试通过。机器人ID：{ $res }
msg-ec27746a = Slack 适配器 (Socket Mode) 启动中...
msg-34222d3a = Slack 适配器 (Webhook 模式) 启动中，正在监听{ $res }：{ $res_2 }{ $res_3 }...
msg-6d8110d2 = 不支持的连接模式：{ $res }请使用 'socket' 或 'webhook'
msg-d71e7f36 = Slack 适配器已被关闭

### astrbot\core\platform\sources\slack\slack_event.py

msg-b233107c = Slack文件上传失败：{ $res }
msg-596945d1 = Slack文件上传响应：{ $response }

### astrbot\core\platform\sources\telegram\tg_adapter.py

msg-cb53f79a = Telegram 基础网址：{ $res }
msg-e6b6040f = Telegram Updater 未初始化，无法启动轮询。
msg-2c4b186e = Telegram平台适配器正在运行。
msg-908d0414 = 向 Telegram 注册指令时发生错误：{ $e }
msg-d2dfe45e = 命令名 '{ $cmd_name }重复注册时，将采用首次注册的定义：{ $res }'
msg-63bdfab8 = 收到启动命令但未检测到有效对话，跳过 /start 回复。
msg-03a27b01 = Telegram 消息：{ $res }
msg-e47b4bb4 = 收到更新但未附带消息。
msg-c97401c6 = [Telegram] 收到一条没有发送者信息的消息。
msg-f5c839ee = Telegram文档文件路径为空，无法保存文件。{ $file_name }.
msg-dca991a9 = Telegram视频文件路径为空，无法保存文件。{ $file_name }.
msg-56fb2950 = 创建媒体组缓存：{ $media_group_id }
msg-0de2d4b5 = 将消息添加到媒体组{ $media_group_id }，当前具有{ $res }项目。
msg-9e5069e9 = 媒体组{ $media_group_id }已达到最大等待时间（{ $elapsed }s >={ $res }正在处理中。
msg-9156b9d6 = 已安排媒体组{ $media_group_id }待处理{ $delay }秒（已等待{ $elapsed }s)
msg-2849c882 = 媒体组{ $media_group_id }未在缓存中找到
msg-c75b2163 = 媒体组{ $media_group_id }为空
msg-0a3626c1 = 正在处理媒体组{ $media_group_id }，总计{ $res }项目
msg-2842e389 = 媒体组的第一条消息转换失败{ $media_group_id }
msg-32fbf7c1 = 已添加{ $res }组件到媒体组{ $media_group_id }
msg-23bae28a = Telegram 适配器已关闭。
msg-e46e7740 = 关闭 Telegram 适配器时发生错误：{ $e }

### astrbot\core\platform\sources\telegram\tg_event.py

msg-7757f090 = [Telegram] 发送聊天动作失败：{ $e }
msg-80b075a3 = 用户隐私设置阻止接收语音消息，已转为发送音频文件。要启用语音消息，请前往Telegram设置 → 隐私与安全 → 语音消息 → 设置为“所有人”。
msg-20665ad1 = MarkdownV2 发送失败：{ $e }使用纯文本替代。
msg-323cb67c = [Telegram] 添加反应失败：{ $e }
msg-abe7fc3d = 编辑消息失败(streaming-break):{ $e }
msg-f7d40103 = 不支持的消息类型:{ $res }
msg-d4b50a96 = 编辑消息失败(流式传输):{ $e }
msg-2701a78f = 发送消息失败(流式传输):{ $e }
msg-2a8ecebd = Markdown转换失败，使用普通文本：{ $e }

### astrbot\core\platform\sources\webchat\webchat_adapter.py

msg-9406158c = WebChatAdapter：{ $res }

### astrbot\core\platform\sources\webchat\webchat_event.py

msg-6b37adcd = webchat 忽略:{ $res }

### astrbot\core\platform\sources\webchat\webchat_queue_mgr.py

msg-4af4f885 = 已启动对话监听器：{ $conversation_id }
msg-10237240 = 处理来自会话的消息时出错{ $conversation_id }：{ $e }

### astrbot\core\platform\sources\wecom\wecom_adapter.py

msg-d4bbf9cb = 验证请求有效性:{ $res }
msg-f8694a8a = 请求验证成功。
msg-8f4cda74 = 验证请求有效性失败，签名异常，请检查配置。
msg-46d3feb9 = 解密失败，签名异常，请检查配置。
msg-4d1dfce4 = 解析成功：{ $msg }
msg-a98efa4b = 将在{ $res }：{ $res_2 }端口启动企业微信适配器。
msg-a616d9ce = 企业微信客服模式不支持通过会话(send_by_session)主动发送消息。
msg-5d01d7b9 = send_by_session 失败：无法为会话{ $res }推断 agent_id。
msg-3f05613d = 已获取微信客服列表：{ $acc_list }
msg-8fd19bd9 = 获取微信客服失败，open_kfid 为空。
msg-5900d9b6 = 发现 open_kfid:{ $open_kfid }
msg-391119b8 = 请打开以下链接，使用微信扫码以获取客服微信: https://api.cl2wm.cn/api/qrcode/code?text={ $kf_url }
msg-5bdf8f5c = { $e }
msg-93c9125e = 音频转换失败:{ $e }如果没有安装 ffmpeg，请先安装。
msg-b2f7d1dc = 暂未实现的事件:{ $res }
msg-61480a61 = 基于账户的营销{ $abm }
msg-42431e46 = 未实现的微信客服消息事件：{ $msg }
msg-fbca491d = 企业微信适配器已关闭

### astrbot\core\platform\sources\wecom\wecom_event.py

msg-e164c137 = 未找到微信客服消息发送方法。
msg-c114425e = WeChat客服上传图片失败:{ $e }
msg-a90bc15d = 微信客服上传图片返回:{ $response }
msg-38298880 = WeChat客服上传语音失败:{ $e }
msg-3aee0caa = 微信客服上传语音返回：{ $response }
msg-15e6381b = 删除临时音频文件失败：{ $e }
msg-a79ae417 = 微信客服上传文件失败：{ $e }
msg-374455ef = 微信客服上传文件返回：{ $response }
msg-a2a133e4 = 微信客服上传视频失败：{ $e }
msg-2732fffd = 微信客服上传视频返回：{ $response }
msg-60815f02 = 该消息类型的发送逻辑尚未实现：{ $res }。
msg-9913aa52 = 企业微信上传图片失败:{ $e }
msg-9e90ba91 = 企业微信上传图片返回：{ $response }
msg-232af016 = 企业微信上传语音失败:{ $e }
msg-e5b8829d = 企业微信上传语音返回：{ $response }
msg-f68671d7 = 企业微信上传文件失败:{ $e }
msg-8cdcc397 = 企业微信文件上传返回：{ $response }
msg-4f3e15f5 = 企业微信上传视频失败:{ $e }
msg-4e9aceea = 企业微信上传视频返回：{ $response }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_adapter.py

msg-bac9a65e = 企业微信消息推送 webhook 配置无效:{ $e }
msg-2102fede = 处理队列消息时发生异常：{ $e }
msg-d4ea688d = 消息类型未知，已忽略。{ $message_data }
msg-88aba3b0 = 处理消息时发生异常:{ $e }
msg-740911ab = 流已结束，正在返回结束消息：{ $stream_id }
msg-9fdbafe9 = 无法找到流ID对应的返回队列：{ $stream_id }
msg-7a52ca2b = 流ID对应的后台队列中没有新消息。{ $stream_id }
msg-9ffb59fb = 聚合内容：{ $latest_plain_content }，图像：{ $res }，完成：{ $finish }
msg-de9ff585 = 流消息发送成功，流ID：{ $stream_id }
msg-558310b9 = 消息加密失败
msg-ced70250 = 处理欢迎消息时发生异常：{ $e }
msg-480c5dac = [WecomAI] 消息已入队:{ $stream_id }
msg-f595dd6e = 处理加密图片失败：{ $result }
msg-e8beeb3d = WecomAIAdapter:{ $res }
msg-0eedc642 = 主动消息发送失败: 未配置企业微信消息推送 Webhook URL，请前往配置添加。session_id={ $res }
msg-9934b024 = 企业微信消息推送失败(session={ $res }):{ $e }
msg-827fa8d0 = 启动企业微信智能机器人适配器，开始监听。{ $res }：{ $res_2 }
msg-87616945 = 企业微信智能机器人适配器正在关闭...

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_api.py

msg-86f6ae9f = 消息解密失败，错误码：{ $ret }
msg-45ad825c = 解密成功，消息内容：{ $message_data }
msg-84c476a7 = JSON 解析失败:{ $e }原始消息：{ $decrypted_msg }
msg-c0d8c5f9 = 解密消息为空
msg-a08bcfc7 = 解密过程发生异常：{ $e }
msg-4dfaa613 = 消息加密失败，错误码：{ $ret }
msg-6e566b12 = 消息加密成功
msg-39bf8dba = 加密过程发生异常:{ $e }
msg-fa5be7c5 = URL 验证失败，错误码：{ $ret }
msg-813a4e4e = URL 验证成功
msg-65ce0d23 = URL 验证发生异常:{ $e }
msg-b1aa892f = 开始下载加密图片:{ $image_url }
msg-10f72727 = { $error_msg }
msg-70123a82 = 图片下载成功，大小：{ $res }字节
msg-85d2dba1 = AES密钥不能为空
msg-67c4fcea = 无效的 AES 密钥长度：应为 32 字节
msg-bde4bb57 = 无效的填充长度（超过32字节）
msg-63c22912 = 图片解密成功，解密后大小：{ $res }字节
msg-6ea489f0 = 文本消息解析失败
msg-eb12d147 = 图片消息解析失败
msg-ab1157ff = 流消息解析失败
msg-e7e945d1 = 混合消息解析失败
msg-06ada9dd = 事件消息解析失败

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_event.py

msg-e44e77b0 = 图片数据为空，跳过。
msg-235f0b46 = 处理图片消息失败：{ $e }
msg-31b11295 = [WecomAI] 不支持的消息组件类型：{ $res }, 跳过

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_queue_mgr.py

msg-8be03d44 = [WecomAI] 创建输入队列:{ $session_id }
msg-9804296a = [WecomAI] 创建输出队列:{ $session_id }
msg-bdf0fb78 = [WecomAI] 移除输出队列:{ $session_id }
msg-40f6bb7b = [WecomAI] 移除待处理响应：{ $session_id }
msg-fbb807cd = [WecomAI] 标记流已结束:{ $session_id }
msg-9d7f5627 = [WecomAI] 移除输入队列：{ $session_id }
msg-7637ed00 = [WecomAI] 设置待处理响应:{ $session_id }
msg-5329c49b = [WecomAI] 清理过期响应及队列:{ $session_id }
msg-09f098ea = [WecomAI] 为会话启动监听器:{ $session_id }
msg-c55856d6 = 处理会话{ $session_id }消息时发生错误:{ $e }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_server.py

msg-adaee66c = URL 验证参数缺失
msg-742e0b43 = 收到企业微信智能机器人 WebHook URL 验证请求。
msg-f86c030c = 消息回调参数缺失
msg-cce4e44c = 收到消息回调，msg_signature={ $msg_signature }, 时间戳={ $timestamp }，随机数={ $nonce }
msg-16a7bfed = 消息解密失败，错误码：{ $ret_code }
msg-a567f8e3 = 消息处理器执行异常：{ $e }
msg-88aba3b0 = 处理消息时发生异常:{ $e }
msg-1cccaaf4 = 启动企业微信智能机器人服务器，开始监听。{ $res }：{ $res_2 }
msg-866d0b8b = 服务器运行异常:{ $e }
msg-3269840c = 企业微信智能机器人服务器正在关闭...

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_utils.py

msg-14d01778 = JSON 解析失败:{ $e }原始字符串：{ $json_str }
msg-b1aa892f = 开始下载加密图片:{ $image_url }
msg-70123a82 = 图片下载成功，大小：{ $res }字节
msg-10f72727 = { $error_msg }
msg-1d91d2bb = AES密钥不能为空
msg-bb32bedd = 无效的AES密钥长度：必须为32字节
msg-bde4bb57 = 无效的填充长度（超过32字节）
msg-63c22912 = 图片解密成功，解密后大小：{ $res }字节
msg-6886076b = 图片已转换为base64编码，编码后长度为：{ $res }

### astrbot\core\platform\sources\wecom_ai_bot\wecomai_webhook.py

msg-a5c90267 = 消息推送 webhook URL 不能为空
msg-76bfb25b = 消息推送 webhook URL 缺少 key 参数。
msg-3545eb07 = Webhook 请求失败: HTTP{ $res },{ $text }
msg-758dfe0d = Webhook 返回错误：{ $res } { $res_2 }
msg-ad952ebe = 企业微信消息推送成功:{ $res }
msg-73d3e179 = 文件不存在:{ $file_path }
msg-774a1821 = 上传媒体失败：HTTP{ $res },{ $text }
msg-6ff016a4 = 上传媒体失败：{ $res } { $res_2 }
msg-0e8252d1 = 上传媒体失败：返回缺少 media_id
msg-4f5f40e1 = 文件消息缺少有效文件路径，已跳过：{ $component }
msg-2c9fe93d = 清理临时语音文件失败{ $target_voice_path }：{ $e }
msg-98d2b67a = 企业微信消息推送暂不支持组件类型。{ $res }，已跳过

### astrbot\core\platform\sources\wecom_ai_bot\WXBizJsonMsgCrypt.py

msg-5bdf8f5c = { $e }
msg-fe69e232 = 接收ID不匹配
msg-00b71c27 = 签名不匹配
msg-5cfb5c20 = { $signature }

### astrbot\core\platform\sources\weixin_official_account\weixin_offacc_adapter.py

msg-d4bbf9cb = 验证请求有效性:{ $res }
msg-b2edb1b2 = 未知响应，请检查回调地址填写是否正确。
msg-f8694a8a = 请求验证成功。
msg-8f4cda74 = 验证请求有效性失败，签名异常，请检查配置。
msg-46d3feb9 = 解密失败，签名异常，请检查配置。
msg-e23d8bff = 解析失败。msg为None。
msg-4d1dfce4 = 解析成功：{ $msg }
msg-193d9d7a = 用户消息缓冲状态: user={ $from_user }状态={ $state }
msg-57a3c1b2 = wx 缓冲区在触发器上命中：用户={ $from_user }
msg-bed995d9 = 重试窗口触发微信缓冲区命中：用户={ $from_user }
msg-3a94b6ab = wx 被动窗口消息发送完成：用户={ $from_user }消息ID={ $msg_id }
msg-50c4b253 = wx 在被动窗口完成消息发送但非最终状态：用户={ $from_user }消息ID={ $msg_id }
msg-7d8b62e7 = wx 在窗口中完成但非最终状态；返回占位符：user={ $from_user }消息ID={ $msg_id }
msg-2b9b8aed = wx 任务在被动窗口中执行失败
msg-7bdf4941 = wx 被动窗口超时：用户={ $from_user }消息ID={ $msg_id }
msg-98489949 = wx 触发思考时：用户={ $from_user }
msg-01d0bbeb = wx new trigger: user={ $from_user }消息ID={ $msg_id }
msg-52bb36cd = wx 启动任务：用户={ $from_user }消息ID={ $msg_id }预览={ $preview }
msg-ec9fd2ed = wx 缓冲区立即命中：用户={ $from_user }
msg-61c91fb9 = wx 未在首个窗口完成；返回占位符：user={ $from_user }消息ID={ $msg_id }
msg-35604bba = wx任务在首个窗口执行失败
msg-e56c4a28 = 微信首窗口超时：用户={ $from_user }消息ID={ $msg_id }
msg-e163be40 = 将在{ $res }：{ $res_2 }端口启动微信公众平台适配器。
msg-c1740a04 = 重复消息ID已检查：{ $res }
msg-04718b37 = 已获取未来结果：{ $result }
msg-296e66c1 = 回调处理消息超时: message_id={ $res }
msg-eb718c92 = 转换消息时出现异常:{ $e }
msg-93c9125e = 音频转换失败:{ $e }如果未安装 ffmpeg，请先安装。
msg-b2f7d1dc = 暂未实现的事件:{ $res }
msg-61480a61 = 基于账户的营销{ $abm }
msg-2e7e0187 = 用户消息缓冲状态未找到，无法处理消息: user={ $res }消息ID={ $res_2 }
msg-84312903 = 微信公众平台适配器已被关闭。

### astrbot\core\platform\sources\weixin_official_account\weixin_offacc_event.py

msg-fa7f7afc = 将纯文本分割为{ $res }被动回复的分块。消息未发送。
msg-59231e07 = 微信公众平台上传图片失败：{ $e }
msg-d3968fc5 = 微信公众平台上传图片返回：{ $response }
msg-7834b934 = 微信公众平台上传语音失败：{ $e }
msg-4901d769 = 微信公众平台上传语音接口返回：{ $response }
msg-15e6381b = 删除临时音频文件失败：{ $e }
msg-60815f02 = 该消息类型的发送逻辑尚未实现：{ $res }。

### astrbot\core\provider\entities.py

msg-7fc6f623 = 图片{ $image_url }The result obtained is empty and will be ignored.

### astrbot\core\provider\func_tool_manager.py

msg-0c42a4d9 = 添加函数调用工具：{ $name }
msg-e8fdbb8c = 未找到 MCP 服务配置文件，已创建默认配置文件{ $mcp_json_file }
msg-cf8aed84 = 收到 MCP 客户端{ $name }终止信号
msg-3d7bcc64 = 正在初始化 MCP 客户端{ $name }失败
msg-1b190842 = MCP服务器{ $name }列出工具响应：{ $tools_res }
msg-6dc4f652 = 已连接 MCP 服务{ $name }工具：{ $tool_names }
msg-a44aa4f2 = 清除 MCP 客户端资源{ $name }：{ $e }。
msg-e9c96c53 = MCP 服务已关闭{ $name }
msg-10f72727 = { $error_msg }
msg-85f156e0 = 正在使用配置测试 MCP 服务器连接：{ $config }
msg-93c54ce0 = 清理MCP客户端测试连接后的残留。
msg-368450ee = 此函数调用工具所属的插件{ $res }已被禁用，请先在管理面板启用再激活此工具。
msg-4ffa2135 = 加载 MCP 配置失败：{ $e }
msg-a486ac39 = 保存 MCP 配置失败：{ $e }
msg-58dfdfe7 = 从 ModelScope 同步了{ $synced_count }一个 MCP 服务器
msg-75f1222f = 未找到可用的 ModelScope MCP 服务器
msg-c9f6cb1d = ModelScope API 请求失败: HTTP{ $res }
msg-c8ebb4f7 = 网络连接错误:{ $e }
msg-0ac6970f = 同步 ModelScope MCP 服务器时发生错误：{ $e }

### astrbot\core\provider\manager.py

msg-9e1a7f1f = Provider{ $provider_id }不存在，无法设置。
msg-5fda2049 = 未知的提供者类型：{ $provider_type }
msg-a5cb19c6 = 未找到 ID 为{ $provider_id }这可能是由于您修改了提供商（模型）ID 导致的。
msg-78b9c276 = { $res }
msg-5bdf8f5c = { $e }
msg-b734a1f4 = 提供商{ $provider_id }配置项 key{ $idx }使用环境变量{ $env_key }但未设置。
msg-664b3329 = 提供商{ $res }已禁用，跳过
msg-f43f8022 = 载入中{ $res }({ $res_2 }) 服务提供商 ...
msg-edd4aefe = 加载{ $res }({ $res_2 }提供商适配器失败：{ $e }可能是由于缺少依赖项。
msg-78e514a1 = 加载{ $res }({ $res_2 }提供商适配器失败：{ $e }原因未知
msg-4636f83c = 未找到适用于{ $res }({ $res_2 }) 的提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。
msg-e9c6c4a2 = 未找到{ $res }的类
msg-f705cf50 = 提供者类{ $cls_type }不是 STTProvider 的子类
msg-d20620aa = 已选择{ $res }({ $res_2 }) 作为当前语音转文本提供商适配器。
msg-afbe5661 = 提供者类{ $cls_type }不是 TTSProvider 的子类
msg-74d437ed = 已选择{ $res }({ $res_2 }) 作为当前文本转语音提供商适配器。
msg-08cd85c9 = 提供者类{ $cls_type }不是 Provider 的子类
msg-16a2b8e0 = 已选择{ $res }({ $res_2 }) 作为当前提供商适配器。
msg-0e1707e7 = 提供者类{ $cls_type }不是EmbeddingProvider的子类
msg-821d06e0 = 提供者类{ $cls_type }不是 RerankProvider 的子类
msg-14c35664 = 未知的提供商类型：{ $res }
msg-186fd5c6 = 实例化{ $res }({ $res_2 }提供商适配器失败：{ $e }
msg-ede02a99 = 用户配置中的提供者：{ $config_ids }
msg-95dc4227 = 自动选择{ $res }作为当前提供商适配器。
msg-a6187bac = 自动选择{ $res }作为当前语音转文本提供商适配器。
msg-bf28f7e2 = 自动选择{ $res }作为当前文本转语音提供商适配器。
msg-dba10c27 = 终止{ $provider_id }Provider Adapter({ $res },{ $res_2 },{ $res_3 }) ...
msg-9d9d9765 = { $provider_id }提供商适配器已终止{ $res },{ $res_2 },{ $res_3 })
msg-925bb70a = 提供商{ $target_prov_ids }已从配置中删除。
msg-a1657092 = 新提供者配置必须包含'id'字段
msg-1486c653 = 提供商ID{ $npid }已存在
msg-f9fc1545 = 提供商ID{ $origin_provider_id }未找到
msg-4e2c657c = 禁用 MCP 服务器时出错

### astrbot\core\provider\provider.py

msg-e6f0c96f = 提供程序类型{ $provider_type_name }未注册
msg-c7953e3f = 批次{ $batch_idx }处理失败，已重试{ $max_retries }次:{ $e }
msg-10f72727 = { $error_msg }
msg-7ff71721 = 重排序提供程序测试失败，未返回任何结果

### astrbot\core\provider\register.py

msg-19ddffc0 = 检测到大模型提供商适配器{ $provider_type_name }已注册，可能发生了大模型提供商适配器类型的命名冲突。
msg-7e134b0d = 服务提供商{ $provider_type_name }已注册

### astrbot\core\provider\sources\anthropic_source.py

msg-d6b1df6e = 无法解析图像数据URI：{ $res }...
msg-6c2c0426 = Anthropic不支持的图像URL格式：{ $res }...
msg-999f7680 = 完成：{ $completion }
msg-8d2c43ec = API返回的completion为空。
msg-26140afc = Anthropic API 返回的 completion 无法解析：{ $completion }。
msg-8e4c8c24 = 工具调用参数 JSON 解析失败:{ $tool_info }
msg-7fc6f623 = 图片{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = 不支持的额外内容块类型：{ $res }

### astrbot\core\provider\sources\azure_tts_source.py

msg-93d9b5cf = [Azure TTS] 使用代理:{ $res }
msg-9eea5bcb = 客户端未初始化。请使用 'async with' 上下文。
msg-fd53d21d = 时间同步失败
msg-77890ac4 = OTTS请求失败:{ $e }
msg-c6ec6ec7 = OTTS未返回音频文件
msg-5ad71900 = 无效的Azure订阅密钥
msg-6416da27 = [Azure TTS Native] 使用代理:{ $res }
msg-90b31925 = 缺少OTTS参数：{ $res }
msg-10f72727 = { $error_msg }
msg-60b044ea = 配置错误：缺少必要参数{ $e }
msg-5c7dee08 = 订阅密钥格式无效，应为32位字母数字或其他[...]格式。

### astrbot\core\provider\sources\bailian_rerank_source.py

msg-dc1a9e6e = 阿里云百炼 API Key 不能为空。
msg-f7079f37 = AstrBot 百炼 Rerank 初始化完成。模型:{ $res }
msg-5b6d35ce = 百炼 API 错误：{ $res }–{ $res_2 }
msg-d600c5e2 = 百炼 Rerank 返回空结果:{ $data }
msg-d3312319 = 结果{ $idx }缺少 relevance_score，使用默认值 0.0
msg-2855fb44 = 解析结果{ $idx }时出错:{ $e }，结果={ $result }
msg-392f26e8 = 百炼 Rerank 消耗 Token:{ $tokens }
msg-595e0cf9 = 百炼 Rerank 客户端会话已关闭，返回空结果。
msg-d0388210 = 文档列表为空，返回空结果。
msg-44d6cc76 = 查询文本为空，返回空结果。
msg-bd8b942a = 文档数量({ $res }超过限制(500)，将截断前500个文档
msg-0dc3bca4 = 百炼 Rerank 请求: query='{ $res }...', 文档数量={ $res_2 }
msg-4a9f4ee3 = 百炼 Rerank 成功返回{ $res }一个结果
msg-fa301307 = 百炼 Rerank 网络请求失败:{ $e }
msg-10f72727 = { $error_msg }
msg-9879e226 = 百炼 Rerank 处理失败:{ $e }
msg-4f15074c = 关闭 百炼 Rerank 客户端会话
msg-d01b1b0f = 关闭百炼Rerank客户端时出错：{ $e }

### astrbot\core\provider\sources\dashscope_tts.py

msg-f23d2372 = Dashscope TTS 模型未配置。
msg-74a7cc0a = 音频合成失败，返回内容为空。可能是模型不受支持或服务不可用。
msg-bc8619d3 = dashscope SDK 缺少 MultiModalConversation 模块。请升级 dashscope 包以使用 Qwen TTS 模型。
msg-95bbf71e = 未为Qwen TTS模型指定语音，使用默认语音'Cherry'。
msg-3c35d2d0 = 模型 ' 的音频合成失败{ $model }'.'{ $response }
msg-16dc3b00 = 无法解码base64音频数据。
msg-26603085 = 无法从URL下载音频{ $url }：{ $e }
msg-78b9c276 = { $res }

### astrbot\core\provider\sources\edge_tts_source.py

msg-f4ab0713 = pyffmpeg 转换失败:{ $e }尝试使用 ffmpeg 命令行进行转换
msg-ddc3594a = [EdgeTTS] FFmpeg 标准输出:{ $res }
msg-1b8c0a83 = FFmpeg错误输出：{ $res }
msg-1e980a68 = [EdgeTTS] 返回值(0代表成功):{ $res }
msg-c39d210c = 生成的WAV文件不存在或为空。
msg-57f60837 = FFmpeg 转换失败：{ $res }
msg-ca94a42a = FFmpeg 转换失败：{ $e }
msg-be660d63 = 音频生成失败：{ $e }

### astrbot\core\provider\sources\fishaudio_tts_api_source.py

msg-c785baf0 = [FishAudio TTS] 使用代理:{ $res }
msg-822bce1c = 无效的FishAudio参考模型ID：'{ $res }请确保ID是32位十六进制字符串（例如：626bb6d3f3364c9cbc3aa6a67300a664）。您可以从 https://fish.audio/zh-CN/discovery 获取有效的模型ID。
msg-5956263b = Fish Audio API请求失败: 状态码{ $res }, 响应内容:{ $error_text }

### astrbot\core\provider\sources\gemini_embedding_source.py

msg-173efb0e = [Gemini Embedding] 使用代理:{ $proxy }
msg-58a99789 = Gemini Embedding API请求失败:{ $res }
msg-5c4ea38e = Gemini Embedding API批量请求失败：{ $res }

### astrbot\core\provider\sources\gemini_source.py

msg-1474947f = [Gemini] 使用代理：{ $proxy }
msg-e2a81024 = 检测到密钥异常({ $res }正在尝试更换 API Key 重试... 当前 Key:{ $res_2 }...
msg-0d388dae = 检测到密钥异常({ $res })，且已没有可用的密钥。 当前密钥：{ $res_2 }...
msg-1465290c = 已达到 Gemini 速率限制，请稍后再试...
msg-7e9c01ca = 流式输出不支持图像模态，已自动降级为文本模态。
msg-89bac423 = 代码执行工具与搜索工具互斥，已忽略搜索工具。
msg-301cf76e = 代码执行工具与URL上下文工具互斥，已忽略URL上下文工具。
msg-356e7b28 = 当前 SDK 版本不支持 URL 上下文工具，已忽略该设置，请升级 google-genai 包。
msg-7d4e7d48 = gemini-2.0-lite 不支持代码执行、搜索工具和URL上下文，将忽略这些设置。
msg-cc5c666f = 已启用原生工具，函数工具将被忽略。
msg-aa7c77a5 = 无效的思考层级：{ $thinking_level }，使用 HIGH
msg-59e1e769 = 文本内容为空，已添加空格占位
msg-34c5c910 = 无法解码谷歌双子座思维签名：{ $e }
msg-a2357584 = assistant 角色的消息内容为空，已添加空格占位
msg-f627f75d = 检测到启用了Gemini原生工具，且上下文中存在函数调用，建议使用 /reset 重置上下文。
msg-cb743183 = 收到的 candidate.content 为空:{ $candidate }
msg-34b367fc = API 返回的 candidate.content 为空。
msg-73541852 = 模型生成内容未通过 Gemini 平台的安全检查
msg-ae3cdcea = 模型生成内容违反 Gemini 平台政策。
msg-5d8f1711 = 收到的 candidate.content.parts 为空:{ $candidate }
msg-57847bd5 = API返回的candidate.content.parts为空。
msg-a56c85e4 = 生成式人工智能结果：{ $result }
msg-42fc0767 = 请求失败，返回的 candidates 为空：{ $result }
msg-faf3a0dd = 请求失败，返回的候选列表为空。
msg-cd690916 = 温度参数已超过最大值2，但复述操作仍被触发。
msg-632e23d7 = 发生复诵，正在提高温度至{ $temperature }重试...
msg-41ff84bc = { $model }不支持系统提示，已自动移除（影响人格设置）。
msg-ef9512f7 = { $model }不支持函数调用，已自动去除。
msg-fde41b1d = { $model }不支持多模态输出，已降级为文本模式。
msg-4e168d67 = 收到的数据块中候选列表为空。{ $chunk }
msg-11af7d46 = 收到的数据块中内容为空:{ $chunk }
msg-8836d4a2 = 请求失败。
msg-757d3828 = 获取模型列表失败：{ $res }
msg-7fc6f623 = 图片{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = 不支持的额外内容块类型：{ $res }

### astrbot\core\provider\sources\gemini_tts_source.py

msg-29fe386a = [Gemini TTS] 使用代理：{ $proxy }
msg-012edfe1 = Gemini TTS API 未返回音频内容。

### astrbot\core\provider\sources\genie_tts.py

msg-583dd8a6 = 请先安装 genie_tts。
msg-935222b4 = 无法加载角色{ $res }：{ $e }
msg-a6886f9e = Genie TTS 未保存到文件。
msg-e3587d60 = Genie TTS 生成失败：{ $e }
msg-3303e3a8 = Genie TTS 无法为以下内容生成音频：{ $text }
msg-1cfe1af1 = Genie TTS 流错误：{ $e }

### astrbot\core\provider\sources\gsvi_tts_source.py

msg-520e410f = GSVI TTS API 请求失败，状态码:{ $res }错误:{ $error_text }

### astrbot\core\provider\sources\gsv_selfhosted_source.py

msg-5fb63f61 = [GSV TTS] 初始化完成
msg-e0c38c5b = [GSV TTS] 初始化失败：{ $e }
msg-4d57bc4f = [GSV TTS] 提供程序 HTTP 会话未就绪或已关闭。
msg-2a4a0819 = [GSV TTS] 请求地址：{ $endpoint }，参数：{ $params }
msg-5fdee1da = [GSV TTS] 请求已发送至{ $endpoint }状态失败{ $res }：{ $error_text }
msg-3a51c2c5 = [GSV TTS] 请求{ $endpoint }第{ $res }第 2 次失败：{ $e }，重试中...
msg-49c1c17a = [GSV TTS] 请求{ $endpoint }最终失败：{ $e }
msg-1beb6249 = [GSV TTS] 成功设置 GPT 模型路径：{ $res }
msg-17f1a087 = [GSV TTS] GPT 模型路径未配置，将使用内置 GPT 模型
msg-ddeb915f = [GSV TTS] 成功设置 SoVITS 模型路径：{ $res }
msg-bee5c961 = [GSV TTS] SoVITS 模型路径未配置，将使用内置 SoVITS 模型
msg-423edb93 = [GSV TTS] 设置模型路径时发生网络错误：{ $e }
msg-7d3c79cb = [GSV TTS] 设置模型路径时发生未知错误：{ $e }
msg-d084916a = [GSV TTS] TTS 文本不能为空
msg-fa20c883 = [GSV TTS] 正在调用语音合成接口，参数：{ $params }
msg-a7fc38eb = [GSV TTS] 合成失败，输入文本：{ $text }，错误信息：{ $result }
msg-a49cb96b = [GSV TTS] 会话已关闭

### astrbot\core\provider\sources\minimax_tts_api_source.py

msg-77c88c8a = 从SSE消息解析JSON数据失败
msg-7873b87b = MiniMax TTS API请求失败:{ $e }

### astrbot\core\provider\sources\openai_embedding_source.py

msg-cecb2fbc = [OpenAI Embedding] 使用代理:{ $proxy }

### astrbot\core\provider\sources\openai_source.py

msg-c891237f = 图片请求失败（{ $reason }已移除图片并重试（保留文本内容）。
msg-d6f6a3c2 = 获取模型列表失败：{ $e }
msg-1f850e09 = API 返回的 completion 类型错误：{ $res }：{ $completion }。
msg-999f7680 = 完成：{ $completion }
msg-844635f7 = 意外的字典格式内容：{ $raw_content }
msg-8d2c43ec = API返回的completion为空。
msg-87d75331 = { $completion_text }
msg-0614efaf = 工具集未提供
msg-c46f067a = API 返回的 completion 因内容安全过滤被拒绝（非 AstrBot）。
msg-647f0002 = API 返回的 completion 无法解析：{ $completion }。
msg-5cc50a15 = API 调用过于频繁，请尝试使用其他 Key 重试。当前 Key:{ $res }
msg-c4e639eb = 上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数:{ $res }
msg-5f8be4fb = { $res }不支持函数工具调用，已自动去除，不影响使用。
msg-45591836 = 该模型似乎不支持函数调用工具。请输入 /tool off_all
msg-6e47d22a = API 调用失败，正在重试{ $max_retries }本次尝试再次失败。
msg-974e7484 = 未知错误
msg-7fc6f623 = 图片{ $image_url }The result obtained is empty and will be ignored.
msg-0b041916 = 不支持的额外内容块类型：{ $res }

### astrbot\core\provider\sources\openai_tts_api_source.py

msg-d7084760 = [OpenAI TTS] 使用代理:{ $proxy }

### astrbot\core\provider\sources\sensevoice_selfhosted_source.py

msg-ee0daf96 = 下载或加载 SenseVoice 模型可能需要一些时间...
msg-cd6da7e9 = SenseVoice 模型加载完成。
msg-28cbbf07 = 文件不存在:{ $audio_url }
msg-d98780e5 = 正在将 silk 文件转换为 wav ...
msg-4e8f1d05 = SenseVoice识别到的文案：{ $res }
msg-55668aa2 = 未能提取到情绪信息
msg-0cdbac9b = 处理音频文件时出错：{ $e }

### astrbot\core\provider\sources\vllm_rerank_source.py

msg-6f160342 = Rerank API 返回了空的列表数据。原始响应:{ $response_data }

### astrbot\core\provider\sources\volcengine_tts.py

msg-4b55f021 = 请求头:{ $headers }
msg-d252d96d = 请求 URL:{ $res }
msg-72e07cfd = 请求体:{ $res }...
msg-fb8cdd69 = 响应状态码:{ $res }
msg-4c62e457 = 响应内容：{ $res }...
msg-1477973b = 火山引擎 TTS API 返回错误：{ $error_msg }
msg-75401c15 = 火山引擎 TTS API 请求失败:{ $res },{ $response_text }
msg-a29cc73d = 火山引擎 TTS 异常详情：{ $error_details }
msg-01433007 = 火山引擎 TTS 异常:{ $e }

### astrbot\core\provider\sources\whisper_api_source.py

msg-28cbbf07 = 文件不存在:{ $audio_url }
msg-b335b8db = 正在使用tencent_silk_to_wav将silk文件转换为wav...
msg-68b5660f = 正在使用convert_to_pcm_wav将amr文件转换为wav...
msg-cad3735e = 无法删除临时文件{ $audio_url }：{ $e }

### astrbot\core\provider\sources\whisper_selfhosted_source.py

msg-27fda50a = 下载或加载 Whisper 模型可能需要一些时间...
msg-4e70f563 = Whisper 模型加载完成。
msg-28cbbf07 = 文件不存在:{ $audio_url }
msg-d98780e5 = 正在将 silk 文件转换为 wav ...
msg-e3e1215c = Whisper 模型未初始化

### astrbot\core\provider\sources\xinference_rerank_source.py

msg-1ec1e6e4 = Xinference 重排：使用 API 密钥进行身份验证。
msg-7bcb6e1b = Xinference 重排：未提供 API 密钥。
msg-b0d1e564 = 模型{ $res }' 已在运行，用户ID为：{ $uid }
msg-16965859 = 启动中{ $res }模型...
msg-7b1dfdd3 = 模型已启动。
msg-3fc7310e = 模型{ $res }'未运行且自动启动已禁用。提供程序将不可用。
msg-15f19a42 = 初始化Xinference模型失败：{ $e }
msg-01af1651 = Xinference 初始化失败，异常信息：{ $e }
msg-2607cc7a = Xinference 重排序模型未初始化。
msg-3d28173b = 重排序API响应：{ $response }
msg-4c63e1bd = Rerank API 返回了空列表。原始响应：{ $response }
msg-cac71506 = Xinference 重排序失败：{ $e }
msg-4135cf72 = Xinference 重排序失败，异常信息：{ $e }
msg-ea2b36d0 = 正在关闭 Xinference 重排客户端...
msg-633a269f = 无法关闭Xinference客户端：{ $e }

### astrbot\core\provider\sources\xinference_stt_provider.py

msg-4e31e089 = Xinference STT：正在使用API密钥进行身份验证。
msg-e291704e = Xinference STT：未提供API密钥。
msg-b0d1e564 = 模型{ $res }' 已在运行，用户ID为：{ $uid }
msg-16965859 = 启动中{ $res }模型...
msg-7b1dfdd3 = 模型已启动。
msg-3fc7310e = 模型{ $res }'未运行且自动启动已禁用。提供程序将不可用。
msg-15f19a42 = 初始化Xinference模型失败：{ $e }
msg-01af1651 = Xinference 初始化失败，异常信息：{ $e }
msg-42ed8558 = Xinference STT 模型未初始化。
msg-bbc43272 = 无法下载音频{ $audio_url }，状态：{ $res }
msg-f4e53d3d = 文件未找到：{ $audio_url }
msg-ebab7cac = 音频字节为空。
msg-7fd63838 = 音频需要转换（{ $conversion_type }正在使用临时文件...
msg-d03c4ede = 正在将silk格式转换为wav格式...
msg-79486689 = 正在将amr转换为wav...
msg-c4305a5b = Xinference 语音转文字结果：{ $text }
msg-d4241bd5 = Xinference STT 转录失败，状态为{ $res }：{ $error_text }
msg-8efe4ef1 = Xinference 语音转文字失败：{ $e }
msg-b1554c7c = Xinference STT 失败，异常信息：{ $e }
msg-9d33941a = 已移除临时文件：{ $temp_file }
msg-7dc5bc44 = 无法删除临时文件{ $temp_file }：{ $e }
msg-31904a1c = 正在关闭 Xinference STT 客户端...
msg-633a269f = 无法关闭Xinference客户端：{ $e }

### astrbot\core\skills\skill_manager.py

msg-ed9670ad = 压缩文件未找到：{ $zip_path }
msg-73f9cf65 = 上传的文件不是有效的zip压缩包。
msg-69eb5f95 = 压缩档案为空。
msg-9e9abb4c = { $top_dirs }
msg-20b8533f = ZIP 归档文件必须包含一个顶级文件夹。
msg-1db1caf7 = 无效的技能文件夹名称。
msg-d7814054 = 压缩包内包含绝对路径。
msg-179bd10e = 压缩档案包含无效的相对路径。
msg-90f2904e = 压缩包包含意外的顶级条目。
msg-95775a4d = 技能文件夹中未找到SKILL.md文件。
msg-a4117c0b = 解压后未找到技能文件夹。
msg-94041ef2 = 技能已存在。

### astrbot\core\star\base.py

msg-57019272 = 获取配置失败：{ $e }

### astrbot\core\star\command_management.py

msg-011581bb = 指定的处理函数不存在或不是指令。
msg-a0c37004 = 指令名不能为空。
msg-ae8b2307 = 指令名 '{ $candidate_full }' 已被其他指令占用。
msg-247926a7 = 别名{ $alias_full }' 已被其他指令占用。
msg-dbd19a23 = 权限类型必须为 admin 或 member。
msg-9388ea1e = 未找到指令所属插件。
msg-0dd9b70d = 指令解析处理函数{ $res }失败，跳过该指令。原因：{ $e }

### astrbot\core\star\config.py

msg-c2189e8d = namespace 不能为空。
msg-97f66907 = namespace 不能以 internal_ 开头。
msg-09179604 = key 仅支持 str 类型。
msg-1163e4f1 = value 仅支持 str、int、float、bool、list 类型。
msg-ed0f93e4 = 配置文件{ $namespace }.json 不存在。
msg-e3b5cdfb = 配置项{ $key }不存在。

### astrbot\core\star\context.py

msg-60eb9e43 = 提供商{ $chat_provider_id }未找到
msg-da70a6fb = 代理未生成最终的LLM响应
msg-141151fe = 提供程序未找到
msg-a5cb19c6 = 未找到 ID 为{ $provider_id }这可能是由于您修改了提供商（模型）ID 导致的。
msg-2a44300b = 该会话来源的对话模型（提供商）类型不正确：{ $res }
msg-37c286ea = 返回的 Provider 不是 TTSProvider 类型。
msg-ff775f3b = 返回的 Provider 不是 STTProvider 类型
msg-fd8c8295 = 无法找到会话的平台{ $res }消息未发送
msg-2b806a28 = 插件(模块路径){ $module_path }) 已添加LLM工具：{ $res }

### astrbot\core\star\session_llm_manager.py

msg-7b90d0e9 = Session{ $session_id }TTS状态已更新为：{ $res }

### astrbot\core\star\session_plugin_manager.py

msg-16cc2a7a = 插件{ $res }在会话中{ $session_id }在中间被禁用，跳过处理器{ $res_2 }

### astrbot\core\star\star_manager.py

msg-bfa28c02 = 未安装 watchfiles，无法实现插件的热重载。
msg-f8e1c445 = 插件热重载监视任务异常：{ $e }
msg-78b9c276 = { $res }
msg-28aeca68 = 检测到文件变化：{ $changes }
msg-aeec7738 = 检测到插件{ $plugin_name }检测到文件变化，正在重载...
msg-4f989555 = 插件{ $d }未找到 main.py 或者{ $d }.py，跳过。
msg-74b32804 = 正在安装插件{ $p }所需的依赖库：{ $pth }
msg-936edfca = 更新插件{ $p }依赖失败。代码：{ $e }
msg-ebd47311 = 插件{ $root_dir_name }导入失败，尝试从已安装依赖恢复:{ $import_exc }
msg-1b6e94f1 = 插件{ $root_dir_name }已从 site-packages 恢复依赖，跳过重新安装。
msg-81b7c9b9 = 插件{ $root_dir_name }依赖恢复失败，正在重新安装依赖：{ $recover_exc }
msg-22fde75d = 插件不存在。
msg-3a307a9e = 插件元数据信息不完整。name、desc、version 和 author 是必填字段。
msg-55e089d5 = 删除模块{ $key }
msg-64de1322 = 删除模块{ $module_name }
msg-66823424 = 模块{ $module_name }未载入
msg-45c8df8d = 插件已清除{ $dir_name }中{ $key }模块
msg-f7d9aa9b = 清理处理器:{ $res }
msg-3c492aa6 = 清理工具:{ $res }
msg-e0002829 = 插件{ $res }未正常终止：{ $e }可能导致该插件运行异常。
msg-0fe27735 = 正在载入插件{ $root_dir_name }...
msg-b2ec4801 = { $error_trace }
msg-db351291 = 插件{ $root_dir_name }导入失败。原因：{ $e }
msg-a3db5f45 = 失败插件仍在插件列表中，正在清理...
msg-58c66a56 = 插件{ $root_dir_name }元数据载入失败：{ $e }使用默认元数据。
msg-da764b29 = { $metadata }
msg-17cd7b7d = 插件{ $res }已禁用。
msg-4baf6814 = 插件{ $path }未通过装饰器注册。尝试通过旧版本方式载入。
msg-840994d1 = 插件未找到{ $plugin_dir_path }的元数据。
msg-944ffff1 = 插入权限过滤器{ $cmd_type }到{ $res }的{ $res_2 }方法。
msg-64edd12c = 钩子（插件加载时触发）{ $res }-{ $res_2 }
msg-db49f7a1 = ----- 插件{ $root_dir_name }加载失败 -----
msg-26039659 = |{ $line }
msg-4292f44d = ----------------------------------
msg-d2048afe = 同步指令配置失败:{ $e }
msg-df515dec = 已清理安装失败的插件目录：{ $plugin_path }
msg-1f2aa1a9 = 清理安装失败插件目录失败:{ $plugin_path }，原因:{ $e }
msg-1e947210 = 已清理安装失败插件的配置：{ $plugin_config_path }
msg-7374541f = 清理安装失败插件配置失败:{ $plugin_config_path }，原因:{ $e }
msg-e871b08f = 读取插件{ $dir_name }README.md 文件失败:{ $e }
msg-70ca4592 = 该插件是 AstrBot 的保留插件，无法卸载。
msg-e247422b = 插件{ $plugin_name }未正常终止{ $e }可能导致资源泄露等问题。
msg-0c25dbf4 = 插件{ $plugin_name }数据不完整，无法卸载。
msg-d6f8142c = 插件已成功移除，但删除插件文件夹失败：{ $e }您可以手动删除位于 addons/plugins/ 下的该文件夹。
msg-6313500c = 插件已删除{ $plugin_name }配置文件
msg-f0f01b67 = 删除插件配置文件失败：{ $e }
msg-c4008b30 = 插件已删除{ $plugin_name }持久化数据 (plugin_data)
msg-88d1ee05 = 删除插件持久化数据失败 (plugin_data):{ $e }
msg-ba805469 = 插件已删除{ $plugin_name }插件持久化数据 (plugins_data)
msg-cf6eb821 = 删除插件持久化数据失败 (plugins_data):{ $e }
msg-e1853811 = 插件已移除{ $plugin_name }处理函数{ $res }({ $res_2 })
msg-95b20050 = 插件已移除{ $plugin_name }平台适配器{ $adapter_name }
msg-9f248e88 = 该插件是 AstrBot 的保留插件，无法更新。
msg-ff435883 = 正在终止插件{ $res }...
msg-355187b7 = 插件{ $res }未激活，无需终止，跳过。
msg-4369864f = hook(on_plugin_unloaded) ->{ $res }-{ $res_2 }
msg-1b95e855 = 插件{ $plugin_name }不存在。
msg-c1bc6cd6 = 检测到插件{ $res }已安装，正在终止旧插件...
msg-4f3271db = 检测到同名插件{ $res }存在于不同目录{ $res_2 }正在终止...
msg-d247fc54 = 读取新插件 metadata.yaml 失败，跳过同名检查：{ $e }
msg-0f8947f8 = 删除插件压缩包失败：{ $e }

### astrbot\core\star\star_tools.py

msg-397b7bf9 = StarTools 未初始化
msg-ca30e638 = 未找到适配器：AiocqhttpAdapter
msg-77ca0ccb = 不支持的平台：{ $platform }
msg-3ed67eb2 = 无法获取调用者模块信息
msg-e77ccce6 = 无法获取模块{ $res }元数据信息
msg-76ac38ee = 无法获取插件名称
msg-751bfd23 = 无法创建目录{ $data_dir }权限不足
msg-68979283 = 无法创建目录{ $data_dir }：{ $e }

### astrbot\core\star\updator.py

msg-66be72ec = 插件{ $res }未指定仓库地址。
msg-7a29adea = 插件{ $res }根目录名称未指定。
msg-99a86f88 = 正在更新插件，路径:{ $plugin_path }仓库地址:{ $repo_url }
msg-df2c7e1b = 删除旧版本插件{ $plugin_path }文件夹创建失败:{ $e }，使用覆盖安装。
msg-b3471491 = 正在解压压缩包:{ $zip_path }
msg-7197ad11 = 删除临时文件:{ $zip_path }和{ $res }
msg-f8a43aa5 = 删除更新文件失败，可以手动删除。{ $zip_path }和{ $res }

### astrbot\core\star\filter\command.py

msg-995944c2 = 参数 '{ $param_name }' (GreedyStr) 必须是最后一个参数。
msg-04dbdc3a = 必要参数缺失。该指令的完整参数如下：{ $res }
msg-bda71712 = parameter{ $param_name }必须是布尔值（true/false, yes/no, 1/0）。
msg-a9afddbf = parameter{ $param_name }类型错误。完整参数：{ $res }

### astrbot\core\star\filter\custom_filter.py

msg-8f3eeb6e = 操作数必须是 CustomFilter 的子类。
msg-732ada95 = CustomFilter类只能与其他CustomFilter类配合使用。
msg-51c0c77d = CustomFilter 类只能与其他 CustomFilter 类配合使用。

### astrbot\core\star\register\star.py

msg-64619f8e = 'register_star' 装饰器已弃用，将在未来版本中移除。

### astrbot\core\star\register\star_handler.py

msg-7ff2d46e = 注册指令{ $command_name }调用子指令时未提供 sub_command 参数。
msg-b68436e1 = 注册裸指令时未提供 command_name 参数。
msg-1c183df2 = { $command_group_name }指令组的子指令组 sub_command 未指定。
msg-9210c7e8 = 根指令组的名称未指定。
msg-678858e7 = 注册指令组失败。
msg-6c3915e0 = LLM 函数工具{ $res }_{ $llm_tool_name }的参数{ $res_2 }缺少类型注释。
msg-1255c964 = LLM 函数工具{ $res }_{ $llm_tool_name }不支持的参数类型：{ $res_2 }

### astrbot\core\utils\history_saver.py

msg-5e287ce4 = 解析对话历史失败：{ $exc }

### astrbot\core\utils\io.py

msg-665b0191 = SSL证书验证失败{ $url }正在禁用SSL验证（CERT_NONE）作为备用方案。这种做法不安全，会使应用程序面临中间人攻击的风险。请检查并解决证书问题。
msg-04ab2fae = 下载文件失败:{ $res }
msg-63dacf99 = 文件大小：{ $res }KB | 文件路径:{ $url }
msg-14c3d0bb = {"000a"}下载进度:{ $res }速度：{ $speed }KB/s
msg-4e4ee68e = SSL 证书验证失败，已关闭 SSL 验证（不安全，仅用于临时下载）。请检查目标服务器的证书配置。
msg-5a3beefb = SSL证书验证失败{ $url }正在回退到未经验证的连接（CERT_NONE）。这是不安全的，会使应用程序面临中间人攻击。请检查远程服务器的证书问题。
msg-315e5ed6 = 准备下载指定发行版本的 AstrBot WebUI 文件:{ $dashboard_release_url }
msg-c709cf82 = 正在准备下载指定版本的 AstrBot WebUI：{ $url }

### astrbot\core\utils\llm_metadata.py

msg-d6535d03 = 成功获取{ $res }个大型语言模型元数据。
msg-8cceaeb0 = 获取LLM元数据失败：{ $e }

### astrbot\core\utils\media_utils.py

msg-2f697658 = [媒体工具] 获取媒体时长：{ $duration_ms }毫秒
msg-52dfbc26 = [媒体工具] 无法获取媒体文件时长:{ $file_path }
msg-486d493a = [媒体工具] ffprobe未安装或不在PATH环境变量中，无法获取媒体时长。请安装ffmpeg: https://ffmpeg.org/
msg-0f9c647b = [媒体工具] 获取媒体时长时出错：{ $e }
msg-aff4c5f8 = [媒体工具] 已清理失败的opus输出文件：{ $output_path }
msg-82427384 = [媒体工具] 清理失败的opus输出文件时出错：{ $e }
msg-215a0cfc = [媒体工具] ffmpeg音频转换失败：{ $error_msg }
msg-8cce258e = ffmpeg 转换失败：{ $error_msg }
msg-f0cfcb92 = [媒体工具] 音频转换成功:{ $audio_path }->{ $output_path }
msg-ead1395b = [媒体工具] ffmpeg未安装或不在PATH环境变量中，无法转换音频格式。请安装ffmpeg: https://ffmpeg.org/
msg-5df3a5ee = 未找到ffmpeg
msg-6322d4d2 = [媒体工具] 转换音频格式时出错：{ $e }
msg-e125b1a5 = [媒体工具] 已清理失败项{ $output_format }输出文件：{ $output_path }
msg-5cf417e3 = [媒体工具] 清理失败{ $output_format }输出文件时出错:{ $e }
msg-3766cbb8 = [媒体工具] ffmpeg视频转换失败：{ $error_msg }
msg-77f68449 = [媒体工具] 视频转换成功:{ $video_path }->{ $output_path }
msg-3fb20b91 = [媒体工具] ffmpeg未安装或不在PATH环境变量中，无法转换视频格式。请安装ffmpeg: https://ffmpeg.org/
msg-696c4a46 = [媒体工具] 转换视频格式时出错：{ $e }
msg-98cc8fb8 = [媒体工具] 清理失败的音频输出文件时出错：{ $e }
msg-3c27d5e8 = [媒体工具] 清理失败的视频封面文件时出错：{ $e }
msg-072774ab = ffmpeg 提取封面失败：{ $error_msg }

### astrbot\core\utils\metrics.py

msg-314258f2 = 保存指标到数据库失败:{ $e }

### astrbot\core\utils\migra_helper.py

msg-497ddf83 = 第三方代理运行器配置迁移失败：{ $e }
msg-78b9c276 = { $res }
msg-e21f1509 = 迁移提供商{ $res }转换为新结构
msg-dd3339e6 = 提供方-源结构迁移已完成
msg-1cb6c174 = 从版本4.5迁移到4.6失败：{ $e }
msg-a899acc6 = Webchat会话迁移失败：{ $e }
msg-b9c52817 = token_usage列迁移失败：{ $e }
msg-d9660ff5 = 迁移提供程序源结构失败：{ $e }

### astrbot\core\utils\network_utils.py

msg-54b8fda8 = [{ $provider_label }网络/代理连接失败 ({ $error_type }代理地址:{ $effective_proxy }错误:{ $error }
msg-ea7c80f1 = [{ $provider_label }网络连接失败 ({ $error_type }错误:{ $error }
msg-f8c8a73c = [{ $provider_label }使用代理：{ $proxy }

### astrbot\core\utils\path_util.py

msg-cf211d0f = 路径映射规则错误：{ $mapping }
msg-ecea161e = 路径映射：{ $url }->{ $srcPath }

### astrbot\core\utils\pip_installer.py

msg-aa9e40b8 = pip 模块不可用 (sys.executable={ $res }, frozen={ $res_2 }ASTRBOT_DESKTOP_CLIENT={ $res_3 })
msg-4c3d7a1c = 读取依赖文件失败，跳过冲突检测：{ $exc }
msg-fbf35dfa = 读取 site-packages 元数据失败，使用回退模块名：{ $exc }
msg-c815b9dc = { $conflict_message }
msg-842a7c69 = 已加载{ $module_name }来自插件站点包：{ $module_location }
msg-d93a8842 = 已恢复依赖项{ $dependency_name }同时优先考虑{ $module_name }来自插件站点包。
msg-7632a3cc = 模块{ $module_name }未在插件站点包中找到：{ $site_packages_path }
msg-cd739739 = 无法优先选择模块{ $module_name }来自插件站点包：{ $reason }
msg-de510412 = 未能为加载器修补 pip distlib 查找器{ $res }({ $package_name }):{ $exc }
msg-d2de9221 = Distlib查找器补丁未对加载器生效{ $res }({ $package_name }).
msg-58ebda51 = 已修补针对冻结加载器的pip distlib查找器：{ $res }({ $package_name })
msg-b1fa741c = 跳过修补distlib查找器，因为_finder_registry不可用。
msg-4ef0e609 = 跳过修补distlib查找器，因为注册API不可用。
msg-b8c741dc = Pip 包管理器: pip{ $res }
msg-6b72a960 = 安装失败，错误码：{ $result_code }
msg-c8325399 = { $line }

### astrbot\core\utils\session_waiter.py

msg-0c977996 = 等待超时
msg-ac406437 = session_filter 必须是 SessionFilter

### astrbot\core\utils\shared_preferences.py

msg-9a1e6a9a = 获取特定偏好设置时，scope_id 和 key 不能为 None。

### astrbot\core\utils\temp_dir_cleaner.py

msg-752c7cc8 = 无效{ $res }={ $configured }，回退到{ $res_2 }MB。
msg-b1fc3643 = 跳过临时文件{ $path }由于状态错误：{ $e }
msg-5e61f6b7 = 无法删除临时文件{ $res }：{ $e }
msg-391449f0 = 临时目录超出限制（{ $total_size }>{ $limit }). 已移除{ $removed_files }文件已发布{ $released }字节（目标{ $target_release }字节数。
msg-aaf1e12a = TempDirCleaner 已启动。间隔={ $res }s cleanup_ratio={ $res_2 }
msg-e6170717 = TempDirCleaner 运行失败：{ $e }
msg-0fc33fbc = 临时目录清理器已停止。

### astrbot\core\utils\tencent_record_helper.py

msg-377ae139 = pilk 模块未安装，请前往管理面板->平台日志->安装pip库 安装 pilk 这个库
msg-f4ab0713 = pyffmpeg 转换失败:{ $e }尝试使用 ffmpeg 命令行进行转换
msg-33c88889 = [FFmpeg] 标准输出：{ $res }
msg-2470430c = [FFmpeg] 标准错误输出：{ $res }
msg-1321d5f7 = [FFmpeg] 返回码：{ $res }
msg-c39d210c = 生成的WAV文件不存在或为空。
msg-6e04bdb8 = 未安装 pilk：请运行 pip install pilk

### astrbot\core\utils\trace.py

msg-fffce1b9 = [trace]{ $payload }
msg-78b9c276 = { $res }

### astrbot\core\utils\webhook_utils.py

msg-64c7ddcf = 获取 callback_api_base 失败:{ $e }
msg-9b5d1bb1 = 获取 dashboard 端口失败:{ $e }
msg-3db149ad = 获取仪表板 SSL 配置失败：{ $e }
msg-3739eec9 = { $display_log }

### astrbot\core\utils\quoted_message\extractor.py

msg-80530653 = quoted_message_parser：停止获取嵌套的转发消息{ $max_fetch }跳数

### astrbot\core\utils\quoted_message\image_resolver.py

msg-6dfa6994 = quoted_message_parser: 跳过非图像本地路径引用{ $res }
msg-9326ec62 = quoted_message_parser: 无法解析引用的图片 ref={ $res }之后{ $res_2 }操作

### astrbot\core\utils\quoted_message\onebot_client.py

msg-03ad9f29 = quoted_message_parser: 操作{ $action }参数传递失败{ $res }：{ $exc }
msg-519d0dec = quoted_message_parser: 针对该操作的所有尝试均失败{ $action }，last_params={ $res }，错误={ $last_error }

### astrbot\core\utils\t2i\local_strategy.py

msg-94a58a1e = 无法加载任何字体
msg-d5c7d255 = 加载图像失败：HTTP{ $res }
msg-7d59d0a0 = 加载图片失败：{ $e }

### astrbot\core\utils\t2i\network_strategy.py

msg-be0eeaa7 = 成功获取{ $res }官方T2I端点。
msg-3bee02f4 = 获取官方端点失败：{ $e }
msg-829d3c71 = HTTP{ $res }
msg-05fb621f = 端点{ $endpoint }失败：{ $e }正在尝试下一个...
msg-9a836926 = 所有端点均失败：{ $last_exception }

### astrbot\core\utils\t2i\renderer.py

msg-4225607b = 通过AstrBot API渲染图像失败：{ $e }正在回退到本地渲染。

### astrbot\core\utils\t2i\template_manager.py

msg-47d72ff5 = 模板名称包含非法字符。
msg-d1b2131b = 模板不存在。
msg-dde05b0f = 同名模板已存在。
msg-0aa209bf = 用户模板不存在，无法删除。

### astrbot\dashboard\server.py

msg-e88807e2 = 未找到该路由
msg-06151c57 = 缺少API密钥
msg-88dca3cc = 无效的API密钥
msg-fd267dc8 = API密钥权限不足
msg-076fb3a3 = 未授权
msg-6f214cc1 = 令牌已过期
msg-5041dc95 = Token 无效
msg-1241c883 = 检查端口{ $port }发生错误：{ $e }
msg-7c3ba89d = 已为仪表板初始化随机JWT密钥。
msg-a3adcb66 = WebUI 已被禁用
msg-44832296 = 正在启动 WebUI，监听地址：{ $scheme }//{ $host }：{ $port }
msg-3eed4a73 = 提示: WebUI 将监听所有网络接口，请注意安全。（可在 data/cmd_config.json 中配置 dashboard.host 以修改 host）
msg-289a2fe8 = {"\u000a"}错误：端口{ $port }已被占用{"000a"}占用信息: {"\u000a"}{ $process_info }请确保：{"\u000a"}1. 没有其他 AstrBot 实例正在运行{"\u000a"}2. 端口{ $port }未被其他程序占用{"000a"}3. 如需使用其他端口，请修改配置文件
msg-6d1dfba8 = 端口{ $port }已被占用
msg-c0161c7c = { $display }
msg-ac4f2855 = 当 dashboard.ssl.enable 为 true 时，必须配置 cert_file 和 key_file。
msg-3e87aaf8 = SSL 证书文件不存在：{ $cert_path }
msg-5ccf0a9f = SSL 私钥文件不存在：{ $key_path }
msg-5e4aa3eb = SSL CA 证书文件不存在：{ $ca_path }
msg-cb049eb2 = AstrBot WebUI 已优雅关闭

### astrbot\dashboard\utils.py

msg-32a21658 = 缺少必要的库以生成 t-SNE 可视化。请安装 matplotlib 和 scikit-learn：{ $e }
msg-aa3a3dbf = 知识库未找到
msg-0e404ea3 = FAISS 索引不存在:{ $index_path }
msg-8d92420c = 索引为空
msg-24c0450e = 提取{ $res }一个用于可视化的向量...
msg-632d0acf = 开始 t-SNE 降维...
msg-61f0449f = 生成可视化图表...
msg-4436ad2b = 生成 t-SNE 可视化时出错：{ $e }
msg-78b9c276 = { $res }

### astrbot\dashboard\routes\api_key.py

msg-8e0249fa = 至少需要一个有效的作用域
msg-1b79360d = 无效的作用域
msg-d6621696 = expires_in_days 必须为整数
msg-33605d95 = expires_in_days 必须大于 0
msg-209030fe = 缺少密钥：key_id
msg-24513a81 = API密钥未找到

### astrbot\dashboard\routes\auth.py

msg-ee9cf260 = 为了确保安全，请尽快修改默认密码。
msg-87f936b8 = 用户名或密码错误
msg-1198c327 = 您不能在演示模式下执行此操作。
msg-25562cd3 = 原密码错误
msg-d31087d2 = 新用户名和新密码不能同时为空。
msg-b512c27e = 两次输入的新密码不一致。
msg-7b947d8b = JWT密钥未在cmd_config中设置。

### astrbot\dashboard\routes\backup.py

msg-6920795d = 清理过期的上传会话：{ $upload_id }
msg-3e96548d = 清理过期上传会话失败：{ $e }
msg-259677a9 = 清理分片目录失败:{ $e }
msg-d7263882 = 读取备份清单失败：{ $e }
msg-40f76598 = 跳过无效备份文件:{ $filename }
msg-18a49bfc = 获取备份列表失败：{ $e }
msg-78b9c276 = { $res }
msg-6e08b5a5 = 创建备份失败:{ $e }
msg-9cce1032 = 后台导出任务{ $task_id }失败:{ $e }
msg-55927ac1 = 缺少备份文件
msg-374cab8a = 请上传 ZIP 格式的备份文件。
msg-d53d6730 = 上传的备份文件已保存：{ $unique_filename }(原始名称:{ $res })
msg-98e64c7f = 上传备份文件失败：{ $e }
msg-49c3b432 = 缺少 filename 参数
msg-df33d307 = 无效的文件大小
msg-162ad779 = 初始化分片上传: upload_id={ $upload_id }，文件名={ $unique_filename }，total_chunks={ $total_chunks }
msg-de676924 = 初始化分片上传失败:{ $e }
msg-eecf877c = 缺少必要参数
msg-f175c633 = 无效的分片索引
msg-ad865497 = 缺少分片数据
msg-947c2d56 = 上传的会话不存在或已过期。
msg-f3a464a5 = 分片索引超出范围
msg-7060da1d = 接收分片: upload_id={ $upload_id }，块={ $res }/{ $total_chunks }
msg-06c107c1 = 上传分片失败：{ $e }
msg-f040b260 = 已标记备份为上传来源:{ $zip_path }
msg-559c10a8 = 标记备份来源失败：{ $e }
msg-d1d752ef = 缺少 upload_id 参数
msg-390ed49a = 分片不完整，缺少:{ $res }...
msg-8029086a = 分片上传完成:{ $filename }，大小={ $file_size }，块={ $total }
msg-4905dde5 = Failed to complete multipart upload:{ $e }
msg-b63394b1 = 取消分片上传:{ $upload_id }
msg-2b39da46 = 取消上传失败:{ $e }
msg-f12b1f7a = 无效的文件名
msg-44bb3b89 = 备份文件不存在:{ $filename }
msg-b005980b = 预检查备份文件失败:{ $e }
msg-65b7ede1 = 请先确认导入。导入将清空并覆盖现有数据，此操作不可撤销。
msg-b152e4bf = 导入备份失败:{ $e }
msg-5e7f1683 = 后台导入任务{ $task_id }失败:{ $e }
msg-6906aa65 = 缺少参数 task_id
msg-5ea3d72c = 未找到该任务
msg-f0901aef = 获取任务进度失败:{ $e }
msg-8d23792b = 缺少参数 filename
msg-4188ede6 = 缺少参数 token
msg-0c708312 = 服务器配置错误
msg-cc228d62 = Token 已过期，请刷新页面后重试。
msg-5041dc95 = Token 无效
msg-96283fc5 = 备份文件不存在
msg-00aacbf8 = 下载备份失败：{ $e }
msg-3ea8e256 = 删除备份失败：{ $e }
msg-e4a57714 = 缺少参数 new_name
msg-436724bb = 新文件名无效
msg-9f9d8558 = 文件名{ $new_filename }' 已存在
msg-a5fda312 = 备份文件重命名：{ $filename }->{ $new_filename }
msg-e7c82339 = 重命名备份失败：{ $e }

### astrbot\dashboard\routes\chat.py

msg-a4a521ff = 缺少键：文件名
msg-c9746528 = 无效的文件路径
msg-3c2f6dee = 文件访问错误
msg-e5b19b36 = 缺少键值：attachment_id
msg-cfa38c4d = 附件未找到
msg-377a7406 = 缺少键：文件
msg-bae87336 = 创建附件失败
msg-5c531303 = 缺少JSON请求体
msg-1c3efd8f = 缺少键：消息或文件
msg-04588d0f = 缺少键值：session_id 或 conversation_id
msg-c6ec40ff = 消息内容为空（不允许仅回复）
msg-2c3fdeb9 = 消息均为空
msg-9bc95e22 = session_id 为空
msg-344a401b = [WebChat] 用户{ $username }断开聊天长连接。
msg-6b54abec = WebChat 流错误：{ $e }
msg-53509ecb = 网络聊天流消息ID不匹配
msg-1211e857 = [WebChat] 用户{ $username }断开聊天长连接。{ $e }
msg-be34e848 = 提取网页搜索引用失败：{ $e }
msg-80bbd0ff = WebChat 流意外错误：{ $e }
msg-dbf41bfc = 缺少键值：session_id
msg-d922dfa3 = 会话{ $session_id }未找到
msg-c52a1454 = 权限被拒绝
msg-e800fd14 = 删除UMO路由失败{ $unified_msg_origin }在会话清理期间：{ $exc }
msg-44c45099 = 无法删除附件文件{ $res }：{ $e }
msg-f033d8ea = 获取附件失败：{ $e }
msg-e6f655bd = 删除附件失败：{ $e }
msg-a6ef3b67 = 缺少键：display_name

### astrbot\dashboard\routes\chatui_project.py

msg-04827ead = 缺少键：title
msg-34fccfbb = 缺少键：project_id
msg-a7c08aee = 项目{ $project_id }未找到
msg-c52a1454 = 权限被拒绝
msg-dbf41bfc = 缺少键值：session_id
msg-d922dfa3 = 会话{ $session_id }未找到

### astrbot\dashboard\routes\command.py

msg-1d47363b = handler_full_name 与 enabled 均为必填。
msg-35374718 = handler_full_name 与 new_name 均为必填。
msg-f879f2f4 = handler_full_name 与 permission 均为必填。

### astrbot\dashboard\routes\config.py

msg-680e7347 = 配置项{ $path }{ $key }无类型定义，跳过校验
msg-ef2e5902 = 正在保存配置，is_core={ $is_core }
msg-78b9c276 = { $res }
msg-acef166d = 验证配置时出现异常：{ $e }
msg-42f62db0 = 格式校验未通过:{ $errors }
msg-3e668849 = 缺少配置数据
msg-196b9b25 = 缺少 provider_source_id
msg-dbbbc375 = 未找到对应的提供程序源
msg-a77f69f4 = 缺少 original_id
msg-96f154c4 = 缺少或错误的配置数据
msg-c80b2c0f = 提供者源ID '{ $res }' 已存在，请尝试其他ID。
msg-537b700b = 路由表数据缺失或错误
msg-b5079e61 = 更新路由表失败:{ $e }
msg-cf97d400 = 缺少 UMO 或配置文件 ID
msg-2a05bc8d = 缺少 UMO
msg-7098aa3f = 删除路由表项失败：{ $e }
msg-902aedc3 = 缺少配置文件 ID
msg-b9026977 = abconf_id 不能为空
msg-acf0664a = 删除失败
msg-59c93c1a = 删除配置文件失败：{ $e }
msg-930442e2 = 更新失败
msg-7375d4dc = 更新配置文件失败:{ $e }
msg-53a8fdb2 = 正在尝试检查提供商：{ $res }(ID:{ $res_2 }类型：{ $res_3 }，模型：{ $res_4 })
msg-8b0a48ee = 提供商{ $res }(ID:{ $res_2 }) 可用。
msg-7c7180a7 = 提供商{ $res }(ID:{ $res_2 }) 不可用。错误：{ $error_message }
msg-1298c229 = 回溯追踪{ $res }：{ $res_2 }
msg-d7f9a42f = { $message }
msg-cd303a28 = API调用：/config/provider/check_one id={ $provider_id }
msg-55b8107a = ID为'{ $provider_id }在provider_manager中未找到'。
msg-d1a98a9b = ID为'{ $provider_id }' 未找到
msg-cb9c402c = 缺少参数 provider_type
msg-e092d4ee = 缺少参数 provider_id
msg-1ff28fed = 未找到 ID 为{ $provider_id }提供商
msg-92347c35 = Provider{ $provider_id }类型不支持获取模型列表
msg-d0845a10 = 缺少参数 provider_config
msg-5657fea4 = provider_config 缺少 type 字段
msg-09ed9dc7 = Provider adapter loading failed, please check the provider type configuration or view the server logs.
msg-1cce1cd4 = 未找到适用于{ $provider_type }Provider Adapter
msg-8361e44d = 未找到{ $provider_type }的类
msg-4325087c = Provider 不是 EmbeddingProvider 类型
msg-a9873ea4 = 检测到{ $res }嵌入向量维度为{ $dim }
msg-d170e384 = 获取嵌入维度失败：{ $e }
msg-abfeda72 = 缺少参数 source_id
msg-0384f4c9 = 未找到 ID 为{ $provider_source_id }提供者来源
msg-aec35bdb = provider_source 缺少 type 字段
msg-cbb9d637 = 动态导入提供商适配器失败：{ $e }
msg-468f64b3 = Provider{ $provider_type }无法获取模型列表
msg-cb07fc1c = 已获取 provider_source{ $provider_source_id }模型列表:{ $models }
msg-d2f6e16d = 获取模型列表失败：{ $e }
msg-25ea8a96 = 不支持的权限范围：{ $scope }
msg-23c8933f = 缺少名称或关键参数
msg-536e77ae = 插件{ $name }未找到或未配置
msg-1b6bc453 = 配置项未找到或非文件类型
msg-fc0a457e = 未上传任何文件
msg-31c718d7 = 无效的名称参数
msg-e1edc16e = 缺少名称参数
msg-8e634b35 = 无效的路径参数
msg-0b52a254 = 插件{ $name }未找到
msg-bff0e837 = 参数错误
msg-2f29d263 = 机器人名称不允许修改
msg-1478800f = 未找到对应平台
msg-ca6133f7 = 缺少参数 id
msg-1199c1f9 = 正在使用缓存的平台徽标令牌{ $res }
msg-889a7de5 = 平台类未找到{ $res }
msg-317f359c = 平台徽标令牌已注册{ $res }
msg-323ec1e2 = 平台{ $res }未找到徽标文件：{ $logo_file_path }
msg-bc6d0bcf = 无法导入平台所需的模块{ $res }：{ $e }
msg-b02b538d = 平台文件系统错误{ $res }徽标：{ $e }
msg-31123607 = 平台徽标注册时发生意外错误{ $res }：{ $e }
msg-af06ccab = 配置文件{ $conf_id }不存在
msg-082a5585 = 插件{ $plugin_name }不存在
msg-ca334960 = 插件{ $plugin_name }未配置注册信息

### astrbot\dashboard\routes\conversation.py

msg-62392611 = 数据库查询出错：{ $e }：{ $res }
msg-b21b052b = 数据库查询出错：{ $e }
msg-10f72727 = { $error_msg }
msg-036e6190 = 获取对话列表失败:{ $e }
msg-a16ba4b4 = 缺少必要参数：user_id 和 cid
msg-9a1fcec9 = 对话不存在
msg-73a8a217 = 获取对话详情失败:{ $e }：{ $res }
msg-976cd580 = 获取对话详情失败:{ $e }
msg-c193b9c4 = 更新对话信息失败:{ $e }：{ $res }
msg-9f96c4ee = 更新对话信息失败:{ $e }
msg-e1cb0788 = 批量删除时，conversations参数不能为空。
msg-38e3c4ba = 删除对话失败:{ $e }：{ $res }
msg-ebf0371a = 删除对话失败:{ $e }
msg-af54ee29 = 缺少必要参数: history
msg-b72552c8 = history 必须是有效的 JSON 字符串或数组
msg-fdf757f3 = 更新对话历史失败:{ $e }：{ $res }
msg-33762429 = 更新对话历史失败:{ $e }
msg-498f11f8 = 导出列表不能为空
msg-98aa3644 = 导出对话失败: user_id={ $user_id }, cid={ $cid }，错误={ $e }
msg-ed77aa37 = 未成功导出任何对话。
msg-f07b18ee = 批量导出对话失败:{ $e }：{ $res }
msg-85dc73fa = 批量导出对话失败:{ $e }

### astrbot\dashboard\routes\cron.py

msg-fb5b419b = Cron管理器未初始化
msg-78b9c276 = { $res }
msg-112659e5 = 无法列出作业：{ $e }
msg-8bc87eb5 = 无效负载
msg-29f616c2 = 需要会话
msg-ae7c99a4 = 当 run_once=true 时，必须指定 run_at。
msg-4bb8c206 = 当 run_once=false 时，cron_expression 是必需的
msg-13fbf01e = run_at 必须是 ISO 格式的日期时间
msg-da14d97a = 创建作业失败：{ $e }
msg-804b6412 = 作业未找到
msg-94b2248d = 更新作业失败：{ $e }
msg-42c0ee7a = 删除作业失败：{ $e }

### astrbot\dashboard\routes\file.py

msg-78b9c276 = { $res }

### astrbot\dashboard\routes\knowledge_base.py

msg-ce669289 = 上传文档{ $res }失败:{ $e }
msg-87e99c2d = 后台任务上传{ $task_id }失败:{ $e }
msg-78b9c276 = { $res }
msg-d5355233 = 导入文档{ $file_name }失败:{ $e }
msg-5e7f1683 = 后台导入任务{ $task_id }失败:{ $e }
msg-e1949850 = 获取知识库列表失败:{ $e }
msg-299af36d = 知识库名称不能为空
msg-faf380ec = 缺少参数 embedding_provider_id
msg-9015b689 = 嵌入模型不存在或类型错误({ $res })
msg-a63b3aa9 = 嵌入向量维度不匹配，实际为{ $res }，然而配置是{ $res_2 }
msg-9b281e88 = 测试嵌入模型失败：{ $e }
msg-d3fb6072 = 重排序模型不存在。
msg-fbec0dfd = 重排序模型返回结果异常
msg-872feec8 = 测试重排序模型失败：{ $e }请检查平台日志输出。
msg-a4ac0b9e = 创建知识库失败:{ $e }
msg-c8d487e9 = 缺少参数 kb_id
msg-978b3c73 = 知识库不存在
msg-2137a3e6 = 获取知识库详情失败:{ $e }
msg-e7cf9cfd = 至少需要提供一个更新字段。
msg-d3d82c22 = 知识库更新失败：{ $e }
msg-5d5d4090 = 删除知识库失败：{ $e }
msg-787a5dea = 获取知识库统计失败:{ $e }
msg-97a2d918 = 获取文档列表失败：{ $e }
msg-b170e0fa = Content-Type 必须为 multipart/form-data
msg-5afbfa8e = 缺少文件
msg-6636fd31 = 最多只能上传10个文件
msg-975f06d7 = 上传文档失败：{ $e }
msg-35bacf60 = 缺少参数 documents 或格式错误
msg-6cc1edcd = 文档格式错误，必须包含 file_name 和 chunks
msg-376d7d5f = chunks 必须是列表
msg-e7e2f311 = chunks 必须是非空字符串列表
msg-42315b8d = 导入文档失败：{ $e }
msg-6906aa65 = 缺少参数 task_id
msg-5ea3d72c = 未找到该任务
msg-194def99 = 获取上传进度失败：{ $e }
msg-df6ec98e = 缺少参数 doc_id
msg-7c3cfe22 = 文档不存在
msg-b54ab822 = 获取文档详情失败:{ $e }
msg-0ef7f633 = 删除文档失败：{ $e }
msg-2fe40cbd = 缺少参数 chunk_id
msg-fc13d42a = 删除文本块失败：{ $e }
msg-4ef8315b = 获取块列表失败:{ $e }
msg-b70a1816 = 缺少参数 query
msg-82ee646e = 缺少参数 kb_names 或格式错误
msg-07a61a9a = t-SNE 可视化生成失败：{ $e }
msg-20a3b3f7 = 检索失败:{ $e }
msg-1b76f5ab = 缺少参数 url
msg-5dc86dc6 = 从URL上传文档失败：{ $e }
msg-890b3dee = 后台URL上传任务{ $task_id }失败:{ $e }

### astrbot\dashboard\routes\live_chat.py

msg-40f242d5 = [在线聊天]{ $res }开始说话 时间戳={ $stamp }
msg-a168d76d = [实时聊天] 时间戳不匹配或用户未处于发言状态：{ $stamp }vs{ $res }
msg-e01b2fea = [实时聊天] 没有音频帧数据
msg-33856925 = [实时聊天] 音频文件已保存：{ $audio_path }, 大小:{ $res }字节
msg-9e9b7e59 = [实时聊天] 组装 WAV 文件失败：{ $e }
msg-21430f56 = [实时聊天] 已删除临时文件：{ $res }
msg-6b4f88bc = [在线聊天] 删除临时文件失败：{ $e }
msg-0849d043 = [实时聊天] WebSocket 连接已建立:{ $username }
msg-5477338a = [实时聊天] WebSocket 错误:{ $e }
msg-fdbfdba8 = [实时聊天] WebSocket 连接已关闭：{ $username }
msg-7be90ac0 = [实时聊天] start_speaking 缺少时间戳
msg-8215062a = [实时聊天] 解码音频数据失败:{ $e }
msg-438980ea = [实时聊天] end_speaking 缺少时间戳
msg-b35a375c = [实时聊天] 用户打断：{ $res }
msg-2c3e7bbc = [实时聊天] STT 提供商未配置
msg-0582c8ba = [实时聊天] STT 识别结果为空
msg-57c2b539 = [实时聊天] STT 结果：{ $user_text }
msg-6b7628c6 = [实时聊天] 检测到用户中断
msg-2cab2269 = [实时聊天] 消息 ID 不匹配:{ $result_message_id }不等于{ $message_id }
msg-74c2470e = [实时聊天] 解析 AgentStats 失败:{ $e }
msg-4738a2b3 = [实时聊天] 解析 TTSStats 失败:{ $e }
msg-944d5022 = [实时聊天] 开始播放音频流
msg-009104d8 = [实时聊天] 机器人回复完成：{ $bot_text }
msg-0c4c3051 = [实时聊天] 音频处理失败：{ $e }
msg-140caa36 = [实时聊天] 保存中断消息：{ $interrupted_text }
msg-869f51ea = [在线聊天] 用户消息：{ $user_text }(session:{ $res }, ts:{ $timestamp })
msg-d26dee52 = [实时聊天] 机器人消息（中断）：{ $interrupted_text }(session:{ $res }, ts:{ $timestamp })
msg-1377f378 = [实时聊天] 记录消息失败:{ $e }

### astrbot\dashboard\routes\log.py

msg-5bf500c1 = Log SSE 历史补发错误:{ $e }
msg-e4368397 = 日志 SSE 连接错误：{ $e }
msg-547abccb = 获取日志历史失败：{ $e }
msg-cb5d4ebb = 获取 Trace 设置失败:{ $e }
msg-7564d3b0 = 请求数据为空
msg-d2a1cd76 = 更新 Trace 设置失败:{ $e }

### astrbot\dashboard\routes\open_api.py

msg-855e0b38 = 无法创建聊天会话{ $session_id }：{ $e }
msg-fc15cbcd = { $username_err }
msg-bc3b3977 = 用户名无效
msg-2cd6e70f = { $ensure_session_err }
msg-53632573 = { $resolve_err }
msg-d4765667 = 未能更新聊天配置路由{ $umo }随着{ $config_id }：{ $e }
msg-7c7a9f55 = 更新聊天配置路由失败：{ $e }
msg-74bff366 = 页码和每页大小必须是整数
msg-1507569c = 消息为空
msg-1389e46a = 消息必须是字符串或列表
msg-697561eb = 消息部分必须是一个对象
msg-2c4bf283 = 回复部分缺少消息ID
msg-60ddb927 = 不支持的消息部件类型：{ $part_type }
msg-cf310369 = 附件未找到：{ $attachment_id }
msg-58e0b84a = { $part_type }部分缺失附件ID
msg-e565c4b5 = 文件未找到：{ $file_path }
msg-c6ec40ff = 消息内容为空（不允许仅回复）
msg-2b00f931 = 缺少键：message
msg-a29d9adb = 缺少键值：umo
msg-4990e908 = 无效的umo：{ $e }
msg-45ac857c = 机器人未找到或未在平台上运行：{ $platform_id }
msg-ec0f0bd2 = Open API 发送消息失败：{ $e }
msg-d04109ab = 发送消息失败：{ $e }

### astrbot\dashboard\routes\persona.py

msg-4a12aead = 获取人格列表失败：{ $e }：{ $res }
msg-c168407f = 获取人格列表失败：{ $e }
msg-63c6f414 = 缺少必要参数：persona_id
msg-ce7da6f3 = 人格不存在。
msg-9c07774d = 获取人格详情失败:{ $e }：{ $res }
msg-ee3b44ad = 获取人格详情失败:{ $e }
msg-ad455c14 = 人格ID不能为空。
msg-43037094 = 系统提示词不能为空
msg-ec9dda44 = 预设对话数量必须为偶数（用户和助手轮流对话）。
msg-26b214d5 = 创建人格失败：{ $e }：{ $res }
msg-8913dfe6 = 创建人格失败：{ $e }
msg-3d94d18d = 更新人格失败:{ $e }：{ $res }
msg-f2cdfbb8 = 更新人格失败:{ $e }
msg-51d84afc = 删除角色失败:{ $e }：{ $res }
msg-8314a263 = 删除角色失败:{ $e }
msg-b8ecb8f9 = 移动人格失败：{ $e }：{ $res }
msg-ab0420e3 = 移动人格失败：{ $e }
msg-e5604a24 = 获取文件夹列表失败:{ $e }：{ $res }
msg-4d7c7f4a = 获取文件夹列表失败:{ $e }
msg-cf0ee4aa = 获取文件夹树失败:{ $e }：{ $res }
msg-bb515af0 = 获取文件夹树失败:{ $e }
msg-c92b4863 = 缺少必要参数: folder_id
msg-77cdd6fa = 文件夹不存在。
msg-2d34652f = 获取文件夹详情失败:{ $e }：{ $res }
msg-650ef096 = 获取文件夹详情失败:{ $e }
msg-27c413df = 文件夹名称不能为空
msg-b5866931 = 创建文件夹失败:{ $e }：{ $res }
msg-5e57f3b5 = 创建文件夹失败:{ $e }
msg-9bd8f820 = 更新文件夹失败：{ $e }：{ $res }
msg-1eada044 = 更新文件夹失败：{ $e }
msg-9cef0256 = 删除文件夹失败：{ $e }：{ $res }
msg-22020727 = 删除文件夹失败：{ $e }
msg-7a69fe08 = items 不能为空
msg-e71ba5c2 = 每个条目必须包含 id、type 和 sort_order 字段。
msg-dfeb8320 = type 字段必须是 'persona' 或 'folder'
msg-aec43ed3 = 更新排序失败：{ $e }：{ $res }
msg-75ec4427 = 更新排序失败：{ $e }

### astrbot\dashboard\routes\platform.py

msg-bcc64513 = 未找到 webhook_uuid 为{ $webhook_uuid }的平台
msg-1478800f = 未找到对应平台
msg-378cb077 = 平台{ $res }未实现 webhook_callback 方法
msg-2d797305 = 平台不支持统一的 Webhook 模式。
msg-83f8dedf = 处理 webhook 回调时发生错误:{ $e }
msg-af91bc78 = 回调处理失败
msg-136a952f = 获取平台统计信息失败：{ $e }
msg-60bb0722 = 获取统计信息失败:{ $e }

### astrbot\dashboard\routes\plugin.py

msg-1198c327 = 您不能在演示模式下执行此操作。
msg-adce8d2f = 缺少插件目录名
msg-2f1b67fd = 重载失败:{ $err }
msg-71f9ea23 = /api/plugin/reload-failed:{ $res }
msg-27286c23 = /api/plugin/reload:{ $res }
msg-b33c0d61 = 缓存MD5匹配，使用缓存的插件市场数据。
msg-64b4a44c = 远程插件市场数据为空：{ $url }
msg-fdbffdca = 成功获取远程插件市场数据，包含{ $res }一个插件
msg-48c42bf8 = Request{ $url }失败，状态码：{ $res }
msg-6ac25100 = Request{ $url }失败，错误：{ $e }
msg-7e536821 = 远程插件市场数据获取失败，使用缓存数据。
msg-d4b4c53a = 获取插件列表失败，且无可用缓存数据。
msg-37f59b88 = Failed to load cache MD5:{ $e }
msg-8048aa4c = Failed to retrieve remote MD5:{ $e }
msg-593eacfd = 缓存文件中未找到MD5信息。
msg-dedcd957 = 无法获取远程MD5，将使用缓存
msg-21d7e754 = 插件数据MD5：本地={ $cached_md5 }, remote={ $remote_md5 }, valid={ $is_valid }
msg-0faf4275 = 检查缓存有效性失败：{ $e }
msg-e26aa0a5 = 加载缓存文件:{ $cache_file }缓存时间：{ $res }
msg-23d627a1 = 加载插件市场缓存失败:{ $e }
msg-22d12569 = 插件市场数据已缓存至：{ $cache_file }，MD5：{ $md5 }
msg-478c99a9 = 保存插件市场缓存失败:{ $e }
msg-3838d540 = 获取插件 Logo 失败:{ $e }
msg-da442310 = 正在安装插件{ $repo_url }
msg-e0abd541 = 安装插件{ $repo_url }成功。
msg-78b9c276 = { $res }
msg-acfcd91e = 正在安装用户上传的插件{ $res }
msg-48e05870 = 安装插件{ $res }成功
msg-8af56756 = 正在卸载插件{ $plugin_name }
msg-6d1235b6 = 卸载插件{ $plugin_name }成功
msg-7055316c = 正在更新插件{ $plugin_name }
msg-d258c060 = 更新插件{ $plugin_name }成功。
msg-398370d5 = /api/plugin/update:{ $res }
msg-2d225636 = 插件列表不能为空
msg-32632e67 = 批量更新插件{ $name }
msg-08dd341c = /api/plugin/update-all: 更新插件{ $name }失败:{ $res }
msg-cb230226 = 停用插件{ $plugin_name }。
msg-abc710cd = /api/plugin/off:{ $res }
msg-06e2a068 = 启用插件{ $plugin_name }。
msg-82c412e7 = /api/plugin/on:{ $res }
msg-77e5d67e = 正在获取插件{ $plugin_name }README文件内容
msg-baed1b72 = 插件名称为空
msg-773cca0a = 插件名称不能为空
msg-082a5585 = 插件{ $plugin_name }不存在
msg-ba106e58 = 插件{ $plugin_name }目录不存在
msg-e38e4370 = 插件目录未找到：{ $plugin_dir }
msg-df027f16 = 插件未找到{ $plugin_name }目录
msg-5f304f4b = 插件{ $plugin_name }没有README文件
msg-a3ed8739 = /api/plugin/readme:{ $res }
msg-2f9e2c11 = 读取README文件失败：{ $e }
msg-dcbd593f = 正在获取插件{ $plugin_name }更新日志
msg-ea5482da = /api/plugin/changelog:{ $res }
msg-8e27362e = 读取更新日志失败:{ $e }
msg-0842bf8b = 插件{ $plugin_name }没有更新日志文件
msg-8e36313d = 源字段必须为列表形式。
msg-643e51e7 = /api/plugin/source/save:{ $res }

### astrbot\dashboard\routes\session_management.py

msg-e1949850 = 获取知识库列表失败:{ $e }
msg-3cd6eb8c = 获取规则列表失败:{ $e }
msg-363174ae = 缺少必要参数: umo
msg-809e51d7 = 缺少必要参数: rule_key
msg-ce203e7e = 不支持的规则键:{ $rule_key }
msg-2726ab30 = 更新会话规则失败：{ $e }
msg-f021f9fb = 删除会话规则失败：{ $e }
msg-6bfa1fe5 = 缺少必要参数: umos
msg-4ce0379e = 参数 umos 必须是数组
msg-979c6e2f = 删除 umo{ $umo }规则失败：{ $e }
msg-77d2761d = 批量删除会话规则失败：{ $e }
msg-6619322c = 获取 UMO 列表失败:{ $e }
msg-b944697c = 获取会话状态列表失败:{ $e }
msg-adba3c3b = 必须指定至少一个要修改的状态。
msg-4a8eb7a6 = 请指定分组 ID
msg-67f15ab7 = 分组 '{ $group_id }' 不存在
msg-50fbcccb = 未找到符合条件的会话
msg-59714ede = 更新{ $umo }服务状态失败:{ $e }
msg-31640917 = 批量更新服务状态失败：{ $e }
msg-4d83eb92 = 缺少必要参数: provider_type, provider_id
msg-5f333041 = 不支持的 provider_type:{ $provider_type }
msg-6fa017d7 = 更新{ $umo }Provider 失败：{ $e }
msg-07416020 = 批量更新 Provider 失败：{ $e }
msg-94c745e6 = 获取分组列表失败:{ $e }
msg-fb7cf353 = 分组名称不能为空
msg-ae3fce8a = 创建分组失败:{ $e }
msg-07de5ff3 = Group ID 不能为空
msg-35b8a74f = 更新分组失败：{ $e }
msg-3d41a6fd = 删除分组失败:{ $e }

### astrbot\dashboard\routes\skills.py

msg-78b9c276 = { $res }
msg-1198c327 = 您不能在演示模式下执行此操作。
msg-52430f2b = 文件缺失
msg-2ad598f3 = 仅支持 .zip 文件
msg-a11f2e1c = 临时技能文件删除失败：{ $temp_path }
msg-67367a6d = 缺少技能名称

### astrbot\dashboard\routes\stat.py

msg-1198c327 = 您不能在演示模式下执行此操作。
msg-78b9c276 = { $res }
msg-0e5bb0b1 = proxy_url 为必填项
msg-f0e0983e = 失败。状态码：{ $res }
msg-68e65093 = 错误：{ $e }
msg-b5979fe8 = 版本参数为必填项
msg-b88a1887 = 无效的版本格式
msg-8cb9bb6b = 检测到路径遍历尝试：{ $version }->{ $changelog_path }
msg-7616304c = 版本更新日志{ $version }未找到

### astrbot\dashboard\routes\subagent.py

msg-78b9c276 = { $res }
msg-eda47201 = 获取 subagent 配置失败:{ $e }
msg-3e5b1fe0 = 配置必须为 JSON 对象。
msg-9f285dd3 = 保存子代理配置失败:{ $e }
msg-665f4751 = 获取可用工具失败:{ $e }

### astrbot\dashboard\routes\t2i.py

msg-76cc0933 = 获取活动模板时出错
msg-5350f35b = 模板未找到
msg-d7b101c5 = 名称和内容为必填项。
msg-e910b6f3 = 同名模板已存在。
msg-18cfb637 = 内容为必填项。
msg-2480cf2f = 模板未找到。
msg-9fe026f1 = 模板名称不能为空。
msg-eeefe1dc = 模板 '{ $name }' 不存在，无法应用。
msg-0048e060 = 设置活动模板时出错
msg-8fde62dd = 重置默认模板时出错

### astrbot\dashboard\routes\tools.py

msg-78b9c276 = { $res }
msg-977490be = 获取 MCP 服务器列表失败：{ $e }
msg-50a07403 = 服务器名称不能为空
msg-23d2bca3 = 必须提供有效的服务器配置。
msg-31252516 = 服务器{ $name }已存在
msg-20b8309f = 启用 MCP 服务器{ $name }超时。
msg-fff3d0c7 = 启用 MCP 服务器{ $name }失败:{ $e }
msg-7f1f7921 = 保存配置失败
msg-a7f06648 = 添加 MCP 服务器失败：{ $e }
msg-278dc41b = 服务器{ $old_name }不存在
msg-f0441f4b = 启用前停用 MCP 服务器{ $old_name }超时:{ $e }
msg-7c468a83 = 启用前停用 MCP 服务器{ $old_name }失败:{ $e }
msg-8a4c8128 = 停止 MCP 服务器{ $old_name }超时。
msg-9ac9b2fc = 停止 MCP 服务器{ $old_name }失败:{ $e }
msg-b988392d = 更新 MCP 服务器失败：{ $e }
msg-c81030a7 = 服务器{ $name }不存在
msg-4cdbd30d = 停止 MCP 服务器{ $name }超时。
msg-1ed9a96e = 停止 MCP 服务器{ $name }失败:{ $e }
msg-a26f2c6a = 删除 MCP 服务器失败：{ $e }
msg-bbc84cc5 = 无效的 MCP 服务器配置
msg-aa0e3d0d = MCP 服务器配置不能为空
msg-d69cbcf2 = 一次只能配置一个 MCP 服务器。
msg-bd43f610 = 测试 MCP 连接失败:{ $e }
msg-057a3970 = 获取工具列表失败:{ $e }
msg-29415636 = 缺少必要参数：name 或 action
msg-75d85dc1 = 启用工具失败:{ $e }
msg-21a922b8 = 工具{ $tool_name }不存在或操作失败。
msg-20143f28 = 操作工具失败：{ $e }
msg-295ab1fe = 未知:{ $provider_name }
msg-fe38e872 = 同步失败:{ $e }

### astrbot\dashboard\routes\update.py

msg-a3503781 = 迁移失败：{ $res }
msg-543d8e4d = 迁移失败：{ $e }
msg-251a5f4a = 检查更新失败:{ $e }不影响除项目更新外的正常使用
msg-aa6bff26 = /api/update/releases:{ $res }
msg-c5170c27 = 下载管理面板文件失败：{ $e }。
msg-db715c26 = 正在更新依赖项...
msg-9a00f940 = 更新依赖失败：{ $e }
msg-6f96e3ba = /api/update_project:{ $res }
msg-3217b509 = 下载管理面板文件失败：{ $e }
msg-9cff28cf = /api/update_dashboard:{ $res }
msg-1198c327 = 您不能在演示模式下执行此操作。
msg-38e60adf = 缺少参数 package 或参数不合法。
msg-a1191473 = /api/update_pip:{ $res }

### astrbot\i18n\ftl_translate.py

msg-c861e2c1 = 翻译错误：{ $e }
msg-b0bed5f4 = 审查错误：{ $e }
msg-75f207ed = 文件未找到：{ $ftl_path }
msg-1bb0fe21 = 开始翻译和审阅{ $res }元素...
msg-afe74fa1 = 工作流因某个元素失败：{ $e }
msg-af13b7d6 = 成功！已保存至{ $ftl_path }

### astrbot\utils\http_ssl_common.py

msg-5304f0e3 = 无法将 certifi CA 证书包加载到 SSL 上下文中；仅回退至系统信任存储。{ $exc }

### scripts\generate_changelog.py

msg-a79937ef = 警告：未安装 openai 包。请使用以下命令安装：pip install openai
msg-090bfd36 = 警告：调用LLM API失败：{ $e }
msg-a3ac9130 = 回退至简易变更日志生成...
msg-6f1011c5 = 最新标签：{ $latest_tag }
msg-8c7f64d7 = 错误：存储库中未找到标签
msg-a89fa0eb = 自上次提交以来未发现任何提交{ $latest_tag }
msg-846ebecf = 已找到{ $res }自上次提交以来的提交次数{ $latest_tag }
msg-9ad686af = 警告：无法从标签解析版本信息{ $latest_tag }
msg-f5d43a54 = 正在生成变更日志{ $version }...
msg-e54756e8 = ✓ 变更日志已生成：{ $changelog_file }
msg-82be6c98 = 预览：
msg-321ac5b1 = { $changelog_content }

### astrbot\cli\__main__.py
msg-d79e1ff9 = AstrBot CLI 版本: {$__version__}

### astrbot\core\pipeline\__init__.py
msg-1c9fc93d = 模块 {$__name__} 没有成员 {$name}

### astrbot\core\provider\sources\azure_tts_source.py
msg-15c55ed8 = 无效的other[...]格式，应形如 other[{...}]

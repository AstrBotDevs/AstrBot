# 导入所需的库和模块
import asyncio  # 异步IO支持，用于处理异步操作
import random  # 随机数生成，用于随机选择表情
import traceback  # 异常追踪，用于格式化异常信息
from collections.abc import AsyncGenerator  # 异步生成器类型注解
from pathlib import Path  # 文件路径处理

# 从AstrBot核心模块导入
from astrbot.core import logger  # 日志记录器
from astrbot.core.message.components import Image, Plain, Record, Reply  # 消息组件类型
from astrbot.core.platform.astr_message_event import AstrMessageEvent  # 消息事件基类
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path  # 获取临时文件路径
from astrbot.core.utils.media_utils import (  # 多媒体工具函数
    describe_media_ref,  # 描述媒体引用（用于日志）
    ensure_jpeg,  # 确保图像为JPEG格式
    ensure_wav,  # 确保音频为WAV格式
    file_uri_to_path,  # 文件URI转本地路径
    is_file_uri,  # 判断是否为文件URI
)

# 导入管道相关的基类和注册装饰器
from ..context import PipelineContext  # 管道上下文
from ..stage import Stage, register_stage  # 管道阶段基类和注册装饰器


@register_stage  # 注册为管道阶段，使该阶段能被管道自动发现和调用
class PreProcessStage(Stage):
    """
    消息预处理阶段
    
    功能：在消息进入核心处理之前进行必要的预处理工作，包括：
    1. 发送预回应表情（如Telegram的表情回应）
    2. 路径映射处理（支持不同环境的文件路径转换）
    3. 媒体文件格式标准化（音频转WAV、图像转JPEG）
    4. 语音转文本处理（STT - Speech to Text）
    5. 临时文件生命周期管理
    
    该阶段确保下游处理器接收到的消息都是标准化、可处理的形式
    """
    
    async def initialize(self, ctx: PipelineContext) -> None:
        """
        初始化预处理阶段，加载必要的配置
        
        功能：在管道启动时进行初始化，从上下文配置中加载各项设置
        包括平台设置、STT设置等
        
        Args:
            ctx (PipelineContext): 管道上下文对象，包含全局配置和插件管理器
        """
        # 保存管道上下文的引用
        self.ctx = ctx
        # 保存全局配置的引用
        self.config = ctx.astrbot_config
        # 保存插件管理器的引用
        self.plugin_manager = ctx.plugin_manager

        # 获取语音转文本(STT)的配置设置，默认为空字典
        self.stt_settings: dict = self.config.get("provider_stt_settings", {})
        # 获取平台通用设置，默认为空字典
        self.platform_settings: dict = self.config.get("platform_settings", {})

    @staticmethod
    def _track_temp_media(event: AstrMessageEvent, media_path: str) -> None:
        """
        追踪事件拥有的临时媒体文件
        
        功能：管理临时媒体文件的生命周期，确保当事件结束时临时文件能被正确清理
        只追踪位于AstrBot临时目录下的文件，避免意外删除用户文件
        
        工作原理：
        1. 解析媒体文件的绝对路径
        2. 检查文件是否在AstrBot临时目录下
        3. 如果是临时文件，注册到事件的生命周期管理中
        
        Args:
            event (AstrMessageEvent): 拥有该临时文件的消息事件
            media_path (str): 需要追踪的本地媒体文件路径
        """
        try:
            # 将媒体路径解析为绝对路径
            path = Path(media_path).resolve()
            # 获取AstrBot临时目录的绝对路径
            temp_dir = Path(get_astrbot_temp_path()).resolve()
            # 检查媒体文件是否位于临时目录下
            # relative_to 会抛出异常如果路径不在临时目录下
            path.relative_to(temp_dir)
        except (OSError, ValueError):
            # 如果文件不在临时目录下或路径无效，不进行追踪，直接返回
            return
        # 将临时文件注册到事件中，事件结束时会自动清理
        event.track_temporary_local_file(str(path))

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        """
        处理消息事件的预处理流程
        
        功能：执行完整的消息预处理流程，包括：
        1. 平台特定功能（如预回应表情）
        2. 路径映射转换
        3. 媒体文件格式标准化
        4. 回复链中的媒体处理
        5. 语音转文本转换
        
        Args:
            event (AstrMessageEvent): 需要预处理的消息事件
            
        Returns:
            None | AsyncGenerator[None, None]: 通常返回None，异步生成器用于流式处理
        """
        
        # ===== 第一步：平台特定的预回应表情处理 =====
        # 定义支持预回应表情的平台列表
        supported = {"telegram", "lark", "discord"}
        # 获取当前消息来自的平台名称
        platform = event.get_platform_name()
        
        # 从配置中获取平台特定的预回应表情设置
        # 配置路径：platform_specific.<platform>.pre_ack_emoji
        cfg = (
            self.config.get("platform_specific", {})  # 获取平台特定配置
            .get(platform, {})  # 获取当前平台的配置
            .get("pre_ack_emoji", {})  # 获取预回应表情配置
        ) or {}  # 如果为None则使用空字典
        # 获取可用的表情列表
        emojis = cfg.get("emojis") or []
        
        # 检查是否需要发送预回应表情
        if (
            cfg.get("enable", False)  # 功能已启用
            and platform in supported  # 当前平台支持
            and emojis  # 有可用的表情列表
            and event.is_at_or_wake_command  # 是唤醒命令或@消息
        ):
            try:
                # 随机选择一个表情并发送给消息作为回应
                await event.react(random.choice(emojis))
            except Exception as e:
                # 表情发送失败时记录警告日志
                logger.warning(f"{platform} 预回应表情发送失败: {e}")

        # ===== 第二步：路径映射处理 =====
        # 检查是否配置了路径映射规则
        if mappings := self.platform_settings.get("path_mapping", []):
            # 获取消息的所有消息组件
            message_chain = event.get_messages()

            # 遍历每个消息组件
            for idx, component in enumerate(message_chain):
                # 只处理Record或Image类型的组件，且必须有URL
                if isinstance(component, Record | Image) and component.url:
                    # 遍历所有映射规则
                    for mapping in mappings:
                        # 解析映射规则：格式为 "原始路径:目标路径"
                        from_, to_ = mapping.split(":")
                        # 去除路径末尾的斜杠，统一格式
                        from_ = from_.removesuffix("/")
                        to_ = to_.removesuffix("/")

                        # 获取URL的实际路径（如果是文件URI则转换）
                        url = (
                            file_uri_to_path(component.url)  # 文件URI转路径
                            if is_file_uri(component.url)  # 判断是否为文件URI
                            else component.url  # 不是URI则保持原样
                        )
                        # 如果URL以映射的源路径开头
                        if url.startswith(from_):
                            # 执行路径替换映射
                            component.url = url.replace(from_, to_, 1)
                            # 记录映射的调试信息
                            logger.debug(f"路径映射: {url} -> {component.url}")
                    # 更新消息链中的组件
                    message_chain[idx] = component

        # ===== 第三步：媒体文件格式标准化 =====
        # 获取消息链（可能在第二步中被修改）
        message_chain = event.get_messages()
        
        # 遍历所有消息组件进行标准化处理
        for idx, component in enumerate(message_chain):
            # 处理音频组件（Record）
            if isinstance(component, Record):
                try:
                    # 将音频组件转换为本地文件路径
                    original_path = await component.convert_to_file_path()
                    # 追踪原始音频文件的临时文件
                    self._track_temp_media(event, original_path)
                    # 确保音频格式为WAV（统一的音频格式）
                    record_path = await ensure_wav(original_path)
                    # 追踪转换后的WAV文件
                    self._track_temp_media(event, record_path)
                    # 更新组件的文件路径属性
                    component.file = record_path
                    component.path = record_path
                    # 更新消息链中的组件
                    message_chain[idx] = component
                except Exception as e:
                    # 音频处理失败时记录警告
                    logger.warning(f"Voice processing failed: {e}")
            
            # 处理图像组件（Image）
            elif isinstance(component, Image):
                try:
                    # 将图像组件转换为本地文件路径
                    original_path = await component.convert_to_file_path()
                    # 追踪原始图像文件的临时文件
                    self._track_temp_media(event, original_path)
                    # 确保图像格式为JPEG（统一的图像格式）
                    image_path = await ensure_jpeg(original_path)
                    # 追踪转换后的JPEG文件
                    self._track_temp_media(event, image_path)
                    # 更新组件的文件路径和URL属性
                    component.file = image_path
                    component.path = image_path
                    # Image.convert_to_file_path() 方法优先使用url属性，所以保持url同步
                    component.url = image_path
                    # 更新消息链中的组件
                    message_chain[idx] = component
                except Exception as e:
                    # 获取媒体引用描述用于日志
                    media_ref = component.url or component.file
                    logger.warning(
                        "Image processing failed for %s: %s",
                        describe_media_ref(media_ref),  # 描述媒体来源
                        e,
                    )

        # ===== 第四步：处理回复链中的媒体组件 =====
        # 遍历所有消息组件，检查是否包含回复（Reply）
        for component in event.get_messages():
            # 如果是回复消息且有回复的消息链
            if isinstance(component, Reply) and component.chain:
                # 遍历回复消息链中的每个组件
                for idx, reply_comp in enumerate(component.chain):
                    # 处理回复中的音频组件
                    if isinstance(reply_comp, Record):
                        try:
                            # 转换为本地文件路径
                            original_path = await reply_comp.convert_to_file_path()
                            # 追踪临时文件
                            self._track_temp_media(event, original_path)
                            # 转换为WAV格式
                            record_path = await ensure_wav(original_path)
                            # 追踪转换后的文件
                            self._track_temp_media(event, record_path)
                            # 更新组件属性
                            reply_comp.file = record_path
                            reply_comp.path = record_path
                            # 更新回复链中的组件
                            component.chain[idx] = reply_comp
                        except Exception as e:
                            # 回复链中的音频处理失败
                            logger.warning(
                                f"Voice processing in reply chain failed: {e}"
                            )
                    # 处理回复中的图像组件
                    elif isinstance(reply_comp, Image):
                        try:
                            # 转换为本地文件路径
                            original_path = await reply_comp.convert_to_file_path()
                            # 追踪临时文件
                            self._track_temp_media(event, original_path)
                            # 转换为JPEG格式
                            image_path = await ensure_jpeg(original_path)
                            # 追踪转换后的文件
                            self._track_temp_media(event, image_path)
                            # 更新组件属性
                            reply_comp.file = image_path
                            reply_comp.path = image_path
                            # 保持url与文件路径同步
                            reply_comp.url = image_path
                            # 更新回复链中的组件
                            component.chain[idx] = reply_comp
                        except Exception as e:
                            # 获取媒体引用描述
                            media_ref = reply_comp.url or reply_comp.file
                            logger.warning(
                                "Image processing in reply chain failed for %s: %s",
                                describe_media_ref(media_ref),
                                e,
                            )

        # ===== 第五步：语音转文本处理（STT） =====
        # 检查是否启用了语音转文本功能
        if self.stt_settings.get("enable", False):
            # 获取插件管理器上下文
            ctx = self.plugin_manager.context
            # 获取当前会话的STT提供者
            stt_provider = ctx.get_using_stt_provider(event.unified_msg_origin)
            
            # 如果没有配置STT提供者，记录警告并返回
            if not stt_provider:
                logger.warning(
                    f"会话 {event.unified_msg_origin} 未配置语音转文本模型。",
                )
                return

            # 定义内部异步函数：处理单个音频组件的语音转文本
            async def _stt_record(record_comp: Record, is_reply: bool = False):
                """
                对单个音频组件执行语音转文本转换
                
                功能：将音频组件转换为文本，支持重试机制
                因为某些平台（如napcat）的文件可能不会立即就绪
                
                Args:
                    record_comp (Record): 需要转换的音频组件
                    is_reply (bool): 是否为回复消息中的音频
                    
                Returns:
                    Plain | None: 成功返回包含文本的Plain组件，失败返回None
                """
                # 根据是否为回复消息设置前缀文本
                prefix = "引用消息" if is_reply else ""
                try:
                    # 将音频组件转换为本地文件路径
                    path = await record_comp.convert_to_file_path()
                except Exception as e:
                    # 获取音频路径失败
                    logger.warning(f"获取{prefix}语音路径失败: {e}")
                    return None

                # 设置重试次数为5次
                retry = 5
                # 重试循环
                for i in range(retry):
                    try:
                        # 调用STT提供者进行语音转文本
                        result = await stt_provider.get_text(audio_url=path)
                        if result:
                            # 转文本成功，添加标记后缀
                            suffix = "(引用消息)" if is_reply else ""
                            logger.info(f"语音转文本{suffix}结果: " + result)
                            # 返回包含文本的Plain组件
                            return Plain(result)
                        # 如果结果为空，跳出重试循环
                        break
                    except FileNotFoundError:
                        # 文件未找到的特殊处理（napcat平台的已知问题）
                        # 文件可能不会立即准备就绪，等待后重试
                        logger.debug(f"文件尚未就绪 ({path})，重试 {i + 1}/{retry}")
                        await asyncio.sleep(0.5)  # 等待0.5秒后重试
                        continue
                    except BaseException as e:
                        # 其他异常，记录错误并停止重试
                        logger.error(traceback.format_exc())
                        suffix = "(引用消息)" if is_reply else ""
                        logger.error(f"语音转文本{suffix}失败: {e}")
                        break
                # 所有重试都失败，返回None
                return None

            # 处理当前消息中的音频组件
            message_chain = event.get_messages()
            for idx, component in enumerate(message_chain):
                # 如果是音频组件
                if isinstance(component, Record):
                    # 执行语音转文本
                    plain_comp = await _stt_record(component)
                    if plain_comp:
                        # 转换成功，替换音频组件为文本组件
                        message_chain[idx] = plain_comp
                        # 将识别出的文本添加到消息字符串中
                        event.message_str += plain_comp.text
                        event.message_obj.message_str += plain_comp.text

            # 处理回复消息链中的音频组件
            for component in event.get_messages():
                # 如果是回复消息且有回复链
                if isinstance(component, Reply) and component.chain:
                    # 遍历回复链中的组件
                    for idx, reply_comp in enumerate(component.chain):
                        # 如果是音频组件
                        if isinstance(reply_comp, Record):
                            # 执行语音转文本（标记为回复消息）
                            plain_comp = await _stt_record(reply_comp, is_reply=True)
                            if plain_comp:
                                # 替换音频组件为文本组件
                                component.chain[idx] = plain_comp
                                # 将文本添加到消息字符串中
                                event.message_str += plain_comp.text
                                event.message_obj.message_str += plain_comp.text
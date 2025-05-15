import time
import aiohttp
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.message.components import Plain, Image # Import Image
from astrbot import logger
import base64
from PIL import Image as PILImage # 使用别名避免冲突
import io


class WeChatPadProMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        # 添加平台特定的参数，例如适配器实例
        adapter: object, # 传递适配器实例
    ):
        # logger.info(f"WeChatPadProMessageEvent __init__ called with:")
        # logger.info(f"  message_str: {message_str}")
        # logger.info(f"  message_obj: {message_obj}")
        # logger.info(f"  message_obj.message: {message_obj.message}") # Log the message components list
        # logger.info(f"  platform_meta: {platform_meta}")
        # logger.info(f"  session_id: {session_id}")
        # logger.info(f"  adapter: {adapter}")

        # Pass the message components list to the parent class constructor
        # Pass message_str to the parent class constructor, similar to gewechat adapter
        # Pass message_str and message_obj to the parent class constructor, similar to fake adapter
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.message_obj = message_obj # Save the full message object
        self.adapter = adapter # Save the adapter instance

    async def send(self, message: MessageChain):
        """
        发送消息到 WeChatPadPro 平台。
        """
        # 在这里实现将 MessageChain 转换为 WeChatPadPro 消息格式并发送的逻辑
        # 遍历消息链，处理不同类型的消息组件
        for component in message.chain:
            # logger.info(f"Processing component: {component}") # Log the component
            # logger.info(f"Type of component: {type(component)}") # Log the type of the component
            # logger.info(f"Image class in scope: {Image}") # Log the Image class itself
            time.sleep(1)
            if isinstance(component, Plain):
                # 发送文本消息
                message_text = component.text
                # 实现 reply_with_mention 功能
                if (
                    self.message_obj.type == MessageType.GROUP_MESSAGE # 确保是群聊消息
                    and self.adapter.settings.get("reply_with_mention", False) # 检查适配器设置是否启用 reply_with_mention
                    and self.message_obj.sender # 确保有发送者信息
                    and (self.message_obj.sender.user_id or self.message_obj.sender.nickname) # 确保发送者有 ID 或昵称
                ):
                    # 在文本消息前加上 @ 消息发送者的信息
                    # 优先使用 nickname，如果没有则使用 user_id
                    mention_text = self.message_obj.sender.nickname if self.message_obj.sender.nickname else self.message_obj.sender.user_id
                    message_text = f"@{mention_text} {message_text}"
                    logger.info(f"已添加 @ 信息: {message_text}")

                if message_text:
                    payload = {
                        "MsgItem": [
                            {
                                "MsgType": 1, # 1 for Text
                                "TextContent": message_text,
                                "ToUserName": self.session_id, # 接收者 wxid
                            }
                        ]
                    }
                    url = f"{self.adapter.base_url}/message/SendTextMessage" # 使用文本消息发送接口
                    params = {"key": self.adapter.auth_key}
                    async with aiohttp.ClientSession() as session:
                        try:
                            async with session.post(url, params=params, json=payload) as response:
                                response_data = await response.json()
                                if response.status == 200 and response_data.get("Code") == 200:
                                    logger.info(f"成功发送文本消息到 {self.session_id}: {message_text}")
                                else:
                                    logger.error(f"发送文本消息失败到 {self.session_id}: {response.status}, {response_data}")
                        except aiohttp.ClientConnectorError as e:
                            logger.error(f"连接到 WeChatPadPro 服务失败: {e}")
                        except Exception as e:
                            logger.error(f"发送文本消息时发生错误: {e}")

            elif isinstance(component, Image):
                # 发送图片消息
                try:
                    # 假设 Image 对象有 to_base64() 方法
                    image_base64 = await component.convert_to_base64() # 需要 Image 组件支持转为 base64
                    # logger.info(f"转换后的base64图片：{image_base64}")

                    # Base64图片格式校验
                    try:
                        image_data = base64.b64decode(image_base64, validate=True)
                        logger.info("Base64图片格式校验成功。")
                    except (base64.binascii.Error, ValueError) as e:
                        logger.error(f"Base64图片格式校验失败: {e}")
                        await self.send(MessageChain([Plain("发送图片失败：图片编码格式不正确。")]))
                        continue # 跳过发送此图片

                    # 图片压缩处理
                    try:
                        img = PILImage.open(io.BytesIO(image_data)) # 使用别名 PILImage

                        # 示例压缩：对于 JPEG 格式，降低质量；对于其他格式，转换为 JPEG 并降低质量
                        output_buffer = io.BytesIO()
                        if img.format == 'JPEG':
                            img.save(output_buffer, format='JPEG', quality=80) # 降低JPEG质量到80
                        else:
                            # 尝试转换为JPEG进行压缩，如果图片是透明的，先转换为RGB
                            if img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')
                            img.save(output_buffer, format='JPEG', quality=80) # 转换为JPEG并降低质量

                        compressed_image_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                        logger.info(f"图片压缩成功，原大小: {len(image_base64)} bytes, 压缩后大小: {len(compressed_image_base64)} bytes")
                        image_base64_to_send = compressed_image_base64 # 使用压缩后的base64
                    except Exception as e:
                        logger.error(f"图片压缩处理失败: {e}")
                        # 如果压缩失败，可以选择发送原图或者跳过
                        # 这里选择发送原图，或者可以根据需求发送错误消息并跳过
                        image_base64_to_send = image_base64 # 压缩失败，发送原图
                        logger.warning("图片压缩失败，将尝试发送原图。")


                    payload = {
                        "MsgItem": [
                            {
                                "AtWxIDList": [], # 根据需要添加 @ 的用户 wxid 列表
                                "ImageContent": image_base64_to_send, # 使用处理后的base64
                                "MsgType": 3, # 图片消息类型
                                "TextContent": "",
                                "ToUserName": self.session_id, # 接收者 wxid
                            }
                        ]
                    }
                    url = f"{self.adapter.base_url}/message/SendImageNewMessage" # 使用新的图片发送接口
                    params = {"key": self.adapter.auth_key}
                    async with aiohttp.ClientSession() as session:
                        try:
                            async with session.post(url, params=params, json=payload) as response:
                                response_data = await response.json()
                                logger.info(response_data)
                                if response.status == 200 and response_data.get("Code") == 200:
                                    logger.info(f"成功发送图片消息到 {self.session_id}")
                                else:
                                    logger.error(f"发送图片消息失败到 {self.session_id}: {response.status}, {response_data}")
                        except aiohttp.ClientConnectorError as e:
                            logger.error(f"连接到 WeChatPadPro 服务失败: {e}")
                        except Exception as e:
                            logger.error(f"发送图片消息时发生错误: {e}")

                except Exception as e:
                    logger.error(f"处理图片消息失败: {e}")
                    # 可以选择发送一个错误提示文本消息
                    await self.send(MessageChain([Plain("发送图片失败。")]))
            # TODO: 添加对其他消息组件类型的处理 (Record, Video, At等)
            # elif isinstance(component, Record):
            #     pass
            # elif isinstance(component, Video):
            #     pass
            # elif isinstance(component, At):
            #     pass
            # ...

        await super().send(message) # 调用父类的 send 方法进行指标上报等操作


    # 根据 WeChatPadPro 的事件特点，可能需要重写 AstrMessageEvent 中的其他方法
    # 例如：
    # def get_sender_id(self) -> str:
    #     # 从 self.message_obj 中获取发送者 ID
    #     return self.message_obj.sender.user_id
    #
    # def is_private_chat(self) -> bool:
    #     # 根据 self.message_obj 判断是否是私聊
    #     return self.message_obj.type == MessageType.FRIEND_MESSAGE
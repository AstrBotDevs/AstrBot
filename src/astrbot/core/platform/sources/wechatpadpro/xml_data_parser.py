from defusedxml import ElementTree as eT
from astrbot.api import logger
from astrbot.api.message_components import (
    WechatEmoji as Emoji,
    Plain,
    Image,
    BaseMessageComponent,
)


class GeweDataParser:
    def __init__(
        self,
        content: str,
        is_private_chat: bool = False,
        cached_texts=None,
        cached_images=None,
        raw_message: dict = None,
        downloader=None,
    ):
        self._xml = None
        self.content = content
        self.is_private_chat = is_private_chat
        self.cached_texts = cached_texts or {}
        self.cached_images = cached_images or {}
        self.downloader = downloader

        raw_message = raw_message or {}
        self.from_user_name = raw_message.get("from_user_name", {}).get("str", "")
        self.to_user_name = raw_message.get("to_user_name", {}).get("str", "")
        self.msg_id = raw_message.get("msg_id", "")

    def _format_to_xml(self):
        if self._xml:
            return self._xml

        try:
            msg_str = self.content
            if not self.is_private_chat:
                parts = self.content.split(":\n", 1)
                msg_str = parts[1] if len(parts) == 2 else self.content

            self._xml = eT.fromstring(msg_str)
            return self._xml
        except Exception as e:
            logger.error(f"[XML解析失败] {e}")
            raise

    async def parse_mutil_49(self) -> list[BaseMessageComponent] | None:
        """
        处理 msg_type == 49 的多种 appmsg 类型（目前支持 type==57）
        """
        try:
            appmsg_type = self._format_to_xml().findtext(".//appmsg/type")
            if appmsg_type == "57":
                return await self.parse_reply()
        except Exception as e:
            logger.warning(f"[parse_mutil_49] 解析失败: {e}")
        return None

    async def parse_reply(self) -> list[BaseMessageComponent]:
        """
        处理 type == 57 的引用消息：支持文本（1）、图片（3）、嵌套49（49）
        """
        components = []

        try:
            appmsg = self._format_to_xml().find("appmsg")
            if appmsg is None:
                return [Plain("[引用消息解析失败]")]

            refermsg = appmsg.find("refermsg")
            if refermsg is None:
                return [Plain("[引用消息解析失败]")]

            quote_type = int(refermsg.findtext("type", "0"))
            nickname = refermsg.findtext("displayname", "未知发送者")
            quote_content = refermsg.findtext("content", "")
            svrid = refermsg.findtext("svrid")

            match quote_type:
                case 1:  # 文本引用
                    quoted_text = self.cached_texts.get(str(svrid), quote_content)
                    components.append(Plain(f"[引用] {nickname}: {quoted_text}"))

                case 3:  # 图片引用
                    quoted_image_b64 = self.cached_images.get(str(svrid))
                    if not quoted_image_b64:
                        try:
                            quote_xml = eT.fromstring(quote_content)
                            img = quote_xml.find("img")
                            cdn_url = (
                                img.get("cdnbigimgurl") or img.get("cdnmidimgurl")
                                if img is not None
                                else None
                            )
                            if cdn_url and self.downloader:
                                image_resp = await self.downloader(
                                    self.from_user_name, self.to_user_name, self.msg_id
                                )
                                quoted_image_b64 = (
                                    image_resp.get("Data", {})
                                    .get("Data", {})
                                    .get("Buffer")
                                )
                        except Exception as e:
                            logger.warning(f"[引用图片解析失败] svrid={svrid} err={e}")

                    if quoted_image_b64:
                        components.extend(
                            [
                                Image.fromBase64(quoted_image_b64),
                                Plain(f"[引用] {nickname}: [引用的图片]"),
                            ]
                        )
                    else:
                        components.append(
                            Plain(f"[引用] {nickname}: [引用的图片 - 未能获取]")
                        )

                case 49:  # 嵌套引用
                    try:
                        nested_root = eT.fromstring(quote_content)
                        nested_title = nested_root.findtext(".//appmsg/title", "")
                        components.append(Plain(f"[引用] {nickname}: {nested_title}"))
                    except Exception as e:
                        logger.warning(f"[嵌套引用解析失败] err={e}")
                        components.append(Plain(f"[引用] {nickname}: [嵌套引用消息]"))

                case _:  # 其他未识别类型
                    logger.info(f"[未知引用类型] quote_type={quote_type}")
                    components.append(Plain(f"[引用] {nickname}: [不支持的引用类型]"))

            # 主消息标题
            title = appmsg.findtext("title", "")
            if title:
                components.append(Plain(title))

        except Exception as e:
            logger.error(f"[parse_reply] 总体解析失败: {e}")
            return [Plain("[引用消息解析失败]")]

        return components

    def parse_emoji(self) -> Emoji | None:
        """
        处理 msg_type == 47 的表情消息（emoji）
        """
        try:
            emoji_element = self._format_to_xml().find(".//emoji")
            if emoji_element is not None:
                return Emoji(
                    md5=emoji_element.get("md5"),
                    md5_len=emoji_element.get("len"),
                    cdnurl=emoji_element.get("cdnurl"),
                )
        except Exception as e:
            logger.error(f"[parse_emoji] 解析失败: {e}")

        return None

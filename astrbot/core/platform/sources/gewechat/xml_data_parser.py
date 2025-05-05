from defusedxml import ElementTree as eT
from astrbot.api import logger
from astrbot.api.message_components import (
    WechatEmoji as Emoji,
    Reply,
    Plain,
    BaseMessageComponent,
    Share,
)


class GeweDataParser:
    def __init__(self, data, is_private_chat):
        self.data = data
        self.is_private_chat = is_private_chat

    def _format_to_xml(self):
        return eT.fromstring(self.data)

    def parse_mutil_49(self) -> list[BaseMessageComponent] | None:
        appmsg_type = self._format_to_xml().find(".//appmsg/type")
        if appmsg_type is None:
            return

        match appmsg_type.text:
            case "57":
                return self.parse_reply()
            case "5":
                return self.parse_officialAccounts()

    def parse_emoji(self) -> Emoji | None:
        try:
            emoji_element = self._format_to_xml().find(".//emoji")
            # 提取 md5 和 len 属性
            if emoji_element is not None:
                md5_value = emoji_element.get("md5")
                emoji_size = emoji_element.get("len")
                cdnurl = emoji_element.get("cdnurl")

                return Emoji(md5=md5_value, md5_len=emoji_size, cdnurl=cdnurl)

        except Exception as e:
            logger.error(f"gewechat: parse_emoji failed, {e}")

    def parse_officialAccounts(self) -> list[Share] | None:
        """解析公众号消息

        Returns:
            list[Share]: 一个包含 Share 消息对象的列表。
        """
        try:
            root = self._format_to_xml()
            url = root.find(".//url")
            title = root.find(".//title")

            if url is not None and title is not None and url.text is not None and title.text is not None and url.text.strip() != "" and title.text.strip() != "":
                clean_url = url.text.strip()
                clean_title = title.text.strip()
                logger.debug(f"gewechat: Official Accounts: {clean_url} {clean_title}")
                return [Share(url=clean_url, title=clean_title)]
            else:
                return None
        except Exception as e:
            logger.error(f"gewechat: parse_officialAccounts failed, {e}")

    def parse_reply(self) -> list[Reply, Plain] | None:
        """解析引用消息

        Returns:
            list[Reply, Plain]: 一个包含两个元素的列表。Reply 消息对象和引用者说的文本内容。微信平台下引用消息时只能发送文本消息。
        """
        try:
            replied_id = -1
            replied_uid = 0
            replied_nickname = ""
            replied_content = ""  # 被引用者说的内容
            content = ""  # 引用者说的内容

            root = self._format_to_xml()
            refermsg = root.find(".//refermsg")
            if refermsg is not None:
                # 被引用的信息
                svrid = refermsg.find("svrid")
                fromusr = refermsg.find("fromusr")
                displayname = refermsg.find("displayname")
                refermsg_content = refermsg.find("content")
                if svrid is not None:
                    replied_id = svrid.text
                if fromusr is not None:
                    replied_uid = fromusr.text
                if displayname is not None:
                    replied_nickname = displayname.text
                if refermsg_content is not None:
                    # 处理引用嵌套，包括嵌套公众号消息
                    if refermsg_content.text.startswith(
                        "<msg>"
                    ) or refermsg_content.text.startswith("<?xml"):
                        try:
                            logger.debug("gewechat: Reference message is nested")
                            refer_root = eT.fromstring(refermsg_content.text)
                            img = refer_root.find("img")
                            if img is not None:
                                replied_content = "[图片]"
                            else:
                                app_msg = refer_root.find("appmsg")
                                refermsg_content_title = app_msg.find("title")
                                refermsg_content_type = app_msg.find("type")
                                logger.debug(
                                    f"gewechat: Reference message nesting: {refermsg_content_title.text}"
                                )
                                if refermsg_content_type.text == "51":
                                    replied_content = "[视频号]"
                                else:
                                    replied_content = refermsg_content_title.text
                        except Exception as e:
                            logger.error(f"gewechat: nested failed, {e}")
                            # 处理异常情况
                            replied_content = refermsg_content.text
                    else:
                        replied_content = refermsg_content.text

                # 提取引用者说的内容
            title = root.find(".//appmsg/title")
            if title is not None:
                content = title.text

            reply_seg = Reply(
                id=replied_id,
                chain=[Plain(replied_content)],
                sender_id=replied_uid,
                sender_nickname=replied_nickname,
                message_str=replied_content,
            )
            plain_seg = Plain(content)
            return [reply_seg, plain_seg]

        except Exception as e:
            logger.error(f"gewechat: parse_reply failed, {e}")

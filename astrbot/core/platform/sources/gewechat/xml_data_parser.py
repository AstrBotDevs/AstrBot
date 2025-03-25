from defusedxml import ElementTree as eT
from astrbot.api import logger
from astrbot.api.message_components import WechatEmoji as Emoji, Reply, Plain


class GeweDataParser:
    def __init__(self, data, is_private_chat):
        self.data = data
        self.is_private_chat = is_private_chat

    def _format_to_xml(self):
        return eT.fromstring(self.data)

    def parse_mutil_49(self):
        appmsg_type = self._format_to_xml().find(".//appmsg/type")
        if appmsg_type is None:
            return

        match appmsg_type.text:
            case "57":
                return self.parse_reply()

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

    def parse_reply(self) -> Reply | None:
        try:
            replied_id = -1
            replied_uid = 0
            replied_nickname = ""
            replied_content = ""
            content = ""

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
                    replied_content = refermsg_content.text

                # 提取引用者说的内容
            title = root.find(".//appmsg/title")
            if title is not None:
                content = title.text

            r = Reply(
                id=replied_id,
                chain=[Plain(content)],
                sender_id=replied_uid,
                sender_nickname=replied_nickname,
                sender_str=replied_content,
                message_str=content,
            )
            return r

        except Exception as e:
            logger.error(f"gewechat: parse_reply failed, {e}")

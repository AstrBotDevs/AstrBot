from astrbot import logger
import aiohttp
import json


class GeweDownloader:
    def __init__(self, base_url: str, download_base_url: str, token: str):
        self.base_url = base_url
        self.download_base_url = download_base_url
        self.headers = {"Content-Type": "application/json", "X-GEWE-TOKEN": token}

    async def _post_json(self, baseurl: str, route: str, payload: dict):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{baseurl}{route}", headers=self.headers, json=payload
            ) as resp:
                return await resp.read()

    async def download_voice(self, appid: str, xml: str, msg_id: str):
        payload = {"appId": appid, "xml": xml, "msgId": msg_id}
        return await self._post_json(self.base_url, "/message/downloadVoice", payload)

    async def download_image(self, appid: str, xml: str) -> str:
        """返回一个可下载的 URL"""
        choices = [2, 3]  #  2:常规图片 3:缩略图

        for choice in choices:
            try:
                payload = {"appId": appid, "xml": xml, "type": choice}
                data = await self._post_json(
                    self.base_url, "/message/downloadImage", payload
                )
                json_blob = json.loads(data)
                if "fileUrl" in json_blob["data"]:
                    return self.download_base_url + json_blob["data"]["fileUrl"]

            except BaseException as e:
                logger.error(f"gewe download image: {e}")
                continue

        raise Exception("无法下载图片")

    async def download_emoji_md5(self, app_id, emoji_md5):
        """下载emoji"""
        try:
            payload = {"appId": app_id, "emojiMd5": emoji_md5}

            # gewe 计划中的接口，暂时没有实现。返回代码404
            data = await self._post_json(
                self.base_url, "/message/downloadEmojiMd5", payload
            )
            json_blob = json.loads(data)
            return json_blob
        except BaseException as e:
            logger.error(f"gewe download emoji: {e}")

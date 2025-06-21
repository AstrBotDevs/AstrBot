"""
使用此功能应该先 pip install baidu-aip
"""

from . import ContentSafetyStrategy
from aip import AipContentCensor


class BaiduAipStrategy(ContentSafetyStrategy):
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        self.client = AipContentCensor(self.app_id, self.api_key, self.secret_key)

    def check(self, content: str):
        res = self.client.textCensorUserDefined(content)
        if "conclusionType" not in res:
            return False, ""
        if res["conclusionType"] == 1:
            return True, ""
        else:
            if "data" not in res:
                return False, ""
            count = len(res["data"])
            info = f"百度审核服务发现 {count} 处违规：\n"
            for i in res["data"]:
                info += f"{i['msg']}；\n"
            info += "\n判断结果：" + res["conclusion"]
            return False, info

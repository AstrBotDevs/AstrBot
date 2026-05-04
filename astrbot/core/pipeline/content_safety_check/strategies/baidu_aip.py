"""使用此功能应该先 pip install baidu-aip"""

from typing import Any, cast

from aip import AipContentCensor

from . import ContentSafetyStrategy


class BaiduAipStrategy(ContentSafetyStrategy):
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        self.client = AipContentCensor(self.app_id, self.api_key, self.secret_key)

    def check(self, content: str) -> tuple[bool, str]:
        res = self.client.textCensorUserDefined(content)
        if "conclusionType" not in res:
            return False, ""
        if res["conclusionType"] == 1:
            return True, ""
        if "data" not in res:
            return False, ""
        count = len(res["data"])
        parts = [f"百度审核服务发现 {count} 处违规：\n"]
        for i in res["data"]:
            # 百度 AIP 返回结构是动态 dict；类型检查时 i 可能被推断为序列，转成 dict 后用 get 取字段
            parts.append(f"{cast(dict[str, Any], i).get('msg', '')}；\n")
        parts.append("\n判断结果：" + res["conclusion"])
        info = "".join(parts)
        return False, info

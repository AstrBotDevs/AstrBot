from aip import AipContentCensor
from util.cmd_config import BaiduAIPConfig


class BaiduJudge:
    def __init__(self, baidu_configs: BaiduAIPConfig) -> None:
        self.app_id = baidu_configs.app_id
        self.api_key = baidu_configs.api_key
        self.secret_key = baidu_configs.secret_key
        self.client = AipContentCensor(self.app_id, 
                                       self.api_key, 
                                       self.secret_key)

    def judge(self, text):
        res = self.client.textCensorUserDefined(text)
        if 'conclusionType' not in res:
            return False, "百度审核服务未知错误"
        if res['conclusionType'] == 1:
            return True, "合规"
        else:
            if 'data' not in res:
                return False, "百度审核服务未知错误"
            count = len(res['data'])
            info = f"百度审核服务发现 {count} 处违规：\n"
            for i in res['data']:
                info += f"{i['msg']}；\n"
            info += "\n判断结果："+res['conclusion']
            return False, info

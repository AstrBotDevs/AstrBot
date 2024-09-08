from aip import AipContentCensor


class BaiduJudge:
    def __init__(self, baidu_configs) -> None:
        if 'app_id' in baidu_configs and 'api_key' in baidu_configs and 'secret_key' in baidu_configs:
            self.app_id = str(baidu_configs['app_id'])
            self.api_key = baidu_configs['api_key']
            self.secret_key = baidu_configs['secret_key']
            self.client = AipContentCensor(
                self.app_id, self.api_key, self.secret_key)
        else:
            raise ValueError("Baidu configs error! 请填写百度内容审核服务相关配置！")

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

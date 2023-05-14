from revChatGPT.V1 import Chatbot
from revChatGPT import typings
from model.provider.provider import Provider
from util import general_utils as gu


class ProviderRevChatGPT(Provider):
    def __init__(self, config):
        self.rev_chatgpt = []
        for i in range(0, len(config['account'])):
            try:
                gu.log(f"创建rev_ChatGPT负载{str(i)}中...", level=gu.LEVEL_INFO, tag="RevChatGPT")

                if 'password' in config['account'][i]:
                    config['account'][i]['password'] = str(config['account'][i]['password'])
                revstat = {
                    'obj': Chatbot(config=config['account'][i]),
                    'busy': False
                }
                self.rev_chatgpt.append(revstat)
            except BaseException as e:
                gu.log(f"创建rev_ChatGPT负载{str(i)}失败: {str(e)}", level=gu.LEVEL_ERROR, tag="RevChatGPT")

    def forget(self) -> bool:
        return False
    
    def request_text(self, prompt: str, bot) -> str:
        resp = ''
        err_count = 0
        retry_count = 5

        while err_count < retry_count:
            try:
                for data in bot.ask(prompt):
                    resp = data["message"]
                break
            except typings.Error as e:
                if e.code == typings.ErrorType.RATE_LIMIT_ERROR:
                    raise e
                if e.code == typings.ErrorType.INVALID_ACCESS_TOKEN_ERROR:
                    raise e
                if e.code == typings.ErrorType.EXPIRED_ACCESS_TOKEN_ERROR:
                    raise e
                if e.code == typings.ErrorType.PROHIBITED_CONCURRENT_QUERY_ERROR:
                    raise e
                
                err_count += 1
                gu.log(f"请求出现问题: {str(e)} | 正在重试: {str(err_count)}", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                if err_count >= retry_count:
                    raise e
            except BaseException as e:
                err_count += 1
                gu.log(f"请求出现问题: {str(e)} | 正在重试: {str(err_count)}", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                if err_count >= retry_count:
                    raise e
        if resp == '':
            resp = "RevChatGPT出现故障."
        
        # print("[RevChatGPT] "+str(resp))
        return resp

    def text_chat(self, prompt):
        res = ''
        err_msg = ''
        cursor = 0
        for revstat in self.rev_chatgpt:
            cursor += 1
            if not revstat['busy']:
                try:
                    revstat['busy'] = True
                    res = self.request_text(prompt, revstat['obj'])
                    revstat['busy'] = False
                    return res.strip()
                # todo: 细化错误管理
                except BaseException as e:
                    revstat['busy'] = False
                    gu.log(f"请求出现问题: {str(e)}", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                    err_msg += f"账号{cursor} - 错误原因: {str(e)}"
                    continue
            else:
                err_msg += f"账号{cursor} - 错误原因: 忙碌"
                continue
        res = f'回复失败。错误跟踪：{err_msg}'
        return res
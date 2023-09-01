from revChatGPT.V1 import Chatbot
from revChatGPT import typings
from model.provider.provider import Provider
from util import general_utils as gu
from util import cmd_config as cc
import time


class ProviderRevChatGPT(Provider):
    def __init__(self, config):
        self.rev_chatgpt = []
        self.cc = cc.CmdConfig()
        for i in range(0, len(config['account'])):
            try:
                gu.log(f"创建逆向ChatGPT负载{str(i+1)}中...", level=gu.LEVEL_INFO, tag="RevChatGPT")

                if 'password' in config['account'][i]:
                    gu.log(f"创建逆向ChatGPT负载{str(i+1)}失败: 已不支持账号密码登录，请使用access_token方式登录。", level=gu.LEVEL_ERROR, tag="RevChatGPT")
                    continue
                rev_account_config = {
                    'access_token': config['account'][i]['access_token'],
                }
                if self.cc.get("rev_chatgpt_model") != "":
                    rev_account_config['model'] = self.cc.get("rev_chatgpt_model")
                if len(self.cc.get("rev_chatgpt_plugin_ids")) > 0:
                    rev_account_config['plugin_ids'] = self.cc.get("rev_chatgpt_plugin_ids")
                if self.cc.get("rev_chatgpt_PUID") != "":
                    rev_account_config['PUID'] = self.cc.get("rev_chatgpt_PUID")
                if len(self.cc.get("rev_chatgpt_unverified_plugin_domains")) > 0:
                    rev_account_config['unverified_plugin_domains'] = self.cc.get("rev_chatgpt_unverified_plugin_domains")
                cb = Chatbot(config=rev_account_config)
                # cb.captcha_solver = self.__captcha_solver
                revstat = {
                    'obj': cb,
                    'busy': False
                }
                self.rev_chatgpt.append(revstat)
            except BaseException as e:
                gu.log(f"创建逆向ChatGPT负载{str(i+1)}失败: {str(e)}", level=gu.LEVEL_ERROR, tag="RevChatGPT")

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
                if e.code == typings.ErrorType.INVALID_ACCESS_TOKEN_ERROR:
                    raise e
                if e.code == typings.ErrorType.EXPIRED_ACCESS_TOKEN_ERROR:
                    raise e
                if e.code == typings.ErrorType.PROHIBITED_CONCURRENT_QUERY_ERROR:
                    raise e
                
                if "The message you submitted was too long" in str(e):
                    raise e
                if "You've reached our limit of messages per hour." in str(e):
                    raise e
                if "Rate limited by proxy" in str(e):
                    gu.log(f"触发请求频率限制, 60秒后自动重试。", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                    time.sleep(60)
                
                err_count += 1
                gu.log(f"请求异常: {str(e)}，正在重试。({str(err_count)})", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                if err_count >= retry_count:
                    raise e
            except BaseException as e:
                err_count += 1
                gu.log(f"请求异常: {str(e)}，正在重试。({str(err_count)})", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                if err_count >= retry_count:
                    raise e
        if resp == '':
            resp = "RevChatGPT请求异常。"
        
        # print("[RevChatGPT] "+str(resp))
        return resp

    def text_chat(self, prompt) -> str:
        while self.is_all_busy():
            time.sleep(1)
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
        raise Exception(f'回复失败。错误跟踪：{err_msg}')
    
    def is_all_busy(self) -> bool:
        for revstat in self.rev_chatgpt:
            if not revstat['busy']:
                return False
        return True
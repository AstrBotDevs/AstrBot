from revChatGPT.V1 import Chatbot
from revChatGPT import typings
from model.provider.provider import Provider
from util import general_utils as gu
from util import cmd_config as cc
import time


class ProviderRevChatGPT(Provider):
    def __init__(self, config):
        self.rev_chatgpt: list[dict] = []
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
                # 后八位c
                g_id = rev_account_config['access_token'][-8:]
                revstat = {
                    'id': g_id,
                    'obj': cb,
                    'busy': False,
                    'user': []
                }
                self.rev_chatgpt.append(revstat)
            except BaseException as e:
                gu.log(f"创建逆向ChatGPT负载{str(i+1)}失败: {str(e)}", level=gu.LEVEL_ERROR, tag="RevChatGPT")

    def forget(self, session_id = None) -> bool:
        for i in self.rev_chatgpt:
            for user in i['user']:
                if session_id == user['id']:
                    try:
                        i['obj'].reset_chat()
                        return True
                    except BaseException as e:
                        gu.log(f"重置RevChatGPT失败。原因: {str(e)}", level=gu.LEVEL_ERROR, tag="RevChatGPT")
                        return False
        return False

    def get_revchatgpt(self) -> list:
        return self.rev_chatgpt
        
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
                if "Your authentication token has expired. Please try signing in again." in str(e):
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

    def text_chat(self, prompt, session_id = None) -> str:

        # 选择一个人少的账号。
        selected_revstat = None
        min_revstat = None
        min_ = None
        new_user = False
        conversation_id = ''
        parent_id = ''
        for revstat in self.rev_chatgpt:
            for user in revstat['user']:
                if session_id == user['id']:
                    selected_revstat = revstat
                    conversation_id = user['conversation_id']
                    parent_id = user['parent_id']
                    break
            if min_ is None:
                min_ = len(revstat['user'])
                min_revstat = revstat
            elif len(revstat['user']) < min_:
                min_ = len(revstat['user'])
                min_revstat = revstat
            # if session_id in revstat['user']:
            #     selected_revstat = revstat
            #     break
        
        if selected_revstat is None:
            selected_revstat = min_revstat
            selected_revstat['user'].append({
                'id': session_id,
                'conversation_id': '',
                'parent_id': ''
            })
            new_user = True

        gu.log(f"选择账号{str(selected_revstat)}", tag="RevChatGPT", level=gu.LEVEL_DEBUG)

        while selected_revstat['busy']:
            gu.log(f"账号忙碌，等待中...", tag="RevChatGPT", level=gu.LEVEL_DEBUG)
            time.sleep(1)
        selected_revstat['busy'] = True
        
        if not new_user:
            # 非新用户，则使用其专用的会话
            selected_revstat['obj'].conversation_id = conversation_id
            selected_revstat['obj'].parent_id = parent_id
        else:
            # 新用户，则使用新的会话
            selected_revstat['obj'].reset_chat()

        res = ''
        err_msg = ''
        err_cnt = 0
        while err_cnt < 15:
            try:
                res = self.request_text(prompt, selected_revstat['obj'])
                selected_revstat['busy'] = False
                # 记录新用户的会话
                if new_user:
                    i = 0
                    for user in selected_revstat['user']:
                        if user['id'] == session_id:
                            selected_revstat['user'][i]['conversation_id'] = selected_revstat['obj'].conversation_id
                            selected_revstat['user'][i]['parent_id'] = selected_revstat['obj'].parent_id
                            break
                        i += 1
                return res.strip()
            except BaseException as e:
                if "Your authentication token has expired. Please try signing in again." in str(e):
                    raise Exception(f"此账号(access_token后8位为{selected_revstat['id']})的access_token已过期，请重新获取，或者切换账号。")
                if "The message you submitted was too long" in str(e):
                    raise Exception("发送的消息太长，请分段发送。")
                if "You've reached our limit of messages per hour." in str(e):
                    raise Exception("触发RevChatGPT请求频率限制。请1小时后再试，或者切换账号。")
                gu.log(f"请求异常: {str(e)}", level=gu.LEVEL_WARNING, tag="RevChatGPT")
                err_cnt += 1
                time.sleep(3)

        raise Exception(f'回复失败。原因：{err_msg}。如果您设置了多个账号，可以使用/switch指令切换账号。输入/switch查看详情。')
            

        # while self.is_all_busy():
        #     time.sleep(1)
        # res = ''
        # err_msg = ''
        # cursor = 0
        # for revstat in self.rev_chatgpt:
        #     cursor += 1
        #     if not revstat['busy']:
        #         try:
        #             revstat['busy'] = True
        #             res = self.request_text(prompt, revstat['obj'])
        #             revstat['busy'] = False
        #             return res.strip()
        #         # todo: 细化错误管理
        #         except BaseException as e:
        #             revstat['busy'] = False
        #             gu.log(f"请求出现问题: {str(e)}", level=gu.LEVEL_WARNING, tag="RevChatGPT")
        #             err_msg += f"账号{cursor} - 错误原因: {str(e)}"
        #             continue
        #     else:
        #         err_msg += f"账号{cursor} - 错误原因: 忙碌"
        #         continue
        # raise Exception(f'回复失败。错误跟踪：{err_msg}')
    
    def is_all_busy(self) -> bool:
        for revstat in self.rev_chatgpt:
            if not revstat['busy']:
                return False
        return True
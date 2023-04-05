from revChatGPT.V1 import Chatbot
from model.provider.provider import Provider

class ProviderRevChatGPT(Provider):
    def __init__(self, config):
        self.rev_chatgpt = []
        for i in range(0, len(config['account'])):
            try:
                print(f"[System] 创建rev_ChatGPT负载{str(i)}: " + str(config['account'][i]))
                if 'password' in config['account'][i]:
                    config['account'][i]['password'] = str(config['account'][i]['password'])
                revstat = {
                    'obj': Chatbot(config=config['account'][i]),
                    'busy': False
                }
                self.rev_chatgpt.append(revstat)
            except BaseException as e:
                print(f"[System] 创建rev_ChatGPT负载失败: {str(e)}")

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
            except BaseException as e:
                try:
                    print("[RevChatGPT] 请求出现了一些问题, 正在重试。次数"+str(err_count))
                    err_count += 1
                    if err_count >= retry_count:
                        raise e
                except BaseException:
                    err_count += 1
        
        print("[RevChatGPT] "+str(resp))
        return resp

    def text_chat(self, prompt):
        res = ''
        print("[Debug] "+str(self.rev_chatgpt))
        for revstat in self.rev_chatgpt:
            if not revstat['busy']:
                try:
                    revstat['busy'] = True
                    print("[Debug] 使用逆向ChatGPT回复ing", end='', flush=True)
                    res = self.request_text(prompt, revstat['obj'])
                    print("OK")
                    revstat['busy'] = False
                    # 处理结果文本
                    chatgpt_res = res.strip()
                    return res
                except Exception as e:
                    print("[System-Error] 逆向ChatGPT回复失败" + str(e))
                    try:
                        if e.code == 2:
                            print("[System-Error] 频率限制，正在切换账号。"+ str(e))
                            continue
                        else:
                            res = '所有的非忙碌OpenAI账号经过测试都暂时出现问题，请稍后再试或者联系管理员~'
                            return res
                    except BaseException:
                        continue
        res = '所有的OpenAI账号都有负载, 请稍后再试~'
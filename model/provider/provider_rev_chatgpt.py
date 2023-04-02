from revChatGPT.V1 import Chatbot
from model.provider.provider import Provider

class ProviderRevChatGPT(Provider):
    def __init__(self, config):
        if 'password' in config:
            config['password'] = str(config['password'])
        self.bot = Chatbot(config=config)

    def forget(self) -> bool:
        self.bot.reset_chat()
        return True

    def text_chat(self, prompt):
        resp = ''
        err_count = 0
        retry_count = 5

        while err_count < retry_count:
            try:
                for data in self.bot.ask(prompt):
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
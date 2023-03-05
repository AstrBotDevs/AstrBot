from revChatGPT.V1 import Chatbot

class revChatGPT:
    def __init__(self, config):
        
        if 'password' in config:
            config['password'] = str(config['password'])
        self.chatbot = Chatbot(config=config)

    def chat(self, prompt):
        resp = ''

        err_count = 0
        retry_count = 5

        while err_count < retry_count:
            try:
                for data in self.chatbot.ask(prompt):
                    resp = data["message"]
                break
            except BaseException as e:
                print(e)
                print("[RevChatGPT] 请求出现了一些问题, 正在重试。次数"+str(err_count))
                err_count += 1
                if err_count == retry_count:
                    raise e
        
        print("[RevChatGPT] "+str(resp))
        return resp
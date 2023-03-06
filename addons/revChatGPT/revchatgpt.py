from revChatGPT.V1 import Chatbot, Error

class revChatGPT:
    def __init__(self, config):
        
        if 'password' in config:
            config['password'] = str(config['password'])
        self.chatbot = Chatbot(config=config)

    def chat(self, prompt):
        resp = ''

        """
        Base class for exceptions in this module.
        Error codes:
        -1: User error
        0: Unknown error
        1: Server error
        2: Rate limit error
        3: Invalid request error
        4: Expired access token error
        5: Invalid access token error
        6: Prohibited concurrent query error
        """


        err_count = 0
        retry_count = 5

        while err_count < retry_count:
            try:
                for data in self.chatbot.ask(prompt):
                    resp = data["message"]
                break
            except Error as e:
                try:
                    if e.code == 2:
                        print("[RevChatGPT] 频率限制")
                        raise e
                    else:
                        print("[RevChatGPT] 请求出现了一些问题, 正在重试。次数"+str(err_count))
                        err_count += 1
                        if err_count >= retry_count:
                            raise e
                except BaseException:
                    err_count += 1
        
        print("[RevChatGPT] "+str(resp))
        return resp
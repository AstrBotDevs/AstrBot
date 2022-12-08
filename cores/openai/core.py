import openai
import yaml


inst = None

class ChatGPT:
    def __init__(self, chatGPT_configs):
        with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
            cfg = yaml.safe_load(ymlfile)
            if cfg['openai']['key'] != '':
                print("读取ChatGPT Key成功")
                openai.api_key = cfg['openai']['key']
            else:
                print("请先去完善ChatGPT的Key。详情请前往https://beta.openai.com/account/api-keys")
        self.chatGPT_configs = chatGPT_configs
        global inst
        inst = self
    
    async def chat(self, prompt):
        print("[ChatGPT] 接收到prompt:\n"+prompt)
        response = openai.Completion.create(
            prompt=prompt,
            **self.chatGPT_configs
        )
        return response["choices"][0]["text"]
    
    def newSession(self):
        return openai.Session()

def getInst() -> ChatGPT:
    global inst
    return inst
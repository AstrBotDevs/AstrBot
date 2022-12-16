import openai
import yaml
from util.errors.errors import PromptExceededError


inst = None

class ChatGPT:
    def __init__(self):
        with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
            cfg = yaml.safe_load(ymlfile)
            if cfg['openai']['key'] != '':
                print("读取ChatGPT Key成功")
                openai.api_key = cfg['openai']['key']
            else:
                print("请先去完善ChatGPT的Key。详情请前往https://beta.openai.com/account/api-keys")

        chatGPT_configs = cfg['openai']['chatGPTConfigs']
        print(f'加载ChatGPTConfigs: {chatGPT_configs}')
        self.chatGPT_configs = chatGPT_configs
        self.openai_configs = cfg['openai']
        global inst
        inst = self
    
    def chat(self, prompt):
        print("[OpenAI API]收到")
        try:
            response = openai.Completion.create(
                prompt=prompt,
                **self.chatGPT_configs
            )
        except(openai.error.InvalidRequestError) as e:
            raise PromptExceededError("OpenAI遇到错误：输入了一个不合法的请求。\n"+str(e))

        # print(response['usage'])
        print("[ChatGPT] "+response["choices"][0]["text"])
        return response["choices"][0]["text"].strip(), response['usage']['total_tokens']

    def getConfigs(self):
        return self.openai_configs

def getInst() -> ChatGPT:
    global inst
    return inst
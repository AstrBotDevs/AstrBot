import openai
import yaml
from util.errors.errors import PromptExceededError
import json
import time

inst = None

class ChatGPT:
    def __init__(self):
        self.key_list = []
        with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
            cfg = yaml.safe_load(ymlfile)
            if cfg['openai']['key'] != '':
                print("读取ChatGPT Key成功")
                self.key_list = cfg['openai']['key']
                print(f"Key列表: {self.key_list}")
                # openai.api_key = cfg['openai']['key']
            else:
                print("请先去完善ChatGPT的Key。详情请前往https://beta.openai.com/account/api-keys")
        
        # init key record
        self.init_key_record()

        chatGPT_configs = cfg['openai']['chatGPTConfigs']
        print(f'加载ChatGPTConfigs: {chatGPT_configs}')
        self.chatGPT_configs = chatGPT_configs
        self.openai_configs = cfg['openai']
        global inst
        inst = self
    
    def chat(self, prompt, image_mode = False):
        try:
            if not image_mode:
                response = openai.Completion.create(
                    prompt=prompt,
                    **self.chatGPT_configs
                )
            else:
                response = openai.Image.create(
                    prompt=prompt,
                    n=1,
                    size="512x512",
                )
        except Exception as e:
            print(e)
            if 'You exceeded' in str(e) or 'Billing hard limit has been reached' in str(e) or 'No API key provided.' in str(e):
                print("当前Key已超额，正在切换")
                self.key_stat[openai.api_key]['exceed'] = True
                self.save_key_record()

                response, is_switched = self.handle_switch_key(prompt)
                if not is_switched:
                    # 所有Key都超额
                    raise e
            else:
                if not image_mode:
                    response = openai.Completion.create(
                        prompt=prompt,
                        **self.chatGPT_configs
                    )
                else:
                    response = openai.Image.create(
                        prompt=prompt,
                        n=1,
                        size="512x512",
                    )
        if not image_mode:
            self.key_stat[openai.api_key]['used'] += response['usage']['total_tokens']
            self.save_key_record()
            print("[ChatGPT] "+response["choices"][0]["text"])
            return response["choices"][0]["text"].strip(), response['usage']['total_tokens']
        else:
            return response['data'][0]['url']
            
    def handle_switch_key(self, prompt):
        while True:
            is_all_exceed = True
            for key in self.key_stat:
                if not self.key_stat[key]['exceed']:
                    is_all_exceed = False
                    openai.api_key = key
                    print(f"切换到Key: {key}, 已使用token: {self.key_stat[key]['used']}")
                    if prompt != '':
                        try:
                            response = openai.Completion.create(
                                prompt=prompt,
                                **self.chatGPT_configs
                            )
                            return response, True
                        except Exception as e:
                            print(e)
                            if 'You exceeded' in str(e):
                                print("当前Key已超额，正在切换")
                                self.key_stat[openai.api_key]['exceed'] = True
                                self.save_key_record()
                                time.sleep(1)
                                continue
                    else:
                        return True
            if is_all_exceed:
                print("所有Key已超额")
                return None, False
                
    def getConfigs(self):
        return self.openai_configs
    
    def save_key_record(self):
        with open("chatgpt_key_record", 'w', encoding='utf-8') as f:
            json.dump(self.key_stat, f)

    def get_key_stat(self):
        return self.key_stat
    def get_key_list(self):
        return self.key_list
    
    # 添加key
    def append_key(self, key, sponsor):
        self.key_list.append(key)
        self.key_stat[key] = {'exceed': False, 'used': 0, 'sponsor': sponsor}
        self.save_key_record()
        self.init_key_record()
    # 检查key是否可用
    def check_key(self, key):
        pre_key = openai.api_key
        openai.api_key = key
        try:
            openai.Completion.create(
                prompt="test",
                **self.chatGPT_configs
            )
            openai.api_key = pre_key
            return True
        except Exception as e:
            pass
        openai.api_key = pre_key
        return False

    # 将key_list的key转储到key_record中，并记录相关数据
    def init_key_record(self):
        with open("chatgpt_key_record", 'r', encoding='utf-8') as keyfile:
            try:
                self.key_stat = json.load(keyfile)
            except Exception as e:
                print(e)
                self.key_stat = {}
            finally:
                for key in self.key_list:
                    if key not in self.key_stat:
                        self.key_stat[key] = {'exceed': False, 'used': 0}
                        if openai.api_key is None:
                            print("切换")
                            openai.api_key = key
                    else:
                        if self.key_stat[key]['exceed']:
                            print(f"Key: {key} 已超额")
                            continue
                        else:
                            if openai.api_key is None:
                                openai.api_key = key
                                print(f"使用Key: {key}, 已使用token: {self.key_stat[key]['used']}")
                if openai.api_key == None:
                    self.handle_switch_key("")
            self.save_key_record()

def getInst() -> ChatGPT:
    global inst
    return inst
import openai
import yaml
from util.errors.errors import PromptExceededError
import json
import time
import os
import sys

inst = None
# 适配pyinstaller
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'
key_record_path = abs_path+'chatgpt_key_record'

class ChatGPT:
    def __init__(self, cfg):
        self.key_list = []
        if cfg['key'] != '' or cfg['key'] != '修改我！！':
            print("[System] 读取ChatGPT Key成功")
            self.key_list = cfg['key']
            # openai.api_key = cfg['key']
        else:
            input("[System] 请先去完善ChatGPT的Key。详情请前往https://beta.openai.com/account/api-keys")
        
        # init key record
        self.init_key_record()

        chatGPT_configs = cfg['chatGPTConfigs']
        print(f'[System] 加载ChatGPTConfigs: {chatGPT_configs}')
        self.chatGPT_configs = chatGPT_configs
        self.openai_configs = cfg
    
    def chat(self, req, image_mode = False):
        # ChatGPT API 2023/3/2
        # messages = [{"role": "user", "content": prompt}]
        try:
            response = openai.ChatCompletion.create(
                messages=req,
                **self.chatGPT_configs
            )
        except Exception as e:
            print(e)
            if 'You exceeded' in str(e) or 'Billing hard limit has been reached' in str(e) or 'No API key provided' in str(e) or 'Incorrect API key provided' in str(e):
                print("[System] 当前Key已超额或者不正常,正在切换")
                self.key_stat[openai.api_key]['exceed'] = True
                self.save_key_record()

                response, is_switched = self.handle_switch_key(req)
                if not is_switched:
                    # 所有Key都超额或不正常
                    raise e
            else:
                response = openai.ChatCompletion.create(
                    messages=req,
                    **self.chatGPT_configs
                )
        self.key_stat[openai.api_key]['used'] += response['usage']['total_tokens']
        self.save_key_record()
        print("[ChatGPT] "+str(response["choices"][0]["message"]["content"]))
        return str(response["choices"][0]["message"]["content"]).strip(), response['usage']['total_tokens']
            
    def handle_switch_key(self, req):
        # messages = [{"role": "user", "content": prompt}]
        while True:
            is_all_exceed = True
            for key in self.key_stat:
                if not self.key_stat[key]['exceed']:
                    is_all_exceed = False
                    openai.api_key = key
                    print(f"[System] 切换到Key: {key}, 已使用token: {self.key_stat[key]['used']}")
                    if len(req) > 0:
                        try:
                            response = openai.ChatCompletion.create(
                                messages=req,
                                **self.chatGPT_configs
                            )
                            return response, True
                        except Exception as e:
                            print(e)
                            if 'You exceeded' in str(e):
                                print("[System] 当前Key已超额,正在切换")
                                self.key_stat[openai.api_key]['exceed'] = True
                                self.save_key_record()
                                time.sleep(1)
                                continue
                    else:
                        return True
            if is_all_exceed:
                print("[System] 所有Key已超额")
                return None, False
                
    def getConfigs(self):
        return self.openai_configs
    
    def save_key_record(self):
        with open(key_record_path, 'w', encoding='utf-8') as f:
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
        messages = [{"role": "user", "content": "1"}]
        try:
            response = openai.ChatCompletion.create(
                messages=messages,
                **self.chatGPT_configs
            )
            openai.api_key = pre_key
            return True
        except Exception as e:
            pass
        openai.api_key = pre_key
        return False

    #将key_list的key转储到key_record中，并记录相关数据
    def init_key_record(self):
        if not os.path.exists(key_record_path):
            with open(key_record_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)
        with open(key_record_path, 'r', encoding='utf-8') as keyfile:
            try:
                self.key_stat = json.load(keyfile)
            except Exception as e:
                print(e)
                self.key_stat = {}
            finally:
                for key in self.key_list:
                    if key not in self.key_stat:
                        self.key_stat[key] = {'exceed': False, 'used': 0}
                        # if openai.api_key is None:
                        #     openai.api_key = key
                    else:
                        # if self.key_stat[key]['exceed']:
                        #     print(f"Key: {key} 已超额")
                        #     continue
                        # else:
                        #     if openai.api_key is None:
                        #         openai.api_key = key
                        #         print(f"使用Key: {key}, 已使用token: {self.key_stat[key]['used']}")
                        pass
                if openai.api_key == None:
                    self.handle_switch_key("")
            self.save_key_record()
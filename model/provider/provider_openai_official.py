import openai
import yaml
from util.errors.errors import PromptExceededError
import json
import time
import os
import sys
from cores.database.conn import dbConn
from model.provider.provider import Provider
import threading

abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'
key_record_path = abs_path+'chatgpt_key_record'

class ProviderOpenAIOfficial(Provider):
    def __init__(self, cfg):
        self.key_list = []
        if 'api_base' in cfg and cfg['api_base'] != 'none' and cfg['api_base'] != '':
            openai.api_base = cfg['api_base']
        if cfg['key'] != '' and cfg['key'] != None:
            print("[System] 读取ChatGPT Key成功")
            self.key_list = cfg['key']
        else:
            input("[System] 请先去完善ChatGPT的Key。详情请前往https://beta.openai.com/account/api-keys")
        
        # init key record
        self.init_key_record()

        self.chatGPT_configs = cfg['chatGPTConfigs']
        print(f'[System] 加载ChatGPTConfigs: {self.chatGPT_configs}')
        self.openai_configs = cfg
        # 会话缓存
        self.session_dict = {}
        # 最大缓存token
        self.max_tokens = cfg['total_tokens_limit']
        # 历史记录持久化间隔时间
        self.history_dump_interval = 20

        # 读取历史记录
        try:
            db1 = dbConn()
            for session in db1.get_all_session():
                self.session_dict[session[0]] = json.loads(session[1])['data']
            print("[System] 历史记录读取成功喵")
        except BaseException as e:
            print("[System] 历史记录读取失败: " + str(e))

        # 读取统计信息
        if not os.path.exists(abs_path+"configs/stat"):
            with open(abs_path+"configs/stat", 'w', encoding='utf-8') as f:
                    json.dump({}, f)
        self.stat_file = open(abs_path+"configs/stat", 'r', encoding='utf-8')
        global count
        res = self.stat_file.read()
        if res == '':
            count = {}
        else:
            try: 
                count = json.loads(res)
            except BaseException:
                pass

        # 创建转储定时器线程
        threading.Thread(target=self.dump_history, daemon=True).start()

        # 人格
        self.now_personality = {}


    # 转储历史记录的定时器~ Soulter
    def dump_history(self):
        time.sleep(10)
        db = dbConn()
        while True:
            try:
                # print("转储历史记录...")
                for key in self.session_dict:
                    # print("TEST: "+str(db.get_session(key)))
                    data = self.session_dict[key]
                    data_json = {
                        'data': data
                    }
                    if db.check_session(key):
                        db.update_session(key, json.dumps(data_json))
                    else:
                        db.insert_session(key, json.dumps(data_json))
                # print("转储历史记录完毕")
            except BaseException as e:
                print(e)
            # 每隔10分钟转储一次
            time.sleep(10*self.history_dump_interval)

    def text_chat(self, prompt, session_id):
        # 会话机制
        if session_id not in self.session_dict:
            self.session_dict[session_id] = []

            fjson = {}
            try:
                f = open(abs_path+"configs/session", "r", encoding="utf-8")
                fjson = json.loads(f.read())
                f.close()
            except:
                pass
            finally:
                fjson[session_id] = 'true'
                f = open(abs_path+"configs/session", "w", encoding="utf-8")
                f.write(json.dumps(fjson))
                f.flush()
                f.close()

        cache_data_list, new_record, req = self.wrap(prompt, session_id)
        retry = 0
        response = None
        while retry < 5:
            try:
                response = openai.ChatCompletion.create(
                    messages=req,
                    **self.chatGPT_configs
                )
                break
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
                        break
                if 'maximum context length' in str(e):
                    print("token超限, 清空对应缓存")
                    self.session_dict[session_id] = []
                    cache_data_list, new_record, req = self.wrap(prompt, session_id)
                retry+=1
        if retry >= 5:
            raise BaseException("连接超时")
        
        self.key_stat[openai.api_key]['used'] += response['usage']['total_tokens']
        self.save_key_record()
        print("[ChatGPT] "+str(response["choices"][0]["message"]["content"]))
        chatgpt_res = str(response["choices"][0]["message"]["content"]).strip()
        current_usage_tokens = response['usage']['total_tokens']

        # 超过指定tokens， 尽可能的保留最多的条目，直到小于max_tokens
        if current_usage_tokens > self.max_tokens:
            t = current_usage_tokens
            index = 0
            while t > self.max_tokens:
                if index >= len(cache_data_list):
                    break
                # 保留人格信息
                if 'user' in cache_data_list[index] and cache_data_list[index]['user']['role'] != 'system':
                    t -= int(cache_data_list[index]['single_tokens'])
                    del cache_data_list[index]
                else:
                    index += 1
            # 删除完后更新相关字段
            self.session_dict[session_id] = cache_data_list
            # cache_prompt = get_prompts_by_cache_list(cache_data_list)

        # 添加新条目进入缓存的prompt
        new_record['AI'] = {
            'role': 'assistant',
            'content': chatgpt_res,
        }
        new_record['usage_tokens'] = current_usage_tokens
        if len(cache_data_list) > 0:
            new_record['single_tokens'] = current_usage_tokens - int(cache_data_list[-1]['usage_tokens'])
        else:
            new_record['single_tokens'] = current_usage_tokens
        cache_data_list.append(new_record)

        self.session_dict[session_id] = cache_data_list

        return chatgpt_res
        
    def image_chat(self, prompt, img_num = 1, img_size = "1024x1024"):
        retry = 0
        image_url = ''
        while retry < 5:
            try:
                # print("test1")
                response = openai.Image.create(
                    prompt=prompt,
                    n=img_num,
                    size=img_size
                )
                # print("test2")
                image_url = []
                for i in range(img_num):
                    image_url.append(response['data'][i]['url'])
                print(image_url)
                break
            except Exception as e:
                print(e)
                if 'You exceeded' in str(e) or 'Billing hard limit has been reached' in str(
                        e) or 'No API key provided' in str(e) or 'Incorrect API key provided' in str(e):
                    print("[System] 当前Key已超额或者不正常,正在切换")
                    self.key_stat[openai.api_key]['exceed'] = True
                    self.save_key_record()

                    response, is_switched = self.handle_switch_key(req)
                    if not is_switched:
                        # 所有Key都超额或不正常
                        raise e
                    else:
                        break
                retry += 1
        if retry >= 5:
            raise BaseException("连接超时")
                
        return image_url

    def forget(self, session_id) -> bool:
        self.session_dict[session_id] = []
        return True
    
    '''
    获取缓存的会话
    '''
    def get_prompts_by_cache_list(self, cache_data_list, divide=False, paging=False, size=5, page=1):
        prompts = ""
        if paging:
            page_begin = (page-1)*size
            page_end = page*size
            if page_begin < 0:
                page_begin = 0
            if page_end > len(cache_data_list):
                page_end = len(cache_data_list)
            cache_data_list = cache_data_list[page_begin:page_end]
        for item in cache_data_list:
            prompts += str(item['user']['role']) + ":\n" + str(item['user']['content']) + "\n"
            prompts += str(item['AI']['role']) + ":\n" + str(item['AI']['content']) + "\n"

            if divide:
                prompts += "----------\n"
        return prompts
    
        
    def get_user_usage_tokens(self,cache_list):
        usage_tokens = 0
        for item in cache_list:
            usage_tokens += int(item['single_tokens'])
        return usage_tokens
        
    '''
    获取统计信息
    '''
    def get_stat(self):
        try:
            f = open(abs_path+"configs/stat", "r", encoding="utf-8")
            fjson = json.loads(f.read())
            f.close()
            guild_count = 0
            guild_msg_count = 0
            guild_direct_msg_count = 0

            for k,v in fjson.items():
                guild_count += 1
                guild_msg_count += v['count']
                guild_direct_msg_count += v['direct_count']
            
            session_count = 0

            f = open(abs_path+"configs/session", "r", encoding="utf-8")
            fjson = json.loads(f.read())
            f.close()
            for k,v in fjson.items():
                session_count += 1
            return guild_count, guild_msg_count, guild_direct_msg_count, session_count
        except:
            return -1, -1, -1, -1

    # 包装信息
    def wrap(self, prompt, session_id):
        # 获得缓存信息
        context = self.session_dict[session_id]
        new_record = {
            "user": {
                "role": "user",
                "content": prompt,
            },
            "AI": {},
            'usage_tokens': 0,
        }
        req_list = []
        for i in context:
            if 'user' in i:
                req_list.append(i['user'])
            if 'AI' in i:
                req_list.append(i['AI'])
        req_list.append(new_record['user'])
        return context, new_record, req_list
    
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


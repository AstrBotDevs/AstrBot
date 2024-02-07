from openai import OpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.images_response import ImagesResponse
import json
import time
import os
import sys
from cores.database.conn import dbConn
from model.provider.provider import Provider
import threading
from util import general_utils as gu
from util.cmd_config import CmdConfig
from util.general_utils import Logger
import traceback
import tiktoken


abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

class ProviderOpenAIOfficial(Provider):
    def __init__(self, cfg):
        self.cc = CmdConfig()
        self.logger = Logger()

        self.key_list = []
        # 如果 cfg['key'] 中有长度为 1 的字符串，那么是格式错误，直接报错
        for key in cfg['key']:
            if len(key) == 1:
                raise BaseException("检查到了长度为 1 的Key。配置文件中的 openai.key 处的格式错误 (符号 - 的后面要加空格)。")
        if cfg['key'] != '' and cfg['key'] != None:
            self.key_list = cfg['key']
        if len(self.key_list) == 0:
            raise Exception("您打开了 OpenAI 模型服务，但是未填写 key。请前往填写。")
        
        self.key_stat = {}
        for k in self.key_list:
            self.key_stat[k] = {'exceed': False, 'used': 0}

        self.api_base = None
        if 'api_base' in cfg and cfg['api_base'] != 'none' and cfg['api_base'] != '':
            self.api_base = cfg['api_base']
            self.logger.log(f"设置 api_base 为: {self.api_base}", tag="OpenAI")
            
        # 创建 OpenAI Client
        self.client = OpenAI(
            api_key=self.key_list[0],
            base_url=self.api_base
        )

        self.openai_model_configs: dict = cfg['chatGPTConfigs']
        self.logger.log(f'加载 OpenAI Chat Configs: {self.openai_model_configs}', tag="OpenAI")
        self.openai_configs = cfg
        # 会话缓存
        self.session_dict = {}
        # 最大缓存token
        self.max_tokens = cfg['total_tokens_limit']
        # 历史记录持久化间隔时间
        self.history_dump_interval = 20

        self.enc = tiktoken.get_encoding("cl100k_base")

        # 从 SQLite DB 读取历史记录
        try:
            db1 = dbConn()
            for session in db1.get_all_session():
                self.session_dict[session[0]] = json.loads(session[1])['data']
            self.logger.log("读取历史记录成功。", tag="OpenAI")
        except BaseException as e:
            self.logger.log("读取历史记录失败，但不影响使用。", level=gu.LEVEL_ERROR, tag="OpenAI")

        # 创建转储定时器线程
        threading.Thread(target=self.dump_history, daemon=True).start()

        # 人格
        self.curr_personality = {}

    # 转储历史记录
    def dump_history(self):
        time.sleep(10)
        db = dbConn()
        while True:
            try:
                # print("转储历史记录...")
                for key in self.session_dict:
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

    def personality_set(self, default_personality: dict, session_id: str):
        self.curr_personality = default_personality
        new_record = {
            "user": {
                "role": "user",
                "content": default_personality['prompt'],
            },
            "AI": {
                "role": "assistant",
                "content": "好的，接下来我会扮演这个角色。"
            },
            'type': "personality",
            'usage_tokens': 0,
            'single-tokens': 0
        }
        self.session_dict[session_id].append(new_record)

    def text_chat(self, prompt, 
                  session_id = None, 
                  image_url = None, 
                  function_call=None,
                  extra_conf: dict = None,
                  default_personality: dict = None):
        if session_id is None:
            session_id = "unknown"
            if "unknown" in self.session_dict:
                del self.session_dict["unknown"] 
        # 会话机制
        if session_id not in self.session_dict:
            self.session_dict[session_id] = []
        
        if len(self.session_dict[session_id]) == 0:
            # 设置默认人格
            if default_personality is not None:
                self.personality_set(default_personality, session_id)


        # 使用 tictoken 截断消息
        _encoded_prompt = self.enc.encode(prompt)
        if self.openai_model_configs['max_tokens'] < len(_encoded_prompt):
            prompt = self.enc.decode(_encoded_prompt[:int(self.openai_model_configs['max_tokens']*0.80)])
            self.logger.log(f"注意，有一部分 prompt 文本由于超出 token 限制而被截断。", level=gu.LEVEL_WARNING, tag="OpenAI")

        cache_data_list, new_record, req = self.wrap(prompt, session_id, image_url)
        self.logger.log(f"CACHE_DATA_: {str(cache_data_list)}", level=gu.LEVEL_DEBUG, tag="OpenAI")
        self.logger.log(f"OPENAI REQUEST: {str(req)}", level=gu.LEVEL_DEBUG, tag="OpenAI")
        retry = 0
        response = None
        err = ''

        # 截断倍率
        truncate_rate = 0.75

        use_gpt4v = False
        for i in req:
            if isinstance(i['content'], list):
                use_gpt4v = True
                break
        if image_url is not None:
            use_gpt4v = True
        if use_gpt4v:
            conf = self.openai_model_configs.copy()
            conf['model'] = 'gpt-4-vision-preview'
        else:
            conf = self.openai_model_configs

        if extra_conf is not None:
            conf.update(extra_conf)

        while retry < 10:
            try:
                if function_call is None:
                    response = self.client.chat.completions.create(
                        messages=req,
                        **conf
                    )
                else:
                    response = self.client.chat.completions.create(
                        messages=req,
                        tools = function_call,
                        **conf
                    )
                break
            except Exception as e:
                print(traceback.format_exc())
                if 'Invalid content type. image_url is only supported by certain models.' in str(e):
                    raise e
                if 'You exceeded' in str(e) or 'Billing hard limit has been reached' in str(e) or 'No API key provided' in str(e) or 'Incorrect API key provided' in str(e):
                    self.logger.log("当前 Key 已超额或异常, 正在切换", level=gu.LEVEL_WARNING, tag="OpenAI")
                    self.key_stat[self.client.api_key]['exceed'] = True
                    is_switched = self.handle_switch_key()
                    if not is_switched:
                        # 所有Key都超额或不正常
                        raise e
                    retry -= 1
                elif 'maximum context length' in str(e):
                    self.logger.log("token 超限, 清空对应缓存，并进行消息截断", tag="OpenAI")
                    self.session_dict[session_id] = []
                    prompt = prompt[:int(len(prompt)*truncate_rate)]
                    truncate_rate -= 0.05
                    cache_data_list, new_record, req = self.wrap(prompt, session_id)

                elif 'Limit: 3 / min. Please try again in 20s.' in str(e) or "OpenAI response error" in str(e):
                    time.sleep(30)
                    continue
                else:
                    self.logger.log(str(e), level=gu.LEVEL_ERROR, tag="OpenAI")
                time.sleep(2)
                err = str(e)
                retry += 1
        if retry >= 10:
            self.logger.log(r"如果报错, 且您的机器在中国大陆内, 请确保您的电脑已经设置好代理软件(梯子), 并在配置文件设置了系统代理地址。详见 https://github.com/Soulter/QQChannelChatGPT/wiki", tag="OpenAI")
            raise BaseException("连接出错: "+str(err))
        assert isinstance(response, ChatCompletion)
        self.logger.log(f"OPENAI RESPONSE: {response.usage}", level=gu.LEVEL_DEBUG, tag="OpenAI")

        # 结果分类
        choice = response.choices[0]
        if choice.message.content != None:
            # 文本形式
            chatgpt_res = str(choice.message.content).strip()
        elif choice.message.tool_calls != None and len(choice.message.tool_calls) > 0:
            # tools call (function calling)
            return choice.message.tool_calls[0].function

        self.key_stat[self.client.api_key]['used'] += response.usage.total_tokens
        current_usage_tokens = response.usage.total_tokens

        # 超过指定tokens， 尽可能的保留最多的条目，直到小于max_tokens
        if current_usage_tokens > self.max_tokens:
            t = current_usage_tokens
            index = 0
            while t > self.max_tokens:
                if index >= len(cache_data_list):
                    break
                # 保留人格信息
                if cache_data_list[index]['type'] != 'personality':
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

        image_generate_configs = self.cc.get("openai_image_generate", None)
        
        while retry < 5:
            try:
                response: ImagesResponse = self.client.images.generate(
                    prompt=prompt,
                    **image_generate_configs
                )
                image_url = []
                for i in range(img_num):
                    image_url.append(response.data[i].url)
                break
            except Exception as e:
                self.logger.log(str(e), level=gu.LEVEL_ERROR)
                if 'You exceeded' in str(e) or 'Billing hard limit has been reached' in str(
                        e) or 'No API key provided' in str(e) or 'Incorrect API key provided' in str(e):
                    self.logger.log("当前 Key 已超额或者不正常, 正在切换", level=gu.LEVEL_WARNING, tag="OpenAI")
                    self.key_stat[self.client.api_key]['exceed'] = True
                    is_switched = self.handle_switch_key()
                    if not is_switched:
                        # 所有Key都超额或不正常
                        raise e
                elif 'Your request was rejected as a result of our safety system.' in str(e):
                    self.logger.log("您的请求被 OpenAI 安全系统拒绝, 请稍后再试", level=gu.LEVEL_WARNING, tag="OpenAI")
                    raise e
                else:
                    retry += 1
        if retry >= 5:
            raise BaseException("连接超时")
                
        return image_url

    def forget(self, session_id = None) -> bool:
        if session_id is None:
            return False
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
        
    # 包装信息
    def wrap(self, prompt, session_id, image_url = None):
        if image_url is not None:
            prompt = [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url
                    }
                }
            ]
        # 获得缓存信息
        context = self.session_dict[session_id]
        new_record = {
            "user": {
                "role": "user",
                "content": prompt,
            },
            "AI": {},
            'type': "common",
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
    
    def handle_switch_key(self):
        # messages = [{"role": "user", "content": prompt}]
        is_all_exceed = True
        for key in self.key_stat:
            if key == None or self.key_stat[key]['exceed']:
                continue
            is_all_exceed = False
            self.client.api_key = key
            self.logger.log(f"切换到 Key: {key}(已使用 token: {self.key_stat[key]['used']})", level=gu.LEVEL_INFO, tag="OpenAI")
            break
        if is_all_exceed:
            self.logger.log("所有 Key 已超额", level=gu.LEVEL_CRITICAL, tag="OpenAI")
            return False
        return True
        
    def get_configs(self):
        return self.openai_configs
    
    def get_key_stat(self):
        return self.key_stat
    
    def get_key_list(self):
        return self.key_list
    
    def get_curr_key(self):
        return self.client.api_key
    
    def set_key(self, key):
        self.client.api_key = key
    
    # 添加key
    def append_key(self, key, sponsor):
        self.key_list.append(key)
        self.key_stat[key] = {'exceed': False, 'used': 0, 'sponsor': sponsor}

    # 检查key是否可用
    def check_key(self, key):
        client_ = OpenAI(
            api_key=key,
            base_url=self.api_base
        )
        messages = [{"role": "user", "content": "please just echo `test`"}]
        client_.chat.completions.create(
            messages=messages,
            **self.openai_model_configs
        )
        return True

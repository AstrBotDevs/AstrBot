import os
import sys
import json
import time
import tiktoken
import threading
import traceback

from openai import AsyncOpenAI
from openai.types.images_response import ImagesResponse
from openai.types.chat.chat_completion import ChatCompletion

from cores.database.conn import dbConn
from model.provider.provider import Provider
from util import general_utils as gu
from util.cmd_config import CmdConfig
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot-core')

class ProviderOpenAIOfficial(Provider):
    def __init__(self, cfg) -> None:
        super().__init__()

        os.makedirs("data/openai", exist_ok=True)

        self.cc = CmdConfig
        self.key_data_path = "data/openai/keys.json"
        self.api_keys = []
        self.chosen_api_key = None
        self.base_url = None
        self.keys_data = {
            "keys": []
        }

        if cfg['key']: self.api_keys = cfg['key']
        if cfg['api_base']: self.base_url = cfg['api_base']
        if not self.api_keys:
            logger.warn("看起来你没有添加 OpenAI 的 API 密钥，OpenAI LLM 能力将不会启用。")
        else:
            self.chosen_api_key = self.api_keys[0]

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=self.base_url
        )
        self.model_configs: dict = cfg['chatGPTConfigs']
        self.session_memory = {} # 会话记忆
        self.session_memory_lock = threading.Lock()
        self.max_tokens = self.model_configs['max_tokens'] # 上下文窗口大小
        self.tokenizer = tiktoken.get_encoding("cl100k_base") # todo: 根据 model 切换分词器

        # 从 SQLite DB 读取历史记录
        try:
            db1 = dbConn()
            for session in db1.get_all_session():
                self.session_memory_lock.acquire()
                self.session_memory[session[0]] = json.loads(session[1])['data']
                self.session_memory_lock.release()
        except BaseException as e:
            logger.warn(f"读取 OpenAI LLM 对话历史记录 失败：{e}。仍可正常使用。")
        
        # 定时保存历史记录
        threading.Thread(target=self.dump_history, daemon=True).start()


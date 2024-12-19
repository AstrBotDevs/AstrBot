import traceback
from astrbot.core.config.astrbot_config import AstrBotConfig
from .provider import Provider
from typing import List
from astrbot.core.db import BaseDatabase
from collections import defaultdict
from .register import provider_cls_map, llm_tools
from astrbot.core import logger

class ProviderManager():
    def __init__(self, config: AstrBotConfig, db_helper: BaseDatabase):
        self.providers_config: List = config['provider']
        self.provider_settings: dict = config['provider_settings']
        self.provider_insts: List[Provider] = []
        '''加载的 Provider 的实例'''
        self.llm_tools = llm_tools
        self.curr_provider_inst: Provider = None
        self.loaded_ids = defaultdict(bool)
        self.db_helper = db_helper
        
        for provider_cfg in self.providers_config:
            if not provider_cfg['enable']:
                continue
            
            if provider_cfg['id'] in self.loaded_ids:
                raise ValueError(f"Provider ID 重复：{provider_cfg['id']}。")
            self.loaded_ids[provider_cfg['id']] = True
            
            match provider_cfg['type']:
                case "openai_chat_completion":
                    from .sources.openai_source import ProviderOpenAIOfficial # noqa: F401
                case "llm_tuner":
                    logger.info("加载 LLM Tuner 工具 ...")
                    from .sources.llmtuner_source import LLMTunerModelLoader # noqa: F401
                    
            
    async def initialize(self):
        for provider_config in self.providers_config:
            if not provider_config['enable']:
                continue
            if provider_config['type'] not in provider_cls_map:
                logger.error(f"未找到适用于 {provider_config['type']}({provider_config['id']}) 的 大模型提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。")
                continue
            cls_type = provider_cls_map[provider_config['type']]
            logger.info(f"尝试实例化 {provider_config['type']}({provider_config['id']}) 大模型提供商适配器 ...")
            try:
                inst = cls_type(provider_config, self.provider_settings, self.db_helper, self.provider_settings.get('persistant_history', True))
                self.provider_insts.append(inst)
            except Exception as e:
                traceback.print_exc()
                logger.error(f"实例化 {provider_config['type']}({provider_config['id']}) 大模型提供商适配器 失败：{e}")
        
        if len(self.provider_insts) > 0:
            self.curr_provider_inst = self.provider_insts[0]

    def get_insts(self):
        return self.provider_insts
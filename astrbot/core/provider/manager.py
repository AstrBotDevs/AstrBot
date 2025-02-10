import traceback
import uuid
from astrbot.core.config.astrbot_config import AstrBotConfig
from .provider import Provider, STTProvider, TTSProvider, Personality
from .entites import ProviderType
from typing import List
from astrbot.core.db import BaseDatabase
from collections import defaultdict
from .register import provider_cls_map, llm_tools
from astrbot.core import logger, sp

class ProviderManager():
    def __init__(self, config: AstrBotConfig, db_helper: BaseDatabase):
        self.providers_config: List = config['provider']
        self.provider_settings: dict = config['provider_settings']
        self.provider_stt_settings: dict = config.get('provider_stt_settings', {})
        self.provider_tts_settings: dict = config.get('provider_tts_settings', {})
        self.persona_configs: list = config.get('persona', [])
        
        # 人格情景管理
        # 目前没有拆成独立的模块
        self.default_persona_name = self.provider_settings.get('default_personality', 'default')
        self.personas: List[Personality] = []
        self.selected_default_persona = None
        for persona in self.persona_configs:
            begin_dialogs = persona.get("begin_dialogs", [])
            mood_imitation_dialogs = persona.get("mood_imitation_dialogs", [])
            bd_processed = []
            mid_processed = ""
            if begin_dialogs:
                if len(begin_dialogs) % 2 != 0:
                    logger.error(f"{persona['name']} 人格情景预设对话格式不对，条数应该为偶数。")
                    begin_dialogs = []
                user_turn = True
                for dialog in begin_dialogs:
                    bd_processed.append({
                        "role": "user" if user_turn else "assistant",
                        "content": dialog,
                        "_no_save": None # 不持久化到 db
                    })
                    user_turn = not user_turn
            if mood_imitation_dialogs:
                if len(mood_imitation_dialogs) % 2 != 0:
                    logger.error(f"{persona['name']} 对话风格对话格式不对，条数应该为偶数。")
                    mood_imitation_dialogs = []
                user_turn = True
                for dialog in mood_imitation_dialogs:
                    role = "A" if user_turn else "B"
                    mid_processed += f"{role}: {dialog}\n"
                    if not user_turn:
                        mid_processed += '\n'
                    user_turn = not user_turn
            
            try:
                persona = Personality(
                    **persona, 
                    _begin_dialogs_processed=bd_processed,
                    _mood_imitation_dialogs_processed=mid_processed
                )
                if persona['name'] == self.default_persona_name:
                    self.selected_default_persona = persona
                self.personas.append(persona)
            except Exception as e:
                logger.error(f"解析 Persona 配置失败：{e}")
        
        if not self.selected_default_persona and len(self.personas) > 0:
            # 默认选择第一个
            self.selected_default_persona = self.personas[0]
            
        if not self.selected_default_persona:
            self.selected_default_persona = Personality(
                prompt="You are a helpful and friendly assistant.",
                name="default",
                _begin_dialogs_processed=[],
                _mood_imitation_dialogs_processed=""
            )
            self.personas.append(self.selected_default_persona)
                
        
        self.provider_insts: List[Provider] = []
        '''加载的 Provider 的实例'''
        self.stt_provider_insts: List[STTProvider] = []
        '''加载的 Speech To Text Provider 的实例'''
        self.tts_provider_insts: List[TTSProvider] = []
        '''加载的 Text To Speech Provider 的实例'''
        self.llm_tools = llm_tools
        self.curr_provider_inst: Provider = None
        '''当前使用的 Provider 实例'''
        self.curr_stt_provider_inst: STTProvider = None
        '''当前使用的 Speech To Text Provider 实例'''
        self.curr_tts_provider_inst: TTSProvider = None
        '''当前使用的 Text To Speech Provider 实例'''
        self.loaded_ids = defaultdict(bool)
        self.db_helper = db_helper
        
        # kdb(experimental)
        self.curr_kdb_name = ""
        kdb_cfg = config.get("knowledge_db", {})
        if kdb_cfg and len(kdb_cfg):
            self.curr_kdb_name = list(kdb_cfg.keys())[0]
        
        changed = False
        for provider_cfg in self.providers_config:
            if not provider_cfg['enable']:
                continue
            
            if provider_cfg['id'] in self.loaded_ids:
                new_id = f"{provider_cfg['id']}_{str(uuid.uuid4())[:8]}"
                logger.info(f"Provider ID 重复：{provider_cfg['id']}。已自动更改为 {new_id}。")
                provider_cfg['id'] = new_id
                changed = True
            self.loaded_ids[provider_cfg['id']] = True
            
            try:
                match provider_cfg['type']:
                    case "openai_chat_completion":
                        from .sources.openai_source import ProviderOpenAIOfficial as ProviderOpenAIOfficial
                    case "zhipu_chat_completion":
                        from .sources.zhipu_source import ProviderZhipu as ProviderZhipu
                    case "llm_tuner":
                        logger.info("加载 LLM Tuner 工具 ...")
                        from .sources.llmtuner_source import LLMTunerModelLoader as LLMTunerModelLoader
                    case "dify":
                        from .sources.dify_source import ProviderDify as ProviderDify
                    case "googlegenai_chat_completion":
                        from .sources.gemini_source import ProviderGoogleGenAI as ProviderGoogleGenAI
                    case "openai_whisper_api":
                        from .sources.whisper_api_source import ProviderOpenAIWhisperAPI as ProviderOpenAIWhisperAPI
                    case "openai_whisper_selfhost":
                        from .sources.whisper_selfhosted_source import ProviderOpenAIWhisperSelfHost as ProviderOpenAIWhisperSelfHost
                    case "openai_tts_api":
                        from .sources.openai_tts_api_source import ProviderOpenAITTSAPI as ProviderOpenAITTSAPI
                    case "fishaudio_tts_api":
                        from .sources.fishaudio_tts_api_source import ProviderFishAudioTTSAPI as ProviderFishAudioTTSAPI
            except (ImportError, ModuleNotFoundError) as e:
                logger.critical(f"加载 {provider_cfg['type']}({provider_cfg['id']}) 提供商适配器失败：{e}。可能是因为有未安装的依赖。")
                continue
            except Exception as e:
                logger.critical(f"加载 {provider_cfg['type']}({provider_cfg['id']}) 提供商适配器失败：{e}。未知原因")
                continue
        
        if changed:
            try:
                config.save_config()
            except Exception as e:
                logger.warning(f"保存配置文件失败：{e}")

    async def initialize(self):
        
        selected_provider_id = sp.get("curr_provider")
        selected_stt_provider_id = self.provider_stt_settings.get("provider_id")
        selected_tts_provider_id = self.provider_settings.get("provider_id")
        provider_enabled = self.provider_settings.get("enable", False)
        stt_enabled = self.provider_stt_settings.get("enable", False)
        tts_enabled = self.provider_tts_settings.get("enable", False)
            
        for provider_config in self.providers_config:
            if not provider_config['enable']:
                continue
            if provider_config['type'] not in provider_cls_map:
                logger.error(f"未找到适用于 {provider_config['type']}({provider_config['id']}) 的提供商适配器，请检查是否已经安装或者名称填写错误。已跳过。")
                continue

            provider_metadata = provider_cls_map[provider_config['type']]
            logger.debug(f"尝试实例化 {provider_config['type']}({provider_config['id']}) 提供商适配器 ...")
            try:
                # 按任务实例化提供商
                
                if provider_metadata.provider_type == ProviderType.SPEECH_TO_TEXT:
                    # STT 任务
                    inst = provider_metadata.cls_type(provider_config, self.provider_settings)
                    
                    if getattr(inst, "initialize", None):
                        await inst.initialize()
                    
                    self.stt_provider_insts.append(inst)
                    if selected_stt_provider_id == provider_config['id'] and stt_enabled:
                        self.curr_stt_provider_inst = inst
                        logger.info(f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前语音转文本提供商适配器。")
                        
                elif provider_metadata.provider_type == ProviderType.TEXT_TO_SPEECH:
                    # TTS 任务
                    inst = provider_metadata.cls_type(provider_config, self.provider_settings)
                    
                    if getattr(inst, "initialize", None):
                        await inst.initialize()
                    
                    self.tts_provider_insts.append(inst)
                    if selected_tts_provider_id == provider_config['id'] and tts_enabled:
                        self.curr_tts_provider_inst = inst
                        logger.info(f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前文本转语音提供商适配器。")
                    
                elif provider_metadata.provider_type == ProviderType.CHAT_COMPLETION:
                    # 文本生成任务
                    inst = provider_metadata.cls_type(
                        provider_config, 
                        self.provider_settings, 
                        self.db_helper,
                        self.provider_settings.get('persistant_history', True),
                        self.selected_default_persona
                    )
                    
                    if getattr(inst, "initialize", None):
                        await inst.initialize()
                    
                    self.provider_insts.append(inst)
                    if selected_provider_id == provider_config['id'] and provider_enabled:
                        self.curr_provider_inst = inst
                        logger.info(f"已选择 {provider_config['type']}({provider_config['id']}) 作为当前提供商适配器。")
                        
            except Exception as e:
                traceback.print_exc()
                logger.error(f"实例化 {provider_config['type']}({provider_config['id']}) 提供商适配器失败：{e}")
        
        if len(self.provider_insts) > 0 and not self.curr_provider_inst and provider_enabled:
            self.curr_provider_inst = self.provider_insts[0]
            
        if len(self.stt_provider_insts) > 0 and not self.curr_stt_provider_inst and stt_enabled:
            self.curr_stt_provider_inst = self.stt_provider_insts[0]
            
        if len(self.tts_provider_insts) > 0 and not self.curr_tts_provider_inst and tts_enabled:
            self.curr_tts_provider_inst = self.tts_provider_insts[0]
            
        if not self.curr_provider_inst:
            logger.warning("未启用任何用于 文本生成 的提供商适配器。")
            
        if stt_enabled and not self.curr_stt_provider_inst:
                logger.warning("未启用任何用于 语音转文本 的提供商适配器。")
        
        if tts_enabled and not self.curr_tts_provider_inst:
                logger.warning("未启用任何用于 文本转语音 的提供商适配器。")
        

    def get_insts(self):
        return self.provider_insts
    
    async def terminate(self):
        for provider_inst in self.provider_insts:
            if hasattr(provider_inst, "terminate"):
                await provider_inst.terminate()
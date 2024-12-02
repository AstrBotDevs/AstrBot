import os
import json
import shutil
import logging
from . import DEFAULT_CONFIG_VERSION_2
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

ASTRBOT_CONFIG_PATH = "data/cmd_config.json"
logger = logging.getLogger("astrbot")

@dataclass
class RateLimit:
    time: int = 60
    count: int = 30

@dataclass
class PlatformSettings:
    unique_session: bool = False
    rate_limit: RateLimit = field(default_factory=RateLimit)
    reply_prefix: str = ""
    forward_threshold: int = 200
    
    def __post_init__(self):
        self.rate_limit = RateLimit(**self.rate_limit)
    
@dataclass
class PlatformConfig():
    id: str = ""
    name: str = ""
    enable: bool = False

@dataclass
class QQOfficialPlatformConfig(PlatformConfig):
    appid: str = ""
    secret: str = ""
    enable_group_c2c: bool = True
    enable_guild_direct_message: bool = True
    
@dataclass
class AiocqhttpPlatformConfig(PlatformConfig):
    ws_reverse_host: str = ""
    ws_reverse_port: int = 6199
    qq_id_whitelist: List[str] = field(default_factory=list)
    qq_group_id_whitelist: List[str] = field(default_factory=list)
    
@dataclass
class WechatPlatformConfig(PlatformConfig):
    wechat_id_whitelist: List[str] = field(default_factory=list)
    
@dataclass
class ModelConfig:
    model: str = "gpt-4o"
    max_tokens: int = 6000
    temperature: float = 0.9
    top_p: float = 1
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

@dataclass
class ImageGenerationModelConfig:
    enable: bool = True
    model: str = "dall-e-3"
    size: str = "1024x1024"
    style: str = "vivid"
    quality: str = "standard"
    
@dataclass
class EmbeddingModel:
    enable: bool = False
    model: str = ""
    
@dataclass
class LLMConfig:
    id: str = ""
    name: str = "openai"
    enable: bool = True
    key: List[str] = field(default_factory=list)
    api_base: str = ""
    prompt_prefix: str = ""
    default_personality: str = ""
    model_config: ModelConfig = field(default_factory=ModelConfig)
    image_generation_model_config: Optional[ImageGenerationModelConfig] = field(default_factory=ImageGenerationModelConfig)
    embedding_model: Optional[EmbeddingModel] = field(default_factory=EmbeddingModel)

    def __post_init__(self):
        if isinstance(self.model_config, dict):
            self.model_config = ModelConfig(**self.model_config)
        if isinstance(self.image_generation_model_config, dict):
            self.image_generation_model_config = ImageGenerationModelConfig(**self.image_generation_model_config) if self.image_generation_model_config else None
        if isinstance(self.embedding_model, dict):
            self.embedding_model = EmbeddingModel(**self.embedding_model) if self.embedding_model else None

@dataclass
class LLMSettings:
    wake_prefix: str = ""
    web_search: bool = False
    identifier: bool = False

@dataclass
class BaiduAIPConfig:
    enable: bool = False
    app_id: str = ""
    api_key: str = ""
    secret_key: str = ""

@dataclass
class InternalKeywordsConfig:
    enable: bool = True
    extra_keywords: List[str] = field(default_factory=list)

@dataclass
class ContentSafetyConfig:
    baidu_aip: BaiduAIPConfig = field(default_factory=BaiduAIPConfig)
    internal_keywords: InternalKeywordsConfig = field(default_factory=InternalKeywordsConfig)
    
    def __post_init__(self):
        self.baidu_aip = BaiduAIPConfig(**self.baidu_aip)
        self.internal_keywords = InternalKeywordsConfig(**self.internal_keywords)
        
@dataclass
class DashboardConfig:
    enable: bool = True
    username: str = ""
    password: str = ""
    
    
@dataclass
class ATRILongTermMemory:
    enable: bool = False
    summary_threshold_cnt: int = 5
    
@dataclass
class ATRIActiveMessage:
    enable: bool = False
    
@dataclass
class ProjectATRI:
    enable: bool = False
    long_term_memory: ATRILongTermMemory = field(default_factory=ATRILongTermMemory)
    active_message: ATRIActiveMessage = field(default_factory=ATRIActiveMessage)
    persona: str = ""
    embedding_provider_id: str = ""
    summarize_provider_id: str = ""
    chat_provider_id: str = ""
    chat_base_model_path: str = ""
    chat_adapter_model_path: str = ""
    quantization_bit: int = 4
    
    def __post_init__(self):
        if isinstance(self.long_term_memory, dict):
            self.long_term_memory = ATRILongTermMemory(**self.long_term_memory)
        if isinstance(self.active_message, dict):
            self.active_message = ATRIActiveMessage(**self.active_message)

@dataclass
class AstrBotConfig():
    config_version: int = 2
    platform_settings: PlatformSettings = field(default_factory=PlatformSettings)
    llm: List[LLMConfig] = field(default_factory=list)
    llm_settings: LLMSettings = field(default_factory=LLMSettings)
    content_safety: ContentSafetyConfig = field(default_factory=ContentSafetyConfig)
    t2i: bool = True
    admins_id: List[str] = field(default_factory=list)
    https_proxy: str = ""
    http_proxy: str = ""
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    platform: List[PlatformConfig] = field(default_factory=list)
    wake_prefix: List[str] = field(default_factory=list)
    log_level: str = "INFO"
    t2i_endpoint: str = ""
    pip_install_arg: str = ""
    plugin_repo_mirror: str = ""
    project_atri: ProjectATRI = field(default_factory=ProjectATRI)

    def __init__(self) -> None:
        self.init_configs()
        
        # compability
        if isinstance(self.wake_prefix, str):
            self.wake_prefix = [self.wake_prefix]
            
        if len(self.wake_prefix) == 0:
            self.wake_prefix.append("/")
        
    def load_from_dict(self, data: Dict):
        '''从字典中加载配置到对象。

        @note: 适用于 version 2 配置文件。
        '''
        self.config_version=data.get("version", 2)
        self.platform=[]
        
        left_platforms = ["qq_official", "aiocqhttp", "wechat"]
        for p in data.get("platform", []):
            if 'name' not in p:
                logger.warning("A platform config missing name, skipping.")
                continue
            if p["name"] == "qq_official":
                self.platform.append(QQOfficialPlatformConfig(**p))
                left_platforms.remove(p["name"])
            elif p["name"] == "aiocqhttp":
                self.platform.append(AiocqhttpPlatformConfig(**p))
                left_platforms.remove(p["name"])
            elif p["name"] == "wechat":
                self.platform.append(WechatPlatformConfig(**p))
                left_platforms.remove(p["name"])
        # 注入默认配置
        for p in left_platforms:
            if p == "qq_official":
                self.platform.append(QQOfficialPlatformConfig(id="default", name=p))
            elif p == "aiocqhttp":
                self.platform.append(AiocqhttpPlatformConfig(id="default", name=p))
            elif p == "wechat":
                self.platform.append(WechatPlatformConfig(id="default", name=p))
                
        self.platform_settings=PlatformSettings(**data.get("platform_settings", {}))
        self.llm=[LLMConfig(**l) for l in data.get("llm", [])]
        self.llm_settings=LLMSettings(**data.get("llm_settings", {}))
        self.content_safety=ContentSafetyConfig(**data.get("content_safety", {}))
        self.t2i=data.get("t2i", True)
        self.admins_id=data.get("admins_id", [])
        self.https_proxy=data.get("https_proxy", "")
        self.http_proxy=data.get("http_proxy", "")
        self.dashboard=DashboardConfig(**data.get("dashboard", {}))
        self.wake_prefix=data.get("wake_prefix", ["/"])
        self.log_level=data.get("log_level", "INFO")
        self.t2i_endpoint=data.get("t2i_endpoint", "")
        self.pip_install_arg=data.get("pip_install_arg", "")
        self.plugin_repo_mirror=data.get("plugin_repo_mirror", "")
        self.project_atri=ProjectATRI(**data.get("project_atri", {}))
        
    def flush_config(self, config: dict = None):
        '''将配置写入文件, 如果没有传入配置，则写入默认配置'''
        with open(ASTRBOT_CONFIG_PATH, "w", encoding="utf-8-sig") as f:
            json.dump(config if config else DEFAULT_CONFIG_VERSION_2, f, indent=2, ensure_ascii=False)
            f.flush()
    
    def save_config(self):
        '''将现存配置写入文件'''
        self.flush_config(self.to_dict())
    
    def init_configs(self):
        '''初始化必需的配置项'''
        config = None
        
        if not self.check_exist():
            self.flush_config()
            config = DEFAULT_CONFIG_VERSION_2
        else:
            config = self.get_all()
        
        # 加载配置到对象
        self.load_from_dict(config)
        # 保存到文件
        # 这一步操作是为了保证配置文件中的字段的完整性。
        # 在版本变动新增配置项时，将对象中新增的配置项的默认值写入文件。
        self.save_config()

    def get(self, key: str, default=None):
        '''从文件系统中直接获取配置'''
        with open(ASTRBOT_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            if key in d:
                return d[key]
            else:
                return default

    def get_all(self):
        '''从文件系统中获取所有配置'''
        with open(ASTRBOT_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            conf_str = f.read() 
        if conf_str.startswith(u'/ufeff'): # remove BOM
            conf_str = conf_str.encode('utf8')[3:].decode('utf8')
        if not conf_str:
            return {}
        conf = json.loads(conf_str)
        return conf

    def put(self, key, value):
        with open(ASTRBOT_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            d[key] = value
            with open(ASTRBOT_CONFIG_PATH, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
                f.flush()
                
    def to_dict(self) -> Dict:
        return asdict(self)

    def check_exist(self) -> bool:
        return os.path.exists(ASTRBOT_CONFIG_PATH)
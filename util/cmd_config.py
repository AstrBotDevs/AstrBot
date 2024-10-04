import os
import json
import shutil
import logging
from util.io import on_error
from type.config import DEFAULT_CONFIG_VERSION_2, MAPPINGS_1_2
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
class NakuruPlatformConfig(PlatformConfig):
    host: str = "172.0.0.1",
    port: int = 5700,
    websocket_port: int = 6700,
    enable_group: bool = True,
    enable_guild: bool = True,
    enable_direct_message: bool = True,
    enable_group_increase: bool = True
    
@dataclass
class AiocqhttpPlatformConfig(PlatformConfig):
    ws_reverse_host: str = ""
    ws_reverse_port: int = 6199

@dataclass
class ModelConfig:
    model: str = "gpt-4o"
    max_tokens: int = 6000
    temperature: float = 0.9
    top_p: float = 1
    frequency_penalty: float = 0
    presence_penalty: float = 0

@dataclass
class ImageGenerationModelConfig:
    enable: bool = True
    model: str = "dall-e-3"
    size: str = "1024x1024"
    style: str = "vivid"
    quality: str = "standard"
    
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
    image_generation_model_config: Optional[ImageGenerationModelConfig] = None

    def __post_init__(self):
        self.model_config = ModelConfig(**self.model_config)
        if self.image_generation_model_config:
            self.image_generation_model_config = ImageGenerationModelConfig(**self.image_generation_model_config)
@dataclass
class LLMSettings:
    wake_prefix: str = ""
    web_search: bool = False

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
class AstrBotConfig():
    config_version: int = 2
    platform_settings: PlatformSettings = field(default_factory=PlatformSettings)
    llm: List[LLMConfig] = field(default_factory=list)
    llm_settings: LLMSettings = field(default_factory=LLMSettings)
    content_safety: ContentSafetyConfig = field(default_factory=ContentSafetyConfig)
    t2i: bool = True
    dump_history_interval: int = 10
    admins_id: List[str] = field(default_factory=list)
    https_proxy: str = ""
    http_proxy: str = ""
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    platform: List[PlatformConfig] = field(default_factory=list)
    wake_prefix: List[str] = field(default_factory=list)
    log_level: str = "INFO"
    t2i_endpoint: str = ""

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
        for p in data.get("platform", []):
            if 'name' not in p:
                logger.warning("A platform config missing name, skipping.")
                continue
            if p["name"] == "qq_official":
                self.platform.append(QQOfficialPlatformConfig(**p))
            elif p["name"] == "nakuru":
                self.platform.append(NakuruPlatformConfig(**p))
            elif p["name"] == "aiocqhttp":
                self.platform.append(AiocqhttpPlatformConfig(**p))
            else:
                self.platform.append(PlatformConfig(**p))
        self.platform_settings=PlatformSettings(**data.get("platform_settings", {}))
        self.llm=[LLMConfig(**l) for l in data.get("llm", [])]
        self.llm_settings=LLMSettings(**data.get("llm_settings", {}))
        self.content_safety=ContentSafetyConfig(**data.get("content_safety", {}))
        self.t2i=data.get("t2i", True)
        self.dump_history_interval=data.get("dump_history_interval", 10)
        self.admins_id=data.get("admins_id", [])
        self.https_proxy=data.get("https_proxy", "")
        self.http_proxy=data.get("http_proxy", "")
        self.dashboard=DashboardConfig(**data.get("dashboard", {}))
        self.wake_prefix=data.get("wake_prefix", ["/"])
        self.log_level=data.get("log_level", "INFO")
        self.t2i_endpoint=data.get("t2i_endpoint", "")

    def migrate_config_1_2(self, old: dict) -> dict:
        '''将配置文件从版本 1 迁移至版本 2'''
        logger.info("正在更新配置文件到 version 2...")
        new_config = DEFAULT_CONFIG_VERSION_2
        mappings = MAPPINGS_1_2

        def set_nested_value(d, keys, value):
            cursor = d
            for key in keys[:-1]:
                cursor = cursor[key]
            cursor[keys[-1]] = value

        for old_path, new_path in mappings:
            value = old
            try:
                for key in old_path:
                    value = value[key] # soooooo convenient!!
                set_nested_value(new_config, new_path, value)
            except KeyError:
                # 如果旧配置中没有这个键，跳过，即使用新配置的默认值
                continue

        logger.info("配置文件更新完成。")
        return new_config
        
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
            # check if the config is outdated
            if 'config_version' not in config: # version 1
                config = self.migrate_config_1_2(config)
                self.flush_config(config)
        
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
    
def try_migrate():
    '''
    - 将 cmd_config.json 迁移至 data/cmd_config.json (如果存在)
    - 将 addons/plugins 迁移至 data/plugins (如果存在)
    '''
    if os.path.exists("cmd_config.json") and not os.path.exists("data/cmd_config.json"):
        try:
            shutil.move("cmd_config.json", "data/cmd_config.json")
        except:
            logger.error("迁移 cmd_config.json 失败。")

    if os.path.exists("addons/plugins"):
        if os.path.exists("data/plugins"):
            try:
                shutil.rmtree("data/plugins", onerror=on_error)
            except:
                logger.error("删除 data/plugins 失败。")
        try:
            shutil.move("addons/plugins", "data/")
            shutil.rmtree("addons", onerror=on_error)
        except:
            logger.error("迁移 addons/plugins 失败。")
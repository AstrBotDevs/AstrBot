from dataclasses import dataclass
@dataclass
class PlatformMetadata():
    name: str # 平台的名称
    description: str # 平台的描述
    
    default_config_tmpl: dict = None # 平台的默认配置模板
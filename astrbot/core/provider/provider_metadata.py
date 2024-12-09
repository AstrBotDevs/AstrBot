from dataclasses import dataclass

@dataclass
class ProviderMetaData():
    type: str # 提供商适配器名称，如 openai, ollama
    desc: str = "" # 提供商适配器描述.
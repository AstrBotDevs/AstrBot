from dataclasses import dataclass

@dataclass
class Middleware():
    name: str = ""
    description: str = ""
    origin: str = ""  # 注册来源
    func: callable = None
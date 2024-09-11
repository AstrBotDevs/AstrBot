from dataclasses import dataclass

@dataclass
class Middleware():
    name: str = ""
    description: str = ""
    func: callable = None
    origin: str  # 注册来源
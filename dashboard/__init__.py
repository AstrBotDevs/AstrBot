from dataclasses import dataclass

class DashBoardData():
    stats: dict = {}

@dataclass
class Response():
    status: str
    message: str
    data: dict

from typing import List


class Store:
    async def save(self, text: str):
        pass

    async def query(self, query: str, top_n: int = 3) -> List[str]:
        pass

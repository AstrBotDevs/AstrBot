from util.t2i.strategies.base_strategy import RenderStrategy

class RenderContext:
    def __init__(self, strategy: RenderStrategy):
        self._strategy = strategy

    def set_strategy(self, strategy: RenderStrategy):
        self._strategy = strategy

    async def render(self, text: str, return_url: bool = False):
        return await self._strategy.render(text, return_url)

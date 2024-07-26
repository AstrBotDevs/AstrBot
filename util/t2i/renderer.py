from util.t2i.strategies.local_strategy import LocalRenderStrategy
from util.t2i.strategies.network_strategy import NetworkRenderStrategy
from util.t2i.context import RenderContext
from SparkleLogging.utils.core import LogManager
from logging import Logger

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class TextToImageRenderer:
    def __init__(self):
        self.network_strategy = NetworkRenderStrategy()
        self.local_strategy = LocalRenderStrategy()
        self.context = RenderContext(self.network_strategy)

    async def render(self, text: str, use_network: bool = True, return_url: bool = False):
        if use_network:
            try:
                return await self.context.render(text, return_url=return_url)
            except BaseException as e:
                logger.error(f"Failed to render image via AstrBot API: {e}. Falling back to local rendering.")
                self.context.set_strategy(self.local_strategy)
                return await self.context.render(text)
        else:
            self.context.set_strategy(self.local_strategy)
            return await self.context.render(text)

from .network_strategy import NetworkRenderStrategy
from .local_strategy import LocalRenderStrategy
from astrbot.core.log import LogManager

logger = LogManager.GetLogger(log_name="astrbot")


class HtmlRenderer:
    def __init__(self, endpoint_url: str | None = None):
        self.network_strategy = NetworkRenderStrategy(endpoint_url)
        self.local_strategy = LocalRenderStrategy()

    async def initialize(self):
        await self.network_strategy.initialize()
        #await self.local_strategy.initialize()

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        options: dict | None = None,
        return_url: bool = False,
        use_network: bool = True,
    ):
        """使用自定义文转图模板。该方法会通过网络调用 t2i 终结点图文渲染API。
        @param tmpl_str: HTML Jinja2 模板 / Markdown 文本。
        @param tmpl_data: jinja2 模板数据 / pillowmd渲染器样式模版
        @param options: 渲染选项。

        @return: 图片 URL 或者文件路径，取决于 return_url 参数。

        @example: 参见 https://astrbot.app 插件开发部分。
        """
        if use_network:
            return await self.network_strategy.render_custom_template(
                tmpl_str, tmpl_data, return_url, options
            )
        else:
            return await self.local_strategy.render_custom_template(
                tmpl_str, tmpl_data, options
            )

    async def render_t2i(
        self,
        text: str,
        template_name: str | None = None,
        return_url: bool = False,
        use_network: bool = True,
    ):
        """使用默认文转图模板。"""
        if use_network:
            try:
                return await self.network_strategy.render(
                    text, return_url=return_url, template_name=template_name
                )
            except BaseException as e:
                logger.error(
                    f"Failed to render image via AstrBot API: {e}. Falling back to local rendering."
                )
                return await self.local_strategy.render(text, template_name)
        else:
            return await self.local_strategy.render(text, template_name)

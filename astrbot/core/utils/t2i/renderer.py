from .network_strategy import NetworkRenderStrategy
from .local_strategy import LocalRenderStrategy
from astrbot.core.log import LogManager

logger = LogManager.GetLogger(log_name="astrbot")


class HtmlRenderer:
    def __init__(self, endpoint_url: str = None):
        self.network_strategy = NetworkRenderStrategy(endpoint_url)
        self.local_strategy = LocalRenderStrategy()

    def set_network_endpoint(self, endpoint_url: str):
        """设置 t2i 的网络端点。"""
        logger.info("文本转图像服务接口: " + endpoint_url)
        self.network_strategy.set_endpoint(endpoint_url)

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = False,
        options: dict = None,
    ):
        """使用自定义文转图模板。该方法会通过网络调用 t2i 终结点图文渲染API。
        @param tmpl_str: HTML Jinja2 模板。
        @param tmpl_data: jinja2 模板数据。
        @param options: 渲染选项。

        @return: 图片 URL 或者文件路径，取决于 return_url 参数。

        @example: 参见 https://astrbot.app 插件开发部分。
        """
        return await self.network_strategy.render_custom_template(
            tmpl_str, tmpl_data, return_url, options
        )

    async def render_t2i(
        self, text: str, use_network: bool = True, return_url: bool = False
    ):
        """使用默认文转图模板。"""
        if use_network:
            try:
                return await self.network_strategy.render(text, return_url=return_url)
            except BaseException as e:
                logger.error(
                    f"Failed to render image via AstrBot API: {e}. Falling back to local rendering."
                )
                return await self.local_strategy.render(text)
        else:
            return await self.local_strategy.render(text)

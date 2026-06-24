# 导入日志管理器，用于获取统一的日志记录器
from astrbot.core.log import LogManager

# 导入本地渲染策略类
from .local_strategy import LocalRenderStrategy
# 导入网络渲染策略类
from .network_strategy import NetworkRenderStrategy

# 获取名为 "astrbot" 的日志记录器实例
logger = LogManager.GetLogger(log_name="astrbot")


class HtmlRenderer:
    """
    HTML 渲染器主类。
    整合了网络渲染和本地渲染两种策略，提供统一的文转图渲染接口。
    优先使用网络渲染，失败时自动降级到本地渲染。
    """

    def __init__(self, endpoint_url: str | None = None) -> None:
        """
        初始化 HTML 渲染器。

        Args:
            endpoint_url: 自定义的网络渲染端点 URL，为 None 时使用默认官方端点
        """
        # 创建网络渲染策略实例，用于远程 API 渲染
        self.network_strategy = NetworkRenderStrategy(endpoint_url)
        # 创建本地渲染策略实例，用于本地后备渲染
        self.local_strategy = LocalRenderStrategy()

    async def initialize(self) -> None:
        """
        异步初始化渲染器。
        主要初始化网络渲染策略，包括获取可用端点列表等。
        """
        # 调用网络策略的初始化方法
        await self.network_strategy.initialize()

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = False,
        options: dict | None = None,
    ):
        """
        使用自定义文转图模板进行渲染。
        该方法会通过网络调用 t2i 终结点图文渲染 API。

        Args:
            tmpl_str: HTML Jinja2 模板字符串。
            tmpl_data: Jinja2 模板数据字典，用于填充模板变量。
            options: 渲染选项字典，如页面大小、图片格式、质量等。

        Returns:
            str: 图片 URL 或文件路径，取决于 return_url 参数。

        Note:
            使用示例可参考 https://docs.astrbot.app 插件开发部分文档。
        """
        # 委托给网络渲染策略处理自定义模板渲染
        return await self.network_strategy.render_custom_template(
            tmpl_str,      # 传入模板字符串
            tmpl_data,     # 传入模板渲染数据
            return_url,    # 传入返回类型标志
            options,       # 传入渲染选项
        )

    async def render_t2i(
        self,
        text: str,
        use_network: bool = True,
        return_url: bool = False,
        template_name: str | None = None,
    ):
        """
        使用默认文转图模板将文本渲染为图像。
        支持网络渲染和本地渲染两种方式，网络渲染失败时自动降级。

        Args:
            text: 要渲染的文本内容。
            use_network: 是否优先使用网络渲染，默认为 True。
            return_url: 是否返回图片 URL，False 则返回本地文件路径。
            template_name: 使用的模板名称，为 None 时使用默认模板。

        Returns:
            str: 渲染后的图像文件路径或 URL。
        """
        # 判断是否使用网络渲染
        if use_network:
            try:
                # 尝试使用网络策略进行渲染
                return await self.network_strategy.render(
                    text,                    # 要渲染的文本
                    return_url=return_url,   # 返回类型
                    template_name=template_name,  # 模板名称
                )
            except BaseException as e:
                # 网络渲染失败，记录错误日志
                logger.error(
                    f"Failed to render image via AstrBot API: {e}. Falling back to local rendering.",
                )
                # 降级到本地渲染策略
                return await self.local_strategy.render(text)
        else:
            # 直接使用本地渲染策略
            return await self.local_strategy.render(text)
from .QnAStatsRenderer import QnAStatsRenderer

class QnAStatsRendererIndustrial(QnAStatsRenderer):
    """
    工业（深色）主题渲染器。

    用法：
    - 白天（浅色）：QnAStatsRenderer(...)
    - 工业（深色）：QnAStatsRendererIndustrial(...)
    """

    def __init__(self, output_dir: str = "data/quiz_images"):
        super().__init__(output_dir=output_dir, theme="industrial")

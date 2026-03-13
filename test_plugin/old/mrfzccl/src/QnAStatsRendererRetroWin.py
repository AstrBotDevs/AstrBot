from .QnAStatsRenderer import QnAStatsRenderer

class QnAStatsRendererRetroWin(QnAStatsRenderer):
    """
    复古 Win / 像素风主题渲染器。

    用法：
    - 默认（浅色）：QnAStatsRenderer(...)
    - 工业（深色）：QnAStatsRendererIndustrial(...)
    - 复古（Win）：QnAStatsRendererRetroWin(...)
    """

    def __init__(self, output_dir: str = "data/quiz_images"):
        super().__init__(output_dir=output_dir, theme="retro_win")

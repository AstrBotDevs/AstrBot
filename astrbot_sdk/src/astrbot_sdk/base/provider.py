from dishka import Provider, Scope, provide

from astrbot_api import IAstrbotPaths

from .paths import AstrbotPaths


class AstrbotBaseProvider(Provider):
    scope = Scope.APP  # 基础Provider的作用域设为APP

    @provide
    def get_astrbot_paths_cls(self) -> type[IAstrbotPaths]:
        return AstrbotPaths







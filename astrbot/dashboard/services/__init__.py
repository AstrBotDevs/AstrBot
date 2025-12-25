from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class BaseService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle):
        self.cl = core_lifecycle
        self.clpm = core_lifecycle.provider_manager

class Driver:
    def __init__(self) -> None:
        self.config = {}

    def on_startup(self, func):
        pass
    def on_bot_connect(self, func):
        pass

def get_driver():
    return Driver()
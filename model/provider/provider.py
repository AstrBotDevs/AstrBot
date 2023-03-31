import abc

class Provider:
    def __init__(self, cfg):
        pass

    def text_chat(self, prompt):
        pass

    def image_chat(self, prompt):
        pass

    def memory(self):
        pass

    @abc.abstractmethod
    def forget(self) -> bool:
        pass
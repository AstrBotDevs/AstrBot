import abc

class Provider:
    def __init__(self, cfg):
        pass
    
    @abc.abstractmethod
    def text_chat(self, prompt, session_id):
        pass

    @abc.abstractmethod
    def forget(self) -> bool:
        pass
import abc

class Provider:
    def __init__(self, cfg):
        pass
    
    @abc.abstractmethod
    async def text_chat(self, prompt, session_id, image_url: None, function_call: None, extra_conf: dict = None, default_personality: dict = None) -> str:
        pass

    @abc.abstractmethod
    async def forget(self, session_id = None) -> bool:
        pass
from collections import defaultdict

class Provider:
    def __init__(self) -> None:
        self.curr_model_name = "unknown"
        
    def reset_model_stat(self):
        self.model_stat.clear()
        
    def set_curr_model(self, model_name: str):
        self.curr_model_name = model_name
    
    def get_curr_model(self):
        return self.curr_model_name
    
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_url: None = None,
                        tools: None = None,
                        extra_conf: dict = None,
                        default_personality: dict = None,
                        **kwargs) -> str:
        '''
        [require]
        prompt: 提示词
        session_id: 会话id

        [optional]
        image_url: 图片url（识图）
        tools: 函数调用工具
        extra_conf: 额外配置
        default_personality: 默认人格
        '''
        raise NotImplementedError()

    async def image_generate(self, prompt, session_id, **kwargs) -> str:
        '''
        [require]
        prompt: 提示词
        session_id: 会话id
        '''
        raise NotImplementedError()

    async def forget(self, session_id=None) -> bool:
        '''
        重置会话
        '''
        raise NotImplementedError()

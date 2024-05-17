class Provider:
    async def text_chat(self,
                        prompt: str,
                        session_id: str,
                        image_url: None,
                        tools: None,
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
        raise NotImplementedError

    async def image_generate(self, prompt, session_id, **kwargs) -> str:
        '''
        [require]
        prompt: 提示词
        session_id: 会话id
        '''
        raise NotImplementedError

    async def forget(self, session_id=None) -> bool:
        '''
        重置会话
        '''
        raise NotImplementedError

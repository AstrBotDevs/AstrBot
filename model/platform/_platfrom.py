import abc

class Platform():
    def __init__(self, message_handler: callable) -> None:
        '''
        初始化平台的各种接口
        '''
        self.message_handler = message_handler
        pass

    @abc.abstractmethod
    def handle_msg():
        '''
        处理到来的消息
        '''
        pass

    @abc.abstractmethod
    def reply_msg():
        '''
        回复消息（被动发送）
        '''
        pass

    @abc.abstractmethod
    def send_msg():
        '''
        发送消息（主动发送）
        '''
        pass
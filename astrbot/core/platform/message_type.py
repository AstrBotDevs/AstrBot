from enum import Enum

class MessageType(Enum):
    GROUP_MESSAGE = 'GroupMessage'  # 群组形式的消息
    FRIEND_MESSAGE = 'FriendMessage'  # 私聊、好友等单聊消息
    
from enum import Enum


class RstScene(Enum):
    GROUP_UNIQUE_ON = ("group_unique_on", "群聊+会话隔离开启")
    GROUP_UNIQUE_OFF = ("group_unique_off", "群聊+会话隔离关闭")
    PRIVATE = ("private", "私聊")

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @classmethod
    def from_index(cls, index: int) -> "RstScene":
        mapping = {1: cls.GROUP_UNIQUE_ON, 2: cls.GROUP_UNIQUE_OFF, 3: cls.PRIVATE}
        return mapping[index]

    @classmethod
    def get_scene(cls, is_group: bool, is_unique_session: bool) -> "RstScene":
        if is_group:
            return cls.GROUP_UNIQUE_ON if is_unique_session else cls.GROUP_UNIQUE_OFF
        return cls.PRIVATE

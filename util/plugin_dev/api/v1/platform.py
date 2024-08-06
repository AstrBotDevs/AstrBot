'''
消息平台。

Platform类是消息平台的抽象类，定义了消息平台的基本接口。
消息平台的具体实现类需要继承Platform类，并实现其中的抽象方法。
'''

from model.platform import Platform

from model.platform.qq_nakuru import QQNakuru
from model.platform.qq_official import QQOfficial
from model.platform.qq_aiocqhttp import AIOCQHTTP
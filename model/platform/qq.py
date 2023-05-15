from nakuru.entities.components import Plain, At, Image
from util import general_utils as gu
import asyncio
class QQ:
    def __init__(self, is_start: bool, gocq_loop = None) -> None:
        self.is_start = is_start
        self.gocq_loop = gocq_loop

    def run_bot(self, gocq):
        self.client = gocq
        self.client.run()

    def get_msg_loop(self):
        return self.gocq_loop

    async def send_qq_msg(self, 
                          source, 
                          res, 
                          image_mode: bool = False):
        if not self.is_start:
            raise Exception("管理员未启动QQ平台")
        """
         res可以是一个数组, 也就是gocq的消息链。
         插件开发者请使用send方法, 可以不用直接调用这个方法。
        """
        gu.log("回复QQ消息: "+str(res), level=gu.LEVEL_INFO, tag="QQ", max_len=30)

        if isinstance(source, int):
            source = {
                "type": "GroupMessage",
                "group_id": source
            }

        if isinstance(res, list) and len(res) > 0:
            await self.client.sendGroupMessage(source.group_id, res)
            return
        
        # 通过消息链处理
        if not image_mode:
            if source.type == "GroupMessage":
                await self.client.sendGroupMessage(source.group_id, [
                    At(qq=source.user_id),
                    Plain(text=res)
                ])
            elif source.type == "FriendMessage":
                await self.client.sendFriendMessage(source.user_id, [
                    Plain(text=res)
                ])
        else:
            if source.type == "GroupMessage":
                await self.client.sendGroupMessage(source.group_id, [
                    At(qq=source.user_id),
                    Plain(text="好的，我根据你的需要为你生成了一张图片😊"),
                    Image.fromURL(url=res)
                ])
            elif source.type == "FriendMessage":
                await self.client.sendFriendMessage(source.user_id, [
                    Plain(text="好的，我根据你的需要为你生成了一张图片😊"),
                    Image.fromURL(url=res)
                ])

    def send(self, 
            to,
            res):
        '''
        提供给插件的发送QQ消息接口, 不用在外部await。
        参数说明：第一个参数可以是消息对象，也可以是QQ群号。第二个参数是消息内容（消息内容可以是消息链列表，也可以是纯文字信息）。
        '''
        if isinstance(to, int):

        try:
            asyncio.run_coroutine_threadsafe(self.send_qq_msg(message_obj, res), self.gocq_loop).result()
        except BaseException as e:
            raise e
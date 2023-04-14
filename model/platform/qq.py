from nakuru.entities.components import Plain

class QQ:
    def run_bot(self, gocq):
        self.client = gocq
        self.client.run()

    async def send_qq_msg(self, source, res):
        print("[System-Info] 回复QQ消息中..."+res)
        # 通过消息链处理
        if source.type == "GroupMessage":
            await self.client.sendGroupMessage(source.group_id, [
                Plain(text=res)
            ])
        elif source.type == "FriendMessage":
            await self.client.sendFriendMessage(source.user_id, [
                Plain(text=res)
            ])
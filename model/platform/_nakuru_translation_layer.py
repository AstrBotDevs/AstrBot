from nakuru.entities.components import Plain, At, Image
from botpy.message import Message, DirectMessage

class NakuruGuildMember():
    tiny_id: int # 发送者识别号
    user_id: int # 发送者识别号
    title: str 
    nickname: str # 昵称
    role: int # 角色
    icon_url: str # 头像url

class NakuruGuildMessage():
    type: str = "GuildMessage"
    self_id: int # bot的qq号
    self_tiny_id: int # bot的qq号
    sub_type: str # 消息类型
    message_id: str # 消息id
    guild_id: int # 频道号 
    channel_id: int # 子频道号
    user_id: int # 发送者qq号
    message: list # 消息内容
    sender: NakuruGuildMember # 发送者信息
    raw_message: Message

    def __str__(self) -> str:
        return str(self.__dict__)

# gocq-频道SDK兼容层（发）
def gocq_compatible_send(gocq_message_chain: list):
    plain_text = ""
    image_path = None # only one img supported
    for i in gocq_message_chain:
        if isinstance(i, Plain):
            plain_text += i.text
        elif isinstance(i, Image) and image_path == None:
            if i.path is not None:
                image_path = i.path
            else:
                image_path = i.file
    return plain_text, image_path

# gocq-频道SDK兼容层（收）
def gocq_compatible_receive(message: Message) -> NakuruGuildMessage:
    ngm = NakuruGuildMessage()
    try:
        ngm.self_id = message.mentions[0].id
        ngm.self_tiny_id = message.mentions[0].id
    except:
        ngm.self_id = 0
        ngm.self_tiny_id = 0

    ngm.sub_type = "normal"
    ngm.message_id = message.id
    ngm.guild_id = int(message.guild_id)
    ngm.channel_id = int(message.channel_id)
    ngm.user_id = int(message.author.id)
    msg = []
    plain_content = message.content.replace("<@!"+str(ngm.self_id)+">", "").strip()
    msg.append(Plain(plain_content))
    if message.attachments:
        for i in message.attachments:
            if i.content_type.startswith("image"):
                url = i.url
                if not url.startswith("http"):
                    url = "https://"+url
                img = Image.fromURL(url)
                msg.append(img)
    ngm.message = msg
    ngm.sender = NakuruGuildMember()
    ngm.sender.tiny_id = int(message.author.id)
    ngm.sender.user_id = int(message.author.id)
    ngm.sender.title = ""
    ngm.sender.nickname = message.author.username
    ngm.sender.role = 0
    ngm.sender.icon_url = message.author.avatar
    ngm.raw_message = message
    return ngm

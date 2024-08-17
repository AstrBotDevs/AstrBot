from aiocqhttp import Event

class MockOneBotMessage():
    def __init__(self):
        # 这些数据不是敏感的
        self.group_event_sample = Event.from_payload({'self_id': 3430871669, 'user_id': 905617992, 'time': 1723882500, 'message_id': -2147480159, 'message_seq': -2147480159, 'real_id': -2147480159, 'message_type': 'group', 'sender': {'user_id': 905617992, 'nickname': 'Soulter', 'card': '', 'role': 'owner'}, 'raw_message': '[CQ:at,qq=3430871669] just reply me `ok`', 'font': 14, 'sub_type': 'normal', 'message': [{'data': {'qq': '3430871669'}, 'type': 'at'}, {'data': {'text': ' just reply me `ok`'}, 'type': 'text'}], 'message_format': 'array', 'post_type': 'message', 'group_id': 849750470})
        self.friend_event_sample = Event.from_payload({'self_id': 3430871669, 'user_id': 905617992, 'time': 1723882599, 'message_id': -2147480157, 'message_seq': -2147480157, 'real_id': -2147480157, 'message_type': 'private', 'sender': {'user_id': 905617992, 'nickname': 'Soulter', 'card': ''}, 'raw_message': 'just reply me `ok`', 'font': 14, 'sub_type': 'friend', 'message': [{'data': {'text': 'just reply me `ok`'}, 'type': 'text'}], 'message_format': 'array', 'post_type': 'message'})

    def create_random_group_message(self):
        return self.group_event_sample
        
    def create_random_direct_message(self):
        return self.friend_event_sample
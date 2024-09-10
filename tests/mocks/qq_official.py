import botpy.message

class MockQQOfficialMessage():
    def __init__(self):
        # 这些数据已经经过去敏处理
        self.group_plain_text_sample = {'author': {'id': '3E47ABD92415AFEF02DAD74FFAB592D1', 'member_openid': '3E47ABD92415AFEF02DAD74FFAB592D1'}, 'content': 'just reply me `ok`', 'group_id': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'group_openid': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'id': 'ROBOT1.0_test', 'timestamp': '2024-07-27T19:58:52+08:00'}
        self.group_plain_image_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'size': 1440173, 'url': 'https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=Cgk5MDU2MTc5OTISFBvbdDR6nYEHsqWEfYauN9wphLxlGK3zVyD_Cii9ibiql8eHA1CAvaMB&rkey=CAESKE4_cASDm1t162vI7q9gitU2u0SUciVRg1fbyn3zYe9f_XHL2vhiB0s&spec=0', 'width': 1186}], 'author': {'id': '3E47ABD92415AFEF02DAD74FFAB592D1', 'member_openid': '3E47ABD92415AFEF02DAD74FFAB592D1'}, 'content': ' ', 'group_id': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'group_openid': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'id': 'ROBOT1.0_test', 'timestamp': '2024-07-27T20:06:32+08:00'}
        self.group_multimedia_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'size': 1440173, 'url': 'https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=Cgk5MDU2MTc5OTISFBvbdDR6nYEHsqWEfYauN9wphLxlGK3zVyD_CiiMytyomceHA1CAvaMB&rkey=CAQSKDOc_jvbthUjVk7zSzPCqflD2XWA0OWzO5qCNsiRFY4RfQMuHYt8KDU&spec=0', 'width': 1186}], 'author': {'id': '3E47ABD92415AFEF02DAD74FFAB592D1', 'member_openid': '3E47ABD92415AFEF02DAD74FFAB592D1'}, 'content': " What's this", 'group_id': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'group_openid': 'BF5D5CA67932FFC4AFD18D4309DB759D', 'id': 'ROBOT1.0_test', 'timestamp': '2024-07-27T20:15:24+08:00'}
        self.group_event_id_sample = "GROUP_AT_MESSAGE_CREATE:ss6hqvpgtqv99eglilbjpsdzvudsjev64th8srgofxqkgxwpynhysl6q6ws849"
        
        self.guild_plain_text_sample = {'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'bot': False, 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '9941389', 'content': '<@!2519660939131724751> just reply me `ok`', 'guild_id': '7969749791337194879', 'id': '08ffca96ebdaa68fcd6e108de3de0438ef0e48a6c793b506', 'member': {'joined_at': '2022-08-13T13:13:56+08:00', 'nick': 'Soulter', 'roles': ['4', '23']}, 'mentions': [{'avatar': 'http://thirdqq.qlogo.cn/g?b=oidb&k=OUbv2LTECcjQt48ibDS4OcA&kti=ZqTjpgAAAAI&s=0&t=1708501824', 'bot': True, 'id': '2519660939131724751', 'username': '浅橙Bot'}], 'seq': 1903, 'seq_in_channel': '1903', 'timestamp': '2024-07-27T20:10:14+08:00'}
        self.guild_plain_image_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'id': '2665728996', 'size': 1440173, 'url': 'gchat.qpic.cn/qmeetpic/75802001660367636/9941389-2665728996-165FCBF8BD6F42496B58A6C66C5D4255/0', 'width': 1186}], 'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'bot': False, 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '9941389', 'content': '<@!2519660939131724751> ', 'guild_id': '7969749791337194879', 'id': 'testid', 'member': {'joined_at': '2022-08-13T13:13:56+08:00', 'nick': 'Soulter', 'roles': ['4', '23']}, 'mentions': [{'avatar': 'http://thirdqq.qlogo.cn/g?b=oidb&k=mZ2Hn0BN5MLlBJTve0WIoA&kti=ZqTjnwAAAAA&s=0&t=1708501824', 'bot': True, 'id': '2519660939131724751', 'username': '浅橙Bot'}], 'seq': 1905, 'seq_in_channel': '1905', 'timestamp': '2024-07-27T20:11:07+08:00'}
        self.guild_multimedia_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'id': '2501183002', 'size': 1440173, 'url': 'gchat.qpic.cn/qmeetpic/75802001660367636/9941389-2501183002-165FCBF8BD6F42496B58A6C66C5D4255/0', 'width': 1186}], 'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'bot': False, 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '9941389', 'content': "<@!2519660939131724751> What's this", 'guild_id': '7969749791337194879', 'id': 'testid', 'member': {'joined_at': '2022-08-13T13:13:56+08:00', 'nick': 'Soulter', 'roles': ['4', '23']}, 'mentions': [{'avatar': 'http://thirdqq.qlogo.cn/g?b=oidb&k=mZ2Hn0BN5MLlBJTve0WIoA&kti=ZqTjnwAAAAA&s=0&t=1708501824', 'bot': True, 'id': '2519660939131724751', 'username': '浅橙Bot'}], 'seq': 1907, 'seq_in_channel': '1907', 'timestamp': '2024-07-27T20:14:26+08:00'}
        self.guild_event_id_sample = "AT_MESSAGE_CREATE:e4c09708-781d-44d0-b8cf-34bf3d4e2e64"
        
        self.direct_plain_text_sample = {'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '33342831678707631', 'content': 'just reply me `ok`', 'direct_message': True, 'guild_id': '3398240095091349322', 'id': '08caaea38bcaabbe942f10afaf8fb08fa49d3b38a5014898c893b506', 'member': {'joined_at': '2023-03-13T19:40:31+08:00'}, 'seq': 165, 'seq_in_channel': '165', 'src_guild_id': '7969749791337194879', 'timestamp': '2024-07-27T20:12:08+08:00'}
        self.direct_plain_image_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'id': '2658044992', 'size': 1440173, 'url': 'gchat.qpic.cn/qmeetpic/92265551678707631/33342831678707631-2658044992-165FCBF8BD6F42496B58A6C66C5D4255/0', 'width': 1186}], 'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '33342831678707631', 'direct_message': True, 'guild_id': '3398240095091349322', 'id': 'testid', 'member': {'joined_at': '2023-03-13T19:40:31+08:00'}, 'seq': 167, 'seq_in_channel': '167', 'src_guild_id': '7969749791337194879', 'timestamp': '2024-07-27T20:12:29+08:00'}
        self.direct_multimedia_sample = {'attachments': [{'content_type': 'image/png', 'filename': '165FCBF8BD6F42496B58A6C66C5D4255.png', 'height': 1034, 'id': '2526212938', 'size': 1440173, 'url': 'gchat.qpic.cn/qmeetpic/92265551678707631/33342831678707631-2526212938-165FCBF8BD6F42496B58A6C66C5D4255/0', 'width': 1186}], 'author': {'avatar': 'https://qqchannel-profile-1251316161.file.myqcloud.com/168087977775f0eae70da8e512?t=1680879777', 'id': '6946931796791550499', 'username': 'Soulter'}, 'channel_id': '33342831678707631', 'content': "What's this", 'direct_message': True, 'guild_id': '3398240095091349322', 'id': 'testid', 'member': {'joined_at': '2023-03-13T19:40:31+08:00'}, 'seq': 168, 'seq_in_channel': '168', 'src_guild_id': '7969749791337194879', 'timestamp': '2024-07-27T20:13:38+08:00'}
        self.direct_event_id_sample = "DIRECT_MESSAGE_CREATE:e4c09708-781d-44d0-b8cf-34bf3d4e2e64"
        
    def create_random_group_message(self):
        mocked = botpy.message.GroupMessage(
            api=None,
            event_id=self.group_event_id_sample,
            data=self.group_plain_text_sample
        )
        return mocked
        
    def create_random_guild_message(self):
        mocked = botpy.message.Message(
            api=None,
            event_id=self.guild_event_id_sample,
            data=self.guild_plain_text_sample
        )
        return mocked
        
    def create_random_direct_message(self):
        mocked = botpy.message.DirectMessage(
            api=None,
            event_id=self.direct_event_id_sample,
            data=self.direct_plain_text_sample
        )
        return mocked
    
    def create_msg(self, text: str):
        sample = self.group_plain_text_sample.copy()
        sample['content'] = text
        mocked = botpy.message.Message(
            api=None,
            event_id=self.group_event_id_sample,
            data=sample
        )
        return mocked
    

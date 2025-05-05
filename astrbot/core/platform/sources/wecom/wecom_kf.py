# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2014-2020 messense

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from wechatpy.client.api.base import BaseWeChatAPI


class WeChatKF(BaseWeChatAPI):
    """
    微信客服接口

    https://work.weixin.qq.com/api/doc/90000/90135/94670
    """

    def sync_msg(self, token, open_kfid, cursor="", limit=1000):
        """
        微信客户发送的消息、接待人员在企业微信回复的消息、发送消息接口发送失败事件（如被用户拒收）
        、客户点击菜单消息的回复消息，可以通过该接口获取具体的消息内容和事件。不支持读取通过发送消息接口发送的消息。
        支持的消息类型：文本、图片、语音、视频、文件、位置、链接、名片、小程序、事件。


        :param token: 回调事件返回的token字段，10分钟内有效；可不填，如果不填接口有严格的频率限制。不多于128字节
        :param open_kfid: 客服帐号ID
        :param cursor: 上一次调用时返回的next_cursor，第一次拉取可以不填。不多于64字节
        :param limit: 期望请求的数据量，默认值和最大值都为1000。
        注意：可能会出现返回条数少于limit的情况，需结合返回的has_more字段判断是否继续请求。
        :return: 接口调用结果
        """
        data = {"token": token, "cursor": cursor, "limit": limit, "open_kfid": open_kfid}
        return self._post("kf/sync_msg", data=data)

    def get_service_state(self, open_kfid, external_userid):
        """
        获取会话状态

        ID	状态	说明
        0	未处理	新会话接入。可选择：1.直接用API自动回复消息。2.放进待接入池等待接待人员接待。3.指定接待人员进行接待
        1	由智能助手接待	可使用API回复消息。可选择转入待接入池或者指定接待人员处理。
        2	待接入池排队中	在待接入池中排队等待接待人员接入。可选择转为指定人员接待
        3	由人工接待	人工接待中。可选择结束会话
        4	已结束	会话已经结束。不允许变更会话状态，等待用户重新发起咨询

        :param open_kfid: 客服帐号ID
        :param external_userid: 微信客户的external_userid
        :return: 接口调用结果
        """
        data = {
            "open_kfid": open_kfid,
            "external_userid": external_userid,
        }
        return self._post("kf/service_state/get", data=data)

    def trans_service_state(self, open_kfid, external_userid, service_state, servicer_userid=""):
        """
        变更会话状态

        :param open_kfid: 客服帐号ID
        :param external_userid: 微信客户的external_userid
        :param service_state: 当前的会话状态，状态定义参考概述中的表格
        :return: 接口调用结果
        """
        data = {
            "open_kfid": open_kfid,
            "external_userid": external_userid,
            "service_state": service_state,
        }
        if servicer_userid:
            data["servicer_userid"] = servicer_userid
        return self._post("kf/service_state/trans", data=data)

    def get_servicer_list(self, open_kfid):
        """
        获取接待人员列表

        :param open_kfid: 客服帐号ID
        :return: 接口调用结果
        """
        data = {
            "open_kfid": open_kfid,
        }
        return self._get("kf/servicer/list", params=data)

    def add_servicer(self, open_kfid, userid_list):
        """
        添加接待人员
        添加指定客服帐号的接待人员。

        :param open_kfid: 客服帐号ID
        :param userid_list: 接待人员userid列表
        :return: 接口调用结果
        """
        if not isinstance(userid_list, list):
            userid_list = [userid_list]

        data = {
            "open_kfid": open_kfid,
            "userid_list": userid_list,
        }
        return self._post("kf/servicer/add", data=data)

    def del_servicer(self, open_kfid, userid_list):
        """
        删除接待人员
        从客服帐号删除接待人员

        :param open_kfid: 客服帐号ID
        :param userid_list: 接待人员userid列表
        :return: 接口调用结果
        """
        if not isinstance(userid_list, list):
            userid_list = [userid_list]

        data = {
            "open_kfid": open_kfid,
            "userid_list": userid_list,
        }
        return self._post("kf/servicer/del", data=data)

    def batchget_customer(self, external_userid_list):
        """
        客户基本信息获取

        :param external_userid_list: external_userid列表
        :return: 接口调用结果
        """
        if not isinstance(external_userid_list, list):
            external_userid_list = [external_userid_list]

        data = {
            "external_userid_list": external_userid_list,
        }
        return self._post("kf/customer/batchget", data=data)

    def get_account_list(self):
        """
        获取客服帐号列表

        :return: 接口调用结果
        """
        return self._get("kf/account/list")

    def add_contact_way(self, open_kfid, scene):
        """
        获取客服帐号链接

        :param open_kfid: 	客服帐号ID
        :param scene: 场景值，字符串类型，由开发者自定义。不多于32字节;字符串取值范围(正则表达式)：[0-9a-zA-Z_-]*
        :return: 接口调用结果
        """
        data = {"open_kfid": open_kfid, "scene": scene}
        return self._post("kf/add_contact_way", data=data)

    def get_upgrade_service_config(self):
        """
        获取配置的专员与客户群

        :return: 接口调用结果
        """
        return self._get("kf/customer/get_upgrade_service_config")

    def upgrade_service(self, open_kfid, external_userid, service_type, member=None, groupchat=None):
        """
        为客户升级为专员或客户群服务

        :param open_kfid: 	客服帐号ID
        :param external_userid: 微信客户的external_userid
        :param service_type: 表示是升级到专员服务还是客户群服务。1:专员服务。2:客户群服务
        :param member: 推荐的服务专员，type等于1时有效
        :param groupchat: 推荐的客户群，type等于2时有效
        :return: 接口调用结果
        """

        data = {
            "open_kfid": open_kfid,
            "external_userid": external_userid,
            "type": service_type,
        }
        if service_type == 1:
            data["member"] = member
        else:
            data["groupchat"] = groupchat
        return self._post("kf/customer/upgrade_service", data=data)

    def cancel_upgrade_service(self, open_kfid, external_userid):
        """
        为客户取消推荐

        :param open_kfid: 	客服帐号ID
        :param external_userid: 微信客户的external_userid
        :return: 接口调用结果
        """

        data = {"open_kfid": open_kfid, "external_userid": external_userid}
        return self._post("kf/customer/cancel_upgrade_service", data=data)

    def send_msg_on_event(self, code, msgtype, msg_content, msgid=None):
        """
        当特定的事件回调消息包含code字段，可以此code为凭证，调用该接口给用户发送相应事件场景下的消息，如客服欢迎语。
        支持发送消息类型：文本、菜单消息。

        :param code: 事件响应消息对应的code。通过事件回调下发，仅可使用一次。
        :param msgtype: 消息类型。对不同的msgtype，有相应的结构描述，详见消息类型
        :param msg_content: 目前支持文本与菜单消息，具体查看文档
        :param msgid: 消息ID。如果请求参数指定了msgid，则原样返回，否则系统自动生成并返回。不多于32字节；
                      字符串取值范围(正则表达式)：[0-9a-zA-Z_-]*
        :return: 接口调用结果
        """

        data = {"code": code, "msgtype": msgtype}
        if msgid:
            data["msgid"] = msgid
        data.update(msg_content)
        return self._post("kf/send_msg_on_event", data=data)

    def get_corp_statistic(self, start_time, end_time, open_kfid=None):
        """
        获取「客户数据统计」企业汇总数据

        :param start_time: 开始时间
        :param end_time: 结束时间
        :param open_kfid: 	客服帐号ID
        :return: 接口调用结果
        """
        data = {"open_kfid": open_kfid, "start_time": start_time, "end_time": end_time}
        return self._post("kf/get_corp_statistic", data=data)

    def get_servicer_statistic(self, start_time, end_time, open_kfid=None, servicer_userid=None):
        """
        获取「客户数据统计」接待人员明细数据

        :param start_time: 开始时间
        :param end_time: 结束时间
        :param open_kfid: 	客服帐号ID
        :param servicer_userid: 接待人员
        :return: 接口调用结果
        """
        data = {
            "open_kfid": open_kfid,
            "servicer_userid": servicer_userid,
            "start_time": start_time,
            "end_time": end_time,
        }
        return self._post("kf/get_servicer_statistic", data=data)

    def account_update(self, open_kfid, name, media_id):
        """
        修改客服账号

        :param open_kfid: 客服帐号ID
        :param name: 客服名称
        :param media_id: 客服头像临时素材

        :return: 接口调用结果
        """
        data = {"open_kfid": open_kfid, "name": name, "media_id": media_id}
        return self._post("kf/account/update", data=data)

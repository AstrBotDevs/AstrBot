import traceback
import json
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.db import BaseDatabase
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class ConversationRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/conversation/list": ("GET", self.list_conversations),
            "/conversation/detail": (
                "POST",
                self.get_conv_detail,
            ),
            "/conversation/update": ("POST", self.upd_conv),
            "/conversation/delete": ("POST", self.del_conv),
            "/conversation/update_history": (
                "POST",
                self.update_history,
            ),
        }
        self.db_helper = db_helper
        self.register_routes()

    async def list_conversations(self):
        """获取对话列表，支持分页、排序和筛选"""
        try:
            # 获取分页参数
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)

            # 获取筛选参数
            platforms = request.args.get("platforms", "")
            message_types = request.args.get("message_types", "")
            search_query = request.args.get("search", "")
            exclude_ids = request.args.get("exclude_ids", "")
            exclude_platforms = request.args.get("exclude_platforms", "")

            # 转换为列表
            platform_list = platforms.split(",") if platforms else []
            message_type_list = message_types.split(",") if message_types else []
            exclude_id_list = exclude_ids.split(",") if exclude_ids else []
            exclude_platform_list = (
                exclude_platforms.split(",") if exclude_platforms else []
            )

            # 限制页面大小，防止请求过大数据
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 20
            if page_size > 100:
                page_size = 100

            # 使用数据库的分页方法获取会话列表和总数，传入筛选条件
            try:
                conversations, total_count = self.db_helper.get_filtered_conversations(
                    page=page,
                    page_size=page_size,
                    platforms=platform_list,
                    message_types=message_type_list,
                    search_query=search_query,
                    exclude_ids=exclude_id_list,
                    exclude_platforms=exclude_platform_list,
                )
            except Exception as e:
                logger.error(f"数据库查询出错: {str(e)}\n{traceback.format_exc()}")
                return Response().error(f"数据库查询出错: {str(e)}").__dict__

            # 计算总页数
            total_pages = (
                (total_count + page_size - 1) // page_size if total_count > 0 else 1
            )

            result = {
                "conversations": conversations,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_count,
                    "total_pages": total_pages,
                },
            }
            return Response().ok(result).__dict__

        except Exception as e:
            error_msg = f"获取对话列表失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"获取对话列表失败: {str(e)}").__dict__

    async def get_conv_detail(self):
        """获取指定对话详情（通过POST请求）"""
        try:
            data = await request.get_json()
            user_id = data.get("user_id")
            cid = data.get("cid")

            if not user_id or not cid:
                return Response().error("缺少必要参数: user_id 和 cid").__dict__

            conversation = self.db_helper.get_conversation_by_user_id(user_id, cid)
            if not conversation:
                return Response().error("对话不存在").__dict__

            return (
                Response()
                .ok(
                    {
                        "user_id": user_id,
                        "cid": cid,
                        "title": conversation.title,
                        "persona_id": conversation.persona_id,
                        "history": conversation.history,
                        "created_at": conversation.created_at,
                        "updated_at": conversation.updated_at,
                    }
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"获取对话详情失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"获取对话详情失败: {str(e)}").__dict__

    async def upd_conv(self):
        """更新对话信息(标题和角色ID)"""
        try:
            data = await request.get_json()
            user_id = data.get("user_id")
            cid = data.get("cid")
            title = data.get("title")
            persona_id = data.get("persona_id", "")

            if not user_id or not cid:
                return Response().error("缺少必要参数: user_id 和 cid").__dict__
            conversation = self.db_helper.get_conversation_by_user_id(user_id, cid)
            if not conversation:
                return Response().error("对话不存在").__dict__
            if title is not None:
                self.db_helper.update_conversation_title(user_id, cid, title)
            if persona_id is not None:
                self.db_helper.update_conversation_persona_id(user_id, cid, persona_id)

            return Response().ok({"message": "对话信息更新成功"}).__dict__

        except Exception as e:
            logger.error(f"更新对话信息失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"更新对话信息失败: {str(e)}").__dict__

    async def del_conv(self):
        """删除对话"""
        try:
            data = await request.get_json()
            user_id = data.get("user_id")
            cid = data.get("cid")

            if not user_id or not cid:
                return Response().error("缺少必要参数: user_id 和 cid").__dict__
            conversation = self.db_helper.get_conversation_by_user_id(user_id, cid)
            if not conversation:
                return Response().error("对话不存在").__dict__
            self.db_helper.delete_conversation(user_id, cid)

            return Response().ok({"message": "对话删除成功"}).__dict__

        except Exception as e:
            logger.error(f"删除对话失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"删除对话失败: {str(e)}").__dict__

    async def update_history(self):
        """更新对话历史内容"""
        try:
            data = await request.get_json()
            user_id = data.get("user_id")
            cid = data.get("cid")
            history = data.get("history")

            if not user_id or not cid:
                return Response().error("缺少必要参数: user_id 和 cid").__dict__

            if history is None:
                return Response().error("缺少必要参数: history").__dict__

            # 历史记录必须是合法的 JSON 字符串
            try:
                if isinstance(history, list):
                    history = json.dumps(history)
                else:
                    # 验证是否为有效的 JSON 字符串
                    json.loads(history)
            except json.JSONDecodeError:
                return (
                    Response().error("history 必须是有效的 JSON 字符串或数组").__dict__
                )

            conversation = self.db_helper.get_conversation_by_user_id(user_id, cid)
            if not conversation:
                return Response().error("对话不存在").__dict__

            self.db_helper.update_conversation(user_id, cid, history)

            return Response().ok({"message": "对话历史更新成功"}).__dict__

        except Exception as e:
            logger.error(f"更新对话历史失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"更新对话历史失败: {str(e)}").__dict__

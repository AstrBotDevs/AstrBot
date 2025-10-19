"""知识库管理 API 路由"""

import os
import traceback
from quart import request
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .route import Route, Response, RouteContext


class KnowledgeBaseRoute(Route):
    """知识库管理路由

    提供知识库、文档、检索、会话配置等 API 接口
    """

    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.kb_manager = None  # 延迟初始化
        self.kb_db = None
        self.session_config_db = None  # 会话配置数据库
        self.retrieval_manager = None

        # 注册路由
        self.routes = {
            # 系统管理
            "/kb/status": ("GET", self.get_kb_status),
            "/kb/initialize": ("POST", self.initialize_kb),
            # 知识库管理
            "/kb/list": ("GET", self.list_kbs),
            "/kb/create": ("POST", self.create_kb),
            "/kb/get": ("GET", self.get_kb),
            "/kb/update": ("POST", self.update_kb),
            "/kb/delete": ("POST", self.delete_kb),
            "/kb/stats": ("GET", self.get_kb_stats),
            # 文档管理
            "/kb/document/list": ("GET", self.list_documents),
            "/kb/document/upload": ("POST", self.upload_document),
            "/kb/document/get": ("GET", self.get_document),
            "/kb/document/delete": ("POST", self.delete_document),
            # 块管理
            "/kb/chunk/list": ("GET", self.list_chunks),
            "/kb/chunk/get": ("GET", self.get_chunk),
            "/kb/chunk/delete": ("POST", self.delete_chunk),
            # 多媒体管理
            "/kb/media/list": ("GET", self.list_media),
            "/kb/media/delete": ("POST", self.delete_media),
            # 检索
            "/kb/retrieve": ("POST", self.retrieve),
            # 会话配置
            "/kb/session/config/get": ("GET", self.get_session_config),
            "/kb/session/config/set": ("POST", self.set_session_config),
            "/kb/session/config/delete": ("POST", self.delete_session_config),
            "/kb/session/config/list": ("GET", self.list_session_configs),
        }
        self.register_routes()

    def _get_kb_manager(self):
        """获取知识库管理器实例"""
        if not self.kb_manager:
            if not hasattr(self.core_lifecycle, "kb_manager"):
                raise ValueError("知识库模块未启用或未初始化")
            # 从 KnowledgeBaseManager (lifecycle 管理器) 获取实际的组件
            kb_lifecycle = self.core_lifecycle.kb_manager
            if not kb_lifecycle.is_initialized:
                raise ValueError("知识库模块未完成初始化")

            self.kb_manager = kb_lifecycle.kb_manager
            self.kb_db = kb_lifecycle.kb_database
            self.retrieval_manager = kb_lifecycle.retrieval_manager
        return self.kb_manager

    # ===== 系统管理 API =====

    async def get_kb_status(self):
        """获取知识库模块状态

        返回知识库模块是否已启用和初始化
        """
        try:
            if not hasattr(self.core_lifecycle, "kb_manager"):
                return (
                    Response()
                    .ok(
                        {
                            "enabled": False,
                            "initialized": False,
                            "message": "知识库模块未启用",
                        }
                    )
                    .__dict__
                )

            kb_lifecycle = self.core_lifecycle.kb_manager
            config = kb_lifecycle.config

            # 检查是否启用
            enabled = config.get("enabled", False)
            if not enabled:
                return (
                    Response()
                    .ok(
                        {
                            "enabled": False,
                            "initialized": False,
                            "message": "知识库功能未在配置中启用",
                        }
                    )
                    .__dict__
                )

            # 检查是否初始化
            initialized = kb_lifecycle.is_initialized
            if not initialized:
                # 检查是否有embedding provider
                has_embedding = (
                    len(kb_lifecycle.provider_manager.embedding_provider_insts) > 0
                )
                if not has_embedding:
                    return (
                        Response()
                        .ok(
                            {
                                "enabled": True,
                                "initialized": False,
                                "message": "未配置 Embedding Provider，请先在提供商管理中添加支持 embedding 的模型",
                            }
                        )
                        .__dict__
                    )
                else:
                    return (
                        Response()
                        .ok(
                            {
                                "enabled": True,
                                "initialized": False,
                                "message": "知识库模块未初始化，请点击初始化按钮",
                            }
                        )
                        .__dict__
                    )

            return (
                Response()
                .ok(
                    {
                        "enabled": True,
                        "initialized": True,
                        "message": "知识库模块运行正常",
                    }
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"获取知识库状态失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库状态失败: {str(e)}").__dict__

    async def initialize_kb(self):
        """初始化或重新初始化知识库模块

        用于在运行时动态初始化知识库模块
        """
        try:
            if not hasattr(self.core_lifecycle, "kb_manager"):
                return Response().error("知识库模块未启用").__dict__

            kb_lifecycle = self.core_lifecycle.kb_manager
            config = kb_lifecycle.config

            # 检查是否启用
            enabled = config.get("enabled", False)
            if not enabled:
                return (
                    Response()
                    .error(
                        "知识库功能未在配置中启用，请在配置文件中设置 knowledge_base.enabled = true"
                    )
                    .__dict__
                )

            # 尝试初始化
            logger.info("收到知识库初始化请求，正在初始化...")
            success = await kb_lifecycle.reinitialize()

            if success:
                # 清除缓存的实例，强制下次重新获取
                self.kb_manager = None
                self.kb_db = None
                self.retrieval_manager = None

                return Response().ok(message="知识库模块初始化成功").__dict__
            else:
                # 检查失败原因
                has_embedding = (
                    len(kb_lifecycle.provider_manager.embedding_provider_insts) > 0
                )
                if not has_embedding:
                    return (
                        Response()
                        .error(
                            "初始化失败：未配置 Embedding Provider，请先在提供商管理中添加支持 embedding 的模型"
                        )
                        .__dict__
                    )
                else:
                    return (
                        Response()
                        .error("知识库模块初始化失败，请查看后端日志获取详细信息")
                        .__dict__
                    )

        except Exception as e:
            logger.error(f"初始化知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"初始化知识库失败: {str(e)}").__dict__

    # ===== 知识库管理 API =====

    async def list_kbs(self):
        """获取知识库列表

        Query 参数:
        - page: 页码 (默认 1)
        - page_size: 每页数量 (默认 20)
        - refresh_stats: 是否刷新统计信息 (默认 false，首次加载时可设为 true)
        """
        try:
            kb_manager = self._get_kb_manager()
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)
            refresh_stats = request.args.get("refresh_stats", "false").lower() == "true"

            # 转换为 offset 和 limit
            offset = (page - 1) * page_size
            limit = page_size

            kbs = await kb_manager.list_kbs(offset=offset, limit=limit)

            # 如果需要刷新统计信息
            if refresh_stats:
                for kb in kbs:
                    try:
                        await kb_manager._update_kb_stats(kb.kb_id)
                    except Exception as e:
                        logger.warning(f"刷新知识库 {kb.kb_id} 统计信息失败: {e}")
                # 刷新后重新查询以获取最新数据
                kbs = await kb_manager.list_kbs(offset=offset, limit=limit)

            # 转换为字典列表
            kb_list = []
            for kb in kbs:
                kb_dict = {
                    "kb_id": kb.kb_id,
                    "kb_name": kb.kb_name,
                    "description": kb.description,
                    "emoji": kb.emoji or "📚",
                    "embedding_provider_id": kb.embedding_provider_id,
                    "rerank_provider_id": kb.rerank_provider_id,
                    "doc_count": kb.doc_count,
                    "chunk_count": kb.chunk_count,
                    # 添加配置参数
                    "chunk_size": kb.chunk_size or 512,
                    "chunk_overlap": kb.chunk_overlap or 50,
                    "top_k_dense": kb.top_k_dense or 50,
                    "top_k_sparse": kb.top_k_sparse or 50,
                    "top_m_final": kb.top_m_final or 5,
                    "enable_rerank": kb.enable_rerank
                    if kb.enable_rerank is not None
                    else True,
                    "created_at": kb.created_at.isoformat(),
                    "updated_at": kb.updated_at.isoformat(),
                }
                kb_list.append(kb_dict)

            return (
                Response()
                .ok({"items": kb_list, "page": page, "page_size": page_size})
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库列表失败: {str(e)}").__dict__

    async def create_kb(self):
        """创建知识库

        Body:
        - kb_name: 知识库名称 (必填)
        - description: 描述 (可选)
        - emoji: 图标 (可选)
        - embedding_provider_id: 嵌入模型提供商ID (可选)
        - rerank_provider_id: 重排序模型提供商ID (可选)
        - chunk_size: 分块大小 (可选, 默认512)
        - chunk_overlap: 块重叠大小 (可选, 默认50)
        - top_k_dense: 密集检索数量 (可选, 默认50)
        - top_k_sparse: 稀疏检索数量 (可选, 默认50)
        - top_m_final: 最终返回数量 (可选, 默认5)
        - enable_rerank: 是否启用Rerank (可选, 默认True)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_name = data.get("kb_name")
            if not kb_name:
                return Response().error("知识库名称不能为空").__dict__

            description = data.get("description")
            emoji = data.get("emoji")

            # 提取 provider ID (前端可能传入完整对象或直接传入ID字符串)
            embedding_provider = data.get("embedding_provider_id")
            if isinstance(embedding_provider, dict):
                embedding_provider_id = embedding_provider.get("id")
            else:
                embedding_provider_id = embedding_provider

            rerank_provider = data.get("rerank_provider_id")
            if isinstance(rerank_provider, dict):
                rerank_provider_id = rerank_provider.get("id")
            else:
                rerank_provider_id = rerank_provider

            chunk_size = data.get("chunk_size")
            chunk_overlap = data.get("chunk_overlap")
            top_k_dense = data.get("top_k_dense")
            top_k_sparse = data.get("top_k_sparse")
            top_m_final = data.get("top_m_final")
            enable_rerank = data.get("enable_rerank")

            kb = await kb_manager.create_kb(
                kb_name=kb_name,
                description=description,
                emoji=emoji,
                embedding_provider_id=embedding_provider_id,
                rerank_provider_id=rerank_provider_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k_dense=top_k_dense,
                top_k_sparse=top_k_sparse,
                top_m_final=top_m_final,
                enable_rerank=enable_rerank,
            )

            kb_dict = {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "description": kb.description,
                "emoji": kb.emoji or "📚",
                "embedding_provider_id": kb.embedding_provider_id,
                "rerank_provider_id": kb.rerank_provider_id,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "chunk_size": kb.chunk_size or 512,
                "chunk_overlap": kb.chunk_overlap or 50,
                "top_k_dense": kb.top_k_dense or 50,
                "top_k_sparse": kb.top_k_sparse or 50,
                "top_m_final": kb.top_m_final or 5,
                "enable_rerank": kb.enable_rerank
                if kb.enable_rerank is not None
                else True,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }

            return Response().ok(kb_dict, "创建知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"创建知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"创建知识库失败: {str(e)}").__dict__

    async def get_kb(self):
        """获取知识库详情

        Query 参数:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb = await kb_manager.get_kb(kb_id)
            if not kb:
                return Response().error("知识库不存在").__dict__

            kb_dict = {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "description": kb.description,
                "emoji": kb.emoji or "📚",
                "embedding_provider_id": kb.embedding_provider_id,
                "rerank_provider_id": kb.rerank_provider_id,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }

            return Response().ok(kb_dict).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库详情失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库详情失败: {str(e)}").__dict__

    async def update_kb(self):
        """更新知识库

        Body:
        - kb_id: 知识库 ID (必填)
        - kb_name: 新的知识库名称 (可选)
        - description: 新的描述 (可选)
        - emoji: 新的图标 (可选)
        - embedding_provider_id: 新的嵌入模型提供商ID (可选)
        - rerank_provider_id: 新的重排序模型提供商ID (可选)
        - chunk_size: 分块大小 (可选)
        - chunk_overlap: 块重叠大小 (可选)
        - top_k_dense: 密集检索数量 (可选)
        - top_k_sparse: 稀疏检索数量 (可选)
        - top_m_final: 最终返回数量 (可选)
        - enable_rerank: 是否启用Rerank (可选)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb_name = data.get("kb_name")
            description = data.get("description")
            emoji = data.get("emoji")

            # 提取 provider ID (前端可能传入完整对象或直接传入ID字符串)
            embedding_provider = data.get("embedding_provider_id")
            if isinstance(embedding_provider, dict):
                embedding_provider_id = embedding_provider.get("id")
            else:
                embedding_provider_id = embedding_provider

            rerank_provider = data.get("rerank_provider_id")
            if isinstance(rerank_provider, dict):
                rerank_provider_id = rerank_provider.get("id")
            else:
                rerank_provider_id = rerank_provider

            chunk_size = data.get("chunk_size")
            chunk_overlap = data.get("chunk_overlap")
            top_k_dense = data.get("top_k_dense")
            top_k_sparse = data.get("top_k_sparse")
            top_m_final = data.get("top_m_final")
            enable_rerank = data.get("enable_rerank")

            # 检查是否至少提供了一个更新字段
            if all(
                v is None
                for v in [
                    kb_name,
                    description,
                    emoji,
                    embedding_provider_id,
                    rerank_provider_id,
                    chunk_size,
                    chunk_overlap,
                    top_k_dense,
                    top_k_sparse,
                    top_m_final,
                    enable_rerank,
                ]
            ):
                return Response().error("至少需要提供一个更新字段").__dict__

            kb = await kb_manager.update_kb(
                kb_id=kb_id,
                kb_name=kb_name,
                description=description,
                emoji=emoji,
                embedding_provider_id=embedding_provider_id,
                rerank_provider_id=rerank_provider_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k_dense=top_k_dense,
                top_k_sparse=top_k_sparse,
                top_m_final=top_m_final,
                enable_rerank=enable_rerank,
            )

            if not kb:
                return Response().error("知识库不存在").__dict__

            kb_dict = {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "description": kb.description,
                "emoji": kb.emoji or "📚",
                "embedding_provider_id": kb.embedding_provider_id,
                "rerank_provider_id": kb.rerank_provider_id,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "chunk_size": kb.chunk_size or 512,
                "chunk_overlap": kb.chunk_overlap or 50,
                "top_k_dense": kb.top_k_dense or 50,
                "top_k_sparse": kb.top_k_sparse or 50,
                "top_m_final": kb.top_m_final or 5,
                "enable_rerank": kb.enable_rerank
                if kb.enable_rerank is not None
                else True,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }

            return Response().ok(kb_dict, "更新知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"更新知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"更新知识库失败: {str(e)}").__dict__

    async def delete_kb(self):
        """删除知识库

        Body:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            success = await kb_manager.delete_kb(kb_id)
            if not success:
                return Response().error("知识库不存在").__dict__

            return Response().ok(message="删除知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除知识库失败: {str(e)}").__dict__

    async def get_kb_stats(self):
        """获取知识库统计信息

        Query 参数:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb = await kb_manager.get_kb(kb_id)
            if not kb:
                return Response().error("知识库不存在").__dict__

            stats = {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }

            return Response().ok(stats).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库统计失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库统计失败: {str(e)}").__dict__

    # ===== 文档管理 API =====

    async def list_documents(self):
        """获取文档列表

        Query 参数:
        - kb_id: 知识库 ID (必填)
        - page: 页码 (默认 1)
        - page_size: 每页数量 (默认 20)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)

            offset = (page - 1) * page_size
            limit = page_size

            # 使用 KBManagerOps 获取文档列表
            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(kb_manager)
            docs = await ops.list_documents(kb_id, offset=offset, limit=limit)

            doc_list = []
            for doc in docs:
                doc_dict = {
                    "doc_id": doc.doc_id,
                    "kb_id": doc.kb_id,
                    "doc_name": doc.doc_name,
                    "file_type": doc.file_type,
                    "file_size": doc.file_size,
                    "chunk_count": doc.chunk_count,
                    "media_count": doc.media_count,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                }
                doc_list.append(doc_dict)

            return (
                Response()
                .ok({"items": doc_list, "page": page, "page_size": page_size})
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取文档列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取文档列表失败: {str(e)}").__dict__

    async def upload_document(self):
        """上传文档

        支持两种方式:
        1. multipart/form-data 文件上传
        2. JSON 格式 base64 编码上传

        Form Data (multipart/form-data):
        - kb_id: 知识库 ID (必填)
        - file: 文件对象 (必填)

        JSON Body (application/json):
        - kb_id: 知识库 ID (必填)
        - file_name: 文件名 (必填)
        - file_content: base64 编码的文件内容 (必填)
        """
        try:
            kb_manager = self._get_kb_manager()

            # 检查 Content-Type
            content_type = request.content_type

            if content_type and "multipart/form-data" in content_type:
                # 方式 1: multipart/form-data
                form_data = await request.form
                files = await request.files

                kb_id = form_data.get("kb_id")
                if not kb_id:
                    return Response().error("缺少参数 kb_id").__dict__

                if "file" not in files:
                    return Response().error("缺少文件").__dict__

                file = files["file"]
                file_name = file.filename

                # 使用 aiofiles 异步读取文件内容
                import uuid
                import aiofiles

                # 保存到临时文件
                temp_file_path = f"data/temp/{uuid.uuid4()}_{file_name}"
                await file.save(temp_file_path)

                try:
                    # 异步读取文件内容
                    async with aiofiles.open(temp_file_path, "rb") as f:
                        file_content = await f.read()
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

            else:
                # 方式 2: JSON base64
                import base64

                data = await request.json

                kb_id = data.get("kb_id")
                file_name = data.get("file_name")
                file_content_b64 = data.get("file_content")

                if not kb_id or not file_name or not file_content_b64:
                    return (
                        Response()
                        .error("缺少参数 kb_id, file_name 或 file_content")
                        .__dict__
                    )

                try:
                    file_content = base64.b64decode(file_content_b64)
                except Exception:
                    return (
                        Response()
                        .error("file_content 必须是有效的 base64 编码")
                        .__dict__
                    )

            # 提取文件类型
            file_type = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

            # 上传文档
            doc = await kb_manager.upload_document(
                kb_id=kb_id,
                file_name=file_name,
                file_content=file_content,
                file_type=file_type,
            )

            doc_dict = {
                "doc_id": doc.doc_id,
                "kb_id": doc.kb_id,
                "doc_name": doc.doc_name,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "chunk_count": doc.chunk_count,
                "media_count": doc.media_count,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }

            return Response().ok(doc_dict, "上传文档成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"上传文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"上传文档失败: {str(e)}").__dict__

    async def get_document(self):
        """获取文档详情

        Query 参数:
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            doc_id = request.args.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(kb_manager)
            doc = await ops.get_document(doc_id)
            if not doc:
                return Response().error("文档不存在").__dict__

            doc_dict = {
                "doc_id": doc.doc_id,
                "kb_id": doc.kb_id,
                "doc_name": doc.doc_name,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "file_path": doc.file_path,
                "chunk_count": doc.chunk_count,
                "media_count": doc.media_count,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }

            return Response().ok(doc_dict).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取文档详情失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取文档详情失败: {str(e)}").__dict__

    async def delete_document(self):
        """删除文档

        Body:
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(kb_manager)
            success = await ops.delete_document(doc_id)
            if not success:
                return Response().error("文档不存在").__dict__

            return Response().ok(message="删除文档成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除文档失败: {str(e)}").__dict__

    # ===== 块管理 API =====

    async def list_chunks(self):
        """获取块列表

        Query 参数:
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            doc_id = request.args.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(kb_manager)
            chunks = await ops.list_chunks(doc_id)

            chunk_list = []
            for chunk in chunks:
                chunk_dict = {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "kb_id": chunk.kb_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "char_count": chunk.char_count,
                    "created_at": chunk.created_at.isoformat(),
                }
                chunk_list.append(chunk_dict)

            return Response().ok({"items": chunk_list}).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取块列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取块列表失败: {str(e)}").__dict__

    async def get_chunk(self):
        """获取块详情

        Query 参数:
        - chunk_id: 块 ID (必填)
        """
        try:
            kb_db = self.kb_db if self.kb_db else self._get_kb_manager() and self.kb_db
            chunk_id = request.args.get("chunk_id")
            if not chunk_id:
                return Response().error("缺少参数 chunk_id").__dict__

            chunk_data = await kb_db.get_chunk_with_metadata(chunk_id)
            if not chunk_data:
                return Response().error("块不存在").__dict__

            chunk = chunk_data["chunk"]
            doc = chunk_data["document"]
            kb = chunk_data["knowledge_base"]

            chunk_dict = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "kb_id": chunk.kb_id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "char_count": chunk.char_count,
                "created_at": chunk.created_at.isoformat(),
                "document": {
                    "doc_name": doc.doc_name,
                    "file_type": doc.file_type,
                },
                "knowledge_base": {
                    "kb_name": kb.kb_name,
                },
            }

            return Response().ok(chunk_dict).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取块详情失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取块详情失败: {str(e)}").__dict__

    async def delete_chunk(self):
        """删除块

        Body:
        - chunk_id: 块 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            chunk_id = data.get("chunk_id")
            if not chunk_id:
                return Response().error("缺少参数 chunk_id").__dict__

            success = await kb_manager.delete_chunk(chunk_id)
            if not success:
                return Response().error("块不存在").__dict__

            return Response().ok(message="删除块成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除块失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除块失败: {str(e)}").__dict__

    # ===== 多媒体管理 API =====

    async def list_media(self):
        """获取多媒体资源列表

        Query 参数:
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            doc_id = request.args.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            media_list = await kb_manager.list_media(doc_id)

            media_result = []
            for media in media_list:
                media_dict = {
                    "media_id": media.media_id,
                    "doc_id": media.doc_id,
                    "kb_id": media.kb_id,
                    "media_type": media.media_type,
                    "file_name": media.file_name,
                    "file_path": media.file_path,
                    "file_size": media.file_size,
                    "mime_type": media.mime_type,
                    "created_at": media.created_at.isoformat(),
                }
                media_result.append(media_dict)

            return Response().ok({"media": media_result}).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取多媒体列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取多媒体列表失败: {str(e)}").__dict__

    async def delete_media(self):
        """删除多媒体资源

        Body:
        - media_id: 多媒体 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            media_id = data.get("media_id")
            if not media_id:
                return Response().error("缺少参数 media_id").__dict__

            success = await kb_manager.delete_media(media_id)
            if not success:
                return Response().error("多媒体资源不存在").__dict__

            return Response().ok(message="删除多媒体资源成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除多媒体资源失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除多媒体资源失败: {str(e)}").__dict__

    # ===== 检索 API =====

    async def retrieve(self):
        """检索知识库

        Body:
        - query: 查询文本 (必填)
        - kb_ids: 知识库 ID 列表 (必填)
        - top_k: 返回结果数量 (可选, 默认 5)
        - enable_rerank: 是否启用Rerank (可选, 默认使用知识库配置)
        """
        try:
            kb_manager = self._get_kb_manager()
            retrieval_manager = (
                self.retrieval_manager
                if self.retrieval_manager
                else self._get_kb_manager() and self.retrieval_manager
            )
            data = await request.json

            query = data.get("query")
            kb_ids = data.get("kb_ids")

            if not query:
                return Response().error("缺少参数 query").__dict__
            if not kb_ids or not isinstance(kb_ids, list):
                return Response().error("缺少参数 kb_ids 或格式错误").__dict__

            top_k = data.get("top_k", 5)
            enable_rerank = data.get("enable_rerank")

            results = await retrieval_manager.retrieve(
                query=query,
                kb_ids=kb_ids,
                top_m_final=top_k,
                enable_rerank=enable_rerank,
            )

            # 获取manager_ops以查询文档和知识库信息
            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(kb_manager)

            result_list = []
            for result in results:
                # 查询文档和知识库名称
                doc = await ops.get_document(result.doc_id)
                kb = await kb_manager.get_kb(result.kb_id)

                result_dict = {
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "kb_id": result.kb_id,
                    "doc_name": doc.doc_name if doc else "未知文档",
                    "kb_name": kb.kb_name if kb else "未知知识库",
                    "chunk_index": result.metadata.get("chunk_index", 0),
                    "content": result.content,
                    "char_count": len(result.content),
                    "score": result.score,
                }
                result_list.append(result_dict)

            return (
                Response()
                .ok({"results": result_list, "total": len(result_list), "query": query})
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"检索失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"检索失败: {str(e)}").__dict__

    # ===== 会话配置 API =====

    async def get_session_config(self):
        """获取会话知识库配置

        Query 参数:
        - session_id: 会话 ID (必填)
        """
        try:
            kb_db = self.kb_db if self.kb_db else self._get_kb_manager() and self.kb_db
            session_id = request.args.get("session_id")
            if not session_id:
                return Response().error("缺少参数 session_id").__dict__

            kb_ids = await kb_db.get_session_kb_ids(session_id)

            return Response().ok({"session_id": session_id, "kb_ids": kb_ids}).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取会话配置失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取会话配置失败: {str(e)}").__dict__

    async def set_session_config(self):
        """设置会话知识库配置

        Body:
        - scope: 配置范围 (session/platform) (必填)
        - scope_id: 范围标识 (会话 ID 或平台 ID) (必填)
        - kb_ids: 知识库 ID 列表 (必填)
        - top_k: 返回结果数量 (可选)
        - enable_rerank: 是否启用Rerank (可选)
        """
        try:
            kb_db = self.kb_db if self.kb_db else self._get_kb_manager() and self.kb_db
            data = await request.json

            scope = data.get("scope")
            scope_id = data.get("scope_id")
            kb_ids = data.get("kb_ids")
            top_k = data.get("top_k")
            enable_rerank = data.get("enable_rerank")

            if not scope or not scope_id:
                return Response().error("缺少参数 scope 或 scope_id").__dict__
            if kb_ids is None or not isinstance(kb_ids, list):
                return Response().error("缺少参数 kb_ids 或格式错误").__dict__

            if scope not in ["session", "platform"]:
                return Response().error("scope 必须是 session 或 platform").__dict__

            await kb_db.set_session_kb_ids(
                scope=scope,
                scope_id=scope_id,
                kb_ids=kb_ids,
                top_k=top_k,
                enable_rerank=enable_rerank,
            )

            return Response().ok(message="设置会话配置成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"设置会话配置失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"设置会话配置失败: {str(e)}").__dict__

    async def delete_session_config(self):
        """删除会话知识库配置

        Body:
        - scope: 配置范围 (session/platform) (必填)
        - scope_id: 范围标识 (会话 ID 或平台 ID) (必填)
        """
        try:
            kb_db = self.kb_db if self.kb_db else self._get_kb_manager() and self.kb_db
            data = await request.json

            scope = data.get("scope")
            scope_id = data.get("scope_id")

            if not scope or not scope_id:
                return Response().error("缺少参数 scope 或 scope_id").__dict__

            success = await kb_db.delete_session_kb_config(
                scope=scope,
                scope_id=scope_id,
            )

            if not success:
                return Response().error("配置不存在").__dict__

            return Response().ok(message="删除会话配置成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除会话配置失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除会话配置失败: {str(e)}").__dict__

    async def list_session_configs(self):
        """获取所有会话配置列表

        Query 参数:
        - page: 页码 (默认 1)
        - page_size: 每页数量 (默认 20)
        """
        try:
            kb_db = self.kb_db if self.kb_db else self._get_kb_manager() and self.kb_db
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)

            offset = (page - 1) * page_size
            limit = page_size

            configs = await kb_db.list_all_session_configs(offset=offset, limit=limit)

            import json

            config_list = []
            for config in configs:
                config_dict = {
                    "config_id": config.config_id,
                    "scope": config.scope,
                    "scope_id": config.scope_id,
                    "kb_ids": json.loads(config.kb_ids),
                    "created_at": config.created_at.isoformat(),
                    "updated_at": config.updated_at.isoformat(),
                }
                config_list.append(config_dict)

            return (
                Response()
                .ok({"items": config_list, "page": page, "page_size": page_size})
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取会话配置列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取会话配置列表失败: {str(e)}").__dict__

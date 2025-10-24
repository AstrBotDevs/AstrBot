"""知识库管理 API 路由"""

import uuid
import aiofiles
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
            # # 块管理
            "/kb/chunk/list": ("GET", self.list_chunks),
            "/kb/chunk/delete": ("POST", self.delete_chunk),
            # # 多媒体管理
            # "/kb/media/list": ("GET", self.list_media),
            # "/kb/media/delete": ("POST", self.delete_media),
            # 检索
            "/kb/retrieve": ("POST", self.retrieve),
        }
        self.register_routes()

    def _get_kb_manager(self):
        return self.core_lifecycle.kb_manager

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

            kbs = await kb_manager.list_kbs()

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
                    "chunk_size": kb.chunk_size or 512,
                    "chunk_overlap": kb.chunk_overlap or 50,
                    "top_k_dense": kb.top_k_dense or 50,
                    "top_k_sparse": kb.top_k_sparse or 50,
                    "top_m_final": kb.top_m_final or 5,
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
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json
            kb_name = data.get("kb_name")
            if not kb_name:
                return Response().error("知识库名称不能为空").__dict__

            description = data.get("description")
            emoji = data.get("emoji")
            embedding_provider_id = data.get("embedding_provider_id")
            rerank_provider_id = data.get("rerank_provider_id")
            chunk_size = data.get("chunk_size")
            chunk_overlap = data.get("chunk_overlap")
            top_k_dense = data.get("top_k_dense")
            top_k_sparse = data.get("top_k_sparse")
            top_m_final = data.get("top_m_final")

            kb_helper = await kb_manager.create_kb(
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
            )
            kb = kb_helper.kb

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

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            kb = kb_helper.kb

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
            embedding_provider_id = data.get("embedding_provider_id")
            rerank_provider_id = data.get("rerank_provider_id")
            chunk_size = data.get("chunk_size")
            chunk_overlap = data.get("chunk_overlap")
            top_k_dense = data.get("top_k_dense")
            top_k_sparse = data.get("top_k_sparse")
            top_m_final = data.get("top_m_final")

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
                ]
            ):
                return Response().error("至少需要提供一个更新字段").__dict__

            kb_helper = await kb_manager.update_kb(
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
            )

            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            kb = kb_helper.kb

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

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            kb = kb_helper.kb

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
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 100, type=int)

            offset = (page - 1) * page_size
            limit = page_size

            doc_list = await kb_helper.list_documents(offset=offset, limit=limit)

            doc_list = [doc.model_dump() for doc in doc_list]

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
            kb_id = None

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

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            # 上传文档
            doc = await kb_helper.upload_document(
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
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_id = request.args.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            doc = await kb_helper.get_document(doc_id)
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
        - kb_id: 知识库 ID (必填)
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            await kb_helper.delete_document(doc_id)
            return Response().ok(message="删除文档成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除文档失败: {str(e)}").__dict__

    async def delete_chunk(self):
        """删除文本块

        Body:
        - kb_id: 知识库 ID (必填)
        - chunk_id: 块 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            chunk_id = data.get("chunk_id")
            if not chunk_id:
                return Response().error("缺少参数 chunk_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            await kb_helper.delete_chunk(chunk_id)
            return Response().ok(message="删除文本块成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除文本块失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除文本块失败: {str(e)}").__dict__

    async def list_chunks(self):
        """获取块列表

        Query 参数:
        - kb_id: 知识库 ID (必填)
        - page: 页码 (默认 1)
        - page_size: 每页数量 (默认 20)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            doc_id = request.args.get("doc_id")
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 100, type=int)
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__
            kb_helper = await kb_manager.get_kb(kb_id)
            offset = (page - 1) * page_size
            limit = page_size
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            chunk_list = await kb_helper.get_chunks_by_doc_id(
                doc_id=doc_id, offset=offset, limit=limit
            )
            return (
                Response()
                .ok(
                    data={
                        "items": chunk_list,
                        "page": page,
                        "page_size": page_size,
                        "total": await kb_helper.get_chunk_count_by_doc_id(doc_id),
                    }
                )
                .__dict__
            )
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取块列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取块列表失败: {str(e)}").__dict__

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
            data = await request.json

            query = data.get("query")
            kb_names = data.get("kb_names")

            if not query:
                return Response().error("缺少参数 query").__dict__
            if not kb_names or not isinstance(kb_names, list):
                return Response().error("缺少参数 kb_names 或格式错误").__dict__

            top_k = data.get("top_k", 5)

            results = await kb_manager.retrieve(
                query=query,
                kb_names=kb_names,
                top_m_final=top_k,
            )
            result_list = []
            if results:
                result_list = results["results"]

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

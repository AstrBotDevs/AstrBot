"""知识库管理 API 路由"""

import uuid
import aiofiles
import os
import traceback
import asyncio
from quart import request
from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from .route import Route, Response, RouteContext
from ..utils import generate_tsne_visualization


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
        self.upload_progress = {}  # 存储上传进度 {task_id: {status, file_index, file_total, stage, current, total}}
        self.upload_tasks = {}  # 存储后台上传任务 {task_id: {"status", "result", "error"}}

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
            "/kb/document/upload/progress": ("GET", self.get_upload_progress),
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

    async def _background_upload_task(
        self,
        task_id: str,
        kb_helper,
        files_to_upload: list,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ):
        """后台上传任务"""
        try:
            # 初始化任务状态
            self.upload_tasks[task_id] = {
                "status": "processing",
                "result": None,
                "error": None,
            }
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": len(files_to_upload),
                "stage": "waiting",
                "current": 0,
                "total": 100,
            }

            uploaded_docs = []
            failed_docs = []

            for file_idx, file_info in enumerate(files_to_upload):
                try:
                    # 更新整体进度
                    self.upload_progress[task_id].update(
                        {
                            "status": "processing",
                            "file_index": file_idx,
                            "file_name": file_info["file_name"],
                            "stage": "parsing",
                            "current": 0,
                            "total": 100,
                        }
                    )

                    # 创建进度回调函数
                    async def progress_callback(stage, current, total):
                        if task_id in self.upload_progress:
                            self.upload_progress[task_id].update(
                                {
                                    "status": "processing",
                                    "file_index": file_idx,
                                    "file_name": file_info["file_name"],
                                    "stage": stage,
                                    "current": current,
                                    "total": total,
                                }
                            )

                    doc = await kb_helper.upload_document(
                        file_name=file_info["file_name"],
                        file_content=file_info["file_content"],
                        file_type=file_info["file_type"],
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        batch_size=batch_size,
                        tasks_limit=tasks_limit,
                        max_retries=max_retries,
                        progress_callback=progress_callback,
                    )

                    uploaded_docs.append(doc.model_dump())
                except Exception as e:
                    logger.error(f"上传文档 {file_info['file_name']} 失败: {e}")
                    failed_docs.append(
                        {"file_name": file_info["file_name"], "error": str(e)}
                    )

            # 更新任务完成状态
            result = {
                "task_id": task_id,
                "uploaded": uploaded_docs,
                "failed": failed_docs,
                "total": len(files_to_upload),
                "success_count": len(uploaded_docs),
                "failed_count": len(failed_docs),
            }

            self.upload_tasks[task_id] = {
                "status": "completed",
                "result": result,
                "error": None,
            }
            self.upload_progress[task_id]["status"] = "completed"

        except Exception as e:
            logger.error(f"后台上传任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self.upload_tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": str(e),
            }
            if task_id in self.upload_progress:
                self.upload_progress[task_id]["status"] = "failed"

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
                kb_list.append(kb.model_dump())

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

            return Response().ok(kb.model_dump(), "创建知识库成功").__dict__

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

            return Response().ok(kb.model_dump()).__dict__

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
            return Response().ok(kb.model_dump(), "更新知识库成功").__dict__

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
        1. multipart/form-data 文件上传（支持多文件，最多10个）
        2. JSON 格式 base64 编码上传（支持多文件，最多10个）

        Form Data (multipart/form-data):
        - kb_id: 知识库 ID (必填)
        - file: 文件对象 (必填，可多个，字段名为 file, file1, file2, ... 或 files[])

        JSON Body (application/json):
        - kb_id: 知识库 ID (必填)
        - files: 文件数组 (必填)
          - file_name: 文件名 (必填)
          - file_content: base64 编码的文件内容 (必填)

        返回:
        - task_id: 任务ID，用于查询上传进度和结果
        """
        try:
            kb_manager = self._get_kb_manager()

            # 检查 Content-Type
            content_type = request.content_type
            kb_id = None
            chunk_size = None
            chunk_overlap = None
            batch_size = 32
            tasks_limit = 3
            max_retries = 3
            files_to_upload = []  # 存储待上传的文件信息列表

            if content_type and "multipart/form-data" not in content_type:
                return (
                    Response().error("Content-Type 须为 multipart/form-data").__dict__
                )
            form_data = await request.form
            files = await request.files

            kb_id = form_data.get("kb_id")
            chunk_size = int(form_data.get("chunk_size", 512))
            chunk_overlap = int(form_data.get("chunk_overlap", 50))
            batch_size = int(form_data.get("batch_size", 32))
            tasks_limit = int(form_data.get("tasks_limit", 3))
            max_retries = int(form_data.get("max_retries", 3))
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            # 收集所有文件
            file_list = []
            # 支持 file, file1, file2, ... 或 files[] 格式
            for key in files.keys():
                if key == "file" or key.startswith("file") or key == "files[]":
                    file_items = files.getlist(key)
                    file_list.extend(file_items)

            if not file_list:
                return Response().error("缺少文件").__dict__

            # 限制文件数量
            if len(file_list) > 10:
                return Response().error("最多只能上传10个文件").__dict__

            # 处理每个文件
            for file in file_list:
                file_name = file.filename

                # 保存到临时文件
                temp_file_path = f"data/temp/{uuid.uuid4()}_{file_name}"
                await file.save(temp_file_path)

                try:
                    # 异步读取文件内容
                    async with aiofiles.open(temp_file_path, "rb") as f:
                        file_content = await f.read()

                    # 提取文件类型
                    file_type = (
                        file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
                    )

                    files_to_upload.append(
                        {
                            "file_name": file_name,
                            "file_content": file_content,
                            "file_type": file_type,
                        }
                    )
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

            # 获取知识库
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self.upload_tasks[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
            }

            # 启动后台任务
            asyncio.create_task(
                self._background_upload_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    files_to_upload=files_to_upload,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                )
            )

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "file_count": len(files_to_upload),
                        "message": "task created, processing in background",
                    }
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"上传文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"上传文档失败: {str(e)}").__dict__

    async def get_upload_progress(self):
        """获取上传进度和结果

        Query 参数:
        - task_id: 任务 ID (必填)

        返回状态:
        - pending: 任务待处理
        - processing: 任务处理中
        - completed: 任务完成
        - failed: 任务失败
        """
        try:
            task_id = request.args.get("task_id")
            if not task_id:
                return Response().error("缺少参数 task_id").__dict__

            # 检查任务是否存在
            if task_id not in self.upload_tasks:
                return Response().error("找不到该任务").__dict__

            task_info = self.upload_tasks[task_id]
            status = task_info["status"]

            # 构建返回数据
            response_data = {
                "task_id": task_id,
                "status": status,
            }

            # 如果任务正在处理，返回进度信息
            if status == "processing" and task_id in self.upload_progress:
                response_data["progress"] = self.upload_progress[task_id]

            # 如果任务完成，返回结果
            if status == "completed":
                response_data["result"] = task_info["result"]
                # 清理已完成的任务
                # del self.upload_tasks[task_id]
                # if task_id in self.upload_progress:
                #     del self.upload_progress[task_id]

            # 如果任务失败，返回错误信息
            if status == "failed":
                response_data["error"] = task_info["error"]

            return Response().ok(response_data).__dict__

        except Exception as e:
            logger.error(f"获取上传进度失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取上传进度失败: {str(e)}").__dict__

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

            return Response().ok(doc.model_dump()).__dict__

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
            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            await kb_helper.delete_chunk(chunk_id, doc_id)
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
        - debug: 是否启用调试模式，返回 t-SNE 可视化图片 (可选, 默认 False)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            query = data.get("query")
            kb_names = data.get("kb_names")
            debug = data.get("debug", False)

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

            response_data = {
                "results": result_list,
                "total": len(result_list),
                "query": query,
            }

            # Debug 模式：生成 t-SNE 可视化
            if debug:
                try:
                    img_base64 = await generate_tsne_visualization(
                        query, kb_names, kb_manager
                    )
                    if img_base64:
                        response_data["visualization"] = img_base64
                except Exception as e:
                    logger.error(f"生成 t-SNE 可视化失败: {e}")
                    logger.error(traceback.format_exc())
                    response_data["visualization_error"] = str(e)

            return Response().ok(response_data).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"检索失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"检索失败: {str(e)}").__dict__

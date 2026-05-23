"""Memory management API routes"""

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from .route import Response, Route, RouteContext


class MemoryRoute(Route):
    """Memory management routes"""

    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ):
        super().__init__(context)
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.memory_manager = core_lifecycle.memory_manager
        self.provider_manager = core_lifecycle.provider_manager
        self.routes = [
            ("/memory/status", ("GET", self.get_status)),
            ("/memory/initialize", ("POST", self.initialize)),
            ("/memory/update_merge_llm", ("POST", self.update_merge_llm)),
        ]
        self.register_routes()

    async def get_status(self):
        """Get memory system status"""
        try:
            is_initialized = self.memory_manager._initialized

            status_data = {
                "initialized": is_initialized,
                "embedding_provider_id": None,
                "merge_llm_provider_id": None,
            }

            if is_initialized:
                # Get embedding provider info
                if self.memory_manager.embedding_provider:
                    status_data["embedding_provider_id"] = (
                        self.memory_manager.embedding_provider.provider_config["id"]
                    )
                # Get merge LLM provider info
                if self.memory_manager.merge_llm_provider:
                    status_data["merge_llm_provider_id"] = (
                        self.memory_manager.merge_llm_provider.provider_config["id"]
                    )

            return jsonify(Response().ok(status_data).__dict__)
        except Exception as e:
            logger.error(f"Failed to get memory status: {e}")
            return jsonify(Response().error(str(e)).__dict__)

    async def initialize(self):
        """Initialize memory system with embedding and merge LLM providers"""
        try:
            data = await request.get_json()
            embedding_provider_id = data.get("embedding_provider_id")
            merge_llm_provider_id = data.get("merge_llm_provider_id")

            if not embedding_provider_id or not merge_llm_provider_id:
                return jsonify(
                    Response()
                    .error(
                        "embedding_provider_id and merge_llm_provider_id are required"
                    )
                    .__dict__,
                )

            # Check if already initialized
            if self.memory_manager._initialized:
                return jsonify(
                    Response()
                    .error(
                        "Memory system already initialized. Embedding provider cannot be changed.",
                    )
                    .__dict__,
                )

            # Get providers
            embedding_provider = await self.provider_manager.get_provider_by_id(
                embedding_provider_id,
            )
            merge_llm_provider = await self.provider_manager.get_provider_by_id(
                merge_llm_provider_id,
            )

            if not embedding_provider:
                return jsonify(
                    Response()
                    .error(f"Embedding provider {embedding_provider_id} not found")
                    .__dict__,
                )

            if not merge_llm_provider:
                return jsonify(
                    Response()
                    .error(f"Merge LLM provider {merge_llm_provider_id} not found")
                    .__dict__,
                )

            # Initialize memory manager
            await self.memory_manager.initialize(
                embedding_provider=embedding_provider,
                merge_llm_provider=merge_llm_provider,
            )

            logger.info(
                f"Memory system initialized with embedding: {embedding_provider_id}, "
                f"merge LLM: {merge_llm_provider_id}",
            )

            return jsonify(
                Response()
                .ok({"message": "Memory system initialized successfully"})
                .__dict__,
            )

        except Exception as e:
            logger.error(f"Failed to initialize memory system: {e}")
            return jsonify(Response().error(str(e)).__dict__)

    async def update_merge_llm(self):
        """Update merge LLM provider (only allowed after initialization)"""
        try:
            data = await request.get_json()
            merge_llm_provider_id = data.get("merge_llm_provider_id")

            if not merge_llm_provider_id:
                return jsonify(
                    Response().error("merge_llm_provider_id is required").__dict__,
                )

            # Check if initialized
            if not self.memory_manager._initialized:
                return jsonify(
                    Response()
                    .error("Memory system not initialized. Please initialize first.")
                    .__dict__,
                )

            # Get new merge LLM provider
            merge_llm_provider = await self.provider_manager.get_provider_by_id(
                merge_llm_provider_id,
            )

            if not merge_llm_provider:
                return jsonify(
                    Response()
                    .error(f"Merge LLM provider {merge_llm_provider_id} not found")
                    .__dict__,
                )

            # Update merge LLM provider
            self.memory_manager.merge_llm_provider = merge_llm_provider

            logger.info(f"Updated merge LLM provider to: {merge_llm_provider_id}")

            return jsonify(
                Response()
                .ok({"message": "Merge LLM provider updated successfully"})
                .__dict__,
            )

        except Exception as e:
            logger.error(f"Failed to update merge LLM provider: {e}")
            return jsonify(Response().error(str(e)).__dict__)

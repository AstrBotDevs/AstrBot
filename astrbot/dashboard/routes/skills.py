from astrbot.core import logger
from astrbot.dashboard.fastapi_compat import request, send_file
from astrbot.dashboard.services.skills_service import (
    SkillArchive,
    SkillsOperationResult,
    SkillsService,
    SkillsServiceError,
)

from .route import Response, Route, RouteContext


class SkillsRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle) -> None:
        super().__init__(context)
        self.routes = {
            "/skills": ("GET", self.get_skills),
            "/skills/upload": ("POST", self.upload_skill),
            "/skills/batch-upload": ("POST", self.batch_upload_skills),
            "/skills/download": ("GET", self.download_skill),
            "/skills/files": ("GET", self.list_skill_files),
            "/skills/file": [
                ("GET", self.get_skill_file),
                ("POST", self.update_skill_file),
            ],
            "/skills/update": ("POST", self.update_skill),
            "/skills/delete": ("POST", self.delete_skill),
            "/skills/neo/candidates": ("GET", self.get_neo_candidates),
            "/skills/neo/releases": ("GET", self.get_neo_releases),
            "/skills/neo/payload": ("GET", self.get_neo_payload),
            "/skills/neo/evaluate": ("POST", self.evaluate_neo_candidate),
            "/skills/neo/promote": ("POST", self.promote_neo_candidate),
            "/skills/neo/rollback": ("POST", self.rollback_neo_release),
            "/skills/neo/sync": ("POST", self.sync_neo_release),
            "/skills/neo/delete-candidate": ("POST", self.delete_neo_candidate),
            "/skills/neo/delete-release": ("POST", self.delete_neo_release),
        }
        self.service = SkillsService(core_lifecycle)
        self.register_routes()

    @staticmethod
    def _ok(data: dict | list | None = None, message: str | None = None) -> dict:
        return Response().ok(data, message).__dict__

    @staticmethod
    def _error(message: str, data: dict | list | None = None) -> dict:
        response = Response().error(message)
        if data is not None:
            response.data = data
        return response.__dict__

    @staticmethod
    def _result(result: SkillsOperationResult) -> dict:
        if result.ok:
            return SkillsRoute._ok(result.data, result.message)
        return SkillsRoute._error(result.message or "", result.data)

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, trace: bool = True):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            if isinstance(result, SkillsOperationResult):
                return self._result(result)
            return self._ok(result)
        except SkillsServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error(str(exc), exc_info=trace)
            return self._error(str(exc))

    async def _run_json(self, operation, *, trace: bool = True):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, trace=trace)

    async def get_skills(self):
        return await self._run(self.service.get_skills)

    async def upload_skill(self):
        async def _operation():
            files = await request.files
            return await self.service.upload_skill(files.get("file"))

        return await self._run(_operation)

    async def batch_upload_skills(self):
        async def _operation():
            files = await request.files
            return await self.service.batch_upload_skills(files.getlist("files"))

        return await self._run(_operation)

    async def download_skill(self):
        try:
            archive = self.service.prepare_skill_archive_from_legacy_query(
                request.args.get("name")
            )
            if not isinstance(archive, SkillArchive):
                raise TypeError("Invalid skill archive result")
            return await send_file(
                str(archive.path),
                as_attachment=True,
                attachment_filename=archive.filename,
                conditional=True,
            )
        except SkillsServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error(str(exc), exc_info=True)
            return self._error(str(exc))

    async def list_skill_files(self):
        return await self._run(
            lambda: self.service.list_skill_files_from_legacy_query(
                name=request.args.get("name"),
                relative_path=request.args.get("path", ""),
            )
        )

    async def get_skill_file(self):
        return await self._run(
            lambda: self.service.get_skill_file_from_legacy_query(
                name=request.args.get("name"),
                relative_path=request.args.get("path", "SKILL.md"),
            )
        )

    async def update_skill_file(self):
        return await self._run_json(self.service.update_skill_file)

    async def update_skill(self):
        return await self._run_json(self.service.update_skill)

    async def delete_skill(self):
        return await self._run_json(self.service.delete_skill)

    async def get_neo_candidates(self):
        return await self._run(
            self.service.get_neo_candidates_from_legacy_query(
                status=request.args.get("status"),
                skill_key=request.args.get("skill_key"),
                limit=request.args.get("limit"),
                offset=request.args.get("offset"),
            )
        )

    async def get_neo_releases(self):
        return await self._run(
            self.service.get_neo_releases_from_legacy_query(
                skill_key=request.args.get("skill_key"),
                stage=request.args.get("stage"),
                active_only=request.args.get("active_only"),
                limit=request.args.get("limit"),
                offset=request.args.get("offset"),
            )
        )

    async def get_neo_payload(self):
        return await self._run(
            self.service.get_neo_payload_from_legacy_query(
                request.args.get("payload_ref")
            )
        )

    async def evaluate_neo_candidate(self):
        return await self._run_json(self.service.evaluate_neo_candidate)

    async def promote_neo_candidate(self):
        return await self._run_json(self.service.promote_neo_candidate)

    async def rollback_neo_release(self):
        return await self._run_json(self.service.rollback_neo_release)

    async def sync_neo_release(self):
        return await self._run_json(self.service.sync_neo_release)

    async def delete_neo_candidate(self):
        return await self._run_json(self.service.delete_neo_candidate)

    async def delete_neo_release(self):
        return await self._run_json(self.service.delete_neo_release)


__all__ = ["SkillsRoute"]

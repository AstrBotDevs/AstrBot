import json
import os
import shutil
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.utils.version_comparator import VersionComparator

from .models import KBDocument, KBMedia, KnowledgeBase

if TYPE_CHECKING:
    from .kb_helper import KBHelper
    from .kb_mgr import KnowledgeBaseManager


KB_PACKAGE_MANIFEST_VERSION = "1.0"
KB_PACKAGE_KIND = "knowledge_base_package"


def _get_major_version(version_str: str) -> str:
    if not version_str:
        return "0.0"

    version = version_str.lower().replace("v", "").split("-")[0].split("+")[0]
    parts = [part for part in version.split(".") if part]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    if len(parts) == 1:
        return f"{parts[0]}.0"
    return "0.0"


def _format_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _read_json_file_from_zip(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(zf.read(name))


def _guess_embedding_model(provider: EmbeddingProvider) -> str:
    return (
        getattr(provider, "model", "")
        or provider.provider_config.get("embedding_model", "")
        or provider.get_model()
    )


def _guess_rerank_model(provider: RerankProvider) -> str:
    return (
        getattr(provider, "model", "")
        or provider.provider_config.get("rerank_model", "")
        or provider.get_model()
    )


@dataclass
class KBPackagePreCheckResult:
    valid: bool = False
    can_import: bool = False
    version_status: str = ""
    package_version: str = ""
    backup_version: str = ""
    current_version: str = VERSION
    exported_at: str = ""
    suggested_kb_name: str = ""
    knowledge_base: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    provider_summary: dict[str, Any] = field(default_factory=dict)
    local_provider_matches: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "can_import": self.can_import,
            "version_status": self.version_status,
            "package_version": self.package_version,
            "backup_version": self.backup_version,
            "current_version": self.current_version,
            "exported_at": self.exported_at,
            "suggested_kb_name": self.suggested_kb_name,
            "knowledge_base": self.knowledge_base,
            "statistics": self.statistics,
            "provider_summary": self.provider_summary,
            "local_provider_matches": self.local_provider_matches,
            "warnings": self.warnings,
            "error": self.error,
        }


class KnowledgeBasePackageExporter:
    def __init__(self, kb_manager: "KnowledgeBaseManager") -> None:
        self.kb_manager = kb_manager

    async def export_kb(
        self,
        kb_id: str,
        output_dir: str,
        progress_callback=None,
    ) -> str:
        kb_helper = await self.kb_manager.get_kb(kb_id)
        if not kb_helper:
            raise ValueError("知识库不存在")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = (
            "".join(
                char if char.isalnum() or char in {"-", "_"} else "_"
                for char in kb_helper.kb.kb_name
            ).strip("_")
            or "knowledge_base"
        )
        zip_path = output_path / f"astrbot_kb_{safe_name}_{timestamp}.zip"

        kb_metadata = await self._collect_kb_metadata(kb_helper)
        manifest = await self._build_manifest(kb_helper, kb_metadata)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if progress_callback:
                await progress_callback("metadata", 0, 100, "正在导出知识库元数据...")

            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            zf.writestr(
                "kb_metadata.json",
                json.dumps(kb_metadata, ensure_ascii=False, indent=2, default=str),
            )

            if progress_callback:
                await progress_callback("runtime", 20, 100, "正在导出运行时数据...")

            await self._write_runtime_file(
                zf, kb_helper.kb_dir / "doc.db", "runtime/doc.db"
            )
            await self._write_runtime_file(
                zf,
                kb_helper.kb_dir / "index.faiss",
                "runtime/index.faiss",
            )
            await self._write_runtime_tree(
                zf,
                kb_helper.kb_dir / "medias",
                "runtime/medias",
            )
            await self._write_runtime_tree(
                zf,
                kb_helper.kb_dir / "files",
                "runtime/files",
            )

            if progress_callback:
                await progress_callback("runtime", 100, 100, "知识库包导出完成")

        return zip_path.as_posix()

    async def _collect_kb_metadata(
        self,
        kb_helper: "KBHelper",
    ) -> dict[str, Any]:
        async with self.kb_manager.kb_db.get_db() as session:
            kb_stmt = select(KnowledgeBase).where(
                KnowledgeBase.kb_id == kb_helper.kb.kb_id
            )
            doc_stmt = select(KBDocument).where(KBDocument.kb_id == kb_helper.kb.kb_id)
            media_stmt = select(KBMedia).where(KBMedia.kb_id == kb_helper.kb.kb_id)

            kb_record = (await session.execute(kb_stmt)).scalar_one()
            documents = list((await session.execute(doc_stmt)).scalars().all())
            medias = list((await session.execute(media_stmt)).scalars().all())

        return {
            "knowledge_base": kb_record.model_dump(mode="python"),
            "documents": [doc.model_dump(mode="python") for doc in documents],
            "media": [media.model_dump(mode="python") for media in medias],
        }

    async def _build_manifest(
        self,
        kb_helper: "KBHelper",
        kb_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        embedding_summary = {}
        rerank_summary = {}

        ep = await kb_helper.get_ep()
        embedding_summary = {
            "provider_id": kb_helper.kb.embedding_provider_id,
            "provider_type": ep.provider_config.get("type", ""),
            "model": _guess_embedding_model(ep),
            "dimensions": ep.get_dim(),
        }

        rp = await kb_helper.get_rp()
        if rp:
            rerank_summary = {
                "provider_id": kb_helper.kb.rerank_provider_id,
                "provider_type": rp.provider_config.get("type", ""),
                "model": _guess_rerank_model(rp),
            }

        kb = kb_metadata["knowledge_base"]
        documents = kb_metadata["documents"]
        media = kb_metadata["media"]

        return {
            "kind": KB_PACKAGE_KIND,
            "version": KB_PACKAGE_MANIFEST_VERSION,
            "astrbot_version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "knowledge_base": {
                "kb_id": kb["kb_id"],
                "kb_name": kb["kb_name"],
                "description": kb.get("description"),
                "emoji": kb.get("emoji"),
                "chunk_size": kb.get("chunk_size"),
                "chunk_overlap": kb.get("chunk_overlap"),
                "top_k_dense": kb.get("top_k_dense"),
                "top_k_sparse": kb.get("top_k_sparse"),
                "top_m_final": kb.get("top_m_final"),
                "created_at": _format_datetime(kb.get("created_at")),
                "updated_at": _format_datetime(kb.get("updated_at")),
            },
            "statistics": {
                "documents": len(documents),
                "chunks": kb.get("chunk_count", 0),
                "media": len(media),
            },
            "providers": {
                "embedding": embedding_summary,
                "rerank": rerank_summary,
            },
        }

    async def _write_runtime_file(
        self,
        zf: zipfile.ZipFile,
        file_path: Path,
        archive_path: str,
    ) -> None:
        if file_path.exists():
            zf.write(file_path, archive_path)

    async def _write_runtime_tree(
        self,
        zf: zipfile.ZipFile,
        source_dir: Path,
        archive_prefix: str,
    ) -> None:
        if not source_dir.exists():
            return

        for root, _, files in os.walk(source_dir):
            root_path = Path(root)
            for file_name in files:
                file_path = root_path / file_name
                rel_path = file_path.relative_to(source_dir).as_posix()
                zf.write(file_path, f"{archive_prefix}/{rel_path}")


class KnowledgeBasePackageImporter:
    def __init__(self, kb_manager: "KnowledgeBaseManager") -> None:
        self.kb_manager = kb_manager

    def pre_check(self, zip_path: str) -> KBPackagePreCheckResult:
        result = KBPackagePreCheckResult()

        if not os.path.exists(zip_path):
            result.error = f"知识库包不存在: {zip_path}"
            return result

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                manifest = _read_json_file_from_zip(zf, "manifest.json")
                self._validate_manifest(manifest)

                result.valid = True
                result.package_version = manifest.get("version", "")
                result.backup_version = manifest.get("astrbot_version", "")
                result.exported_at = manifest.get("exported_at", "")
                result.knowledge_base = manifest.get("knowledge_base", {})
                result.statistics = manifest.get("statistics", {})
                result.provider_summary = manifest.get("providers", {})
                result.suggested_kb_name = self._suggest_kb_name(
                    result.knowledge_base.get("kb_name", "Imported Knowledge Base")
                )

                version_check = self._check_version_compatibility(result.backup_version)
                result.version_status = version_check["status"]
                result.can_import = version_check["can_import"]
                if version_check.get("warning"):
                    result.warnings.append(version_check["warning"])

                result.local_provider_matches = self._collect_local_provider_matches(
                    result.provider_summary
                )

                if not result.local_provider_matches["embedding"][
                    "compatible_provider_ids"
                ]:
                    result.can_import = False
                    result.error = "当前环境中没有可兼容的嵌入模型提供商。"

                return result
        except (KeyError, json.JSONDecodeError) as exc:
            result.error = f"知识库包格式错误: {exc}"
            return result
        except zipfile.BadZipFile:
            result.error = "无效的 ZIP 文件"
            return result
        except Exception as exc:
            result.error = f"预检查知识库包失败: {exc}"
            return result

    async def import_kb(
        self,
        zip_path: str,
        kb_name: str,
        embedding_provider_id: str,
        rerank_provider_id: str | None = None,
        progress_callback=None,
    ) -> KnowledgeBase:
        if not os.path.exists(zip_path):
            raise ValueError(f"知识库包不存在: {zip_path}")

        check_result = self.pre_check(zip_path)
        if not check_result.valid:
            raise ValueError(check_result.error or "知识库包无效")

        if not kb_name.strip():
            raise ValueError("知识库名称不能为空")

        if await self.kb_manager.get_kb_by_name(kb_name):
            raise ValueError(f"知识库名称 '{kb_name}' 已存在")

        embedding_provider = await self.kb_manager.provider_manager.get_provider_by_id(
            embedding_provider_id
        )
        if not embedding_provider or not isinstance(
            embedding_provider, EmbeddingProvider
        ):
            raise ValueError("嵌入模型提供商不存在或类型错误")

        required_dim = check_result.provider_summary.get("embedding", {}).get(
            "dimensions"
        )
        if required_dim is not None and embedding_provider.get_dim() != int(
            required_dim
        ):
            raise ValueError(
                f"嵌入模型向量维度不匹配: 需要 {required_dim}, 当前是 {embedding_provider.get_dim()}"
            )

        if rerank_provider_id:
            rerank_provider = await self.kb_manager.provider_manager.get_provider_by_id(
                rerank_provider_id
            )
            if not rerank_provider or not isinstance(rerank_provider, RerankProvider):
                raise ValueError("重排序模型提供商不存在或类型错误")

        with zipfile.ZipFile(zip_path, "r") as zf:
            metadata = _read_json_file_from_zip(zf, "kb_metadata.json")

            source_kb = metadata["knowledge_base"]
            source_documents = metadata.get("documents", [])
            source_media = metadata.get("media", [])

            if progress_callback:
                await progress_callback("create", 0, 100, "正在创建知识库...")

            kb_helper = await self.kb_manager.create_kb(
                kb_name=kb_name,
                description=source_kb.get("description"),
                emoji=source_kb.get("emoji"),
                embedding_provider_id=embedding_provider_id,
                rerank_provider_id=rerank_provider_id,
                chunk_size=source_kb.get("chunk_size"),
                chunk_overlap=source_kb.get("chunk_overlap"),
                top_k_dense=source_kb.get("top_k_dense"),
                top_k_sparse=source_kb.get("top_k_sparse"),
                top_m_final=source_kb.get("top_m_final"),
            )

            created_kb_id = kb_helper.kb.kb_id
            old_kb_id = source_kb["kb_id"]
            doc_id_map = {doc["doc_id"]: str(uuid.uuid4()) for doc in source_documents}

            try:
                await kb_helper.terminate()

                if progress_callback:
                    await progress_callback("runtime", 20, 100, "正在恢复运行时数据...")

                await self._restore_runtime(
                    zf=zf,
                    kb_helper=kb_helper,
                    old_kb_id=old_kb_id,
                )

                await self._rewrite_doc_store_metadata(
                    kb_helper.kb_dir / "doc.db",
                    old_kb_id=old_kb_id,
                    new_kb_id=created_kb_id,
                    doc_id_map=doc_id_map,
                )

                if progress_callback:
                    await progress_callback(
                        "metadata", 60, 100, "正在导入知识库元数据..."
                    )

                await self._restore_kb_metadata(
                    new_kb=kb_helper.kb,
                    kb_dir=kb_helper.kb_dir,
                    source_documents=source_documents,
                    source_media=source_media,
                    old_kb_id=old_kb_id,
                    doc_id_map=doc_id_map,
                )

                await kb_helper.initialize()
                await self.kb_manager.kb_db.update_kb_stats(
                    kb_id=created_kb_id,
                    vec_db=kb_helper.vec_db,  # type: ignore[arg-type]
                )
                await kb_helper.refresh_kb()

                if progress_callback:
                    await progress_callback("complete", 100, 100, "知识库导入完成")

                return kb_helper.kb
            except Exception:
                logger.error("知识库包导入失败，正在清理已创建的知识库", exc_info=True)
                await self._cleanup_failed_import(created_kb_id)
                raise

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        if manifest.get("kind") != KB_PACKAGE_KIND:
            raise ValueError("不是有效的知识库包")
        if "knowledge_base" not in manifest or "providers" not in manifest:
            raise ValueError("知识库包缺少必要元数据")

    def _check_version_compatibility(self, backup_version: str) -> dict[str, Any]:
        if not backup_version:
            return {"status": "major_diff", "can_import": False}

        backup_major = _get_major_version(backup_version)
        current_major = _get_major_version(VERSION)
        if VersionComparator.compare_version(backup_major, current_major) != 0:
            return {"status": "major_diff", "can_import": False}

        if VersionComparator.compare_version(backup_version, VERSION) != 0:
            return {
                "status": "minor_diff",
                "can_import": True,
                "warning": f"包版本为 {backup_version}，当前版本为 {VERSION}。",
            }

        return {"status": "match", "can_import": True}

    def _suggest_kb_name(self, original_name: str) -> str:
        base_name = f"{original_name} (Imported)"
        candidate = base_name
        suffix = 2

        while True:
            if all(
                kb_helper.kb.kb_name != candidate
                for kb_helper in self.kb_manager.kb_insts.values()
            ):
                break
            candidate = f"{base_name} {suffix}"
            suffix += 1

        return candidate

    def _collect_local_provider_matches(
        self,
        provider_summary: dict[str, Any],
    ) -> dict[str, Any]:
        embedding_required_dim = provider_summary.get("embedding", {}).get("dimensions")
        embedding_source_id = provider_summary.get("embedding", {}).get("provider_id")
        rerank_source_id = provider_summary.get("rerank", {}).get("provider_id")

        embedding_matches: list[str] = []
        rerank_matches: list[str] = []
        embedding_preselected = None
        rerank_preselected = None

        for provider in self.kb_manager.provider_manager.embedding_provider_insts:
            if embedding_required_dim is not None and provider.get_dim() == int(
                embedding_required_dim
            ):
                provider_id = provider.provider_config.get("id", "")
                embedding_matches.append(provider_id)
                if provider_id == embedding_source_id:
                    embedding_preselected = provider_id

        for provider in self.kb_manager.provider_manager.rerank_provider_insts:
            provider_id = provider.provider_config.get("id", "")
            rerank_matches.append(provider_id)
            if provider_id == rerank_source_id:
                rerank_preselected = provider_id

        if embedding_preselected is None and embedding_matches:
            embedding_preselected = embedding_matches[0]
        if rerank_preselected is None and rerank_matches:
            rerank_preselected = rerank_matches[0]

        return {
            "embedding": {
                "required_dimensions": embedding_required_dim,
                "source_provider_id": embedding_source_id,
                "compatible_provider_ids": embedding_matches,
                "preselected_provider_id": embedding_preselected,
            },
            "rerank": {
                "source_provider_id": rerank_source_id,
                "compatible_provider_ids": rerank_matches,
                "preselected_provider_id": rerank_preselected,
            },
        }

    async def _restore_runtime(
        self,
        zf: zipfile.ZipFile,
        kb_helper: "KBHelper",
        old_kb_id: str,
    ) -> None:
        kb_dir = kb_helper.kb_dir
        kb_dir.mkdir(parents=True, exist_ok=True)

        for file_name in ("doc.db", "index.faiss"):
            target_path = kb_dir / file_name
            if target_path.exists():
                target_path.unlink()

        self._copy_zip_member(zf, "runtime/doc.db", kb_dir / "doc.db")
        self._copy_zip_member(
            zf,
            "runtime/index.faiss",
            kb_dir / "index.faiss",
            required=False,
        )
        self._restore_runtime_tree(
            zf,
            prefix="runtime/medias/",
            target_root=kb_dir / "medias",
            old_kb_id=old_kb_id,
            new_kb_id=kb_helper.kb.kb_id,
        )
        self._restore_runtime_tree(
            zf,
            prefix="runtime/files/",
            target_root=kb_dir / "files",
            old_kb_id=old_kb_id,
            new_kb_id=kb_helper.kb.kb_id,
        )

    def _copy_zip_member(
        self,
        zf: zipfile.ZipFile,
        member: str,
        target: Path,
        required: bool = True,
    ) -> None:
        try:
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except KeyError as exc:
            if required:
                raise ValueError(f"知识库包缺少必要文件: {member}") from exc

    def _restore_runtime_tree(
        self,
        zf: zipfile.ZipFile,
        prefix: str,
        target_root: Path,
        old_kb_id: str,
        new_kb_id: str,
    ) -> None:
        for name in zf.namelist():
            if not name.startswith(prefix) or name == prefix:
                continue

            rel_path = PurePosixPath(name[len(prefix) :])
            parts = list(rel_path.parts)
            if (
                len(parts) >= 2
                and parts[0] in {"medias", "files"}
                and parts[1] == old_kb_id
            ):
                parts[1] = new_kb_id
            elif len(parts) >= 1 and parts[0] == old_kb_id:
                parts[0] = new_kb_id

            target_path = target_root / Path(*parts)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

    async def _rewrite_doc_store_metadata(
        self,
        doc_db_path: Path,
        old_kb_id: str,
        new_kb_id: str,
        doc_id_map: dict[str, str],
    ) -> None:
        connection = sqlite3.connect(doc_db_path)
        try:
            rows = connection.execute("SELECT id, metadata FROM documents").fetchall()
            for row_id, metadata_raw in rows:
                metadata = json.loads(metadata_raw or "{}")
                if metadata.get("kb_id") == old_kb_id:
                    metadata["kb_id"] = new_kb_id
                source_doc_id = metadata.get("kb_doc_id")
                if source_doc_id in doc_id_map:
                    metadata["kb_doc_id"] = doc_id_map[source_doc_id]
                connection.execute(
                    "UPDATE documents SET metadata = ? WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False), row_id),
                )
            connection.commit()
        finally:
            connection.close()

    async def _restore_kb_metadata(
        self,
        new_kb: KnowledgeBase,
        kb_dir: Path,
        source_documents: list[dict[str, Any]],
        source_media: list[dict[str, Any]],
        old_kb_id: str,
        doc_id_map: dict[str, str],
    ) -> None:
        new_documents = []
        for doc in source_documents:
            new_doc = KBDocument(
                doc_id=doc_id_map[doc["doc_id"]],
                kb_id=new_kb.kb_id,
                doc_name=doc["doc_name"],
                file_type=doc["file_type"],
                file_size=doc["file_size"],
                file_path=self._rewrite_runtime_path(
                    doc.get("file_path", ""),
                    kb_dir=kb_dir,
                    storage_kind="files",
                    old_kb_id=old_kb_id,
                    new_kb_id=new_kb.kb_id,
                ),
                chunk_count=doc.get("chunk_count", 0),
                media_count=doc.get("media_count", 0),
                created_at=self._parse_datetime(doc.get("created_at")),
                updated_at=self._parse_datetime(doc.get("updated_at")),
            )
            new_documents.append(new_doc)

        new_media = []
        for media in source_media:
            new_item = KBMedia(
                media_id=str(uuid.uuid4()),
                doc_id=doc_id_map[media["doc_id"]],
                kb_id=new_kb.kb_id,
                media_type=media["media_type"],
                file_name=media["file_name"],
                file_path=self._rewrite_runtime_path(
                    media.get("file_path", ""),
                    kb_dir=kb_dir,
                    storage_kind="medias",
                    old_kb_id=old_kb_id,
                    new_kb_id=new_kb.kb_id,
                ),
                file_size=media["file_size"],
                mime_type=media["mime_type"],
                created_at=self._parse_datetime(media.get("created_at")),
            )
            new_media.append(new_item)

        async with self.kb_manager.kb_db.get_db() as session:
            async with session.begin():
                for doc in new_documents:
                    session.add(doc)
                for media in new_media:
                    session.add(media)
                await session.commit()

    def _rewrite_runtime_path(
        self,
        raw_path: str,
        kb_dir: Path,
        storage_kind: str,
        old_kb_id: str,
        new_kb_id: str,
    ) -> str:
        if not raw_path:
            return ""

        normalized = raw_path.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        for index in range(len(parts) - 1):
            if parts[index] == storage_kind and parts[index + 1] == old_kb_id:
                suffix = parts[index + 2 :]
                return (kb_dir / storage_kind / new_kb_id / Path(*suffix)).as_posix()

        return ""

    def _parse_datetime(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        timestamp = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    async def _cleanup_failed_import(self, kb_id: str) -> None:
        kb_helper = await self.kb_manager.get_kb(kb_id)
        if kb_helper:
            await self.kb_manager.delete_kb(kb_id)

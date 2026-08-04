import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from astrbot.core.skills._skill_inventory import (
    _SKILL_NAME_RE,
    _get_archive_names,
    _get_archive_top_dirs,
    _is_ignored_zip_entry,
    _normalize_archive_skill_dir_name,
    _normalize_archive_skill_name,
    _normalize_skill_markdown_path,
    _normalize_skill_name,
    _validate_archive_paths,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


class SkillManagerArchiveMixin:
    skills_root: str

    def is_sandbox_only_skill(self, name: str) -> bool: ...
    def is_plugin_skill(self, name: str) -> bool: ...
    def is_builtin_skill(self, name: str) -> bool: ...
    def set_skill_active(self, name: str, active: bool) -> None: ...
    def _remove_skill_from_sandbox_cache(self, name: str) -> None: ...
    def _load_config(self) -> dict: ...
    def _save_config(self, config: dict) -> None: ...

    def delete_skill(self, name: str) -> None:
        if self.is_sandbox_only_skill(name):
            raise PermissionError(
                "Sandbox preset skill cannot be deleted from local skill management."
            )
        if self.is_plugin_skill(name):
            raise PermissionError(
                "Plugin-provided skill cannot be deleted from local skill management."
            )
        if self.is_builtin_skill(name):
            raise PermissionError(
                "Builtin preset skill cannot be deleted from local skill management."
            )

        skill_dir = Path(self.skills_root) / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        self._remove_skill_from_sandbox_cache(name)

        config = self._load_config()
        if name in config.get("skills", {}):
            config["skills"].pop(name, None)
            self._save_config(config)

    def _validate_skill_archive_conflicts(
        self,
        *,
        file_names: list[str],
        archive_skill_name: str | None,
        overwrite: bool,
    ) -> None:
        if overwrite:
            return

        conflict_dirs = self._get_skill_archive_conflict_dirs(
            file_names=file_names,
            archive_skill_name=archive_skill_name,
        )
        if conflict_dirs:
            raise FileExistsError(
                "One or more skills from the archive already exist and "
                "overwrite=False. No skills were installed. Conflicting "
                f"paths: {', '.join(conflict_dirs)}"
            )

    def _get_skill_archive_conflict_dirs(
        self,
        *,
        file_names: list[str],
        archive_skill_name: str | None,
    ) -> list[str]:
        top_dirs = _get_archive_top_dirs(file_names)
        conflict_dirs: list[str] = []
        for src_dir_name in top_dirs:
            target_name = self._resolve_archive_skill_target_name(
                src_dir_name=src_dir_name,
                top_dir_count=len(top_dirs),
                file_names=file_names,
                archive_skill_name=archive_skill_name,
            )
            if target_name is None:
                continue
            dest_dir = Path(self.skills_root) / target_name
            if dest_dir.exists():
                conflict_dirs.append(str(dest_dir))
        return conflict_dirs

    @staticmethod
    def _resolve_archive_skill_target_name(
        *,
        src_dir_name: str,
        top_dir_count: int,
        file_names: list[str],
        archive_skill_name: str | None,
    ) -> str | None:
        if f"{src_dir_name}/SKILL.md" not in file_names:
            return None
        candidate_name = _normalize_archive_skill_dir_name(src_dir_name)
        if candidate_name is None:
            return None
        if archive_skill_name and top_dir_count == 1:
            return archive_skill_name
        return candidate_name

    def _extract_skill_archive(self, zf: zipfile.ZipFile, tmp_dir: str) -> None:
        for member in zf.infolist():
            member_name = member.filename.replace("\\", "/")
            if not member_name or _is_ignored_zip_entry(member_name):
                continue
            target_path = Path(tmp_dir).joinpath(*PurePosixPath(member_name).parts)
            if member_name.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, target_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)

    def _install_extracted_skill_dir(
        self,
        *,
        src_dir: Path,
        skill_name: str,
        overwrite: bool,
    ) -> str:
        dest_dir = Path(self.skills_root) / skill_name
        if dest_dir.exists():
            if not overwrite:
                raise FileExistsError(f"Skill {skill_name} already exists.")
            shutil.rmtree(dest_dir)

        shutil.move(str(src_dir), str(dest_dir))
        self.set_skill_active(skill_name, True)
        return skill_name

    def _install_root_skill_from_archive(
        self,
        *,
        tmp_dir: str,
        archive_skill_name: str | None,
        zip_stem: str,
        overwrite: bool,
    ) -> str:
        skill_name = _normalize_skill_name(archive_skill_name or zip_stem)
        if not skill_name or not _SKILL_NAME_RE.fullmatch(skill_name):
            raise ValueError("Invalid skill name.")

        src_dir = Path(tmp_dir)
        if _normalize_skill_markdown_path(src_dir) is None:
            raise ValueError("SKILL.md not found in the root of the zip archive.")

        return self._install_extracted_skill_dir(
            src_dir=src_dir,
            skill_name=skill_name,
            overwrite=overwrite,
        )

    def _install_nested_skills_from_archive(
        self,
        *,
        tmp_dir: str,
        file_names: list[str],
        archive_skill_name: str | None,
        overwrite: bool,
    ) -> list[str]:
        installed_skills: list[str] = []
        for archive_root_name, skill_name in self._iter_nested_archive_skill_targets(
            file_names=file_names,
            archive_skill_name=archive_skill_name,
        ):
            src_dir = Path(tmp_dir) / archive_root_name
            if _normalize_skill_markdown_path(src_dir) is None:
                continue

            installed_skills.append(
                self._install_extracted_skill_dir(
                    src_dir=src_dir,
                    skill_name=skill_name,
                    overwrite=overwrite,
                )
            )
        return installed_skills

    def _iter_nested_archive_skill_targets(
        self,
        *,
        file_names: list[str],
        archive_skill_name: str | None,
    ) -> list[tuple[str, str]]:
        top_dirs = _get_archive_top_dirs(file_names)
        targets: list[tuple[str, str]] = []
        for archive_root_name in top_dirs:
            skill_name = self._resolve_nested_archive_skill_name(
                archive_root_name=archive_root_name,
                top_dir_count=len(top_dirs),
                file_names=file_names,
                archive_skill_name=archive_skill_name,
            )
            if skill_name is not None:
                targets.append((archive_root_name, skill_name))
        return targets

    @staticmethod
    def _resolve_nested_archive_skill_name(
        *,
        archive_root_name: str,
        top_dir_count: int,
        file_names: list[str],
        archive_skill_name: str | None,
    ) -> str | None:
        if f"{archive_root_name}/SKILL.md" not in file_names:
            return None
        normalized_name = _normalize_archive_skill_dir_name(archive_root_name)
        if normalized_name is None:
            return None
        if archive_skill_name and top_dir_count == 1:
            return archive_skill_name
        return normalized_name

    def install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ) -> str:
        zip_path_obj = Path(zip_path)
        if not zip_path_obj.exists():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Uploaded file is not a valid zip archive.")

        installed_skills = []

        with zipfile.ZipFile(zip_path) as zf:
            names, file_names, root_mode = _get_archive_names(zf)
            archive_skill_name = _normalize_archive_skill_name(skill_name_hint)
            _validate_archive_paths(names)
            self._validate_skill_archive_conflicts(
                file_names=file_names,
                archive_skill_name=archive_skill_name,
                overwrite=overwrite,
            )

            with tempfile.TemporaryDirectory(dir=get_astrbot_temp_path()) as tmp_dir:
                self._extract_skill_archive(zf, tmp_dir)

                if root_mode:
                    installed_skills.append(
                        self._install_root_skill_from_archive(
                            tmp_dir=tmp_dir,
                            archive_skill_name=archive_skill_name,
                            zip_stem=zip_path_obj.stem,
                            overwrite=overwrite,
                        )
                    )
                else:
                    installed_skills.extend(
                        self._install_nested_skills_from_archive(
                            tmp_dir=tmp_dir,
                            file_names=file_names,
                            archive_skill_name=archive_skill_name,
                            overwrite=overwrite,
                        )
                    )

        if not installed_skills:
            raise ValueError(
                "No valid SKILL.md found in any folder of the zip archive."
            )

        return ", ".join(installed_skills)

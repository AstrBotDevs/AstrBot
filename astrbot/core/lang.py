# lang.py
import threading
from pathlib import Path

from fluent.runtime import FluentLocalization, FluentResourceLoader

from astrbot.core.utils.astrbot_path import get_astrbot_path


class Lang:
    def __init__(
        self,
        locale: str = "zh-cn",
        files: list[str] | None = None,
        namespace_paths: dict[str, str | Path] | None = None,
        namespace_files: dict[str, list[str]] | None = None,
        default_namespace: str = "default",
    ):
        self._lock = threading.RLock()
        self.locale = locale
        self.files = files
        self.default_namespace = default_namespace

        base_dir = self._get_core_locales_dir()
        if namespace_paths is None:
            self.namespace_paths: dict[str, Path] = {self.default_namespace: base_dir}
        else:
            self.namespace_paths = {
                namespace: Path(path) for namespace, path in namespace_paths.items()
            }
            if self.default_namespace not in self.namespace_paths:
                self.namespace_paths[self.default_namespace] = base_dir

        self.namespace_files = namespace_files or {}
        self.available_locales: list[str] = []
        self.available_locales_by_namespace: dict[str, list[str]] = {}
        self._l10n_map: dict[str, FluentLocalization] = {}
        self.load_locale(self.locale, self.files)

    @staticmethod
    def _get_core_locales_dir() -> Path:
        return Path(get_astrbot_path()) / "astrbot" / "i18n" / "locales"

    @staticmethod
    def _validate_namespace(namespace: str) -> None:
        if not namespace:
            raise ValueError("Namespace must not be empty.")
        if "." in namespace:
            raise ValueError("Namespace must not contain '.'.")

    @staticmethod
    def _collect_files(base_dir: Path, files: list[str] | None) -> list[str]:
        if files is not None:
            return files

        files_set = set()
        for locale_dir in (d for d in base_dir.iterdir() if d.is_dir()):
            for ftl_file in locale_dir.glob("*.ftl"):
                files_set.add(ftl_file.name)
        return sorted(files_set)

    @staticmethod
    def _match_locale(available_locales: list[str], locale: str) -> str:
        return next(
            (
                locale_name
                for locale_name in available_locales
                if locale_name.lower() == locale.lower()
            ),
            locale,
        )

    def _build_localization(
        self, base_dir: Path, locale: str, files: list[str] | None
    ) -> tuple[FluentLocalization, list[str]]:
        if not base_dir.exists() or not base_dir.is_dir():
            raise ValueError(f"Locale directory does not exist: {base_dir}")

        available_locales = [d.name for d in base_dir.iterdir() if d.is_dir()]
        if not available_locales:
            raise ValueError(f"No locale directories found under: {base_dir}")

        matched_locale = self._match_locale(available_locales, locale)
        merged_files = self._collect_files(base_dir, files)
        loader = FluentResourceLoader(str(base_dir / "{locale}"))

        locales_preference = [matched_locale]
        if "zh-cn" in available_locales and matched_locale.lower() != "zh-cn":
            locales_preference.append("zh-cn")

        return FluentLocalization(
            locales_preference, merged_files, loader
        ), available_locales

    def _update_available_locales(self) -> None:
        if self.default_namespace in self.available_locales_by_namespace:
            self.available_locales = self.available_locales_by_namespace[
                self.default_namespace
            ]
            return

        all_locales: set[str] = set()
        for locales in self.available_locales_by_namespace.values():
            all_locales.update(locales)
        self.available_locales = sorted(all_locales)

    def _refresh_namespace(self, namespace: str) -> None:
        base_dir = self.namespace_paths[namespace]
        ns_files = self.namespace_files.get(namespace, self.files)
        l10n, available_locales = self._build_localization(
            base_dir, self.locale, ns_files
        )
        self._l10n_map[namespace] = l10n
        self.available_locales_by_namespace[namespace] = available_locales
        self._update_available_locales()

    def load_locale(
        self,
        locale: str = "zh-cn",
        files: list[str] | None = None,
        namespace_paths: dict[str, str | Path] | None = None,
        namespace_files: dict[str, list[str]] | None = None,
    ):
        with self._lock:
            if namespace_paths is not None:
                self.namespace_paths = {
                    namespace: Path(path) for namespace, path in namespace_paths.items()
                }
                if self.default_namespace not in self.namespace_paths:
                    self.namespace_paths[self.default_namespace] = (
                        self._get_core_locales_dir()
                    )
            if namespace_files is not None:
                self.namespace_files = namespace_files

            self.locale = locale
            if files is not None:
                self.files = files

            l10n_map: dict[str, FluentLocalization] = {}
            available_by_namespace: dict[str, list[str]] = {}
            for namespace, base_dir in self.namespace_paths.items():
                ns_files = self.namespace_files.get(namespace, self.files)
                l10n, available_locales = self._build_localization(
                    base_dir, locale, ns_files
                )
                l10n_map[namespace] = l10n
                available_by_namespace[namespace] = available_locales

            self._l10n_map = l10n_map
            self.available_locales_by_namespace = available_by_namespace
            self._update_available_locales()

    def register_namespace(
        self,
        namespace: str,
        path: str | Path,
        files: list[str] | None = None,
        replace: bool = False,
    ) -> None:
        self._validate_namespace(namespace)
        with self._lock:
            if namespace in self.namespace_paths and not replace:
                raise ValueError(
                    f"Namespace '{namespace}' already exists. Set replace=True to overwrite."
                )

            self.namespace_paths[namespace] = Path(path)
            if files is None:
                self.namespace_files.pop(namespace, None)
            else:
                self.namespace_files[namespace] = files
            self._refresh_namespace(namespace)

    def unregister_namespace(self, namespace: str) -> None:
        self._validate_namespace(namespace)
        with self._lock:
            if namespace == self.default_namespace:
                raise ValueError("Default namespace cannot be unregistered.")
            if namespace not in self.namespace_paths:
                raise ValueError(f"Namespace '{namespace}' is not registered.")

            self.namespace_paths.pop(namespace, None)
            self.namespace_files.pop(namespace, None)
            self._l10n_map.pop(namespace, None)
            self.available_locales_by_namespace.pop(namespace, None)
            self._update_available_locales()

    def list_namespaces(self) -> list[str]:
        with self._lock:
            return sorted(self.namespace_paths.keys())

    def get_namespace_meta(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                namespace: {
                    "path": str(path),
                    "files": self.namespace_files.get(namespace),
                    "available_locales": self.available_locales_by_namespace.get(
                        namespace, []
                    ),
                }
                for namespace, path in self.namespace_paths.items()
            }

    def _resolve_key(self, key: str) -> tuple[str, str]:
        if "." not in key:
            return self.default_namespace, key

        namespace, real_key = key.split(".", 1)
        if namespace in self._l10n_map and real_key:
            return namespace, real_key
        return self.default_namespace, key

    def __call__(self, key: str, **kwargs) -> str:
        if not key:
            return ""
        with self._lock:
            namespace, real_key = self._resolve_key(key)
            l10n = (
                self._l10n_map.get(namespace) or self._l10n_map[self.default_namespace]
            )
        return l10n.format_value(real_key, kwargs)


t = Lang(locale="zh-cn")

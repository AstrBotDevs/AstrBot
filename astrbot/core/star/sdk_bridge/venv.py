"""Per-plugin virtual environments for isolated plugins.

Isolated plugins declare third-party dependencies in pyproject.toml
([project.dependencies], preferred) or requirements.txt. The bridge creates
a venv below data/plugin_venvs/{root_dir_name} with --system-site-packages
(plugins keep access to the core environment, mirroring in-process
behavior) and installs the declared dependencies into it. A content hash
marker skips reinstalls until the declaration changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import sysconfig
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_INSTALL_TIMEOUT_SECONDS = 600
_MARKER_NAME = ".astrbot-deps.json"
_GROUP_VENV_ROOT = "groups"

# Serialize venv creation/installation per plugin directory or group id.
_venv_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True, slots=True)
class EnvironmentGroup:
    """Shared Python environment plan for one or more compatible plugins."""

    id: str
    requirements: tuple[str, ...]
    options: tuple[str, ...]
    plugin_roots: tuple[Path, ...]
    python_executable: Path | None = None


def _venv_dir(plugin_root: Path) -> Path:
    return Path(get_astrbot_data_path()) / "plugin_venvs" / plugin_root.name


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def resolve_dependency_source(plugin_root: Path) -> Path | None:
    """Return the dependency declaration file, or None when undeclared.

    pyproject.toml with non-empty [project.dependencies] wins over
    requirements.txt. A pyproject with dynamic dependencies fails loudly.
    """
    pyproject = plugin_root / "pyproject.toml"
    if pyproject.is_file():
        with pyproject.open("rb") as file:
            project = tomllib.load(file).get("project", {})
        if "dependencies" in project.get("dynamic", []):
            raise ValueError(
                f"{pyproject}: dynamic dependencies are not supported; "
                "declare them statically under [project.dependencies]"
            )
        if project.get("dependencies"):
            return pyproject
    requirements = plugin_root / "requirements.txt"
    if requirements.is_file():
        return requirements
    return None


# pip options that take a value; hoisted from requirement lines into the
# installer argv so uv (and the pip fallback) accept pip-style declarations
# like "torch --index-url https://download.pytorch.org/whl/cpu".
_OPTION_FLAGS_WITH_VALUE = {
    "-i",
    "--index-url",
    "--extra-index-url",
    "-f",
    "--find-links",
    "--trusted-host",
}


def _read_requirement_lines(source: Path) -> tuple[list[str], list[str]]:
    """Parse a requirements.txt into (requirement lines, installer options).

    Mirrors pip's tolerance: UTF-8 BOM is dropped, inline comments after
    whitespace are stripped, global option lines and per-requirement index
    options are hoisted into the installer argument list.
    """
    requirements: list[str] = []
    options: list[str] = []
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line = re.sub(r"\s+#.*$", "", raw).strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        if tokens[0] in _OPTION_FLAGS_WITH_VALUE:
            options.extend(tokens)
            continue
        if len(tokens) > 1 and any(
            token in _OPTION_FLAGS_WITH_VALUE for token in tokens[1:]
        ):
            hoisted: list[str] = []
            index = 1
            while index < len(tokens):
                flag = tokens[index]
                if flag in _OPTION_FLAGS_WITH_VALUE and index + 1 < len(tokens):
                    hoisted.extend([flag, tokens[index + 1]])
                    index += 2
                elif any(
                    flag.startswith(f"{known}=") for known in _OPTION_FLAGS_WITH_VALUE
                ):
                    hoisted.append(flag)
                    index += 1
                else:
                    break
            else:
                options.extend(hoisted)
                requirements.append(tokens[0])
                continue
        requirements.append(line)
    return requirements, options


def _effective_requirements(
    source: Path,
    logger: logging.Logger,
) -> tuple[list[str], list[str]]:
    """Read the dependency declaration into requirement specifiers.

    The host package itself (astrbot) is dropped: plugins run against the
    core environment linked into the venv, and a second copy would shadow
    it for no benefit. Local relative paths are absolutized against the
    plugin directory so they can be passed as install arguments.

    Returns:
        A (requirements, installer options) pair; options are pip-style
        index/find-links flags hoisted out of requirements.txt lines.
    """
    options: list[str] = []
    if source.name == "pyproject.toml":
        with source.open("rb") as file:
            requirements = list(tomllib.load(file)["project"]["dependencies"])
    else:
        requirements, options = _read_requirement_lines(source)
    effective: list[str] = []
    for requirement in requirements:
        name = re.split(r"[<>=~!;\[ @]", requirement, maxsplit=1)[0].strip()
        if name.lower() in {"astrbot", "astrbot-core"}:
            logger.info(
                f"Ignoring self-referential dependency {requirement!r} in "
                f"{source.name}: plugins run against the core environment",
            )
            continue
        if name.lower() in sys.stdlib_module_names:
            logger.info(
                f"Ignoring stdlib dependency {requirement!r} in {source.name}",
            )
            continue
        candidate = source.parent / requirement
        if (
            not re.match(r"^[a-zA-Z0-9_.-]+\s*(@|\[|<|>|=|~|!|;|$)", requirement)
            and candidate.exists()
        ):
            requirement = str(candidate)
        effective.append(requirement)
    return effective, options


def _fingerprint(source: Path) -> str:
    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    digest.update(sys.version.encode())
    digest.update(sys.executable.encode())
    return digest.hexdigest()


def _install_env() -> dict[str, str]:
    """Build the scrubbed environment for installer subprocesses."""
    from astrbot_sdk.runtime.env import runner_env

    env = runner_env()
    for key in (
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
    ):
        if key in os.environ:
            env[key] = os.environ[key]
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["UV_NO_PROGRESS"] = "1"
    return env


async def _run(argv: list[str], cwd: Path, logger: logging.Logger) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=_install_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=_INSTALL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"dependency installation timed out: {' '.join(argv)}"
        ) from None
    if process.returncode != 0:
        text = output.decode(errors="replace")[-2000:]
        raise RuntimeError(
            f"dependency installation failed ({process.returncode}): {text}"
        )
    if output:
        for line in output.decode(errors="replace").splitlines():
            logger.debug(f"[venv] {line}")


async def _install(
    requirements: list[str],
    options: list[str],
    cwd: Path,
    venv_python: Path,
    logger: logging.Logger,
) -> None:
    """Install the declared dependencies into the plugin venv."""
    try:
        await _run(
            [
                sys.executable,
                "-m",
                "uv",
                "pip",
                "install",
                "--python",
                str(venv_python),
                *options,
                *requirements,
            ],
            cwd,
            logger,
        )
        return
    except FileNotFoundError:
        pass
    except RuntimeError as exc:
        if "No module named uv" not in str(exc):
            raise
    # Fallback: stdlib venv pip.
    await _run(
        [str(venv_python), "-m", "pip", "install", *options, *requirements],
        cwd,
        logger,
    )


def _link_core_site_packages(venv_dir: Path) -> None:
    """Expose the core environment's site-packages inside the plugin venv.

    --system-site-packages only chains the base interpreter's packages; a
    venv created from another venv does not inherit the parent's. A .pth
    file adds the running environment's site-packages (including editable
    installs like astrbot_sdk) at the end of the plugin venv's sys.path, so
    plugin-installed packages still win on name conflicts.
    """
    core_purelib = sysconfig.get_path("purelib")
    if not core_purelib:
        return
    venv_purelib = Path(
        sysconfig.get_path(
            "purelib",
            scheme="venv",
            vars={"base": str(venv_dir), "platbase": str(venv_dir)},
        ),
    )
    venv_purelib.mkdir(parents=True, exist_ok=True)
    marker = venv_purelib / "00-astrbot-core.pth"
    # .pth lines starting with "import" are executed; addsitedir also
    # processes the .pth files inside (editable installs like astrbot_sdk),
    # which a plain path entry would not.
    line = f"import site; site.addsitedir({core_purelib!r})"
    lines = marker.read_text(encoding="utf-8").splitlines() if marker.is_file() else []
    if line not in lines:
        marker.write_text(
            "\n".join([line, *lines]) + "\n",
            encoding="utf-8",
        )


async def ensure_plugin_venv(
    plugin_root: Path,
    logger: logging.Logger | None = None,
) -> Path | None:
    """Ensure the plugin venv exists with declared dependencies installed.

    Args:
        plugin_root: Plugin directory with pyproject.toml/requirements.txt.
        logger: Logger receiving installer output.

    Returns:
        The venv Python executable, or None when the plugin declares no
        third-party dependencies (the core interpreter is used instead).

    Raises:
        RuntimeError: Venv creation or dependency installation failed.
        ValueError: The dependency declaration is unsupported.
    """
    logger = logger or logging.getLogger("astrbot.plugin_venv")
    source = resolve_dependency_source(plugin_root)
    if source is None:
        return None
    requirements, options = _effective_requirements(source, logger)
    if not requirements:
        return None

    key = str(plugin_root.resolve())
    lock = _venv_locks.setdefault(key, asyncio.Lock())
    async with lock:
        venv_dir = _venv_dir(plugin_root)
        marker = venv_dir / _MARKER_NAME
        fingerprint = _fingerprint(source)
        python = _venv_python(venv_dir)
        if python.is_file() and marker.is_file():
            try:
                recorded: Any = json.loads(marker.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                recorded = None
            if (
                isinstance(recorded, dict)
                and recorded.get("fingerprint") == fingerprint
            ):
                return python

        logger.info(
            f"Creating plugin venv for {plugin_root.name} at {venv_dir}",
        )
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        await _run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
            plugin_root,
            logger,
        )
        _link_core_site_packages(venv_dir)
        try:
            await _install(requirements, options, plugin_root, python, logger)
        except RuntimeError as exc:
            # Best effort: load the plugin against the core environment and
            # retry the install on the next load (no marker is written). A
            # genuinely missing dependency then fails loudly at import time
            # with the plugin's own error instead of a venv failure.
            logger.error(
                f"Dependency installation failed for {plugin_root.name}; "
                f"loading against the core environment: {exc}"
            )
            return python
        marker.write_text(
            json.dumps({"fingerprint": fingerprint, "source": source.name}),
            encoding="utf-8",
        )
        return python


def _parse_req_entries(
    requirements: Sequence[str],
) -> tuple[dict[str, tuple[SpecifierSet, str | None, Version | None]], list[str]]:
    """Parse requirement lines into canonical constraints keyed by package name."""
    parsed: dict[str, tuple[SpecifierSet, str | None, Version | None]] = {}
    unparsed: list[str] = []
    for raw in requirements:
        # Local wheel paths may contain spaces or OS separators; inspect filename.
        stripped = raw.strip()
        if stripped.lower().endswith(".whl") and " @ " not in stripped:
            stem = Path(stripped).name[:-4]
            parts = stem.split("-")
            if len(parts) >= 2:
                pkg = canonicalize_name(parts[0])
                try:
                    ver: Version | None = Version(parts[1])
                except InvalidVersion:
                    ver = None
                url = str(Path(stripped).resolve())
                if pkg in parsed:
                    prev_spec, prev_url, prev_ver = parsed[pkg]
                    if prev_url is not None and prev_url != url:
                        return {}, [f"__conflict__:{pkg}"]
                    parsed[pkg] = (prev_spec, url, ver or prev_ver)
                else:
                    parsed[pkg] = (SpecifierSet(), url, ver)
                continue
            unparsed.append(stripped)
            continue

        try:
            req = Requirement(stripped)
        except InvalidRequirement:
            unparsed.append(stripped)
            continue

        pkg = canonicalize_name(req.name)
        url_val = req.url
        wheel_ver: Version | None = None
        if url_val and url_val.lower().endswith(".whl"):
            parts = Path(url_val).name[:-4].split("-")
            if len(parts) >= 2:
                try:
                    wheel_ver = Version(parts[1])
                except InvalidVersion:
                    wheel_ver = None
        if pkg in parsed:
            prev_spec, prev_url, prev_ver = parsed[pkg]
            if prev_url and url_val and prev_url != url_val:
                return {}, [f"__conflict__:{pkg}"]
            parsed[pkg] = (
                prev_spec & req.specifier,
                url_val or prev_url,
                wheel_ver or prev_ver,
            )
        else:
            parsed[pkg] = (req.specifier, url_val, wheel_ver)
    return parsed, unparsed


def _specifiers_compatible(
    reqs_a: Sequence[str],
    opts_a: Sequence[str],
    reqs_b: Sequence[str],
    opts_b: Sequence[str],
) -> bool:
    """Check whether two normalized requirement sets can share one venv."""
    if tuple(sorted(set(opts_a))) != tuple(sorted(set(opts_b))):
        return False

    parsed_a, unparsed_a = _parse_req_entries(reqs_a)
    parsed_b, unparsed_b = _parse_req_entries(reqs_b)
    if any(u.startswith("__conflict__:") for u in (*unparsed_a, *unparsed_b)):
        return False
    # Unparseable specs (VCS URLs, editable flags) only merge if identical.
    if set(unparsed_a) != set(unparsed_b) and (unparsed_a or unparsed_b):
        return False

    for pkg in set(parsed_a) & set(parsed_b):
        spec_a, url_a, ver_a = parsed_a[pkg]
        spec_b, url_b, ver_b = parsed_b[pkg]
        if url_a and url_b and url_a != url_b:
            return False
        if (url_a or url_b) and (spec_a or spec_b):
            wheel_ver = ver_a or ver_b
            combined_spec = spec_a & spec_b
            if wheel_ver is None or not combined_spec.contains(
                wheel_ver, prereleases=True
            ):
                return False
            continue

        combined = spec_a & spec_b
        exact_pins: set[Version] = set()
        lower: tuple[Version, bool] | None = None
        upper: tuple[Version, bool] | None = None
        for spec in combined:
            if spec.operator in ("==", "===") and not spec.version.endswith(".*"):
                try:
                    pin = Version(spec.version)
                except InvalidVersion:
                    return False
                exact_pins.add(pin)
                lower = (pin, True)
                upper = (pin, True)
            elif spec.operator in (">=", ">", "~="):
                try:
                    ver = Version(spec.version.removesuffix(".*"))
                except InvalidVersion:
                    continue
                inc = spec.operator != ">"
                if lower is None or ver > lower[0] or (ver == lower[0] and not inc):
                    lower = (ver, inc)
            elif spec.operator in ("<=", "<"):
                try:
                    ver = Version(spec.version.removesuffix(".*"))
                except InvalidVersion:
                    continue
                inc = spec.operator == "<="
                if upper is None or ver < upper[0] or (ver == upper[0] and not inc):
                    upper = (ver, inc)

        if len(exact_pins) > 1:
            return False
        if exact_pins:
            pin = next(iter(exact_pins))
            if not combined.contains(pin, prereleases=True):
                return False
        if lower is not None and upper is not None:
            if lower[0] > upper[0]:
                return False
            if lower[0] == upper[0] and not (lower[1] and upper[1]):
                return False
    return True


def _group_fingerprint(requirements: Sequence[str], options: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for item in sorted(set(requirements)):
        digest.update(item.encode("utf-8"))
        digest.update(b"\x00")
    digest.update(b"|")
    for opt in sorted(set(options)):
        digest.update(opt.encode("utf-8"))
        digest.update(b"\x00")
    digest.update(sys.version.encode("utf-8"))
    digest.update(sys.executable.encode("utf-8"))
    return digest.hexdigest()


def plan_environment_groups(
    plugin_roots: Sequence[Path],
    logger: logging.Logger | None = None,
) -> dict[Path, EnvironmentGroup]:
    """Cluster local plugin directories into compatible Python environment groups.

    Plugins with zero effective third-party dependencies share the ``default``
    group using the Core interpreter. Plugins declaring third-party packages
    are greedily merged when their dependency constraints are compatible.

    Args:
        plugin_roots: Local plugin directories to plan.
        logger: Optional logger for normalization diagnostics.

    Returns:
        Mapping from plugin root path to its assigned ``EnvironmentGroup``.
    """
    log = logger or logging.getLogger("astrbot.plugin_venv")
    default_roots: list[Path] = []
    dep_items: list[tuple[Path, tuple[str, ...], tuple[str, ...]]] = []

    for root in sorted(plugin_roots, key=lambda p: p.name):
        source = resolve_dependency_source(root)
        if source is None:
            default_roots.append(root)
            continue
        reqs, opts = _effective_requirements(source, log)
        if not reqs:
            default_roots.append(root)
            continue
        dep_items.append((root, tuple(sorted(set(reqs))), tuple(opts)))

    groups: list[EnvironmentGroup] = []
    if default_roots:
        groups.append(
            EnvironmentGroup(
                id="default",
                requirements=(),
                options=(),
                plugin_roots=tuple(default_roots),
                python_executable=None,
            )
        )

    dep_clusters: list[tuple[list[Path], set[str], list[str]]] = []
    for root, reqs, opts in dep_items:
        placed = False
        for c_roots, c_reqs, c_opts in dep_clusters:
            if _specifiers_compatible(list(c_reqs), c_opts, reqs, opts):
                c_roots.append(root)
                c_reqs.update(reqs)
                if not c_opts and opts:
                    c_opts.extend(opts)
                placed = True
                break
        if not placed:
            dep_clusters.append(([root], set(reqs), list(opts)))

    for c_roots, c_reqs, c_opts in dep_clusters:
        sorted_reqs = tuple(sorted(c_reqs))
        sorted_opts = tuple(c_opts)
        fp = _group_fingerprint(sorted_reqs, sorted_opts)
        groups.append(
            EnvironmentGroup(
                id=f"grp-{fp[:12]}",
                requirements=sorted_reqs,
                options=sorted_opts,
                plugin_roots=tuple(c_roots),
                python_executable=None,
            )
        )

    mapping: dict[Path, EnvironmentGroup] = {}
    for group in groups:
        for root in group.plugin_roots:
            mapping[root] = group
    return mapping


async def ensure_environment_groups(
    plugin_roots: Sequence[Path],
    logger: logging.Logger | None = None,
) -> dict[Path, EnvironmentGroup]:
    """Prepare shared venvs for compatible plugin groups with conflict fallback.

    Args:
        plugin_roots: Candidate local Python plugin directories.
        logger: Optional logger receiving venv setup output.

    Returns:
        Mapping from plugin root path to materialized ``EnvironmentGroup`` with
        resolved ``python_executable`` paths. Plugins whose dependency manifests
        fail validation are omitted so their individual bridge start surfaces
        the plugin-scoped error cleanly.
    """
    log = logger or logging.getLogger("astrbot.plugin_venv")
    valid_roots: list[Path] = []
    for root in plugin_roots:
        try:
            resolve_dependency_source(root)
        except Exception as exc:  # noqa: BLE001 - handled per-plugin on bridge start
            log.debug(
                "Skipping group planning for %s (%s)",
                root.name,
                exc,
            )
            continue
        valid_roots.append(root)

    planned = plan_environment_groups(valid_roots, log)
    unique_groups: dict[str, EnvironmentGroup] = {}
    for group in planned.values():
        unique_groups[group.id] = group

    resolved: dict[Path, EnvironmentGroup] = {}
    data_root = Path(get_astrbot_data_path()) / "plugin_venvs" / _GROUP_VENV_ROOT
    for group in unique_groups.values():
        if group.id == "default":
            for root in group.plugin_roots:
                resolved[root] = group
            continue

        lock = _venv_locks.setdefault(f"group:{group.id}", asyncio.Lock())
        async with lock:
            venv_dir = data_root / group.id
            marker = venv_dir / _MARKER_NAME
            fp = _group_fingerprint(group.requirements, group.options)
            python = _venv_python(venv_dir)
            cached_ok = False
            if python.is_file() and marker.is_file():
                try:
                    recorded = json.loads(marker.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    recorded = None
                if isinstance(recorded, dict) and recorded.get("fingerprint") == fp:
                    cached_ok = True

            if cached_ok:
                mat = EnvironmentGroup(
                    id=group.id,
                    requirements=group.requirements,
                    options=group.options,
                    plugin_roots=group.plugin_roots,
                    python_executable=python,
                )
                for root in group.plugin_roots:
                    resolved[root] = mat
                continue

            log.info(
                f"Creating shared environment group {group.id} for "
                f"{[r.name for r in group.plugin_roots]} at {venv_dir}",
            )
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            await _run(
                [
                    sys.executable,
                    "-m",
                    "venv",
                    "--system-site-packages",
                    str(venv_dir),
                ],
                group.plugin_roots[0],
                log,
            )
            _link_core_site_packages(venv_dir)
            try:
                await _install(
                    list(group.requirements),
                    list(group.options),
                    group.plugin_roots[0],
                    python,
                    log,
                )
            except RuntimeError as exc:
                if len(group.plugin_roots) > 1:
                    log.warning(
                        f"Shared install failed for group {group.id}; splitting "
                        f"plugins into isolated venvs: {exc}",
                    )
                    for root in group.plugin_roots:
                        indiv_py = await ensure_plugin_venv(root, log)
                        resolved[root] = EnvironmentGroup(
                            id=f"solo-{root.name}",
                            requirements=(),
                            options=(),
                            plugin_roots=(root,),
                            python_executable=indiv_py,
                        )
                    continue
                log.error(
                    f"Dependency installation failed for {group.id}; "
                    f"loading against the core environment: {exc}"
                )
                mat = EnvironmentGroup(
                    id=group.id,
                    requirements=group.requirements,
                    options=group.options,
                    plugin_roots=group.plugin_roots,
                    python_executable=python,
                )
                for root in group.plugin_roots:
                    resolved[root] = mat
                continue

            marker.write_text(
                json.dumps(
                    {
                        "fingerprint": fp,
                        "requirements": list(group.requirements),
                    }
                ),
                encoding="utf-8",
            )
            mat = EnvironmentGroup(
                id=group.id,
                requirements=group.requirements,
                options=group.options,
                plugin_roots=group.plugin_roots,
                python_executable=python,
            )
            for root in group.plugin_roots:
                resolved[root] = mat

    return resolved

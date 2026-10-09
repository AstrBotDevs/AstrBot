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
from pathlib import Path
from typing import Any

import tomllib

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

_INSTALL_TIMEOUT_SECONDS = 600
_MARKER_NAME = ".astrbot-deps.json"

# Serialize venv creation/installation per plugin directory.
_venv_locks: dict[str, asyncio.Lock] = {}


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

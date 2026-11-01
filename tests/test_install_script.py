"""Behavioral tests for the Bash installation wizard without network access."""

import hashlib
import io
import os
import select
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

try:
    import pty
except ImportError:
    pty = None

SCRIPT = Path(__file__).resolve().parents[1] / "docs/public/install.sh"
CHINA_INDEX = "https://mirrors.cernet.edu.cn/pypi/web/simple/"
OFFICIAL_INDEX = "https://pypi.org/simple/"
PYTHON_MIRROR = (
    "https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/"
)

FAKE_UV = rb"""#!/bin/bash
if [ "$1" = --version ]; then printf 'uv fixture\n'; exit 0; fi
tool_bin_dir="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"
if [ "$1" = tool ] && [ "$2" = dir ] && [ "$3" = --bin ]; then
  printf '%s\n' "$tool_bin_dir"
  exit 0
fi
if [ "$1" = tool ] && [ "$2" = update-shell ]; then
  touch "$TEST_DIR/uv-update-shell"
  printf '%s\n' "$PATH" > "$TEST_DIR/update-shell-path"
  if [ "${TEST_UPDATE_SHELL_FAIL:-0}" = mixed ]; then
    printf 'error: The executable directory `%s` is not in PATH, but the current shell could not be determined\n' "$tool_bin_dir" >&2
    printf 'error: The executable directory `%s` is not in PATH, but the Bash configuration files are already up-to-date\n' "$tool_bin_dir" >&2
    exit 2
  fi
  if [ "${TEST_UPDATE_SHELL_FAIL:-0}" = 1 ]; then
    printf 'Cannot write shell configuration\n' >&2
    exit 2
  fi
  case ":$PATH:" in
    *":$tool_bin_dir:"*) exit 0 ;;
  esac
  line="$(printf 'export PATH=%q:\"$PATH\"' "$tool_bin_dir")"
  if grep -Fqx "$line" "$HOME/.bashrc"; then
    printf 'error: The executable directory `%s` is not in PATH, but the Bash configuration files are already up-to-date\n' "$tool_bin_dir" >&2
    exit 2
  fi
  printf '%s\n' "$line" >> "$HOME/.bashrc"
  exit 0
fi
printf '%s\n' "$@" > "$TEST_DIR/uv-args"
printf '%s\n' "${UV_PYTHON_INSTALL_MIRROR:-}" >> "$TEST_DIR/python-mirrors"
if [ "${TEST_FAIL_ONCE:-0}" = 1 ] && [ ! -f "$TEST_DIR/failed-once" ]; then
  touch "$TEST_DIR/failed-once"
  exit 1
fi
if [ "${TEST_INSTALL_EXIT:-0}" != 0 ]; then exit "$TEST_INSTALL_EXIT"; fi
mkdir -p "$tool_bin_dir"
printf '#!/bin/bash\nexit 0\n' > "$tool_bin_dir/astrbot"
chmod +x "$tool_bin_dir/astrbot"
"""

# BASH_ENV supplies only fixture commands; uv itself is a real fixture executable.
MOCK_ENV = r"""
command() {
  if [ "$1" = -v ]; then
    case "$2" in
      uv) [ -f "$UV_UNMANAGED_INSTALL/uv" ]; return $? ;;
      curl) if [ "${TEST_WGET:-0}" = 1 ]; then return 1; fi ;;
    esac
  fi
  builtin command "$@"
}
uname() {
  case "$1" in
    -s) printf '%s\n' "${TEST_PLATFORM:-Darwin}" ;;
    -m) printf '%s\n' "${TEST_ARCH:-arm64}" ;;
    *) /usr/bin/uname "$@" ;;
  esac
}
mock_download() {
  local url="$1" out="$2" cookie="$3"
  printf '%s\n' "$url" >> "$TEST_DIR/requests"
  if [ "${TEST_FAIL_ALL:-0}" = 1 ]; then return 22; fi
  if [[ "$url" == https://mirrors.ustc.edu.cn/* ]]; then
    if [ "${TEST_FAIL_PRIMARY:-0}" = 1 ]; then return 22; fi
    if [ "${TEST_COOKIE:-0}" = 1 ] && [[ "$url" == *.tar.gz ]]; then
      if [ "$cookie" != 'addr=192.0.2.1' ]; then
        printf '<script>document.cookie = "addr=192.0.2.1; path=/";</script>' > "$out"
        return
      fi
      printf '%s\n' "$cookie" > "$TEST_DIR/cookie"
    fi
  fi
  case "$url" in
    *.sha256)
      if [ "${TEST_BAD_HASH:-0}" = 1 ] && [[ "$url" == https://mirrors.ustc.edu.cn/* ]]; then
        printf '%064d  fixture.tar.gz\n' 0 > "$out"
      else cp "$TEST_DIR/checksum" "$out"; fi
      ;;
    *.tar.gz) cp "$TEST_DIR/fixture.tar.gz" "$out" ;;
    *) printf 'Unexpected URL %s\n' "$url" >&2; return 1 ;;
  esac
}
curl() {
  local out='' url='' cookie=''
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      -b) cookie="$2"; shift 2 ;;
      --connect-timeout|--max-time) shift 2 ;;
      --) shift; url="$1"; shift ;;
      -*) shift ;;
      *) url="$1"; shift ;;
    esac
  done
  mock_download "$url" "$out" "$cookie"
}
wget() {
  local out='' url='' cookie=''
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -O) out="$2"; shift 2 ;;
      --header=*) cookie="${1#--header=Cookie: }"; shift ;;
      -T|-t) shift 2 ;;
      --) shift; url="$1"; shift ;;
      -*) shift ;;
      *) url="$1"; shift ;;
    esac
  done
  mock_download "$url" "$out" "$cookie"
}
"""


@unittest.skipUnless(pty is not None, "Bash installer tests require a POSIX terminal")
class ShellInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="astrbot-shell-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".bashrc").touch()
        (self.root / "fake-uv").write_bytes(FAKE_UV)
        (self.root / "fake-uv").chmod(0o755)
        (self.root / "env.sh").write_text(MOCK_ENV)
        with tarfile.open(self.root / "fixture.tar.gz", "w:gz") as archive:
            for name in ("uv", "uvx"):
                member = tarfile.TarInfo(f"uv-fixture/{name}")
                member.mode = 0o755
                member.size = len(FAKE_UV)
                archive.addfile(member, io.BytesIO(FAKE_UV))
        checksum = hashlib.sha256(
            (self.root / "fixture.tar.gz").read_bytes()
        ).hexdigest()
        (self.root / "checksum").write_text(f"{checksum}  fixture.tar.gz\n")
        self.env = os.environ.copy()
        for key in (
            "UV_INSTALL_DIR",
            "UV_PYTHON_INSTALL_MIRROR",
            "XDG_BIN_HOME",
            "XDG_DATA_HOME",
        ):
            self.env.pop(key, None)
        self.env.update(
            HOME=str(self.root),
            PATH="/usr/bin:/bin",
            BASH_ENV=str(self.root / "env.sh"),
            TEST_DIR=str(self.root),
            UV_UNMANAGED_INSTALL=str(self.root / "bin"),
            UV_TOOL_BIN_DIR=str(self.root / "bin"),
            NO_COLOR="1",
            TMPDIR=str(self.root),
        )

    def run_installer(self, args, *, existing=True, answers=None, piped=False):
        if existing:
            (self.root / "bin").mkdir(exist_ok=True)
            shutil.copy2(self.root / "fake-uv", self.root / "bin/uv")
        command = ["/bin/bash"] + (["-s", "--"] if piped else [str(SCRIPT)]) + args
        if answers is None:
            result = subprocess.run(
                command,
                input=SCRIPT.read_bytes() if piped else b"",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self.env,
                timeout=15,
                start_new_session=True,
            )
            status, output = result.returncode, result.stdout.decode()
        else:
            # fork() attaches the child to a controlling terminal so /dev/tty
            # still supplies menu input when stdin contains the script itself.
            script_data = SCRIPT.read_bytes() if piped else b""
            if piped:
                read_fd, write_fd = os.pipe()
            pid, terminal = pty.fork()
            if pid == 0:
                if piped:
                    os.close(write_fd)
                    os.dup2(read_fd, 0)
                    os.close(read_fd)
                os.execve(command[0], command, self.env)
            if piped:
                os.close(read_fd)
                os.set_blocking(write_fd, False)
            output_bytes = bytearray()
            pending = answers.encode()
            deadline = time.monotonic() + 15
            try:
                while time.monotonic() < deadline:
                    readable, writable, _ = select.select(
                        [terminal], [write_fd] if script_data else [], [], 0.1
                    )
                    if writable:
                        written = os.write(write_fd, script_data)
                        script_data = script_data[written:]
                        if not script_data:
                            os.close(write_fd)
                    if readable:
                        try:
                            chunk = os.read(terminal, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        output_bytes.extend(chunk)
                        if pending and b"1-3 [1]:" in output_bytes:
                            os.write(terminal, pending)
                            pending = b""
                else:
                    os.kill(pid, 9)
                    self.fail("Interactive installer timed out")
            finally:
                os.close(terminal)
                if script_data:
                    os.close(write_fd)
                _, wait_status = os.waitpid(pid, 0)
            status = os.WEXITSTATUS(wait_status)
            output = output_bytes.decode().replace("\r\n", "\n")
        self.assertEqual(list(self.root.glob("astrbot-install.*")), [])
        return status, output

    def assert_install(self, index, mirrors):
        self.assertEqual(
            (self.root / "uv-args").read_text().splitlines(),
            [
                "tool",
                "install",
                "--python",
                "3.12",
                "astrbot",
                "--default-index",
                index,
            ],
        )
        self.assertEqual(
            (self.root / "python-mirrors").read_text().splitlines(), mirrors
        )

    def test_defaults_ignore_system_locale(self):
        self.env["LANG"] = "zh_CN.UTF-8"
        status, output = self.run_installer(["--non-interactive"])
        self.assertEqual(status, 0, output)
        self.assert_install(OFFICIAL_INDEX, [""])
        self.assertTrue((self.root / "uv-update-shell").exists())
        self.assertIn("  [INFO]    Download source: Official sources", output)
        self.assertIn(
            "\n  Reload the environment for your shell:\n"
            "    Bash: source ~/.bashrc\n"
            "    Zsh: source ~/.zshrc\n"
            "    Fish: source ~/.config/fish/config.fish\n"
            "    PowerShell: . $PROFILE\n\n"
            "  Then run these commands manually:\n"
            "    astrbot init\n"
            "    astrbot run\n",
            output,
        )

    def test_fresh_install_commands_available_after_bash_reload(self):
        status, output = self.run_installer(["--non-interactive"], existing=False)
        self.assertEqual(status, 0, output)
        shell_env = self.env.copy()
        shell_env.pop("BASH_ENV")
        result = subprocess.run(
            [
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-c",
                'source "$HOME/.bashrc"; command -v uv; command -v astrbot',
            ],
            env=shell_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [str(self.root / "bin/uv"), str(self.root / "bin/astrbot")],
        )

    def test_recovered_uv_updates_shell_with_original_path(self):
        # Spaces in the install directory must survive executable lookup.
        install_dir = self.root / "custom bin"
        install_dir.mkdir()
        shutil.copy2(self.root / "fake-uv", install_dir / "uv")
        self.env["UV_UNMANAGED_INSTALL"] = str(install_dir)
        self.env["PATH"] += ":/custom/bin"
        for tool_bin, entries in ((install_dir, 1), (self.root / "tool bin", 2)):
            with self.subTest(tool_bin=tool_bin):
                (self.root / ".bashrc").write_text("")
                self.env["UV_TOOL_BIN_DIR"] = str(tool_bin)
                for _ in range(2):
                    status, output = self.run_installer(
                        ["--non-interactive"], existing=False
                    )
                    self.assertEqual(status, 0, output)
                    self.assertNotIn("[WARN]", output)
                    self.assertNotIn("tool update-shell", output)
                    self.assertEqual(
                        (self.root / "update-shell-path").read_text().strip(),
                        self.env["PATH"],
                    )
                self.assertEqual(
                    len((self.root / ".bashrc").read_text().splitlines()), entries
                )
        self.assertFalse((self.root / "requests").exists())

    def test_existing_path_does_not_modify_shell_configuration(self):
        self.env["PATH"] = f"{self.root / 'bin'}:{self.env['PATH']}"
        status, output = self.run_installer(["--non-interactive"])
        self.assertEqual(status, 0, output)
        self.assertEqual((self.root / ".bashrc").read_text(), "")

    def test_shell_update_failure_shows_diagnostic_and_retry_command(self):
        for failure, diagnostic in (
            ("1", "Cannot write shell configuration"),
            ("mixed", "current shell could not be determined"),
        ):
            with self.subTest(failure=failure):
                self.env["TEST_UPDATE_SHELL_FAIL"] = failure
                status, output = self.run_installer(["--non-interactive"])
                self.assertEqual(status, 0, output)
                self.assertIn("AstrBot has been installed", output)
                self.assertIn(diagnostic, output)
                self.assertIn("[WARN]", output)
                self.assertIn(f"{self.root / 'bin/uv'} tool update-shell", output)

    def test_exported_uv_function_reaches_shell_setup(self):
        with (self.root / "env.sh").open("a") as fixture:
            fixture.write(
                '\ncommand() { builtin command "$@"; }\n'
                'uv() { "$TEST_DIR/fake-uv" "$@"; }\n'
            )
        (self.root / "bin").mkdir()
        for fail_update in ("0", "1"):
            with self.subTest(fail_update=fail_update):
                self.env["TEST_UPDATE_SHELL_FAIL"] = fail_update
                status, output = self.run_installer(
                    ["--non-interactive"], existing=False
                )
                self.assertEqual(status, 0, output)
                self.assertTrue((self.root / "uv-update-shell").exists())
                self.assertIn("Bash: source ~/.bashrc", output)
                if fail_update == "1":
                    self.assertIn("Cannot write shell configuration", output)
                    self.assertIn(" uv tool update-shell", output)
                else:
                    self.assertTrue((self.root / ".bashrc").read_text())

    def test_retry_from_relative_path_works_in_another_directory(self):
        with (self.root / "env.sh").open("a") as fixture:
            fixture.write('\ncd "$TEST_DIR"\n')
        self.env.update(UV_UNMANAGED_INSTALL="bin", TEST_UPDATE_SHELL_FAIL="1")
        status, output = self.run_installer(["--non-interactive"])
        self.assertEqual(status, 0, output)
        retry = next(
            line.strip()
            for line in output.splitlines()
            if line.endswith(" tool update-shell")
        )
        self.assertIn(f"{self.root / 'bin/uv'} tool update-shell", retry)
        retry_env = self.env.copy()
        retry_env.pop("BASH_ENV")
        retry_env.pop("TEST_UPDATE_SHELL_FAIL")
        retry_env.pop("UV_TOOL_BIN_DIR")
        result = subprocess.run(
            ["/bin/bash", "-c", retry],
            cwd="/",
            env=retry_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".bashrc").read_text())

    def test_separate_uv_and_tool_directories_survive_shell_reload(self):
        uv_bin = self.root / "uv bin"
        tool_bin = self.root / "tool bin"
        self.env["UV_UNMANAGED_INSTALL"] = str(uv_bin)
        self.env["UV_TOOL_BIN_DIR"] = str(tool_bin)
        for fail_update in ("0", "1", "mixed"):
            with self.subTest(fail_update=fail_update):
                (self.root / ".bashrc").write_text("")
                self.env["TEST_UPDATE_SHELL_FAIL"] = fail_update
                status, output = self.run_installer(
                    ["--non-interactive"], existing=False
                )
                self.assertEqual(status, 0, output)
                shell_env = self.env.copy()
                shell_env.pop("BASH_ENV")
                shell_env.pop("TEST_UPDATE_SHELL_FAIL")
                shell_env.pop("UV_TOOL_BIN_DIR")
                if fail_update != "0":
                    retries = [
                        line.strip()
                        for line in output.splitlines()
                        if line.endswith(" tool update-shell")
                    ]
                    self.assertTrue(retries, output)
                    for retry in retries:
                        result = subprocess.run(
                            ["/bin/bash", "-c", retry],
                            cwd="/",
                            env=shell_env,
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run(
                    [
                        "/bin/bash",
                        "--noprofile",
                        "--norc",
                        "-c",
                        'source "$HOME/.bashrc"; command -v uv; command -v astrbot',
                    ],
                    env=shell_env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.splitlines(),
                    [str(uv_bin / "uv"), str(tool_bin / "astrbot")],
                )

    def test_shadowing_uv_function_keeps_its_tool_configuration(self):
        wrapper_bin = self.root / "wrapper bin"
        original_path = self.env["PATH"]
        with (self.root / "env.sh").open("a") as fixture:
            # Exercise Bash's real command builtin inside the wrapper.
            fixture.write(
                '\nunset -f command\nuv() { UV_TOOL_BIN_DIR="$TEST_DIR/wrapper bin" '
                'command uv "$@"; }\n'
            )
        for binary_on_path, fail_update in (
            (True, "0"),
            (True, "1"),
            (False, "0"),
            (False, "1"),
        ):
            with self.subTest(binary_on_path=binary_on_path, fail_update=fail_update):
                self.env["PATH"] = (
                    f"{self.root / 'bin'}:{original_path}"
                    if binary_on_path
                    else original_path
                )
                (self.root / ".bashrc").write_text("")
                self.env["TEST_UPDATE_SHELL_FAIL"] = fail_update
                status, output = self.run_installer(["--non-interactive"])
                self.assertEqual(status, 0, output)
                self.assertTrue((wrapper_bin / "astrbot").exists())
                if fail_update == "1":
                    retries = [
                        line.strip()
                        for line in output.splitlines()
                        if line.endswith(" tool update-shell")
                    ]
                    self.assertTrue(retries, output)
                    retry_env = self.env.copy()
                    retry_env.pop("TEST_UPDATE_SHELL_FAIL")
                    retry_env.pop("UV_TOOL_BIN_DIR")
                    for retry in retries:
                        result = subprocess.run(
                            ["/bin/bash", "-c", retry],
                            env=retry_env,
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                shell_env = self.env.copy()
                shell_env.pop("BASH_ENV")
                result = subprocess.run(
                    [
                        "/bin/bash",
                        "--noprofile",
                        "--norc",
                        "-c",
                        'source "$HOME/.bashrc"; command -v uv; command -v astrbot',
                    ],
                    env=shell_env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.splitlines(),
                    [str(self.root / "bin/uv"), str(wrapper_bin / "astrbot")],
                )

    def test_chinese_defaults_to_all_china_mirrors(self):
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"]
        )
        self.assertEqual(status, 0, output)
        self.assert_install(CHINA_INDEX, [PYTHON_MIRROR])
        self.assertIn("  [INFO]    下载源：中国大陆加速下载镜像源", output)

    def test_explicit_official_source_overrides_chinese_default(self):
        status, output = self.run_installer(
            [
                "--language",
                "zh-CN",
                "--download-source",
                "official",
                "--non-interactive",
            ]
        )
        self.assertEqual(status, 0, output)
        self.assert_install(OFFICIAL_INDEX, [""])

    def test_explicit_python_mirror_overrides_environment(self):
        self.env["UV_PYTHON_INSTALL_MIRROR"] = "https://env.example.com/python"
        status, output = self.run_installer(
            [
                "--download-source",
                "china",
                "--python-install-mirror",
                "https://custom.example.com/python",
                "--non-interactive",
            ]
        )
        self.assertEqual(status, 0, output)
        self.assert_install(CHINA_INDEX, ["https://custom.example.com/python"])

    def test_existing_python_mirror_overrides_china_default(self):
        self.env["UV_PYTHON_INSTALL_MIRROR"] = "https://env.example.com/python"
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"]
        )
        self.assertEqual(status, 0, output)
        self.assert_install(CHINA_INDEX, ["https://env.example.com/python"])

    def test_python_mirror_fallback_preserves_pypi(self):
        self.env["TEST_FAIL_ONCE"] = "1"
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"]
        )
        self.assertEqual(status, 0, output)
        self.assert_install(CHINA_INDEX, [PYTHON_MIRROR, ""])
        self.assertIn("正在切换到官方源重试", output)

    def test_install_failure_propagates_after_retry(self):
        self.env["TEST_INSTALL_EXIT"] = "9"
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"]
        )
        self.assertEqual(status, 9, output)
        self.assertNotIn("AstrBot 安装完成", output)
        self.assertNotIn("    astrbot init", output)
        self.assert_install(CHINA_INDEX, [PYTHON_MIRROR, ""])

    def test_english_menu_and_empty_defaults_when_piped(self):
        status, output = self.run_installer([], answers="\n\n", piped=True)
        self.assertEqual(status, 0, output)
        self.assertIn("\n  🌌 AstrBot Installer\n  -----------------------", output)
        self.assertIn("    1. English\n    2. 简体中文\n    3. 日本語", output)
        self.assertIn("  1-3 [1]:", output)
        self.assertIn("    1. Mainland China accelerated download mirrors", output)
        self.assertIn(
            "  Enter a number, or press Enter to use the default [2]:", output
        )
        self.assert_install(OFFICIAL_INDEX, [""])

    def test_chinese_menu_default(self):
        status, output = self.run_installer([], answers="2\n\n", piped=True)
        self.assertEqual(status, 0, output)
        self.assertIn("  输入编号，按回车使用默认选项 [1]:", output)
        self.assert_install(CHINA_INDEX, [PYTHON_MIRROR])

    def test_japanese_custom_menu(self):
        status, output = self.run_installer(
            [],
            answers="3\n0\n3\nhttps://uv.example.com/releases\nhttps://pypi.example.com/simple/\n",
            piped=True,
        )
        self.assertEqual(status, 0, output)
        self.assertIn(
            "  番号を入力してください。Enter で既定値を使用します [2]:", output
        )
        self.assertIn("  使用するシェルに合わせて環境を再読み込みしてください：", output)
        self.assert_install("https://pypi.example.com/simple/", [""])

    def test_official_archive_is_verified_without_installer_script(self):
        status, output = self.run_installer(["--non-interactive"], existing=False)
        self.assertEqual(status, 0, output)
        requests = (self.root / "requests").read_text().splitlines()
        base = "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
        self.assertEqual(requests, [base, base + ".sha256"])

    def test_linux_archive_selection(self):
        self.env.update(TEST_PLATFORM="Linux", TEST_ARCH="x86_64")
        status, output = self.run_installer(["--non-interactive"], existing=False)
        self.assertEqual(status, 0, output)
        self.assertIn(
            "uv-x86_64-unknown-linux-musl.tar.gz", (self.root / "requests").read_text()
        )

    def test_primary_outage_uses_official_archive(self):
        self.env["TEST_FAIL_PRIMARY"] = "1"
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"], existing=False
        )
        self.assertEqual(status, 0, output)
        self.assertEqual(len((self.root / "requests").read_text().splitlines()), 3)

    def test_checksum_mismatch_uses_official_archive(self):
        self.env["TEST_BAD_HASH"] = "1"
        status, output = self.run_installer(
            ["--language", "zh-CN", "--non-interactive"], existing=False
        )
        self.assertEqual(status, 0, output)
        self.assertIn("SHA256", output)
        self.assertEqual(len((self.root / "requests").read_text().splitlines()), 4)

    def test_cookie_challenge_curl(self):
        self.env["TEST_COOKIE"] = "1"
        status, output = self.run_installer(
            ["--download-source", "china", "--non-interactive"], existing=False
        )
        self.assertEqual(status, 0, output)
        self.assertEqual((self.root / "cookie").read_text(), "addr=192.0.2.1\n")
        self.assertEqual(len((self.root / "requests").read_text().splitlines()), 3)

    def test_cookie_challenge_wget(self):
        self.env.update(TEST_COOKIE="1", TEST_WGET="1")
        status, output = self.run_installer(
            ["--download-source", "china", "--non-interactive"], existing=False
        )
        self.assertEqual(status, 0, output)
        self.assertEqual((self.root / "cookie").read_text(), "addr=192.0.2.1\n")

    def test_all_sources_fail_without_false_success(self):
        self.env["TEST_FAIL_ALL"] = "1"
        status, output = self.run_installer(["--non-interactive"], existing=False)
        self.assertEqual(status, 1, output)
        self.assertNotIn("AstrBot has been installed", output)
        self.assertFalse((self.root / "uv-args").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

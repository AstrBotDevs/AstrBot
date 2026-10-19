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

FAKE_UV = b"""#!/bin/bash
if [ "$1" = --version ]; then printf 'uv fixture\\n'; exit 0; fi
printf '%s\\n' "$@" > "$TEST_DIR/uv-args"
printf '%s\\n' "${UV_PYTHON_INSTALL_MIRROR:-}" >> "$TEST_DIR/python-mirrors"
if [ "${TEST_FAIL_ONCE:-0}" = 1 ] && [ ! -f "$TEST_DIR/failed-once" ]; then
  touch "$TEST_DIR/failed-once"
  exit 1
fi
exit "${TEST_INSTALL_EXIT:-0}"
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
uv() { "$UV_UNMANAGED_INSTALL/uv" "$@"; }
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
            BASH_ENV=str(self.root / "env.sh"),
            TEST_DIR=str(self.root),
            UV_UNMANAGED_INSTALL=str(self.root / "bin"),
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
        self.assertIn("  [INFO]    Download source: Official sources", output)
        self.assertIn(
            "\n  Next, run these commands:\n    astrbot init\n    astrbot run\n", output
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
        self.assertIn("  次に、以下を順番に実行してください：", output)
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

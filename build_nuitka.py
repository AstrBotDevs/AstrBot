#!/usr/bin/env python3
"""
Use Nuitka to build the AstrBot project into standalone executables
"""

import os
import platform
import subprocess
import sys
from pathlib import Path


def get_platform_info():
    """fetch the current platform information"""
    system = platform.system()
    machine = platform.machine()
    return system, machine


def build_with_nuitka():
    """use Nuitka to build the project"""
    system, machine = get_platform_info()

    print(f"🚀 Starting build for {system} ({machine}) platform...")

    # Output directory
    output_dir = Path("build/nuitka")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Base Nuitka command
    nuitka_cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",  # Create standalone directory
        "--onefile",  # Single file mode
        "--follow-imports",  # Follow all imports
        "--enable-plugin=multiprocessing",  # Enable multiprocessing support
        "--output-dir=build/nuitka",  # Output directory
        "--quiet",  # Reduce output verbosity
        "--assume-yes-for-downloads",  # Automatically download dependencies
        "--jobs=4",  # Use multiple CPU cores
    ]

    # include specific packages
    include_packages = [
        "astrbot",
    ]

    for pkg in include_packages:
        nuitka_cmd.extend([f"--include-package={pkg}"])

    # include data directories
    # data_includes = [
    #     "data/config",
    #     "data/plugins",
    #     "data/temp",
    # ]

    # for data_dir in data_includes:
    #     if os.path.exists(data_dir):
    #         nuitka_cmd.extend([f"--include-data-dir={data_dir}={data_dir}"])

    # include packages directory (built-in plugins)
    # if os.path.exists("packages"):
    #     nuitka_cmd.extend(["--include-data-dir=packages=packages"])

    # Platform specific settings
    if system == "Darwin":  # macOS
        nuitka_cmd.extend(
            [
                "--macos-create-app-bundle",  # Create .app bundle
                "--macos-app-name=AstrBot",
            ]
        )
        # macOS icon (if exists)
        icon_path = "dashboard/src-tauri/icons/icon.icns"
        if os.path.exists(icon_path):
            nuitka_cmd.extend([f"--macos-app-icon={icon_path}"])
    elif system == "Windows":
        nuitka_cmd.extend(
            [
                "--windows-console-mode=disable",  # 无控制台窗口
            ]
        )
        # Windows icon (if exists)
        icon_path = "dashboard/src-tauri/icons/icon.ico"
        if os.path.exists(icon_path):
            nuitka_cmd.extend([f"--windows-icon-from-ico={icon_path}"])

    # Main file to compile
    nuitka_cmd.append("main.py")

    print(f"📦 Executing command: {' '.join(nuitka_cmd)}")

    try:
        subprocess.run(nuitka_cmd, check=True)
        print("✅ Nuitka build successful!")

        # Find the generated executable
        if system == "Darwin":
            built_file = list(output_dir.glob("*.app"))
            if built_file:
                print(f"Generated macOS app: {built_file[0]}")
        elif system == "Windows":
            built_file = list(output_dir.glob("*.exe"))
            if built_file:
                print(f"Generated Windows executable: {built_file[0]}")
        else:  # Linux
            built_file = list(output_dir.glob("main.bin"))
            if built_file:
                print(f"Generated Linux executable: {built_file[0]}")

        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Nuitka build failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("AstrBot Nuitka Builder")
    print("=" * 60)

    # 构建
    if build_with_nuitka():
        print("\n" + "=" * 60)
        print("🎉 Build Complete!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Build Failed")
        print("=" * 60)
        sys.exit(1)

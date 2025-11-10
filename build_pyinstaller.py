#!/usr/bin/env python3
"""
Use PyInstaller to build the AstrBot project into standalone executables
"""

import platform
import subprocess
import sys
from pathlib import Path


def get_platform_info():
    """fetch the current platform information"""
    system = platform.system()
    machine = platform.machine()
    return system, machine


def build_with_pyinstaller():
    """use PyInstaller to build the project"""
    system, machine = get_platform_info()

    print(f"🚀 Starting build for {system} ({machine}) platform...")

    # Output directory
    output_dir = Path("build/pyinstaller")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Base PyInstaller command
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",  # Clean cache before build
        "--noconfirm",  # Replace output directory without asking
        "--onefile",  # Single file mode
        "--distpath=build/pyinstaller/dist",  # Distribution directory
        "--workpath=build/pyinstaller/build",  # Work directory
        "--specpath=build/pyinstaller",  # Spec file directory
        "--name=AstrBot",  # Output executable name
    ]
    # Platform specific settings
    # if system == "Darwin":  # macOS
    #     # macOS icon (if exists)
    #     icon_path = "dashboard/src-tauri/icons/icon.icns"
    #     if os.path.exists(icon_path):
    #         pyinstaller_cmd.extend([f"--icon={icon_path}"])
    #     # Create .app bundle
    #     pyinstaller_cmd.extend(["--windowed"])
    # elif system == "Windows":
    #     # Windows icon (if exists)
    #     icon_path = "dashboard/src-tauri/icons/icon.ico"
    #     if os.path.exists(icon_path):
    #         pyinstaller_cmd.extend([f"--icon={icon_path}"])
    #     # No console window
    #     pyinstaller_cmd.extend(["--windowed"])
    # else:  # Linux
    #     pyinstaller_cmd.extend(["--console"])

    # Main file to compile
    pyinstaller_cmd.append("main.py")

    print(f"📦 Executing command: {' '.join(pyinstaller_cmd)}")

    try:
        subprocess.run(pyinstaller_cmd, check=True)
        print("✅ PyInstaller build successful!")

        # Find the generated executable
        dist_dir = output_dir / "dist"
        if system == "Darwin":
            built_file = list(dist_dir.glob("AstrBot.app"))
            if not built_file:
                built_file = list(dist_dir.glob("AstrBot"))
            if built_file:
                print(f"📱 Generated macOS app: {built_file[0]}")
        elif system == "Windows":
            built_file = list(dist_dir.glob("AstrBot.exe"))
            if built_file:
                print(f"💻 Generated Windows executable: {built_file[0]}")
        else:  # Linux
            built_file = list(dist_dir.glob("AstrBot"))
            if built_file:
                print(f"🐧 Generated Linux executable: {built_file[0]}")

        print(f"\n📁 Output directory: {dist_dir.absolute()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller build failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def install_pyinstaller():
    """Install PyInstaller if not already installed"""
    try:
        import PyInstaller

        print(f"✅ PyInstaller already installed (version {PyInstaller.__version__})")
        return True
    except ImportError:
        print("📥 PyInstaller not found, installing...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pyinstaller"], check=True
            )
            print("✅ PyInstaller installed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install PyInstaller: {e}")
            return False


if __name__ == "__main__":
    print("=" * 60)
    print("AstrBot PyInstaller Builder")
    print("=" * 60)

    # Check and install PyInstaller
    if not install_pyinstaller():
        sys.exit(1)

    # Build
    if build_with_pyinstaller():
        print("\n" + "=" * 60)
        print("🎉 Build Complete!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Build Failed")
        print("=" * 60)
        sys.exit(1)

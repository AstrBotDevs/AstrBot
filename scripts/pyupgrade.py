#!/usr/bin/env python3
"""
自动升级 astrbot/ 文件夹下所有 Python 文件的脚本。
使用 pyupgrade 将代码升级到 Python 3.10+ 兼容版本。
"""

import os
import subprocess
import sys
from pathlib import Path

def main():
    # 获取当前脚本目录
    script_dir = Path(__file__).resolve().parent
    
    # 确定 astrbot/ 文件夹的位置
    astrbot_dir = script_dir / "astrbot"
    
    if not astrbot_dir.exists() or not astrbot_dir.is_dir():
        # 如果 astrbot 不在当前目录，尝试查找父目录
        astrbot_dir = script_dir.parent / "astrbot"
        if not astrbot_dir.exists() or not astrbot_dir.is_dir():
            print(f"错误: 无法找到 astrbot 文件夹，请检查路径。")
            sys.exit(1)
    
    print(f"开始处理 {astrbot_dir} 目录下的 Python 文件...")
    
    # 计数器，记录处理的文件数量
    processed_count = 0
    
    # 遍历 astrbot/ 目录及其子目录下的所有 .py 文件
    for root, _, files in os.walk(astrbot_dir):
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                try:
                    # 对每个 .py 文件执行 pyupgrade 命令
                    print(f"正在处理: {file_path}")
                    result = subprocess.run(
                        ["pyupgrade", "--py310-plus", str(file_path)],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    if result.returncode == 0:
                        processed_count += 1
                        print(f"✓ 成功升级: {file_path}")
                    else:
                        print(f"✗ 处理失败: {file_path}")
                        print(f"错误信息: {result.stderr.strip()}")
                except Exception as e:
                    print(f"处理 {file_path} 时发生错误: {e}")
    
    print(f"\n处理完成! 共处理了 {processed_count} 个 Python 文件。")
    print("如果您没有看到任何文件被处理，请确认您已安装 pyupgrade：")
    print("pip install pyupgrade")

if __name__ == "__main__":
    main()
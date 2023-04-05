# -*- coding: utf-8 -*-

from git.repo import Repo
import git
import os
# import zipfile

if __name__ == "__main__":
    try:
        # 检测文件夹
        if not os.path.exists('QQChannelChatGPT'):
            os.mkdir('QQChannelChatGPT')
            
        project_path = os.path.join('QQChannelChatGPT')
        try:
            repo = Repo(project_path)
            # 检查当前commit的hash值
            commit_hash = repo.head.object.hexsha
            print("当前commit的hash值为: " + commit_hash)

            # 得到远程仓库的origin的commit的列表
            origin = repo.remotes.origin
            try:
                origin.fetch()
            except:
                pass
            # 得到远程仓库的commit的hash值
            remote_commit_hash = origin.refs.master.commit.hexsha
            print("https://github.com/Soulter/QQChannelChatGPT的commit的hash值为: " + remote_commit_hash)
            # 比较两个commit的hash值
            if commit_hash != remote_commit_hash:
                res = input("检测到项目有更新, 是否更新? (y/n): ")
                if res == 'y':
                    repo.remotes.origin.pull()
                    print("项目更新完毕")
                if res == 'n':
                    print("已取消更新")
        except:
            print("正在从https://github.com/Soulter/QQChannelChatGPT.git拉取项目...")
            Repo.clone_from('https://github.com/Soulter/QQChannelChatGPT.git',to_path=project_path,branch='master')
            print("项目拉取完毕")
            print("【重要提醒】如果你没有Python（版本>=3.8）或者Git环境, 请先安装, 否则接下来的操作会造成闪退。")
            print("【重要提醒】Python下载地址: https://npm.taobao.org/mirrors/python/3.9.7/python-3.9.7-amd64.exe ")
            print("【重要提醒】Git下载地址: https://registry.npmmirror.com/-/binary/git-for-windows/v2.39.2.windows.1/Git-2.39.2-64-bit.exe")
            print("【重要提醒】安装时, 请务必勾选“Add Python to PATH”选项。")
            input("已确保安装了Python3.9+的版本，按下回车继续...")
            print("正在安装依赖库")
            os.system('python -m pip install -r QQChannelChatGPT\\requirements.txt')
            print("依赖库安装完毕")
            input("初次启动, 请先在QQChannelChatGPT/configs/config.yaml填写相关配置! 按任意键继续...")
        finally:
            print("正在启动项目...")
            os.system('python QQChannelChatGPT\main.py')
    except BaseException as e:
        print(e)
        input("程序出错。可以截图发给QQ：905617992.按下回车键退出...")
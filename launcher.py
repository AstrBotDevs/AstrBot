# -*- coding: utf-8 -*-

from git.repo import Repo
import os
# import zipfile

if __name__ == "__main__":
    # 检测文件夹
    if not os.path.exists('QQChannelChatGPT'):
        os.mkdir('QQChannelChatGPT')
    # if not os.path.exists('pythonemb'):
    #     os.mkdir('pythonemb')

    # python_path = os.path.join('pythonemb', 'python.zip')
    # 检测Python环境
    # if not os.path.exists('pythonemb/python.exe'):
    #     print("正在从https://www.python.org/ftp/python/3.10.10/python-3.10.10-embed-amd64.zip安装Python环境...")
    #     os.system('curl -o pythonemb/python.zip https://www.python.org/ftp/python/3.10.10/python-3.10.10-embed-amd64.zip')
    #     print("解压中...")
    #     file=zipfile.ZipFile(python_path)
    #     for name in file.namelist():
    #         file.extract(name, path='pythonemb')
    #     print("解压完毕, 创建pip...")
    #     os.system('curl https://bootstrap.pypa.io/get-pip.py -o pythonemb\get-pip.py')
    #     os.system('pythonemb\python.exe pythonemb\get-pip.py')
    #     print("pip创建完毕")
    #     print("Python环境安装完成")


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
                repo.remote().pull()
                print("项目更新完毕")
            if res == 'n':
                print("已取消更新")
    except:
        print("正在从https://github.com/Soulter/QQChannelChatGPT.git拉取项目...")
        Repo.clone_from('https://github.com/Soulter/QQChannelChatGPT.git',to_path=project_path,branch='master')
        print("项目拉取完毕")
        print("【重要提醒】如果你没有Python环境, 请先安装Python环境，版本需大于等于3.9, 否则接下来的操作会造成闪退。")
        print("【重要提醒】Python3.9淘宝下载地址: https://npm.taobao.org/mirrors/python/3.9.7/python-3.9.7-amd64.exe ")
        print("【重要提醒】安装时, 请务必勾选“Add Python 3.9 to PATH”选项。")
        print("【重要提醒】QQ: 905617992")
        print("【重要提醒】欢迎给项目Star:) https://github.com/Soulter/QQChannelChatGPT")
        input("已确保安装了Python3.9+的版本，按下回车继续...")
        print("正在安装依赖库...")
        os.system('python -m pip install -r QQChannelChatGPT\\requirements.txt')
        print("依赖库安装完毕")
        input("初次启动, 请先在QQChannelChatGPT/configs/config.yaml填写相关配置! 按任意键继续...")
    finally:
        print("正在启动项目...")
        os.system('python QQChannelChatGPT\main.py')

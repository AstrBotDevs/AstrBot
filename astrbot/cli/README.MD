#Astrbot.cli包

---



```组织结构：
cli
├── __init__.py
|—— __main__.py 
├── init.py 附属于cli根命令组，负责初始化astrbot 根目录结构
└── run.py 附属于cli根命令组 ，负责启动astrbot
   |————conf 子命令组
   ├── __init__.py 附属于cli.conf命令组，负责导出子命令组conf
   ├── __main__.py 附属于cli.conf命令组，命令组入口，需采用绝对导入

... 其他命令组 如plug
```

1. 命令组对应一个文件夹
   比如cli文件夹对应cli根命令组
   conf文件夹对应conf 子命令组
2. __main__.py只能放命令组和基本内置命令，比如自定义的help命令之类的
   且不能使用相对导入，设计为了可以直接使用python -m 运行，和直接运行。
   其余设计为被导入使用的统一采用相对导入，且延迟导入
3. __init__.py 仅导出命令组
4. 命令.py：以命令名命名，除非特殊情况。比如和关键词撞名了
5. 路径统一使用pathlib.Path
6. 最好标注类型
7. 不要使用大写开头的类型，直接用内置的全小写的类型标注

   ---

使用以下命令安装测试
uv tool install -p 3.10 -e .

> tips
> 如果版本为3.12/3.13直接使用uv tool install -e .会报错
> 此时需要使用-p参数指定python版本为3.10

ASTRBOT_ROOT环境变量！指定ASTRBOT根目录!

1. 设置指南：
2. 直接按下win键搜索 环境变量
3. 点击 编辑系统环境变量 - > 按N 或者点击编辑环境变量按钮
4. 新建变量名为ASTRBOT_ROOT，变量值为astrbot根目录路径即可（空目录即可）

# 例如：C:\Users\Administrator\Desktop\astrbot

默认是 ~/.astrbot/

> tips
> 如果使用astrbot init --root cwd将使用当前目录作为astrbot根目录！

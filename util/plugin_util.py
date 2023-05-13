import os
import inspect

# 找出模块里所有的类名
def get_classes(p_name, arg):
    classes = []
    clsmembers = inspect.getmembers(arg, inspect.isclass)
    for (name, _) in clsmembers:
        # print(name, p_name)
        if p_name.lower() == name.lower().replace("plugin", ""):
            classes.append(name)
            break
    return classes

# 获取一个文件夹下所有的模块
def get_modules(path):
    modules = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                modules.append(file[:-3])
    return modules
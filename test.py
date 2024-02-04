from pip._internal.operations.freeze import freeze

# 获取已安装包的信息
installed_packages = freeze()

# 输出已安装包的信息
for package in installed_packages:
    print(package)

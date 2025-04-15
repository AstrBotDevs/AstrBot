import logging
from pip import main as pip_main

logger = logging.getLogger("astrbot")


class PipInstaller:
    def __init__(self, pip_install_arg: str, pypi_index_url: str = None):
        self.pip_install_arg = pip_install_arg
        self.pypi_index_url = pypi_index_url

    def install(
        self,
        package_name: str = None,
        requirements_path: str = None,
        mirror: str = None,
    ):
        args = ["install"]
        if package_name:
            args.append(package_name)
        elif requirements_path:
            args.extend(["-r", requirements_path])

        index_url = mirror or self.pypi_index_url or "https://pypi.org/simple"

        args.extend(["--trusted-host", "mirrors.aliyun.com", "-i", index_url])

        if self.pip_install_arg:
            args.extend(self.pip_install_arg.split())

        logger.info(f"Pip 包管理器: pip {' '.join(args)}")

        result_code = pip_main(args)

        # 清除 pip.main 导致的多余的 logging handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        if result_code != 0:
            raise Exception(f"安装失败，错误码：{result_code}")

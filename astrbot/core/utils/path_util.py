import os
from astrbot.core import logger

def path_Mapping(mappings, srcPath: str)->str:
        """路径映射处理函数。尝试支援 Windows 和 Linux 的路径映射。
        Args:
            mappings: 映射规则列表
            srcPath: 原路径
        Returns:
            str: 处理后的路径
        """
        for mapping in mappings:
            rule = mapping.split(":")
            if len(rule) == 2:
                from_, to_ = mapping.split(":")
            elif len(rule) > 4 or len(rule) == 1:
                # 切割后大于4个项目，或者只有1个项目，那肯定是错误的，只能是2，3，4个项目
                logger.warning(f"路径映射规则错误: {mapping}")
                continue
            else:
                # rule.len == 3 or 4
                if(os.path.exists(rule[0]+":"+rule[1])):
                    # 前面两个项目合并路径存在，说明是本地Window路径。后面一个或两个项目组成的路径本地大概率无法解析，直接拼接
                    from_ = rule[0] + ":" + rule[1]
                    if len(rule) == 3:
                        to_ = rule[2]
                    else:
                        to_ = rule[2] + ":" + rule[3]
                else:
                    # 前面两个项目合并路径不存在，说明第一个项目是本地Linux路径，后面一个或两个项目直接拼接。
                    from_ = rule[0]
                    if len(rule) == 3:
                        to_ = rule[1] + ":" + rule[2]
                    else:
                        # 这种情况下存在四个项目，说明规则也是错误的
                        logger.warning(f"路径映射规则错误: {mapping}")
                        continue

            from_ = from_.removesuffix("/")
            from_ = from_.removesuffix("\\")
            to_ = to_.removesuffix("/")
            to_ = to_.removesuffix("\\")
            # logger.debug(f"\t路径映射-规则(处理): {from_} -> {to_}")

            url = srcPath.removeprefix("file://")
            if url.startswith(from_):
                srcPath = url.replace(from_, to_, 1)
                if ":" in srcPath:
                    # Windows路径处理
                    srcPath = srcPath.replace("/", "\\")
                else:
                    has_replaced_processed = False
                    if srcPath.startswith("."):
                        # 相对路径处理。如果是相对路径，可能是Linux路径，也可能是Windows路径
                        sign = srcPath[1]
                        # 处理两个点的情况
                        if sign == ".":
                            sign = srcPath[2]
                        if sign == "/":
                            srcPath = srcPath.replace("\\", "/")
                            has_replaced_processed = True
                        elif sign == "\\":
                            srcPath = srcPath.replace("/", "\\")
                            has_replaced_processed = True
                    if has_replaced_processed == False:
                        # 如果不是相对路径或不能处理，默认按照Linux路径处理
                        srcPath = srcPath.replace("\\", "/")
                logger.info(f"路径映射: {url} -> {srcPath}")
                return srcPath
        return srcPath
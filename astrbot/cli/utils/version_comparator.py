"""
拷贝自 astrbot.core.utils.version_comparator
"""

import re


class VersionComparator:
    @staticmethod
    def compare_version(v1: str, v2: str) -> int:
        """根据 Semver 语义版本规范来比较版本号的大小。支持不仅局限于 3 个数字的版本号，并处理预发布标签。

        参考: https://semver.org/lang/zh-CN/

        返回 1 表示 v1 > v2，返回 -1 表示 v1 < v2，返回 0 表示 v1 = v2。
        """
        v1 = v1.lower().replace("v", "")
        v2 = v2.lower().replace("v", "")

        def split_version(version):
            match = re.match(
                r"^([0-9]+(?:\.[0-9]+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+(.+))?$",
                version,
            )
            if not match:
                return [], None
            major_minor_patch = match.group(1).split(".")
            prerelease = match.group(2)
            # buildmetadata = match.group(3) # 构建元数据在比较时忽略
            parts = [int(x) for x in major_minor_patch]
            prerelease = VersionComparator._split_prerelease(prerelease)
            return parts, prerelease

        v1_parts, v1_prerelease = split_version(v1)
        v2_parts, v2_prerelease = split_version(v2)

        # 比较数字部分
        length = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (length - len(v1_parts)))
        v2_parts.extend([0] * (length - len(v2_parts)))

        for i in range(length):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1

        # 比较预发布标签
        if v1_prerelease is None and v2_prerelease is not None:
            return 1  # 没有预发布标签的版本高于有预发布标签的版本
        elif v1_prerelease is not None and v2_prerelease is None:
            return -1  # 有预发布标签的版本低于没有预发布标签的版本
        elif v1_prerelease is not None and v2_prerelease is not None:
            len_pre = max(len(v1_prerelease), len(v2_prerelease))
            for i in range(len_pre):
                p1 = v1_prerelease[i] if i < len(v1_prerelease) else None
                p2 = v2_prerelease[i] if i < len(v2_prerelease) else None

                if p1 is None and p2 is not None:
                    return -1
                elif p1 is not None and p2 is None:
                    return 1
                elif isinstance(p1, int) and isinstance(p2, str):
                    return -1
                elif isinstance(p1, str) and isinstance(p2, int):
                    return 1
                elif isinstance(p1, int) and isinstance(p2, int):
                    if p1 > p2:
                        return 1
                    elif p1 < p2:
                        return -1
                elif isinstance(p1, str) and isinstance(p2, str):
                    if p1 > p2:
                        return 1
                    elif p1 < p2:
                        return -1
            return 0  # 预发布标签完全相同

        return 0  # 数字部分和预发布标签都相同

    @staticmethod
    def _split_prerelease(prerelease):
        if not prerelease:
            return None
        parts = prerelease.split(".")
        result = []
        for part in parts:
            if part.isdigit():
                result.append(int(part))
            else:
                result.append(part)
        return result

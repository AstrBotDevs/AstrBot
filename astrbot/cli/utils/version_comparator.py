"""Copied from astrbot.core.utils.version_comparator"""

import re


class VersionComparator:
    @staticmethod
    def compare_version(v1: str, v2: str) -> int:
        """Compare version numbers according to Semver semantics. Supports version numbers with more than 3 digits and handles pre-release tags.

        Reference: https://semver.org/

        Returns 1 if v1 > v2, -1 if v1 < v2, 0 if v1 == v2.
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
            # buildmetadata = match.group(3)  # Build metadata is ignored in comparison
            parts = [int(x) for x in major_minor_patch]
            prerelease = VersionComparator._split_prerelease(prerelease)
            return parts, prerelease

        v1_parts, v1_prerelease = split_version(v1)
        v2_parts, v2_prerelease = split_version(v2)

        # Compare numeric parts
        length = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (length - len(v1_parts)))
        v2_parts.extend([0] * (length - len(v2_parts)))

        for i in range(length):
            if v1_parts[i] > v2_parts[i]:
                return 1
            if v1_parts[i] < v2_parts[i]:
                return -1

        # Compare pre-release tags
        if v1_prerelease is None and v2_prerelease is not None:
            return 1  # Version without pre-release tag is higher than one with it
        if v1_prerelease is not None and v2_prerelease is None:
            return -1  # Version with pre-release tag is lower than one without it
        if v1_prerelease is not None and v2_prerelease is not None:
            len_pre = max(len(v1_prerelease), len(v2_prerelease))
            for i in range(len_pre):
                p1 = v1_prerelease[i] if i < len(v1_prerelease) else None
                p2 = v2_prerelease[i] if i < len(v2_prerelease) else None

                if p1 is None and p2 is not None:
                    return -1
                if p1 is not None and p2 is None:
                    return 1
                if isinstance(p1, int) and isinstance(p2, str):
                    return -1
                if isinstance(p1, str) and isinstance(p2, int):
                    return 1
                if isinstance(p1, int) and isinstance(p2, int):
                    if p1 > p2:
                        return 1
                    if p1 < p2:
                        return -1
                elif isinstance(p1, str) and isinstance(p2, str):
                    if p1 > p2:
                        return 1
                    if p1 < p2:
                        return -1
            return 0  # Pre-release tags are identical

        return 0  # Both numeric parts and pre-release tags are equal

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

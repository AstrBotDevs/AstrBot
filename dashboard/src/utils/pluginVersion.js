const parsePluginVersion = (rawVersion) => {
  if (rawVersion == null) return null;
  const cleaned = String(rawVersion).trim().replace(/^[vV]/, "");
  if (!cleaned) return null;

  const match =
    /^(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(
      cleaned,
    );
  if (!match) return null;

  const numeric = match[1].split(".").map((part) => Number.parseInt(part, 10));
  if (numeric.some((part) => Number.isNaN(part))) return null;

  const prerelease = match[2]
    ? match[2]
        .split(".")
        .map((part) =>
          /^\d+$/.test(part) ? Number.parseInt(part, 10) : part.toLowerCase(),
        )
    : null;

  return { numeric, prerelease };
};

const comparePrerelease = (left, right) => {
  if (!left && !right) return 0;
  if (!left) return 1;
  if (!right) return -1;

  const maxLength = Math.max(left.length, right.length);
  for (let i = 0; i < maxLength; i++) {
    const leftPart = left[i];
    const rightPart = right[i];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    if (leftPart === rightPart) continue;

    const leftIsNumber = typeof leftPart === "number";
    const rightIsNumber = typeof rightPart === "number";

    if (leftIsNumber && rightIsNumber) return leftPart > rightPart ? 1 : -1;
    if (leftIsNumber !== rightIsNumber) return leftIsNumber ? -1 : 1;

    const compareResult = String(leftPart).localeCompare(String(rightPart));
    if (compareResult !== 0) return compareResult > 0 ? 1 : -1;
  }

  return 0;
};

export const comparePluginVersions = (leftVersion, rightVersion) => {
  const left = parsePluginVersion(leftVersion);
  const right = parsePluginVersion(rightVersion);
  if (!left || !right) return null;

  const maxLength = Math.max(left.numeric.length, right.numeric.length);
  for (let i = 0; i < maxLength; i++) {
    const leftPart = left.numeric[i] ?? 0;
    const rightPart = right.numeric[i] ?? 0;
    if (leftPart === rightPart) continue;
    return leftPart > rightPart ? 1 : -1;
  }

  return comparePrerelease(left.prerelease, right.prerelease);
};

const normalizeVersionText = (value) => String(value ?? "").trim();

export const isUnknownVersionText = (value, unknownLabel) => {
  const normalizedValue = normalizeVersionText(value).toLowerCase();
  const candidates = new Set([
    normalizeVersionText(unknownLabel).toLowerCase(),
    "unknown",
    "未知",
  ]);
  return candidates.has(normalizedValue);
};

export const shouldMarkPluginUpdate = (
  localVersion,
  onlineVersion,
  unknownLabel,
) => {
  const compareResult = comparePluginVersions(onlineVersion, localVersion);
  if (compareResult !== null) {
    return compareResult > 0;
  }

  if (isUnknownVersionText(onlineVersion, unknownLabel)) {
    return false;
  }

  return (
    normalizeVersionText(localVersion).toLowerCase() !==
    normalizeVersionText(onlineVersion).toLowerCase()
  );
};

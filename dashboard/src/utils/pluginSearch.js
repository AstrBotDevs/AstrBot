import { pinyin } from "pinyin-pro";

const HAN_IDEOGRAPH_RE = /\p{Unified_Ideograph}/u;

export const normalizeStr = (s) => (s ?? "").toString().toLowerCase().trim();

const normalizeLooseFromNormalized = (normalized) =>
  normalized
    .replace(/[\s_-]+/g, "")
    .replace(/[()（）【】{}·•]/g, "")
    .replace(/\[/g, "")
    .replace(/\]/g, "");

export const normalizeLoose = (s) =>
  normalizeLooseFromNormalized(normalizeStr(s));

const memoizeStringFn = (fn) => {
  const cache = new Map();

  return (raw) => {
    const key = (raw ?? "").toString();
    if (cache.has(key)) {
      return cache.get(key);
    }

    const value = fn(key);
    cache.set(key, value);
    return value;
  };
};

const getNormalizedText = memoizeStringFn(normalizeStr);

const getLooseText = memoizeStringFn((text) =>
  normalizeLooseFromNormalized(getNormalizedText(text)),
);

export const toPinyinText = memoizeStringFn((text) =>
  pinyin(text, { toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, ""),
);

export const toInitials = memoizeStringFn((text) =>
  pinyin(text, { pattern: "first", toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, ""),
);

export const buildSearchQuery = (raw) => {
  const norm = getNormalizedText(raw);
  if (!norm) return null;
  return {
    norm,
    loose: getLooseText(raw),
  };
};

export const matchesText = (value, query) => {
  if (value == null || !query?.norm) return false;
  const text = String(value);

  const normalizedValue = getNormalizedText(text);
  const looseValue = query.loose ? getLooseText(text) : null;

  if (normalizedValue.includes(query.norm)) return true;
  if (query.loose && looseValue?.includes(query.loose)) return true;

  if (!HAN_IDEOGRAPH_RE.test(text)) return false;

  const pinyinValue = toPinyinText(text);
  if (pinyinValue.includes(query.norm)) return true;

  const initialsValue = toInitials(text);
  if (initialsValue.includes(query.norm)) return true;

  return false;
};

export const getPluginSearchFields = (plugin) => {
  const supportPlatforms = Array.isArray(plugin?.support_platforms)
    ? plugin.support_platforms.join(" ")
    : "";
  const tags = Array.isArray(plugin?.tags) ? plugin.tags.join(" ") : "";

  return [
    plugin?.name,
    plugin?.trimmedName,
    plugin?.display_name,
    plugin?.desc,
    plugin?.author,
    plugin?.repo,
    plugin?.version,
    plugin?.astrbot_version,
    supportPlatforms,
    tags,
  ];
};

export const matchesPluginSearch = (plugin, query) => {
  if (!query) return true;

  return getPluginSearchFields(plugin).some((candidate) =>
    matchesText(candidate, query),
  );
};

import { pinyin } from "pinyin-pro";

// Small bounded cache to avoid repeated pinyin conversion work during search.
const MAX_SEARCH_CACHE_SIZE = 500;
const normalizedTextCache = new Map();
const looseTextCache = new Map();
const pinyinTextCache = new Map();
const initialsCache = new Map();
const HAN_IDEOGRAPH_RE = /\p{Unified_Ideograph}/u;

export const normalizeStr = (s) => (s ?? "").toString().toLowerCase().trim();

const normalizeLooseFromNormalized = (normalized) =>
  normalized.replace(/[\s_-]+/g, "").replace(/[()（）【】\[\]{}·•]+/g, "");

export const normalizeLoose = (s) =>
  normalizeLooseFromNormalized(normalizeStr(s));

const setCacheValue = (cache, key, value) => {
  if (cache.has(key)) {
    cache.delete(key);
  }
  cache.set(key, value);

  if (cache.size > MAX_SEARCH_CACHE_SIZE) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey !== undefined) {
      cache.delete(oldestKey);
    }
  }
};

const getNormalizedText = (s) => {
  const text = (s ?? "").toString();
  if (normalizedTextCache.has(text)) {
    return normalizedTextCache.get(text);
  }

  const result = normalizeStr(text);
  setCacheValue(normalizedTextCache, text, result);
  return result;
};

const getLooseText = (s) => {
  const text = (s ?? "").toString();
  if (looseTextCache.has(text)) {
    return looseTextCache.get(text);
  }

  const normalizedText = getNormalizedText(text);
  const result = normalizeLooseFromNormalized(normalizedText);
  setCacheValue(looseTextCache, text, result);
  return result;
};

export const toPinyinText = (s) => {
  const text = (s ?? "").toString();
  if (pinyinTextCache.has(text)) {
    return pinyinTextCache.get(text);
  }

  const result = pinyin(text, { toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, "");
  setCacheValue(pinyinTextCache, text, result);
  return result;
};

export const toInitials = (s) => {
  const text = (s ?? "").toString();
  if (initialsCache.has(text)) {
    return initialsCache.get(text);
  }

  const result = pinyin(text, { pattern: "first", toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, "");
  setCacheValue(initialsCache, text, result);
  return result;
};

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
  if (normalizedValue.includes(query.norm)) return true;

  const looseValue = getLooseText(text);
  if (query.loose && looseValue.includes(query.loose)) return true;

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

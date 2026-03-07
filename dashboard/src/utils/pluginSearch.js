import { pinyin } from "pinyin-pro";

const pinyinTextCache = new Map();
const initialsCache = new Map();

export const normalizeStr = (s) => (s ?? "").toString().toLowerCase().trim();

export const normalizeLoose = (s) =>
  normalizeStr(s).replace(/[\s_-]+/g, "").replace(/[()（）【】\[\]{}·•]+/g, "");

export const toPinyinText = (s) => {
  const text = (s ?? "").toString();
  if (pinyinTextCache.has(text)) {
    return pinyinTextCache.get(text);
  }

  const result = pinyin(text, { toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, "");
  pinyinTextCache.set(text, result);
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
  initialsCache.set(text, result);
  return result;
};

export const buildSearchQuery = (raw) => {
  const norm = normalizeStr(raw);
  if (!norm) return null;
  return {
    norm,
    loose: normalizeLoose(raw),
  };
};

export const matchesText = (value, query) => {
  if (value == null || !query?.norm) return false;
  const text = String(value);

  const normalizedValue = normalizeStr(text);
  if (normalizedValue.includes(query.norm)) return true;

  const looseValue = normalizeLoose(text);
  if (query.loose && looseValue.includes(query.loose)) return true;

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

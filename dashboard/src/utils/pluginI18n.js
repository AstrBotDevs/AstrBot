import { useI18n } from "@/i18n/composables";

function getLocaleData(i18n, locale) {
  if (!i18n || typeof i18n !== "object" || !locale) return null;
  return i18n[locale] || null;
}

function getByPath(source, key) {
  if (!source || typeof source !== "object" || !key) return undefined;

  const parts = key.split(".");
  let current = source;
  for (const part of parts) {
    if (!current || typeof current !== "object" || !(part in current)) {
      return undefined;
    }
    current = current[part];
  }
  return current;
}

export function resolvePluginI18n(i18n, locale, key, fallback = "") {
  const localeData = getLocaleData(i18n, locale);
  const value = getByPath(localeData, key);
  return value === undefined || value === null ? fallback : value;
}

/** Resolve each view label from translations, metadata, then its default. */
export function resolvePluginViewText(i18n, locale, view, attr) {
  const name = typeof view === "string" ? view : view?.page_name || view?.name;
  for (const candidate of new Set([locale, "zh-CN", "en-US"].filter(Boolean))) {
    for (const prefix of ["views", "pages"]) {
      const value = resolvePluginI18n(
        i18n,
        candidate,
        `${prefix}.${name}.${attr}`,
      );
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  }
  const value = typeof view === "object" ? view?.[attr] : undefined;
  return typeof value === "string" && value.trim()
    ? value.trim()
    : attr === "title"
    ? name || ""
    : "";
}

export function usePluginI18n() {
  const { locale } = useI18n();

  const resolve = (i18n, key, fallback = "") => {
    return resolvePluginI18n(i18n, locale.value, key, fallback);
  };

  const pluginName = (plugin) => {
    const fallback = plugin?.display_name?.length
      ? plugin.display_name
      : plugin?.name;
    return resolve(plugin?.i18n, "metadata.display_name", fallback || "");
  };

  const pluginDesc = (plugin, fallback = "") => {
    return resolve(
      plugin?.i18n,
      "metadata.desc",
      fallback || plugin?.desc || plugin?.description || "",
    );
  };

  const pluginShortDesc = (plugin, fallback = "") => {
    return resolve(
      plugin?.i18n,
      "metadata.short_desc",
      fallback ||
        plugin?.short_desc ||
        plugin?.desc ||
        plugin?.description ||
        "",
    );
  };

  const pluginPageText = (plugin, page, attr, fallback = "") => {
    const metadata =
      typeof page === "object"
        ? page
        : plugin?.views?.find((view) => view.name === page) || { name: page };
    return (
      resolvePluginViewText(plugin?.i18n, locale.value, metadata, attr) ||
      fallback
    );
  };

  const pluginViewTitle = (plugin, page, fallback = "") =>
    pluginPageText(plugin, page, "title", fallback);

  const pluginViewDescription = (plugin, page, fallback = "") =>
    pluginPageText(plugin, page, "description", fallback);

  const configText = (i18n, path, attr, fallback = "") => {
    const key = path ? `config.${path}.${attr}` : `config.${attr}`;
    return resolve(i18n, key, fallback);
  };

  return {
    locale,
    resolve,
    pluginName,
    pluginDesc,
    pluginShortDesc,
    pluginPageText,
    pluginViewTitle,
    pluginViewDescription,
    configText,
  };
}

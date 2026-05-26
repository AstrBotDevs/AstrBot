export const GITHUB_PROXY_RADIO_VALUE_KEY = "githubProxyRadioValue";
export const SELECTED_GITHUB_PROXY_KEY = "selectedGitHubProxy";
export const PLUGIN_README_IMAGE_SOURCE_KEY = "pluginReadmeImageSource";
export const PLUGIN_README_IMAGE_SOURCE_CHANGED_EVENT =
  "plugin-readme-image-source-changed";

export const PLUGIN_README_IMAGE_SOURCE = {
  LOCAL: "local",
  GITHUB: "github",
};

export function getSelectedGitHubProxy() {
  if (typeof window === "undefined" || !window.localStorage) return "";
  return localStorage.getItem(GITHUB_PROXY_RADIO_VALUE_KEY) === "1"
    ? localStorage.getItem(SELECTED_GITHUB_PROXY_KEY) || ""
    : "";
}

export function buildGitHubProxyUrl(url, proxy = getSelectedGitHubProxy()) {
  const normalizedProxy = (proxy || "").trim().replace(/\/+$/, "");
  if (!normalizedProxy) return url;
  return `${normalizedProxy}/${url}`;
}

export function getPluginReadmeImageSource() {
  if (typeof window === "undefined" || !window.localStorage) {
    return PLUGIN_README_IMAGE_SOURCE.LOCAL;
  }
  const source = localStorage.getItem(PLUGIN_README_IMAGE_SOURCE_KEY);
  return source === PLUGIN_README_IMAGE_SOURCE.GITHUB
    ? PLUGIN_README_IMAGE_SOURCE.GITHUB
    : PLUGIN_README_IMAGE_SOURCE.LOCAL;
}

export function isPluginReadmeGitHubImageSource() {
  return getPluginReadmeImageSource() === PLUGIN_README_IMAGE_SOURCE.GITHUB;
}

export function setPluginReadmeImageSource(source) {
  if (typeof window === "undefined" || !window.localStorage) return;
  const normalizedSource =
    source === PLUGIN_README_IMAGE_SOURCE.GITHUB
      ? PLUGIN_README_IMAGE_SOURCE.GITHUB
      : PLUGIN_README_IMAGE_SOURCE.LOCAL;
  localStorage.setItem(PLUGIN_README_IMAGE_SOURCE_KEY, normalizedSource);
  window.dispatchEvent(
    new CustomEvent(PLUGIN_README_IMAGE_SOURCE_CHANGED_EVENT, {
      detail: { source: normalizedSource },
    }),
  );
}

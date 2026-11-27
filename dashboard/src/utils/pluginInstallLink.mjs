export const PLUGIN_INSTALL_QUERY_KEYS = [
  "install_url",
  "market_plugin_id",
  "registry_url",
];

export function hasPluginInstallLink({ path, query }) {
  return (
    /^\/extension\/plugins(?:\/|$)/.test(path) &&
    PLUGIN_INSTALL_QUERY_KEYS.some((key) => key in query)
  );
}

/** Read an internal plugin install redirect from an auth route query. */
export function getPluginInstallReturnUrl(router, redirect) {
  if (
    typeof redirect !== "string" ||
    !redirect.startsWith("/extension/") ||
    redirect.includes("\\")
  ) {
    return undefined;
  }
  return hasPluginInstallLink(router.resolve(redirect)) ? redirect : undefined;
}

/** Validate the two supported link formats before opening the installer. */
export function parsePluginInstallLink({
  install_url: repository,
  market_plugin_id: pluginId,
  registry_url: registry,
}) {
  if (repository !== undefined) {
    if (pluginId !== undefined || registry !== undefined) {
      return { error: "dialogs.install.linkConflict" };
    }
    try {
      if (typeof repository !== "string") throw new Error();
      const url = new URL(repository);
      if (
        url.protocol === "https:" &&
        url.hostname === "github.com" &&
        !url.port &&
        !url.username &&
        !url.password &&
        !url.search &&
        !url.hash &&
        /^\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(url.pathname)
      ) {
        return { repository: url.href };
      }
    } catch {
      // Report invalid and repeated values using the same message.
    }
    return { error: "messages.invalidRepositoryUrl" };
  }

  if (
    typeof pluginId !== "string" ||
    !/^[^/\p{Cc}]+\/[^/\p{Cc}]+$/u.test(pluginId) ||
    pluginId.split("/").some((part) => part !== part.trim())
  ) {
    return { error: "dialogs.install.invalidMarketPluginId" };
  }
  if (registry === undefined) return { pluginId, registryUrl: null };

  try {
    if (typeof registry !== "string") throw new Error();
    const url = new URL(registry);
    if (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      !url.hash
    ) {
      return { pluginId, registryUrl: url.href.replace(/\/+$/, "") };
    }
  } catch {
    // Invalid and repeated registry values are rejected below.
  }
  return { error: "dialogs.install.invalidRegistryUrl" };
}

import axios, { type InternalAxiosRequestConfig } from "axios";

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//;
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);
let interceptorsConfigured = false;

function isAbsoluteUrl(value: string): boolean {
  return ABSOLUTE_URL_PATTERN.test(value);
}

function stripTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

function ensureLeadingSlash(value: string): string {
  if (!value) {
    return "/";
  }
  return value.startsWith("/") ? value : `/${value}`;
}

function stripLeadingApiPrefix(path: string): string {
  const normalizedPath = ensureLeadingSlash(path);
  const strippedPath = normalizedPath.replace(/^\/api(?=\/|$)/, "");
  return strippedPath || "/";
}

function baseEndsWithApi(baseUrl: string): boolean {
  if (!baseUrl) {
    return false;
  }

  if (isAbsoluteUrl(baseUrl)) {
    try {
      return new URL(baseUrl).pathname.replace(/\/+$/, "").endsWith("/api");
    } catch {
      return baseUrl.replace(/\/+$/, "").endsWith("/api");
    }
  }

  return stripTrailingSlashes(baseUrl).endsWith("/api");
}

function normalizePathForBase(path: string, baseUrl = ""): string {
  if (!path) {
    return "/";
  }

  if (isAbsoluteUrl(path)) {
    return path;
  }

  const normalizedPath = ensureLeadingSlash(path);
  if (baseEndsWithApi(baseUrl)) {
    return stripLeadingApiPrefix(normalizedPath);
  }
  return normalizedPath;
}

function joinBaseAndPath(baseUrl: string, path: string): string {
  const cleanBase = stripTrailingSlashes(baseUrl);
  const cleanPath = path.replace(/^\/+/, "");
  return `${cleanBase}/${cleanPath}`;
}

function normalizeBaseUrl(baseUrl: string | null | undefined): string {
  return stripTrailingSlashes(baseUrl?.trim() || "");
}

function shouldUseDevProxyBase(baseUrl: string): boolean {
  if (!import.meta.env.DEV || !isAbsoluteUrl(baseUrl)) {
    return false;
  }

  try {
    const parsedUrl = new URL(baseUrl);
    const proxyTarget = import.meta.env.VITE_DEV_API_PROXY_TARGET?.trim();
    const normalizedPathname = parsedUrl.pathname.replace(/\/+$/, "") || "/";
    const isLoopbackHost = LOOPBACK_HOSTS.has(parsedUrl.hostname);
    const targetsProxyPath =
      normalizedPathname === "/" || normalizedPathname === "/api";

    if (proxyTarget) {
      const proxyUrl = new URL(proxyTarget);
      const sameOriginAsProxyTarget =
        parsedUrl.protocol === proxyUrl.protocol &&
        parsedUrl.hostname === proxyUrl.hostname &&
        parsedUrl.port === proxyUrl.port;

      if (sameOriginAsProxyTarget && targetsProxyPath) {
        return true;
      }
    }

    return isLoopbackHost && targetsProxyPath;
  } catch {
    return false;
  }
}

function ensureAxiosInterceptors(): void {
  if (interceptorsConfigured) {
    return;
  }

  axios.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(
      config.baseURL ?? axios.defaults.baseURL,
    );

    config.baseURL = normalizedBaseUrl;

    if (typeof config.url === "string") {
      config.url = normalizePathForBase(config.url, normalizedBaseUrl);
    }

    const token = localStorage.getItem("token");
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }

    const locale = localStorage.getItem("astrbot-locale");
    if (locale) {
      config.headers.set("Accept-Language", locale);
    }

    return config;
  });

  interceptorsConfigured = true;
}

export function normalizeConfiguredApiBaseUrl(
  baseUrl: string | null | undefined,
): string {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);

  if (!normalizedBaseUrl) {
    return "";
  }

  if (shouldUseDevProxyBase(normalizedBaseUrl)) {
    return "/api";
  }

  return normalizedBaseUrl;
}

export function getApiBaseUrl(): string {
  return normalizeConfiguredApiBaseUrl(axios.defaults.baseURL);
}

export function getApiBaseUrlValidationError(
  baseUrl: string | null | undefined,
): string | null {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);

  if (!normalizedBaseUrl || !isAbsoluteUrl(normalizedBaseUrl)) {
    return null;
  }

  if (window.location.protocol !== "https:") {
    return null;
  }

  try {
    const parsedUrl = new URL(normalizedBaseUrl);
    if (parsedUrl.protocol !== "http:") {
      return null;
    }
  } catch {
    return null;
  }

  return "This dashboard is served over HTTPS, so the browser will block an HTTP backend. Put AstrBot behind an HTTPS reverse proxy or tunnel (for example Nginx, Caddy, or Cloudflare Tunnel), then use that HTTPS URL here.";
}

export function setApiBaseUrl(baseUrl: string | null | undefined): string {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);
  axios.defaults.baseURL = normalizedBaseUrl;
  return normalizedBaseUrl;
}

export function resolveApiUrl(
  path: string,
  baseUrl: string | null | undefined = getApiBaseUrl(),
): string {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);
  const normalizedPath = normalizePathForBase(path, normalizedBaseUrl);

  if (isAbsoluteUrl(normalizedPath)) {
    return normalizedPath;
  }

  if (!normalizedBaseUrl) {
    return normalizedPath;
  }

  return joinBaseAndPath(normalizedBaseUrl, normalizedPath);
}

export function resolvePublicUrl(path: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const cleanBase = base.endsWith("/") ? base : `${base}/`;
  return new URL(
    path.replace(/^\/+/, ""),
    window.location.origin + cleanBase,
  ).toString();
}

export function resolveWebSocketUrl(
  path: string,
  queryParams?: Record<string, string>,
): string {
  const resolvedApiUrl = resolveApiUrl(path);
  const url = new URL(resolvedApiUrl, window.location.href);

  if (url.protocol === "https:") {
    url.protocol = "wss:";
  } else if (url.protocol === "http:") {
    url.protocol = "ws:";
  }

  if (queryParams) {
    Object.entries(queryParams).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }

  return url.toString();
}

setApiBaseUrl(import.meta.env.VITE_API_BASE);
ensureAxiosInterceptors();

export default axios;
export * from "axios";

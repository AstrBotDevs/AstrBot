import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//;

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

export function normalizeConfiguredApiBaseUrl(baseUrl: string | null | undefined): string {
  const cleaned = normalizeBaseUrl(baseUrl);
  if (!cleaned || cleaned.startsWith("/")) return cleaned;
  const hasScheme = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(cleaned);
  const isHostWithPort = /^[a-zA-Z\d.-]+:\d+(?:[/?#]|$)/.test(cleaned);
  if (hasScheme && !isHostWithPort) return cleaned;
  return `https://${cleaned}`;
}

export function getApiBaseUrlValidationError(baseUrl: string | null | undefined): string {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);

  if (!normalizedBaseUrl) {
    return "";
  }

  if (normalizedBaseUrl.startsWith("/") && !normalizedBaseUrl.startsWith("//")) {
    return normalizedBaseUrl.includes("\\") ? "API Base URL must use forward slashes" : "";
  }

  try {
    const parsedUrl = new URL(normalizedBaseUrl);
    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      return "API Base URL must use http:// or https://";
    }
    if (!/^https?:\/\//i.test(normalizedBaseUrl)) {
      return "API Base URL must be a valid absolute URL";
    }
  } catch {
    return "API Base URL must be a valid absolute URL";
  }

  return "";
}

export function getApiBaseUrl(): string {
  return normalizeBaseUrl(service.defaults.baseURL);
}

export function setApiBaseUrl(baseUrl: string | null | undefined): string {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);
  service.defaults.baseURL = normalizedBaseUrl;
  return normalizedBaseUrl;
}

export function resolveApiUrl(path: string, baseUrl: string | null | undefined = getApiBaseUrl()): string {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
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
  return new URL(path.replace(/^\/+/, ""), window.location.origin + cleanBase).toString();
}

export function resolveWebSocketUrl(path: string, queryParams?: Record<string, string>): string {
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

const service = axios.create({
  baseURL: normalizeBaseUrl(import.meta.env.VITE_API_BASE),
  timeout: 10000,
});

export const apiV1Client = axios.create({ baseURL: "/api/v1" });

/** Return the canonical API path only for the configured dashboard backend. */
export function getApiRequestPath(requestUrl: string | URL): string | null {
  try {
    const target = new URL(requestUrl, window.location.href);
    const apiRoot = new URL(resolveApiUrl("/api/"), window.location.href);
    const prefix = apiRoot.pathname.replace(/\/+$/, "");
    if (target.origin !== apiRoot.origin) return null;
    if (target.pathname !== prefix && !target.pathname.startsWith(prefix + "/")) return null;
    return "/api" + target.pathname.slice(prefix.length);
  } catch {
    return null;
  }
}

function normalizeAxiosError(error: AxiosError) {
  if (error.response?.status === 401) {
    const requestPath = getApiRequestPath(axios.getUri(error.config ?? {})) ?? "";
    const data = error.response.data as { data?: { totp_required?: boolean } } | undefined;
    const isAuthChallenge =
      [
        "/api/auth/login",
        "/api/auth/setup",
        "/api/auth/setup-status",
        "/api/v1/auth/login",
        "/api/v1/auth/setup",
        "/api/v1/auth/setup-status",
      ].includes(requestPath) || Boolean(data?.data?.totp_required);

    if (requestPath.startsWith("/api/") && !isAuthChallenge) {
      for (const key of [
        "user",
        "token",
        "change_pwd_hint",
        "md5_pwd_hint",
        "legacy_pwd_hint",
        "password_upgrade_required",
      ]) {
        localStorage.removeItem(key);
      }
      if (!window.location.hash.startsWith("#/auth/login")) {
        window.location.hash = "/auth/login";
      }
    }
  }
  if (error.response?.status === 429) {
    const data = error.response.data as { message?: string } | undefined;
    if (data?.message) return Promise.reject(data.message);
  }
  return Promise.reject(error);
}

for (const instance of [service, apiV1Client]) {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    if (instance === apiV1Client) {
      config.baseURL = resolveApiUrl("/api/v1");
    } else if (typeof config.url === "string" && /^\/api(?:\/|$)/.test(config.url)) {
      // Generated clients may provide an empty base URL; the selected backend still applies.
      config.baseURL = service.defaults.baseURL;
    }

    const normalizedBaseUrl = normalizeBaseUrl(config.baseURL ?? service.defaults.baseURL);
    if (typeof config.url === "string") {
      config.url = normalizePathForBase(config.url, normalizedBaseUrl);
    }
    if (getApiRequestPath(axios.getUri(config)) === null) return config;

    const token = localStorage.getItem("token");
    if (token && !config.headers.has("Authorization")) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    const locale = localStorage.getItem("astrbot-locale");
    if (locale && !config.headers.has("Accept-Language")) {
      config.headers.set("Accept-Language", locale);
    }
    return config;
  });
  instance.interceptors.response.use((response) => response, normalizeAxiosError);
}

export { axios as axiosStatic };
export default service;
export * from "axios";

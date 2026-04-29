import axios, { type InternalAxiosRequestConfig } from "axios";

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

export function normalizeConfiguredApiBaseUrl(
  baseUrl: string | null | undefined,
): string {
  const cleaned = normalizeBaseUrl(baseUrl);
  // Prepend https:// if it doesn't already have a protocol
  if (cleaned && !/^https?:\/\//i.test(cleaned)) {
    return `https://${cleaned}`;
  }
  return cleaned;
}

export function getApiBaseUrlValidationError(
  baseUrl: string | null | undefined,
): string {
  const normalizedBaseUrl = normalizeConfiguredApiBaseUrl(baseUrl);

  if (!normalizedBaseUrl) {
    return "";
  }

  try {
    const parsedUrl = new URL(normalizedBaseUrl);
    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      return "API Base URL must use http:// or https://";
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

export function resolveApiUrl(
  path: string,
  baseUrl: string | null | undefined = getApiBaseUrl(),
): string {
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

const service = axios.create({
  baseURL: normalizeBaseUrl(import.meta.env.VITE_API_BASE),
  timeout: 10000,
});

service.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const normalizedBaseUrl = normalizeBaseUrl(
    config.baseURL ?? service.defaults.baseURL,
  );

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

export default service;
export * from "axios";

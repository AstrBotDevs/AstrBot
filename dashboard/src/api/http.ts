import httpClient, { apiV1Client, axiosStatic, getApiBaseUrl, getApiRequestPath, resolveApiUrl } from "@/utils/request";

export { apiV1Client, httpClient };

// Generated clients require AxiosStatic, but dispatch must retain the selected
// backend and the configured instance's request/response interceptors.
export const openApiAxios = new Proxy(axiosStatic, {
  apply(_target, _thisArg, args) {
    return Reflect.apply(httpClient, httpClient, args);
  },
});

let configured = false;
let originalFetch: typeof window.fetch | null = null;

export function fetchWithAuth(input: RequestInfo | URL, init?: RequestInit) {
  const fetchImpl = originalFetch ?? window.fetch.bind(window);
  let resolvedInput = input;
  let requestUrl: URL;
  try {
    requestUrl = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (getApiBaseUrl() && requestUrl.origin === window.location.origin && /^\/api(?:\/|$)/.test(requestUrl.pathname)) {
      const targetUrl = resolveApiUrl(requestUrl.pathname + requestUrl.search);
      requestUrl = new URL(targetUrl, window.location.href);
      resolvedInput = input instanceof Request ? new Request(requestUrl.href, input) : targetUrl;
    }
  } catch {
    return fetchImpl(input, init);
  }

  // Only the configured dashboard API receives dashboard credentials.
  if (getApiRequestPath(requestUrl.href) === null) {
    return fetchImpl(resolvedInput, init);
  }

  const requestHeaders = resolvedInput instanceof Request ? resolvedInput.headers : undefined;
  const headers = new Headers(init?.headers ?? requestHeaders);
  const token = localStorage.getItem("token");
  const locale = localStorage.getItem("astrbot-locale");
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (locale && !headers.has("Accept-Language")) {
    headers.set("Accept-Language", locale);
  }
  return fetchImpl(resolvedInput, { ...init, headers });
}

export function setupHttpClient() {
  if (configured) return;
  originalFetch = window.fetch.bind(window);
  window.fetch = fetchWithAuth;
  configured = true;
}

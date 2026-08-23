import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiV1Client, fetchWithAuth, setupHttpClient } from '@/api/http';

describe('http client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('passes through fetch when no token or locale is stored', async () => {
    const fetchMock = vi.fn(async () => new Response('ok'));
    vi.stubGlobal('fetch', fetchMock);
    await fetchWithAuth('/ping');
    expect(fetchMock).toHaveBeenCalled();
  });

  it('injects auth and locale headers', async () => {
    localStorage.setItem('token', 'tok');
    localStorage.setItem('astrbot-locale', 'zh-CN');
    const fetchMock = vi.fn(async () => new Response('ok'));
    vi.stubGlobal('fetch', fetchMock);
    await fetchWithAuth('/api/v1/ping');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer tok');
    expect(headers.get('Accept-Language')).toBe('zh-CN');
  });

  it('normalizes 401 and 429 axios errors', async () => {
    setupHttpClient();
    setupHttpClient();
    apiV1Client.defaults.adapter = async (config) => {
      const url = String(config.url || '');
      if (url.includes('rate')) {
        const error = {
          config,
          isAxiosError: true,
          response: {
            status: 429,
            data: { message: 'slow down' },
            headers: {},
            statusText: 'Too Many Requests',
            config,
          },
        };
        return Promise.reject(error);
      }
      const error = {
        config: { ...config, url: '/api/v1/plugins', baseURL: '' },
        isAxiosError: true,
        response: {
          status: 401,
          data: {},
          headers: {},
          statusText: 'Unauthorized',
          config: { ...config, url: '/api/v1/plugins', baseURL: '' },
        },
      };
      return Promise.reject(error);
    };

    window.location.hash = '#/dashboard';
    localStorage.setItem('token', 'old');
    await expect(apiV1Client.get('/gone')).rejects.toBeTruthy();
    await expect(apiV1Client.get('/rate')).rejects.toThrow(/slow down/);
  });

  it('sets headers on plain objects and passes successful responses through', async () => {
    setupHttpClient();
    localStorage.setItem('token', 'abc');
    localStorage.setItem('astrbot-locale', 'zh-CN');
    const handlers = (
      apiV1Client.interceptors.request as unknown as {
        handlers: Array<{
          fulfilled: (config: { headers: Record<string, string> }) => {
            headers: Record<string, string>;
          };
        }>;
      }
    ).handlers;
    const config = { headers: {} as Record<string, string> };
    const next = handlers[0]?.fulfilled(config);
    expect(next?.headers.Authorization).toBe('Bearer abc');
    expect(next?.headers['Accept-Language']).toBe('zh-CN');

    apiV1Client.defaults.adapter = async (requestConfig) => ({
      data: { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: requestConfig,
    });
    const response = await apiV1Client.get('/healthy');
    expect(response.data).toEqual({ ok: true });
  });

  it('ignores unparsable 401 request URLs and 429 responses without messages', async () => {
    setupHttpClient();
    apiV1Client.defaults.adapter = async (config) => {
      const url = String(config.url || '');
      if (url.includes('rate')) {
        return Promise.reject({
          config,
          isAxiosError: true,
          response: {
            status: 429,
            data: {},
            headers: {},
            statusText: 'Too Many Requests',
            config,
          },
        });
      }
      return Promise.reject({
        config: { ...config, url: 'http://[', baseURL: '' },
        isAxiosError: true,
        response: {
          status: 401,
          data: {},
          headers: {},
          statusText: 'Unauthorized',
          config: { ...config, url: 'http://[', baseURL: '' },
        },
      });
    };
    await expect(apiV1Client.get('/broken')).rejects.toBeTruthy();
    await expect(apiV1Client.get('/rate')).rejects.toBeTruthy();
  });
});

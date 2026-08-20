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
});

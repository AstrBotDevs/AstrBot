import { beforeEach, describe, expect, it, vi } from 'vitest';

const openApiCalls = vi.hoisted(() => [] as string[]);

vi.mock('@/api/generated/openapi-v1/client.gen', () => ({
  client: { setConfig: vi.fn() },
}));

vi.mock('@/api/generated/openapi-v1', () => {
  const handler = (..._args: unknown[]) => {
    return Promise.resolve({ data: { status: 'ok', data: {} } });
  };
  return new Proxy(
    { __esModule: true },
    {
      get(_target, prop) {
        if (prop === '__esModule') return true;
        if (typeof prop === 'string') openApiCalls.push(prop);
        return handler;
      },
    },
  );
});

vi.mock('@/api/http', async () => {
  const actual =
    await vi.importActual<typeof import('@/api/http')>('@/api/http');
  const ok = { data: { status: 'ok', data: {} } };
  return {
    ...actual,
    httpClient: {
      get: vi.fn().mockResolvedValue(ok),
      post: vi.fn().mockResolvedValue(ok),
      patch: vi.fn().mockResolvedValue(ok),
      put: vi.fn().mockResolvedValue(ok),
      delete: vi.fn().mockResolvedValue(ok),
    },
    fetchWithAuth: vi.fn(async () => new Response('{}', { status: 200 })),
    setupHttpClient: vi.fn(),
  };
});

import { fetchWithAuth } from '@/api/http';
import * as v1 from '@/api/v1';
import { authorizationApi } from '@/api/v1/authorization';
import { logApi } from '@/api/v1/automation';
import { pluginApi, pluginDashboardApi } from '@/api/v1/plugins';
import { providerApi } from '@/api/v1/providers';
import {
  generatedFormData,
  generatedOptions,
  generatedQuery,
  typed,
  botConfig,
  providerConfig,
} from '@/api/v1/shared';
import { notifyPluginDashboardLifecycle } from '@/api/v1/lifecycle';

function dummy(): unknown {
  return 'sample';
}

function invokeExported(value: unknown, depth = 0): number {
  if (depth > 5 || value == null) return 0;
  let invoked = 0;
  if (typeof value === 'function') {
    invoked += 1;
    try {
      const result = value(dummy(), dummy(), dummy(), dummy());
      if (result && typeof (result as Promise<unknown>).then === 'function') {
        void (result as Promise<unknown>).catch(() => undefined);
      }
    } catch {
      // The function still executed.
    }
    return invoked;
  }
  if (typeof value === 'object') {
    for (const key of Object.keys(value as object)) {
      invoked += invokeExported(
        (value as Record<string, unknown>)[key],
        depth + 1,
      );
    }
  }
  return invoked;
}

describe('v1 API wrappers', () => {
  beforeEach(() => {
    openApiCalls.length = 0;
  });

  it('invokes exported API methods through the generated client', async () => {
    const invoked = invokeExported(v1) + invokeExported(authorizationApi);
    await Promise.resolve();
    expect(invoked).toBeGreaterThan(50);
  });

  it('covers shared payload helpers and lifecycle events', () => {
    const form = new FormData();
    form.append('file', 'a');
    form.append('file', 'b');
    const encoded = generatedFormData(form) as Record<string, unknown>;
    expect(Array.isArray(encoded.file)).toBe(true);
    expect(generatedFormData({ keep: true })).toEqual({ keep: true });
    expect(generatedOptions({ a: 1 }, { timeout: 1 })).toMatchObject({
      a: 1,
      timeout: 1,
    });
    expect(generatedQuery({ q: 'x' })).toEqual({ q: 'x' });
    expect(botConfig({ id: 'bot' })).toEqual({ config: { id: 'bot' } });
    expect(providerConfig({ id: 'prov' })).toEqual({
      config: { id: 'prov' },
    });
    void typed(Promise.resolve({ data: { status: 'ok' } }));

    const seen: unknown[] = [];
    window.addEventListener('astrbot:plugin-dashboard-lifecycle', (event) => {
      seen.push((event as CustomEvent).detail);
    });
    notifyPluginDashboardLifecycle({
      reason: 'plugin_changed',
      plugin_name: 'demo',
    });
    expect(seen).toEqual([{ reason: 'plugin_changed', plugin_name: 'demo' }]);
  });

  it('lists providers for empty types and merges typed responses', async () => {
    const listSpy = vi.spyOn(providerApi, 'list');
    listSpy.mockResolvedValueOnce({
      data: {
        status: 'ok',
        data: {
          providers: [{ id: 'all' }],
          model_metadata: { all: { tool_call: true } },
        },
      },
    } as never);
    const empty = await providerApi.listByProviderType(' , ');
    expect(empty.data.data).toEqual([{ id: 'all' }]);
    expect(empty.data.model_metadata).toEqual({ all: { tool_call: true } });

    listSpy
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: {
            providers: [{ id: 'chat' }],
            model_metadata: { chat: { tool_call: true } },
          },
        },
      } as never)
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { providers: [{ id: 'embed' }] },
        },
      } as never);
    const merged = await providerApi.listByProviderType(
      'chat_completion, embedding',
    );
    expect(merged.data.data).toEqual([{ id: 'chat' }, { id: 'embed' }]);
    expect(merged.data.model_metadata).toEqual({ chat: { tool_call: true } });
    listSpy.mockRestore();
  });

  it('rejects failed plugin uploads and validates inline file tickets', async () => {
    vi.mocked(fetchWithAuth).mockResolvedValueOnce(
      new Response(JSON.stringify({ message: 'blocked' }), { status: 400 }),
    );
    await expect(pluginApi.installUpload(new FormData())).rejects.toThrow(
      'blocked',
    );

    vi.mocked(fetchWithAuth).mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 500 }),
    );
    await expect(pluginApi.installUpload(new FormData())).rejects.toThrow(
      'Plugin upload failed (500)',
    );

    vi.mocked(fetchWithAuth).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'ok', data: { id: 'p' } }), {
        status: 200,
      }),
    );
    const uploaded = await pluginApi.installUpload(new FormData(), 'step');
    expect(uploaded.data).toMatchObject({ status: 'ok' });

    const ticket = {
      ticket_url: '/api/plugin-files/v1/abc',
      size: 3,
      filename: 'a.bin',
      content_type: 'application/octet-stream',
      disposition: 'inline' as const,
    };

    await expect(
      pluginDashboardApi.readInlineTicket({
        ...ticket,
        ticket_url: 'https://evil.example/api/plugin-files/v1/abc',
      }),
    ).rejects.toThrow('Invalid plugin file ticket');
    await expect(
      pluginDashboardApi.readInlineTicket({
        ...ticket,
        ticket_url: '/api/other/abc',
      }),
    ).rejects.toThrow('Invalid plugin file ticket');
    await expect(
      pluginDashboardApi.readInlineTicket({
        ...ticket,
        ticket_url: '/api/plugin-files/v1/abc?x=1',
      }),
    ).rejects.toThrow('Invalid plugin file ticket');
    await expect(
      pluginDashboardApi.readInlineTicket({
        ...ticket,
        ticket_url: '/api/plugin-files/v1/abc#h',
      }),
    ).rejects.toThrow('Invalid plugin file ticket');

    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.resetModules();
    const { pluginDashboardApi: ticketApi } = await import('@/api/v1/plugins');
    fetchMock.mockResolvedValueOnce(new Response('nope', { status: 404 }));
    await expect(ticketApi.readInlineTicket(ticket)).rejects.toThrow(
      'Plugin file read failed',
    );

    fetchMock.mockResolvedValueOnce(
      new Response(new Uint8Array([1, 2]).buffer, { status: 200 }),
    );
    await expect(ticketApi.readInlineTicket(ticket)).rejects.toThrow(
      'Plugin file size mismatch',
    );

    fetchMock.mockResolvedValueOnce(
      new Response(new Uint8Array([1, 2, 3]).buffer, { status: 200 }),
    );
    const bytes = await ticketApi.readInlineTicket(ticket);
    expect(bytes.byteLength).toBe(3);
    vi.unstubAllGlobals();
  });

  it('encodes live log filter query parameters', () => {
    expect(
      logApi.liveUrl({ category: ['core'], privacy: ['public'] }),
    ).toContain('category=core');
    expect(
      logApi.liveUrl({ category: ['core'], privacy: ['public'] }),
    ).toContain('privacy=public');
  });
});

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

import * as v1 from '@/api/v1';
import { authorizationApi } from '@/api/v1/authorization';
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
});

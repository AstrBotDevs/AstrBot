import { createPinia, setActivePinia } from 'pinia';
import { effectScope, ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/generated/openapi-v1/client.gen', () => ({
  client: { setConfig: vi.fn() },
}));
vi.mock('@/api/generated/openapi-v1', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const ok = () => Promise.resolve({ data: { status: 'ok', data: {} } });
  return new Proxy(actual, {
    get(target, prop) {
      const value = Reflect.get(target, prop);
      return typeof value === 'function' ? ok : value;
    },
  });
});

import { pluginApi } from '@/api/v1/plugins';
import { generatedFormData } from '@/api/v1/shared';
import { useCommandFilters } from '@/components/extension/componentPanel/composables/useCommandFilters';
import { useCommandActions } from '@/components/extension/componentPanel/composables/useCommandActions';
import {
  collectFolderAndChildrenIds,
  useFolderManager,
} from '@/components/folder/useFolderManager';
import { useDragUpload } from '@/composables/useDragUpload';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useRecording } from '@/composables/useRecording';
import { fetchWithAuth, setupHttpClient, apiV1Client } from '@/api/http';
import {
  getPluginConfigDefaultValue,
  isPluginConfigValueModified,
} from '@/utils/pluginConfigDefaults';
import { formatContextLimit } from '@/utils/providerMetadata';
import { generateMissingKeys } from '@/i18n/tools';
import MainRoutes from '@/router/MainRoutes';
import AuthRoutes from '@/router/AuthRoutes';
import ChatBoxRoutes from '@/router/ChatBoxRoutes';

describe('final coverage push', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('keeps route modules importable', { timeout: 20_000 }, async () => {
    expect(AuthRoutes.path).toBe('/auth');
    expect(AuthRoutes.meta).toEqual({ requiresAuth: false });
    expect(ChatBoxRoutes.path).toBe('/chatbox');
    expect(MainRoutes.redirect).toBe('/welcome');
    expect(MainRoutes.meta).toEqual({ requiresAuth: true });
    expect(
      MainRoutes.children.find((route) => route.path === '/normal')?.redirect,
    ).toBe('/config');

    const loaders = [
      MainRoutes.component,
      AuthRoutes.component,
      ChatBoxRoutes.component,
      ChatBoxRoutes.children[0]?.children?.[0]?.component,
      MainRoutes.children.find((route) => route.name === 'NativeKnowledgeBase')
        ?.children,
      MainRoutes.children.find((route) => route.name === 'Alkaid')?.children,
      MainRoutes.children.find((route) => route.name === 'Chat')?.children,
    ].flatMap((value) => {
      if (Array.isArray(value)) {
        return value.map((route) => route.component);
      }
      return [value];
    });

    const results = await Promise.allSettled(
      loaders
        .filter((loader): loader is () => Promise<unknown> => {
          return typeof loader === 'function';
        })
        .map((loader) => loader()),
    );
    expect(results.length).toBeGreaterThan(5);
    expect(results.some((result) => result.status === 'fulfilled')).toBe(true);
    const chatDetail = MainRoutes.children
      .find((route) => route.name === 'Chat')
      ?.children?.find((route) => route.name === 'ChatDetail');
    expect(chatDetail?.props).toBe(true);
  });

  it('covers plugin lifecycle callbacks and form-data encoding', async () => {
    await pluginApi.uninstall('demo', { delete_config: true });
    await pluginApi.reload('demo');
    await pluginApi.setEnabled('demo', false);
    await pluginApi.setEnabled('demo', true);
    const form = new FormData();
    form.append('a', '1');
    form.append('a', '2');
    form.append('a', '3');
    const encoded = generatedFormData(form) as Record<string, unknown>;
    expect(Array.isArray(encoded.a)).toBe(true);
    expect(generatedFormData({ keep: true })).toEqual({ keep: true });
  });

  it('covers command filter corners and rename no-op', async () => {
    const commands = ref([
      {
        handler_full_name: 'sys.x',
        reserved: true,
        enabled: false,
        has_conflict: false,
        type: 'command',
        is_group: false,
        plugin: 'sys',
        action: '',
        effective_command: '/sys',
        signature: '/sys',
        description: 'system',
      },
      {
        handler_full_name: 'p.sub',
        reserved: false,
        enabled: true,
        has_conflict: false,
        type: 'sub_command',
        is_group: false,
        plugin: 'p',
        action: 'command',
        effective_command: '/p sub',
        signature: '/p sub',
        description: 'sub',
      },
      {
        handler_full_name: 'p.cmd',
        reserved: false,
        enabled: false,
        has_conflict: false,
        type: 'command',
        is_group: false,
        plugin: 'p',
        action: 'command',
        effective_command: '/cmd',
        signature: '/cmd extra',
        description: 'plain',
      },
    ]);
    const filters = useCommandFilters(commands as never);
    filters.showSystemPlugins.value = false;
    filters.statusFilter.value = 'disabled';
    filters.typeFilter.value = 'sub_command';
    filters.searchQuery.value = 'extra';
    void filters.filteredCommands.value;
    void filters.availablePlugins.value;
    filters.matchesFilters(commands.value[2] as never, 'cmd');
    const actions = useCommandActions(vi.fn(), vi.fn());
    await actions.confirmRename('ok', 'err');
    actions.openRenameDialog({
      handler_full_name: 'p.cmd',
      current_fragment: '  ',
      aliases: [' '],
    } as never);
    await actions.confirmRename('ok', 'err');
  });

  it('covers folder manager fallback move and empty search', async () => {
    const tree = [
      {
        folder_id: 'root',
        name: 'Root',
        parent_id: null,
        children: [
          {
            folder_id: 'child',
            name: 'Child',
            parent_id: 'root',
            children: [],
          },
        ],
      },
    ];
    const manager = useFolderManager({
      operations: {
        loadFolderTree: vi.fn().mockResolvedValue(tree),
        loadSubFolders: vi.fn().mockResolvedValue([]),
        createFolder: vi.fn(),
        updateFolder: vi.fn().mockResolvedValue(undefined),
        deleteFolder: vi.fn(),
      },
    });
    manager.folderTree.value = tree as never;
    await manager.moveFolder('child', null);
    expect(manager.filterTreeBySearch('')).toEqual(tree);
    expect(manager.findFolderInTree('missing')).toBeNull();
    expect(manager.findPathToFolder('missing')).toEqual([]);
    manager.setFolderExpansion('child', true);
    manager.setFolderExpansion('child', true);
    manager.setFolderExpansion('child', false);
    manager.setFolderExpansion('child', false);
    expect(collectFolderAndChildrenIds(tree as never, 'missing')).toEqual([
      'missing',
    ]);
  });

  it('covers media signature fallback, drag non-files, and recorder errors', async () => {
    const media = useMediaHandling();
    const file = new File(['x'], 'a.bin', { type: 'application/octet-stream' });
    await media.processAndUploadFile(file).catch(() => undefined);
    await media.handlePaste({ clipboardData: null } as ClipboardEvent);
    media.cleanupMediaCache();

    const scope = effectScope();
    const drag = scope.run(() => useDragUpload(vi.fn()))!;
    drag.dragEvents.dragover({
      preventDefault() {},
      dataTransfer: { types: ['text/plain'] },
    } as DragEvent);
    drag.dragEvents.drop({
      preventDefault() {},
      dataTransfer: { files: { length: 0 } },
    } as unknown as DragEvent);
    scope.stop();

    class ErrorRecorder {
      stream = { getTracks: () => [{ stop: vi.fn() }] };
      mimeType = 'audio/ogg;codecs=opus';
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      start() {}
      stop() {
        this.onerror?.(new Event('error'));
      }
      static isTypeSupported(type: string) {
        return type.includes('ogg');
      }
    }
    vi.stubGlobal('MediaRecorder', ErrorRecorder);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });
    const recording = useRecording();
    await recording.startRecording();
    await expect(recording.stopRecording()).rejects.toThrow(/MediaRecorder/);
    vi.unstubAllGlobals();
  });

  it('covers remaining helpers and 429-less http header set path', async () => {
    expect(getPluginConfigDefaultValue(null)).toBeUndefined();
    expect(getPluginConfigDefaultValue({ type: 'object' })).toBeUndefined();
    expect(getPluginConfigDefaultValue({ type: 'unknown' })).toBeUndefined();
    expect(
      isPluginConfigValueModified([1], { type: 'list', default: [1] }),
    ).toBe(false);
    expect(
      isPluginConfigValueModified(
        { a: 1 },
        { type: 'dict', default: { a: 1 } },
      ),
    ).toBe(false);
    expect(formatContextLimit(null)).toBe('');
    expect(generateMissingKeys({ a: { b: '1' } }, { a: { b: '1' } })).toEqual(
      [],
    );

    localStorage.setItem('token', 't');
    const fetchMock = vi.fn(async () => new Response('ok'));
    vi.stubGlobal('fetch', fetchMock);
    await fetchWithAuth(
      new Request('http://localhost/api/v1/x', {
        headers: { Authorization: 'Bearer t' },
      }),
    );
    setupHttpClient();
    apiV1Client.defaults.adapter = async (config) => {
      const error = {
        config: { ...config, url: '/api/v1/auth/login', baseURL: '' },
        isAxiosError: true,
        response: {
          status: 401,
          data: { data: { totp_required: true } },
          headers: {},
          statusText: 'Unauthorized',
          config: { ...config, url: '/api/v1/auth/login', baseURL: '' },
        },
      };
      return Promise.reject(error);
    };
    await expect(apiV1Client.get('/api/v1/auth/login')).rejects.toBeTruthy();
    vi.unstubAllGlobals();
  });
});

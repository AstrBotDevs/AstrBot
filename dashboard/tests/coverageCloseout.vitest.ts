import { createPinia, setActivePinia } from 'pinia';
import { flushPromises } from '@vue/test-utils';
import { defineComponent, ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/router', () => ({
  router: { push: vi.fn(), replace: vi.fn(), beforeEach: vi.fn() },
}));
vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

const api = vi.hoisted(() => {
  const fn = () => vi.fn();
  return {
    chatApi: {
      listSessions: fn(),
      createSession: fn(),
      deleteSession: fn(),
      batchDeleteSessions: fn(),
      updateSession: fn(),
      listProjects: fn(),
      createProject: fn(),
      updateProject: fn(),
      deleteProject: fn(),
      addProjectSession: fn(),
      removeProjectSession: fn(),
      listProjectSessions: fn(),
    },
    configRouteApi: { upsert: fn() },
    personaApi: {
      tree: fn(),
      folders: fn(),
      list: fn(),
      move: fn(),
      updateFolder: fn(),
      createFolder: fn(),
      deleteFolder: fn(),
      delete: fn(),
      reorder: fn(),
    },
    providerApi: {
      schema: fn(),
      createInSource: fn(),
      update: fn(),
    },
    statsApi: { startTime: fn(), version: fn() },
    authApi: { login: fn(), setup: fn(), logout: fn() },
    systemConfigApi: { get: fn() },
    logApi: { liveUrl: () => '/api/v1/log/live' },
    pluginApi: { market: fn() },
    toolApi: {
      list: fn(),
      setEnabled: fn(),
      setParallel: fn(),
      setParallelEnabled: fn(),
    },
    commandApi: { list: fn(), update: fn() },
    fileApi: { getByName: fn(), upload: fn() },
    authorizationApi: { stepUp: fn(), webChatStepUp: fn() },
  };
});

vi.mock('@/api/v1', () => ({
  ...api,
  UPGRADE_RECOVERY_EVENT: 'astrbot-upgrade-recovery',
  UPGRADE_RECOVERY_TOKEN_KEY: 'astrbot-upgrade-recovery-token',
}));
vi.mock('@/api/v1/authorization', () => ({
  authorizationApi: api.authorizationApi,
}));
vi.mock('@/api/http', async () => {
  const actual =
    await vi.importActual<typeof import('@/api/http')>('@/api/http');
  return {
    ...actual,
    fetchWithAuth: vi.fn(async () => new Response('{}')),
  };
});

import { fetchWithAuth } from '@/api/http';
import { useConversations } from '@/composables/useConversations';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useProjects } from '@/composables/useProjects';
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog';
import { useSessions } from '@/composables/useSessions';
import { useCommandActions } from '@/components/extension/componentPanel/composables/useCommandActions';
import { useCommandFilters } from '@/components/extension/componentPanel/composables/useCommandFilters';
import { useComponentData } from '@/components/extension/componentPanel/composables/useComponentData';
import { useToolActions } from '@/components/extension/componentPanel/composables/useToolActions';
import {
  collectFolderAndChildrenIds,
  useFolderManager,
} from '@/components/folder/useFolderManager';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';
import { usePersonaStore } from '@/stores/personaStore';
import { useRouterLoadingStore } from '@/stores/routerLoading';

function sseResponse(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    }),
    { status },
  );
}

describe('coverage closeout', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('covers common store cache hits, market normalization, and SSE branches', async () => {
    api.statsApi.startTime.mockResolvedValue({
      data: { data: { start_time: 42 } },
    });
    api.statsApi.version.mockResolvedValue({
      data: { data: { version: 'v2.0.0', dashboard_version: 'd2' } },
    });
    api.pluginApi.market.mockResolvedValue({
      data: {
        data: {
          broken: null,
          from_platform: {
            platform: ['wechat', 1],
            name: '  ',
            tags: ['ai', 2],
            pinned: 1,
            stars: 'nope',
          },
          from_support: {
            support_platform: ['qq'],
            name: 'Support',
            desc: 'd',
            short_desc: 's',
            repo: 'https://example.com',
            version: '1.0',
            social_link: 'https://x',
            logo: 'l',
            updated_at: 't',
            download_url: 'u',
            display_name: 'D',
            i18n: { 'zh-CN': {} },
            astrbot_version: '4',
            category: 'chat',
          },
        },
      },
    });
    const common = useCommonStore();
    api.pluginApi.market.mockResolvedValueOnce({
      data: { data: null },
    });
    expect(await common.getPluginCollections(true)).toEqual([]);
    await common.fetchStartTime();
    expect(common.getStartTime()).toBe(42);
    await common.fetchAstrBotVersion();
    expect(await common.fetchAstrBotVersion()).toBe('2.0.0');
    const market = await common.getPluginCollections(true);
    expect(market.some((item) => item.name === 'broken')).toBe(true);
    expect(
      market.find((item) => item.name === 'Support')?.support_platforms,
    ).toEqual(['qq']);
    expect(await common.getPluginCollections()).toBe(common.pluginMarketData);
    await common.getPluginCollections(false, 'https://registry.example');
    expect(api.pluginApi.market).toHaveBeenCalledWith({
      force_refresh: undefined,
      custom_registry: 'https://registry.example',
    });

    const randomUUID = crypto.randomUUID;
    // @ts-expect-error exercise the non-crypto fallback
    crypto.randomUUID = undefined;
    localStorage.setItem('token', 'tok');
    vi.mocked(fetchWithAuth).mockResolvedValue(
      sseResponse([
        'comment\n\n',
        'data: \n\n',
        'data: {not-json\n\n',
        'data: "plain"\n\n',
        'data: {"data":"one"}\n\n',
        'data: {"data":"two","uuid":"keep"}\n\n',
      ]),
    );
    common.log_cache_max_len = 1;
    await common.createEventSource();
    await vi.waitFor(() => {
      expect(common.getLogCache().length).toBe(1);
    });
    expect(common.getLogCache()[0]?.uuid).toBe('keep');
    crypto.randomUUID = randomUUID;
    common.closeEventSource();
    localStorage.removeItem('token');

    localStorage.setItem('token', 'tok');
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response('denied', { status: 401 }),
    );
    await common.createEventSource();
    await vi.waitFor(() => {
      expect(common.eventSource).toBeNull();
      expect(common.sse_connected).toBe(false);
    });

    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
    } as Response);
    vi.useFakeTimers();
    await common.createEventSource();
    await flushPromises();
    expect(
      common
        .getLogCache()
        .some((entry) => String(entry.data).includes('retrying')),
    ).toBe(true);
    common.closeEventSource();
    localStorage.removeItem('token');
    await vi.advanceTimersByTimeAsync(1000);
    vi.useRealTimers();

    localStorage.setItem('token', 'tok');
    vi.mocked(fetchWithAuth).mockResolvedValue(
      sseResponse(['data: {"uuid":"done","data":"bye"}\n\n']),
    );
    vi.useFakeTimers();
    await common.createEventSource();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();
    expect(fetchWithAuth).toHaveBeenCalled();
    common.closeEventSource();
    localStorage.removeItem('token');
    vi.useRealTimers();

    localStorage.setItem('token', 'tok');
    let rejectFetch: ((error: Error) => void) | undefined;
    vi.mocked(fetchWithAuth).mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectFetch = reject;
        }),
    );
    await common.createEventSource();
    common.closeEventSource();
    rejectFetch?.(new Error('aborted'));
    await flushPromises();
    localStorage.removeItem('token');
  });

  it('covers persona breadcrumb, expansion, and nested tree lookup', async () => {
    const persona = usePersonaStore();
    expect(persona.currentFolderName).toBe('根目录');
    persona.setFolderExpansion('a', true);
    persona.setFolderExpansion('a', true);
    persona.setFolderExpansion('a', false);
    persona.setFolderExpansion('a', false);
    persona.toggleFolderExpansion('a');
    persona.toggleFolderExpansion('a');
    expect(persona.expandedFolderIds).toEqual([]);
    persona.breadcrumbPath = [
      {
        folder_id: 'x',
        name: '',
        parent_id: null,
        description: null,
        sort_order: 0,
        children: [],
      },
    ];
    expect(persona.currentFolderName).toBe('根目录');
    persona.folderTree = [
      {
        folder_id: 'root',
        name: 'Root',
        parent_id: null,
        description: null,
        sort_order: 0,
        children: [
          {
            folder_id: 'child',
            name: 'Child',
            parent_id: 'root',
            description: null,
            sort_order: 0,
            children: [],
          },
        ],
      },
    ];
    expect(persona.findFolderInTree('child')?.name).toBe('Child');
    expect(persona.findFolderInTree('missing')).toBeNull();
    api.personaApi.folders.mockResolvedValue({
      data: { status: 'error', data: null },
    });
    api.personaApi.list.mockResolvedValue({
      data: { status: 'error', data: null },
    });
    await persona.navigateToFolder(null);
    expect(persona.currentFolders).toEqual([]);
    expect(persona.breadcrumbPath).toEqual([]);
  });

  it('covers provider dialog schema, duplicate models, and add-without-source', async () => {
    const showMessage = vi.fn();
    const dialog = useProviderModelConfigDialog({
      selectedProviderSource: ref({}),
      configSchema: ref({}),
      buildModelProviderConfig: (id) => ({ id, model: id }),
      modelAlreadyConfigured: () => true,
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage,
    });
    expect(dialog.providerModelConfigSchema.value).toEqual({});
    dialog.openModelAddDialog('gpt');
    expect(showMessage).toHaveBeenCalledWith(
      'models.manualModelExists',
      'error',
    );
    dialog.openProviderEdit({
      id: 'p1',
      provider_source_id: 'src',
      reasoning: true,
    });
    expect(dialog.providerEditData.value).not.toHaveProperty('reasoning');
    expect(dialog.providerEditDialogTitle.value).toContain('p1');

    const adder = useProviderModelConfigDialog({
      selectedProviderSource: ref({}),
      configSchema: ref({ provider: { items: { id: {}, model: {} } } }),
      buildModelProviderConfig: (id) => ({ id, model: id }),
      modelAlreadyConfigured: () => false,
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage,
    });
    adder.openModelAddDialog('m1');
    expect(adder.providerEditDialogTitle.value).toContain('m1');
    await adder.saveEditedProvider();
    expect(showMessage).toHaveBeenCalledWith(
      'providerSources.selectHint',
      'error',
    );

    const cancellable = useProviderModelConfigDialog({
      selectedProviderSource: ref({ id: 'src' }),
      configSchema: ref({ provider: { items: { id: {}, model: {} } } }),
      buildModelProviderConfig: (id) => ({
        id,
        model: id,
        provider_source_id: 'src',
      }),
      modelAlreadyConfigured: () => false,
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage,
      requestStepUp: async () => null,
    });
    cancellable.openModelAddDialog('m2');
    await cancellable.saveEditedProvider();
    api.providerApi.update.mockResolvedValue({
      data: { status: 'error' },
    });
    cancellable.openProviderEdit({ id: 'p2', model: 'm' });
    await cancellable.saveEditedProvider();
  });

  it('covers dashboard step-up token failures, expiry, and busy submit', async () => {
    const Harness = defineComponent({
      setup() {
        return { stepUp: useDashboardStepUp() };
      },
      template: '<div />',
    });
    const wrapper = mountWithVuetify(Harness);
    const stepUp = (
      wrapper.vm as { stepUp: ReturnType<typeof useDashboardStepUp> }
    ).stepUp;

    const pending = stepUp.requestStepUp({
      action: 'a',
      resourceType: 'r',
      resourceId: '1',
    });
    api.authorizationApi.stepUp.mockResolvedValue({
      data: { data: { token: '' } },
    });
    await stepUp.submitStepUp({ password: 'p' });
    expect(stepUp.errorMessage.value).toContain('Unable to issue');
    expect(await stepUp.requestWebChatStepUp('busy')).toBeNull();
    stepUp.cancelStepUp();
    await pending;

    const webChat = stepUp.requestWebChatStepUp('sess');
    expect(await stepUp.requestWebChatStepUp('again')).toBeNull();
    api.authorizationApi.webChatStepUp.mockResolvedValue({
      data: { data: { tokens: null } },
    });
    await stepUp.submitStepUp({ password: 'p' });
    expect(stepUp.errorMessage.value).toContain('Unable to issue');
    api.authorizationApi.webChatStepUp.mockResolvedValue({
      data: { data: { tokens: { '': '', count: 1 } } },
    });
    await stepUp.submitStepUp({ password: 'p' });
    expect(stepUp.errorMessage.value).toContain('Unable to issue');

    vi.useFakeTimers();
    api.authorizationApi.webChatStepUp.mockResolvedValue({
      data: {
        data: { tokens: { 'webchat.tool_run': 'tok' }, expires_in: 'bad' },
      },
    });
    await stepUp.submitStepUp({ password: 'p' });
    await expect(webChat).resolves.toEqual({ 'webchat.tool_run': 'tok' });
    expect(stepUp.webChatExpiresAt.value).toBeGreaterThan(Date.now());
    await vi.advanceTimersByTimeAsync(300_000);
    expect(stepUp.webChatExpiresAt.value).toBeNull();
    vi.useRealTimers();

    const issued = stepUp.requestStepUp({
      action: 'b',
      resourceType: 'r',
      resourceId: '2',
    });
    let resolveStep: ((value: unknown) => void) | undefined;
    api.authorizationApi.stepUp.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStep = resolve;
        }),
    );
    const first = stepUp.submitStepUp({ password: 'p' });
    await Promise.resolve();
    await stepUp.submitStepUp({ password: 'p' });
    resolveStep?.({ data: { data: { token: 'ok' } } });
    await first;
    await expect(issued).resolves.toBe('ok');
    wrapper.unmount();
  });

  it('covers media signature fallback, misses, paste, and revoke', async () => {
    api.fileApi.upload.mockResolvedValue({
      data: {
        data: { attachment_id: 'a1', filename: 'a.bin', type: 'file' },
      },
    });
    const subtle = crypto.subtle;
    Object.defineProperty(crypto, 'subtle', {
      configurable: true,
      value: undefined,
    });
    const media = useMediaHandling();
    const file = new File(['x'], 'a.bin', { type: 'application/octet-stream' });
    const staged = await media.processAndUploadFile(file);
    expect(staged?.signature).toMatch(/^meta:/);
    expect(await media.processAndUploadFile(file)).toBeUndefined();
    Object.defineProperty(crypto, 'subtle', {
      configurable: true,
      value: subtle,
    });
    api.fileApi.upload.mockResolvedValue({
      data: {
        data: { attachment_id: 'h1', filename: 'c.bin', type: 'file' },
      },
    });
    const hashed = await media.processAndUploadFile(
      new File(['z'], 'c.bin', { type: 'application/octet-stream' }),
    );
    expect(hashed?.signature).toMatch(/^sha256:/);

    api.fileApi.upload.mockRejectedValue(new Error('fail'));
    expect(
      await media.processAndUploadFile(new File(['y'], 'b.bin')),
    ).toBeUndefined();

    media.stagedFiles.value = [
      {
        attachment_id: 'i1',
        filename: 'a.png',
        original_name: 'a.png',
        url: 'blob:image',
        type: 'image',
      },
      {
        attachment_id: 'f1',
        filename: 'a.txt',
        original_name: 'a.txt',
        url: 'blob:file',
        type: 'file',
      },
      {
        attachment_id: 'r1',
        filename: 'a.webm',
        original_name: 'a.webm',
        url: 'blob:audio',
        type: 'record',
      },
    ];
    expect(media.stagedImagesUrl.value).toEqual(['blob:image']);
    expect(media.stagedAudioUrl.value).toBe('blob:audio');
    expect(media.stagedNonImageFiles.value).toHaveLength(1);
    media.removeImage(4);
    media.removeFile(0);
    expect(media.stagedFiles.value.some((file) => file.type === 'file')).toBe(
      false,
    );
    api.fileApi.getByName.mockResolvedValue({ data: new Blob(['x']) });
    expect(await media.getMediaFile('preview.png')).toContain('blob:');
    await media.handlePaste({
      clipboardData: {
        items: [{ type: 'image/png', getAsFile: () => null }],
      },
    } as unknown as ClipboardEvent);
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    media.clearStaged();
    media.cleanupMediaCache();
    expect(revoke).toHaveBeenCalled();
    expect(media.stagedImagesUrl.value).toEqual([]);
    expect(media.stagedAudioUrl.value).toBe('');
    expect(media.stagedNonImageFiles.value).toEqual([]);
    revoke.mockRestore();

    api.fileApi.upload.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return {
        data: {
          data: { attachment_id: 'dup', filename: 'p.bin', type: 'file' },
        },
      };
    });
    const pendingFile = new File(['pending-dup'], 'p.bin');
    const first = media.processAndUploadFile(pendingFile);
    await new Promise((resolve) => setTimeout(resolve, 10));
    const second = media.processAndUploadFile(pendingFile);
    expect(await second).toBeUndefined();
    expect(await first).toBeTruthy();
  });

  it('covers conversation lookup, project selection, and session payload guards', async () => {
    api.chatApi.listSessions.mockRejectedValue(null);
    const sessionsProbe = useSessions();
    await sessionsProbe.getSessions();

    const conversations = useConversations();
    conversations.conversations.value = [
      { cid: 'c1', title: 'One', updated_at: 1 },
    ];
    conversations.currCid.value = 'c1';
    expect(conversations.getCurrentConversation.value?.title).toBe('One');
    api.chatApi.listSessions.mockRejectedValue('offline');
    await conversations.getConversations();

    const projects = useProjects();
    api.chatApi.createProject.mockRejectedValue(new Error('fail'));
    expect(await projects.createProject('x')).toBeUndefined();
    projects.selectedProjectId.value = 'p1';
    api.chatApi.deleteProject.mockResolvedValue({ data: { status: 'ok' } });
    api.chatApi.listProjects.mockResolvedValue({
      data: { status: 'ok', data: [] },
    });
    await projects.deleteProject('p1');
    expect(projects.selectedProjectId.value).toBeNull();
    api.chatApi.listProjectSessions.mockResolvedValue({
      data: { status: 'error' },
    });
    expect(await projects.getProjectSessions('p1')).toEqual([]);

    const sessions = useSessions();
    api.chatApi.deleteSession.mockRejectedValue(new Error('fail'));
    await sessions.deleteSession('s1');
    localStorage.setItem('chat.selectedConfigId', 'profile-1');
    api.chatApi.createSession.mockResolvedValue({
      data: { data: { session_id: 's2', platform_id: 'webchat' } },
    });
    api.configRouteApi.upsert.mockRejectedValue(new Error('bind'));
    await sessions.newSession();
    api.chatApi.batchDeleteSessions.mockResolvedValue({
      data: { status: 'ok', data: null },
    });
    await expect(sessions.batchDeleteSessions(['s2'])).rejects.toThrow(
      /Invalid batch delete/,
    );
    sessions.currSessionId.value = 's2';
    api.chatApi.batchDeleteSessions.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          deleted_count: 0,
          failed_count: 1,
          failed_items: [{ session_id: 's2', reason: 'busy' }],
        },
      },
    });
    api.chatApi.listSessions.mockResolvedValue({ data: { data: [] } });
    const result = await sessions.batchDeleteSessions(['s2']);
    expect(result.currentSessionDeleted).toBe(false);
    expect(result.failed_items[0]?.reason).toBe('busy');
  });

  it('covers command, tool, component, and folder remaining branches', async () => {
    const commands = ref([
      {
        command_id: 'p:cmd',
        handler_full_name: 'p.cmd',
        reserved: false,
        enabled: true,
        has_conflict: true,
        type: 'command',
        is_group: false,
        plugin: 'p',
        action: 'command',
        effective_command: '/cmd',
        signature: '/cmd',
        description: 'plain',
      },
      {
        command_id: 'p:group',
        handler_full_name: 'p.group',
        reserved: false,
        enabled: true,
        has_conflict: false,
        type: 'group',
        is_group: true,
        plugin: 'p',
        action: 'command',
        effective_command: '/group',
        sub_commands: [
          {
            command_id: 'p:group.sub',
            handler_full_name: 'p.group.sub',
            reserved: false,
            enabled: true,
            has_conflict: false,
            type: 'sub_command',
            is_group: false,
            plugin: 'p',
            action: 'command',
            effective_command: '/group sub',
            description: 'child',
          },
        ],
      },
    ]);
    const filters = useCommandFilters(commands as never);
    filters.pluginFilter.value = 'other';
    expect(filters.matchesFilters(commands.value[0] as never, '')).toBe(false);
    filters.pluginFilter.value = 'all';
    filters.actionFilter.value = 'other';
    expect(filters.matchesFilters(commands.value[0] as never, '')).toBe(false);
    filters.actionFilter.value = 'all';
    filters.statusFilter.value = 'disabled';
    expect(filters.matchesFilters(commands.value[0] as never, '')).toBe(false);
    filters.statusFilter.value = 'conflict';
    expect(filters.matchesFilters(commands.value[1] as never, '')).toBe(false);
    filters.statusFilter.value = 'all';
    filters.typeFilter.value = 'group';
    expect(filters.matchesFilters(commands.value[0] as never, '')).toBe(false);
    filters.typeFilter.value = 'all';
    filters.searchQuery.value = '';
    filters.toggleGroupExpand(commands.value[1] as never);
    expect(filters.filteredCommands.value.map((cmd) => cmd.command_id)).toEqual(
      expect.arrayContaining(['p:cmd', 'p:group', 'p:group.sub']),
    );
    filters.toggleGroupExpand(commands.value[1] as never);
    expect(filters.isGroupExpanded(commands.value[1] as never)).toBe(false);
    filters.toggleGroupExpand(commands.value[0] as never);

    const toast = vi.fn();
    const actions = useCommandActions(toast, vi.fn());
    expect(
      actions.getTypeInfo('sub_command', {
        group: 'g',
        subCommand: 's',
        command: 'c',
      }).text,
    ).toBe('s');
    expect(
      actions.getStatusInfo({ has_conflict: false, enabled: true } as never, {
        conflict: 'c',
        enabled: 'e',
        disabled: 'd',
      }).text,
    ).toBe('e');
    expect(
      actions.getStatusInfo({ has_conflict: true, enabled: true } as never, {
        conflict: 'c',
        enabled: 'e',
        disabled: 'd',
      }).text,
    ).toBe('c');
    actions.openDetailsDialog(commands.value[0] as never);
    expect(actions.detailsDialog.show).toBe(true);
    api.commandApi.update.mockRejectedValue(new Error('rename-fail'));
    actions.openRenameDialog({
      command_id: 'p:cmd',
      current_fragment: 'cmd',
      aliases: ['c'],
    } as never);
    await actions.confirmRename('ok', 'err');
    expect(toast).toHaveBeenCalledWith('rename-fail', 'error');

    api.toolApi.list.mockResolvedValue({
      data: { status: 'error', message: 'tools-fail' },
    });
    const data = useComponentData();
    await data.fetchTools('err');
    expect(data.snackbar.message).toBe('tools-fail');
    api.toolApi.list.mockRejectedValue(new Error('tools-boom'));
    await data.fetchTools('err');
    expect(data.snackbar.message).toBe('tools-boom');

    const writable = {
      name: 'y',
      readonly: false,
      active: false,
      parallel_eligible: true,
      tool_id: 't',
      parallel_enabled: false,
      parallel_execution_enabled: false,
    };
    const tools = useToolActions(ref([writable] as never), toast);
    api.toolApi.setEnabled.mockRejectedValue(new Error('toggle'));
    await tools.toggleTool(writable as never, 'ro', 'ok', 'err');
    expect(writable.active).toBe(false);
    api.toolApi.setParallel.mockResolvedValue({
      data: { status: 'error', message: 'parallel-status' },
    });
    await tools.toggleToolParallel(writable as never, true, 'err');
    expect(writable.parallel_enabled).toBe(false);
    api.toolApi.setParallel.mockRejectedValue(new Error('parallel'));
    await tools.toggleToolParallel(writable as never, true, 'err');
    expect(writable.parallel_enabled).toBe(false);
    api.toolApi.setParallelEnabled.mockRejectedValue(new Error('exec'));
    await tools.toggleParallelExecution(true, 'err');

    const manager = useFolderManager({
      rootFolderName: 'Root',
      operations: {
        loadFolderTree: vi.fn().mockResolvedValue([]),
        loadSubFolders: vi.fn().mockResolvedValue([]),
        createFolder: vi.fn(),
        updateFolder: vi.fn(),
        deleteFolder: vi.fn(),
      },
    });
    expect(manager.currentFolderName.value).toBe('Root');
    manager.toggleFolderExpansion('child');
    manager.toggleFolderExpansion('child');
    expect(manager.expandedFolderIds.value).toEqual([]);
    const tree = [
      {
        folder_id: 'root',
        name: 'Root',
        parent_id: null,
        children: [
          {
            folder_id: 'mid',
            name: 'Mid',
            parent_id: 'root',
            children: [
              {
                folder_id: 'leaf',
                name: 'Leaf',
                parent_id: 'mid',
                children: [],
              },
            ],
          },
        ],
      },
    ];
    expect(collectFolderAndChildrenIds(tree as never, 'leaf')).toEqual([
      'leaf',
    ]);
  });

  it('covers auth setup non-Error failures and onboarding lookup errors', async () => {
    const auth = useAuthStore();
    api.authApi.setup.mockRejectedValue('nope');
    await expect(auth.setup('u', 'p', 'p')).rejects.toThrow('nope');
    api.authApi.setup.mockResolvedValue({
      data: { status: 'error', message: '' },
    });
    await expect(auth.setup('u', 'p', 'p')).rejects.toThrow();
    api.systemConfigApi.get.mockRejectedValue(new Error('offline'));
    expect(await auth.checkOnboardingCompleted()).toBe(false);
    api.authApi.login.mockResolvedValue({
      data: { status: 'ok', data: { username: 'u', token: 'tok' } },
    });
    api.statsApi.version.mockImplementation(
      async (opts?: { validateStatus?: (status: number) => boolean }) => {
        expect(opts?.validateStatus?.(500)).toBe(true);
        return {
          status: 200,
          data: { data: { version: '1.0.0', dashboard_version: '1.0.0' } },
        };
      },
    );
    api.systemConfigApi.get.mockResolvedValue({
      data: { data: { config: { platform: [{}] } } },
    });
    api.providerApi.schema.mockResolvedValue({
      data: { data: { providers: [{ provider_type: 'chat_completion' }] } },
    });
    await auth.login('u', 'p');
    await auth.finishAuthenticatedSession({
      username: 'u',
      token: 'tok',
      change_pwd_hint: true,
      md5_pwd_hint: false,
    });
  });

  it('restarts the router loading interval when start is called twice', async () => {
    const loading = useRouterLoadingStore();
    vi.useFakeTimers();
    loading.start();
    loading.start();
    await vi.advanceTimersByTimeAsync(50);
    loading.finish();
    await vi.advanceTimersByTimeAsync(300);
    vi.useRealTimers();
    expect(loading.isLoading).toBe(false);
  });
});

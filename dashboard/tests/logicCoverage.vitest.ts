import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, ref } from 'vue';

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
      getSession: fn(),
      stopSession: fn(),
      listProjects: fn(),
      createProject: fn(),
      updateProject: fn(),
      deleteProject: fn(),
      addProjectSession: fn(),
      removeProjectSession: fn(),
      listProjectSessions: fn(),
    },
    toolApi: {
      setEnabled: fn(),
      setParallel: fn(),
      setParallelEnabled: fn(),
    },
    fileApi: {
      getByName: fn(),
      upload: fn(),
    },
    configRouteApi: { upsert: fn() },
    providerApi: {
      schema: fn(),
      setEnabled: fn(),
      test: fn(),
      createInSource: fn(),
      update: fn(),
    },
    personaApi: {
      tree: fn(),
      folders: fn(),
      list: fn(),
      move: fn(),
      updateFolder: fn(),
      createFolder: fn(),
      deleteFolder: fn(),
    },
    pluginApi: { market: fn() },
    statsApi: { startTime: fn(), version: fn(), restart: fn() },
    logApi: { liveUrl: () => '/api/v1/log/live' },
    authApi: {
      login: fn(),
      setup: fn(),
      logout: fn(),
    },
    systemConfigApi: { get: fn() },
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

import { useConversations } from '@/composables/useConversations';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useMediaHandling } from '@/composables/useMediaHandling';
import {
  appendPlain,
  messageBlocks,
  useMessages,
} from '@/composables/useMessages';
import { useProjects } from '@/composables/useProjects';
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog';
import { useProviderSources } from '@/composables/useProviderSources';
import { useRecording } from '@/composables/useRecording';
import { useSessions } from '@/composables/useSessions';
import { useCommandFilters } from '@/components/extension/componentPanel/composables/useCommandFilters';
import { useToolActions } from '@/components/extension/componentPanel/composables/useToolActions';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';
import { usePersonaStore } from '@/stores/personaStore';
import { useRouterLoadingStore } from '@/stores/routerLoading';
import { generateMissingKeys } from '@/i18n/tools';
import { I18nLoader } from '@/i18n/loader';
import { fetchWithAuth } from '@/api/http';
import { restartAstrBot } from '@/utils/restartAstrBot';
import {
  contextLimit,
  formatContextLimit,
  formatTokenCount,
  providerCapabilityBadges,
} from '@/utils/providerMetadata';
import { resolvePluginI18n } from '@/utils/pluginI18n';
import { useCommandActions } from '@/components/extension/componentPanel/composables/useCommandActions';

describe('frontend logic coverage', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('covers session, conversation, and project flows', async () => {
    api.chatApi.listSessions.mockResolvedValue({
      data: {
        data: [
          {
            session_id: 's1',
            display_name: 'one',
            updated_at: '2024-01-01',
            platform_id: 'webchat',
            creator: 'u',
            is_group: 0,
            created_at: '',
          },
        ],
      },
    });
    api.chatApi.createSession.mockResolvedValue({
      data: { data: { session_id: 's2', platform_id: 'webchat' } },
    });
    api.chatApi.deleteSession.mockResolvedValue({ data: { status: 'ok' } });
    api.chatApi.batchDeleteSessions.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          deleted_count: 1,
          failed_count: 0,
          failed_items: [],
        },
      },
    });
    api.chatApi.updateSession.mockResolvedValue({ data: { status: 'ok' } });
    api.chatApi.listProjects.mockResolvedValue({
      data: { status: 'ok', data: [{ project_id: 'p1', title: 'P' }] },
    });
    api.chatApi.createProject.mockResolvedValue({
      data: { status: 'ok', data: { project_id: 'p2' } },
    });
    api.configRouteApi.upsert.mockResolvedValue({ data: { status: 'ok' } });
    localStorage.setItem('chat.selectedConfigId', 'profile-1');

    const sessions = useSessions();
    await sessions.getSessions();
    expect(sessions.getCurrentSession.value).toBeNull();
    sessions.currSessionId.value = 's1';
    expect(sessions.getCurrentSession.value?.session_id).toBe('s1');
    await sessions.newSession();
    await sessions.deleteSession('s2');
    sessions.currSessionId.value = 's1';
    await sessions.batchDeleteSessions(['s1']);
    sessions.showEditTitleDialog('s1', 'old');
    await sessions.saveTitle();
    sessions.updateSessionTitle('s1', 'renamed');
    sessions.newChat(() => undefined);

    const conversations = useConversations(true);
    await conversations.getConversations();
    await conversations.newConversation();
    conversations.showEditTitleDialog('s1', 't');
    conversations.editingTitle.value = 't2';
    conversations.editingCid.value = 's1';
    await conversations.saveTitle();
    conversations.updateConversationTitle('s1', 't3');
    await conversations.deleteConversation('s1');
    conversations.newChat(() => undefined);

    api.chatApi.updateProject.mockResolvedValue({ data: { status: 'ok' } });
    api.chatApi.deleteProject.mockResolvedValue({ data: { status: 'ok' } });
    api.chatApi.addProjectSession.mockResolvedValue({
      data: { status: 'ok' },
    });
    api.chatApi.removeProjectSession.mockResolvedValue({
      data: { status: 'ok' },
    });
    api.chatApi.listProjectSessions.mockResolvedValue({
      data: { status: 'ok', data: [] },
    });
    const projects = useProjects();
    await projects.getProjects();
    await projects.createProject('demo', '📁', 'd');
    await projects.updateProject('p1', 'P2');
    await projects.deleteProject('p1');
    await projects.addSessionToProject('s1', 'p1');
    await projects.removeSessionFromProject('s1');
    await projects.getProjectSessions('p1');
  });

  it('covers media, recording, command filters, and tools', async () => {
    api.fileApi.getByName.mockResolvedValue({ data: new Blob(['x']) });
    api.fileApi.upload.mockResolvedValue({
      data: {
        data: { attachment_id: 'a1', filename: 'a.png', type: 'image' },
      },
    });
    const media = useMediaHandling();
    const file = new File(['img'], 'a.png', { type: 'image/png' });
    await media.processAndUploadImage(file);
    await media.processAndUploadFile(file);
    await media.getMediaFile('a.png');
    await media.getMediaFile('a.png');
    expect(media.stagedImagesUrl.value.length).toBeGreaterThan(0);
    const paste = {
      clipboardData: {
        items: [{ type: 'image/png', getAsFile: () => file }],
      },
    } as unknown as ClipboardEvent;
    await media.handlePaste(paste);
    media.removeImage(0);
    media.removeAudio();
    media.removeFile(0);
    media.clearStaged();
    media.cleanupMediaCache();

    const recording = useRecording();
    await expect(recording.startRecording()).rejects.toThrow(/not supported/);
    await expect(recording.stopRecording()).rejects.toThrow(
      /No media recorder/,
    );

    const commands = ref([
      {
        handler_full_name: 'a.b',
        current_fragment: 'help',
        aliases: ['h'],
        enabled: true,
        has_conflict: true,
        type: 'group',
        is_group: true,
        reserved: true,
        plugin_name: 'core',
        action: 'command',
      },
    ]);
    const filters = useCommandFilters(commands as never);
    expect(filters.hasSystemPluginConflict.value).toBe(true);
    expect(filters.effectiveShowSystemPlugins.value).toBe(true);
    expect(filters.availablePlugins.value.length).toBeGreaterThan(0);
    filters.showSystemPlugins.value = true;
    filters.searchQuery.value = '';
    expect(Array.isArray(filters.filteredCommands.value)).toBe(true);
    filters.toggleGroupExpand(commands.value[0] as never);
    expect(filters.isGroupExpanded(commands.value[0] as never)).toBe(true);

    const tools = useToolActions(
      ref([
        {
          name: 'search',
          description: 'd',
          origin: 'builtin',
          enabled: true,
        },
      ] as never),
      vi.fn(),
    );
    tools.showBuiltinTools.value = false;
    expect(tools.filteredTools.value).toEqual([]);
    tools.showBuiltinTools.value = true;
    tools.toolSearch.value = 'sea';
    expect(tools.filteredTools.value.length).toBe(1);
    expect(tools.toolSummary.value).toBeDefined();
    api.toolApi.setEnabled.mockResolvedValue({
      data: { status: 'ok', message: 'ok' },
    });
    api.toolApi.setParallel.mockResolvedValue({
      data: { status: 'ok', message: 'ok' },
    });
    api.toolApi.setParallelEnabled.mockResolvedValue({
      data: { status: 'ok', message: 'ok' },
    });
    const toast = vi.fn();
    const tool = {
      name: 'search',
      description: 'd',
      origin: 'plugin',
      active: false,
      readonly: false,
      parallel_eligible: true,
      tool_id: 't1',
      parallel_enabled: false,
      parallel_execution_enabled: false,
    };
    const actions = useToolActions(ref([tool] as never), toast);
    await actions.toggleTool(tool as never, 'ro', 'ok', 'err');
    await actions.toggleToolParallel(tool as never, true, 'err');
    await actions.toggleParallelExecution(true, 'err');
    expect(actions.parallelExecutionEnabled.value).toBeTypeOf('boolean');

    const commandActions = useCommandActions(toast, vi.fn());
    await commandActions.toggleCommand(
      {
        handler_full_name: 'a.b',
        enabled: true,
      } as never,
      'ok',
      'err',
    );
  });

  it(
    'covers messages, provider sources, and step-up',
    { timeout: 20_000 },
    async () => {
      api.chatApi.getSession.mockResolvedValue({
        data: {
          data: {
            history: [
              { id: 'h1', content: { type: 'user', message: 'hi' } },
              {
                id: 'h2',
                content: {
                  type: 'bot',
                  message: [{ type: 'plain', text: 'ok' }],
                },
              },
            ],
            threads: [],
            project: { project_id: 'p1', title: 'P' },
            active_runs: [],
          },
        },
      });
      const messages = useMessages({ currentSessionId: ref('s1') });
      await messages.loadSessionMessages('s1');
      expect(messages.activeMessages.value.length).toBe(2);
      messages.createLocalExchange({
        sessionId: 's1',
        messageId: 'n1',
        parts: [{ type: 'plain', text: 'q' }],
      });
      api.chatApi.stopSession.mockResolvedValue({ data: { status: 'ok' } });
      await messages.stopSession('s1');
      messages.cleanupConnections();
      const bot = {
        id: 'b',
        content: {
          type: 'bot' as const,
          message: [{ type: 'plain', text: 'x' }],
        },
      };
      appendPlain(bot, '!');
      expect(messageBlocks(bot.content).length).toBeGreaterThan(0);

      api.providerApi.schema.mockResolvedValue({
        data: {
          status: 'ok',
          data: {
            config_schema: {
              provider: {
                config_template: {
                  openai: {
                    provider_type: 'chat_completion',
                    provider: 'openai',
                  },
                },
              },
            },
            provider_sources: [
              {
                id: 'src1',
                provider_type: 'chat_completion',
                provider: 'openai',
              },
            ],
            providers: [
              {
                id: 'p1',
                provider_source_id: 'src1',
                enable: true,
                model: 'gpt',
              },
            ],
            model_metadata: { gpt: { tool_call: true } },
          },
        },
      });
      api.providerApi.setEnabled.mockResolvedValue({
        data: { status: 'ok', message: 'ok' },
      });
      api.providerApi.test.mockResolvedValue({
        data: { status: 'ok', data: { error: null } },
      });
      const sources = useProviderSources({
        tm: (key) => key,
        showMessage: vi.fn(),
      });
      await sources.loadProviderTemplate();
      sources.updateDefaultTab('chat_completion');
      expect(sources.availableSourceTypes.value.length).toBeGreaterThan(0);
      sources.selectProviderSource(sources.providerSources.value[0] as never);
      expect(sources.sourceProviders.value.length).toBeGreaterThan(0);
      expect(sources.supportsToolCall({ tool_call: true })).toBe(true);
      expect(
        sources.supportsImageInput({ modalities: { input: ['image'] } }),
      ).toBe(true);
      expect(
        sources.formatContextLimit({ limit: { context: 8000 } }),
      ).toContain('K');
      await sources.toggleProviderEnable(
        sources.providers.value[0] as never,
        false,
      );
      await sources.testProvider(sources.providers.value[0] as never);

      const dialog = useProviderModelConfigDialog({
        selectedProviderSource: ref({ id: 'src1', type: 'openai' }),
        configSchema: ref({ provider: { items: { id: {}, model: {} } } }),
        buildModelProviderConfig: (id) => ({ id, model: id }),
        modelAlreadyConfigured: () => false,
        loadConfig: vi.fn(),
        tm: (key) => key,
        showMessage: vi.fn(),
      });
      dialog.openProviderEdit({ id: 'p1' });
      dialog.openModelAddDialog('');
      dialog.openModelAddDialog('gpt-4');
      api.providerApi.update.mockResolvedValue({
        data: { status: 'ok', message: 'saved' },
      });
      api.providerApi.createInSource.mockResolvedValue({
        data: { status: 'ok', message: 'created' },
      });
      await dialog.saveEditedProvider();
      dialog.openModelAddDialog('gpt-5');
      await dialog.saveEditedProvider();

      const { mountWithVuetify } = await import('./utils/mountWithVuetify');
      const Harness = defineComponent({
        setup() {
          const stepUp = useDashboardStepUp();
          return { stepUp };
        },
        template: '<div />',
      });
      const wrapper = mountWithVuetify(Harness);
      const stepUp = (
        wrapper.vm as { stepUp: ReturnType<typeof useDashboardStepUp> }
      ).stepUp;
      const pending = stepUp.requestStepUp({
        action: 'x',
        resourceType: 'system',
        resourceId: '1',
      });
      stepUp.cancelStepUp();
      await expect(pending).resolves.toBeNull();
      const issued = stepUp.requestStepUp({
        action: 'system.restart',
        resourceType: 'system',
        resourceId: 'restart',
      });
      api.authorizationApi.stepUp.mockResolvedValue({
        data: { data: { token: 'step-token' } },
      });
      await stepUp.submitStepUp({ password: 'p' });
      await expect(issued).resolves.toBe('step-token');
      const webChat = stepUp.requestWebChatStepUp('sess-1');
      api.authorizationApi.webChatStepUp.mockResolvedValue({
        data: {
          data: { tokens: { 'webchat.tool_run': 'wc-token' }, expires_in: 1 },
        },
      });
      await stepUp.submitStepUp({ password: 'p', code: '123' });
      await expect(webChat).resolves.toMatchObject({
        'webchat.tool_run': 'wc-token',
      });
      wrapper.unmount();

      api.statsApi.restart.mockResolvedValue({ data: { status: 'ok' } });
      await restartAstrBot(null, async () => 'step-token');
      await restartAstrBot(null, async () => null);
      await restartAstrBot(
        { check: vi.fn(), stop: vi.fn() },
        async () => 'step-token',
      );
      expect(formatTokenCount(12_000)).toContain('K');
      expect(contextLimit({ max_context_tokens: 8000 })).toBe(8000);
      expect(formatContextLimit({ max_context_tokens: 8000 })).toBeTruthy();
      expect(
        providerCapabilityBadges(
          { modalities: ['image'] },
          { modalities: { input: ['image'] }, tool_call: true },
          (key) => key,
        ).length,
      ).toBeGreaterThan(0);
      expect(
        resolvePluginI18n({ 'zh-CN': { name: '插件' } }, 'zh-CN', 'name'),
      ).toBe('插件');
    },
  );

  it('covers persona, auth, common, and router-loading stores', async () => {
    const tree = [
      {
        folder_id: 'a',
        name: 'A',
        parent_id: null,
        children: [{ folder_id: 'b', name: 'B', parent_id: 'a', children: [] }],
      },
    ];
    api.personaApi.tree.mockResolvedValue({
      data: { status: 'ok', data: tree },
    });
    api.personaApi.folders.mockResolvedValue({
      data: { status: 'ok', data: [] },
    });
    api.personaApi.list.mockResolvedValue({ data: { status: 'ok', data: [] } });
    api.personaApi.move.mockResolvedValue({ data: { status: 'ok' } });
    api.personaApi.updateFolder.mockResolvedValue({ data: { status: 'ok' } });
    api.personaApi.createFolder.mockResolvedValue({
      data: { status: 'ok', data: { folder: { folder_id: 'c', name: 'C' } } },
    });
    api.personaApi.deleteFolder.mockResolvedValue({ data: { status: 'ok' } });
    const persona = usePersonaStore();
    await persona.loadFolderTree();
    persona.updateBreadcrumb('b');
    expect(persona.breadcrumbPath.map((n) => n.folder_id)).toContain('b');
    await persona.navigateToFolder('a');
    await persona.refreshCurrentFolder();
    await persona.movePersonaToFolder('p1', 'a');
    await persona.moveFolderToFolder('b', 'a');
    await persona.createFolder({ name: 'C' });
    await persona.updateFolder({ folder_id: 'a', name: 'A2' });
    await persona.deleteFolder('b');
    api.personaApi.delete = vi
      .fn()
      .mockResolvedValue({ data: { status: 'ok' } });
    api.personaApi.reorder = vi
      .fn()
      .mockResolvedValue({ data: { status: 'ok' } });
    await persona.deletePersona('p1');
    await persona.reorderItems([{ id: 'p1', type: 'persona', sort_order: 1 }]);
    expect(persona.findFolderInTree('a')?.name).toBe('A');

    api.authApi.login.mockResolvedValue({
      data: { status: 'ok', data: { username: 'u', token: 'tok' } },
    });
    api.statsApi.version.mockResolvedValue({
      status: 200,
      data: { data: { version: '1.0.0', dashboard_version: '1.0.0' } },
    });
    api.systemConfigApi.get.mockResolvedValue({
      data: { data: { config: { platform: [{}] } } },
    });
    api.providerApi.schema.mockResolvedValue({
      data: { data: { providers: [{ provider_type: 'chat_completion' }] } },
    });
    api.authApi.logout.mockResolvedValue({ data: { status: 'ok' } });
    const auth = useAuthStore();
    await auth.login('u', 'p');
    expect(auth.has_token()).toBe(true);
    api.authApi.login.mockRejectedValue({
      response: { status: 401, data: { data: { totp_required: true } } },
    });
    await expect(auth.login('u', 'p')).resolves.toBe('totp_required');
    api.authApi.setup.mockResolvedValue({
      data: { status: 'ok', data: { username: 'u', token: 't2' } },
    });
    await auth.setup('u', 'p', 'p');
    auth.logout();

    api.pluginApi.market.mockResolvedValue({
      data: {
        data: {
          demo: {
            name: 'demo',
            support_platforms: ['qq'],
            tags: ['ai'],
            author: 'a',
          },
        },
      },
    });
    api.statsApi.startTime.mockResolvedValue({
      data: { data: { start_time: 12 } },
    });
    api.statsApi.version.mockResolvedValue({
      data: { data: { version: 'v1.2.3', dashboard_version: 'd1' } },
    });
    const common = useCommonStore();
    expect(common.getStartTime()).toBe(-1);
    await common.fetchStartTime();
    await common.fetchAstrBotVersion();
    await common.getPluginCollections(true);
    common.closeEventSource();
    localStorage.setItem('token', 't');
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode('data: {"type":"log","data":"hello","uuid":"1"}\n\n'),
        );
        controller.close();
      },
    });
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response(stream, { status: 200 }),
    );
    await common.createEventSource();
    await new Promise((resolve) => setTimeout(resolve, 50));
    common.closeEventSource();

    const loading = useRouterLoadingStore();
    loading.start();
    loading.finish();
    await new Promise((resolve) => setTimeout(resolve, 320));
    expect(loading.isLoading).toBe(false);
  });

  it('covers i18n tools and loader cache', async () => {
    expect(
      generateMissingKeys({ a: '1', nested: { b: '2' } }, { a: '1' }),
    ).toContain('nested');
    const loader = new I18nLoader();
    expect(loader.getLoadingStatus().total).toBeGreaterThan(0);
    loader.clearCache();
    loader.clearCache('zh-CN');
  });
});

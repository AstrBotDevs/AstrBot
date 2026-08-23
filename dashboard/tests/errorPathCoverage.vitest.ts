import { createPinia, setActivePinia } from 'pinia';
import { defineComponent, ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    statsApi: { startTime: fn(), version: fn(), restart: fn() },
    authApi: { login: fn(), logout: fn() },
    systemConfigApi: { get: fn() },
    logApi: { liveUrl: () => '/api/v1/log/live' },
    toolApi: {
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
import { useSessions } from '@/composables/useSessions';
import { useConversations } from '@/composables/useConversations';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useRecording } from '@/composables/useRecording';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';
import { usePersonaStore } from '@/stores/personaStore';
import { restartAstrBot } from '@/utils/restartAstrBot';
import { useToolActions } from '@/components/extension/componentPanel/composables/useToolActions';
import { useComponentData } from '@/components/extension/componentPanel/composables/useComponentData';
import { useCommandActions } from '@/components/extension/componentPanel/composables/useCommandActions';
import { applySidebarCustomization } from '@/utils/sidebarCustomization';
import { MORE_GROUP_KEY } from '@/layouts/full/vertical-sidebar/sidebarItem';
import { I18nValidator } from '@/i18n/validator';
import { rankSuggestionCommands } from '@/components/chat/commandSuggestion';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('error-path coverage', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('covers session/conversation 401 and batch-delete failures', async () => {
    api.chatApi.listSessions.mockRejectedValue({ response: { status: 401 } });
    const sessions = useSessions(true);
    await sessions.getSessions();
    api.chatApi.createSession.mockRejectedValue(new Error('nope'));
    await expect(sessions.newSession()).rejects.toThrow();
    api.chatApi.batchDeleteSessions.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(sessions.batchDeleteSessions(['s1'])).rejects.toThrow();
    api.chatApi.batchDeleteSessions.mockResolvedValue({
      data: { status: 'ok', data: { deleted_count: 1 } },
    });
    await expect(sessions.batchDeleteSessions(['s1'])).rejects.toThrow();
    await sessions.saveTitle();
    api.chatApi.updateSession.mockRejectedValue(new Error('rename'));
    sessions.showEditTitleDialog('s1', 'x');
    await sessions.saveTitle();

    const conversations = useConversations();
    api.chatApi.listSessions.mockRejectedValue({ response: { status: 401 } });
    await conversations.getConversations();
    api.chatApi.createSession.mockRejectedValue(new Error('fail'));
    await expect(conversations.newConversation()).rejects.toThrow();
    api.chatApi.deleteSession.mockRejectedValue(new Error('fail'));
    await conversations.deleteConversation('c1');
    conversations.showEditTitleDialog('c1', 't');
    api.chatApi.updateSession.mockRejectedValue(new Error('fail'));
    await conversations.saveTitle();
  });

  it('covers media duplicates, audio removal, and recording empty blobs', async () => {
    api.fileApi.getByName.mockRejectedValue(new Error('missing'));
    api.fileApi.upload.mockResolvedValue({
      data: {
        data: { attachment_id: 'a1', filename: 'a.png', type: 'image' },
      },
    });
    const media = useMediaHandling();
    expect(await media.getMediaFile('gone.bin')).toBe('');
    media.stagedFiles.value.push({
      attachment_id: 'r1',
      filename: 'a.webm',
      original_name: 'a.webm',
      url: 'blob:audio',
      type: 'record',
    });
    media.stagedFiles.value.push({
      attachment_id: 'f1',
      filename: 'a.txt',
      original_name: 'a.txt',
      url: 'blob:file',
      type: 'file',
    });
    media.removeAudio();
    media.removeFile(0);
    media.clearStaged({ revokeUrls: false });

    class EmptyRecorder {
      stream = { getTracks: () => [{ stop: vi.fn() }] };
      mimeType = 'audio/webm';
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {}
      stop() {
        this.onstop?.();
      }
      static isTypeSupported() {
        return true;
      }
    }
    vi.stubGlobal('MediaRecorder', EmptyRecorder);
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
    await expect(recording.stopRecording((label) => label)).rejects.toThrow(
      /empty/,
    );
    vi.unstubAllGlobals();
  });

  it('covers provider save errors, step-up failures, and desktop restart', async () => {
    const showMessage = vi.fn();
    const dialog = useProviderModelConfigDialog({
      selectedProviderSource: ref(null),
      configSchema: ref({}),
      buildModelProviderConfig: () => null,
      modelAlreadyConfigured: () => true,
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage,
    });
    await dialog.saveEditedProvider();
    dialog.openModelAddDialog('gpt');
    dialog.openProviderEdit({ id: 'p1', model: 'gpt' });
    api.providerApi.update.mockResolvedValue({
      data: { status: 'error', message: 'nope' },
    });
    await dialog.saveEditedProvider();
    api.providerApi.update.mockRejectedValue(new Error('boom'));
    await dialog.saveEditedProvider();

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
    await stepUp.submitStepUp({ password: 'x' });
    const pending = stepUp.requestStepUp({
      action: 'a',
      resourceType: 'r',
      resourceId: '1',
    });
    expect(
      await stepUp.requestStepUp({
        action: 'b',
        resourceType: 'r',
        resourceId: '2',
      }),
    ).toBeNull();
    stepUp.cancelStepUp();
    await pending;
    wrapper.unmount();

    window.astrbotDesktop = {
      isDesktop: true,
      isDesktopRuntime: vi.fn(async () => true),
      restartBackend: vi.fn(async () => ({ ok: false, reason: 'nope' })),
    } as never;
    api.statsApi.startTime.mockRejectedValue(new Error('offline'));
    const waiting = { check: vi.fn(), stop: vi.fn() };
    await expect(restartAstrBot(waiting, async () => 'tok')).rejects.toThrow(
      /nope/,
    );
    expect(waiting.stop).toHaveBeenCalled();
    (
      window.astrbotDesktop as { restartBackend: ReturnType<typeof vi.fn> }
    ).restartBackend = vi.fn(async () => ({ ok: true }));
    api.statsApi.startTime.mockResolvedValue({
      data: { data: { start_time: '12' } },
    });
    await restartAstrBot(waiting, async () => 'tok');
    delete window.astrbotDesktop;
  });

  it('covers persona errors, auth upgrade, tools, commands, and sidebar apply', async () => {
    const persona = usePersonaStore();
    api.personaApi.tree.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.loadFolderTree()).rejects.toThrow();
    api.personaApi.move.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.movePersonaToFolder('p', 'f')).rejects.toThrow();
    api.personaApi.updateFolder.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.moveFolderToFolder('a', null)).rejects.toThrow();
    api.personaApi.createFolder.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.createFolder({ name: 'x' })).rejects.toThrow();
    api.personaApi.delete.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.deletePersona('p')).rejects.toThrow();
    api.personaApi.reorder.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(
      persona.reorderItems([{ id: 'p', type: 'persona', sort_order: 1 }]),
    ).rejects.toThrow();

    api.authApi.login.mockResolvedValue({
      data: { status: 'ok', data: { username: 'u', token: 'tok' } },
    });
    api.statsApi.version.mockResolvedValue({
      status: 200,
      data: { data: { version: '1.0.0', dashboard_version: '2.0.0' } },
    });
    const auth = useAuthStore();
    await expect(auth.login('u', 'p')).resolves.toBe(
      'upgrade_recovery_required',
    );
    api.authApi.login.mockResolvedValue({
      data: { status: 'error', message: 'bad' },
    });
    await expect(auth.login('u', 'p')).rejects.toThrow();

    const toast = vi.fn();
    const readonlyTool = {
      name: 'x',
      readonly: true,
      active: true,
      parallel_eligible: false,
      tool_id: '',
    };
    const tools = useToolActions(ref([readonlyTool] as never), toast);
    await tools.toggleTool(readonlyTool as never, 'ro', 'ok', 'err');
    await tools.toggleToolParallel(readonlyTool as never, true, 'err');
    api.toolApi.setEnabled.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    const writable = {
      name: 'y',
      readonly: false,
      active: false,
      parallel_eligible: true,
      tool_id: 't',
      parallel_enabled: false,
    };
    const tools2 = useToolActions(ref([writable] as never), toast);
    await tools2.toggleTool(writable as never, 'ro', 'ok', 'err');
    api.toolApi.setParallel.mockRejectedValue(new Error('fail'));
    await tools2.toggleToolParallel(writable as never, true, 'err');
    api.toolApi.setParallelEnabled.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await tools2.toggleParallelExecution(true, 'err');

    api.commandApi.list.mockResolvedValue({
      data: {
        status: 'ok',
        data: { items: [], summary: { disabled: 1, conflicts: 2 } },
      },
    });
    api.commandApi.update.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    const data = useComponentData();
    await data.fetchCommands('err');
    api.commandApi.list.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await data.fetchCommands('err');
    api.commandApi.list.mockRejectedValue(new Error('fail'));
    await data.fetchCommands('err');
    const actions = useCommandActions(toast, vi.fn());
    await actions.toggleCommand(
      { command_id: 'a.b', handler_full_name: 'a.b', enabled: true } as never,
      'ok',
      'err',
    );
    actions.openRenameDialog({
      command_id: 'a.b',
      handler_full_name: 'a.b',
      current_fragment: 'a',
      aliases: ['b'],
    } as never);
    await actions.confirmRename('ok', 'err');

    applySidebarCustomization([
      { title: 'core.navigation.chat' },
      {
        title: MORE_GROUP_KEY,
        children: [{ title: 'core.navigation.about' }],
      },
    ]);
    localStorage.setItem(
      'astrbot_sidebar_customization',
      JSON.stringify({
        mainItems: ['core.navigation.chat', 'missing'],
        moreItems: ['core.navigation.about', 'core.navigation.chat'],
      }),
    );
    applySidebarCustomization([
      { title: 'core.navigation.chat' },
      { title: 'core.navigation.settings' },
      {
        title: MORE_GROUP_KEY,
        children: [{ title: 'core.navigation.about' }],
      },
    ]);

    const validator = new I18nValidator();
    expect(
      validator.validateValues({
        'zh-CN': { empty: '  ', bad: '{1}', nested: { n: 1 } },
      }).length,
    ).toBeGreaterThan(0);
    expect(
      rankSuggestionCommands(
        [
          {
            handler_full_name: 'a',
            effective_command: '/helpme',
            description: 'about help',
            plugin_display_name: 'helper',
            enabled: true,
            reserved: false,
          },
        ],
        'help',
        (value) => value.toLowerCase(),
      ).length,
    ).toBeGreaterThan(0);

    const common = useCommonStore();
    localStorage.setItem('token', 't');
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response('x', { status: 500 }),
    );
    await common.createEventSource();
    common.closeEventSource();
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response(null, { status: 200 }) as Response,
    );
    await common.createEventSource();
    common.closeEventSource();
    common.log_cache_max_len = 1;
    const encoder = new TextEncoder();
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'data: {"uuid":"1","data":"a"}\n\ndata: {"data":"b"}\n\n',
              ),
            );
            controller.close();
          },
        }),
        { status: 200 },
      ),
    );
    await common.createEventSource();
    await common.createEventSource();
    await new Promise((resolve) => setTimeout(resolve, 30));
    common.closeEventSource();
  });

  it('covers remaining auth, projects, recording stop errors, and schema hiding', async () => {
    api.systemConfigApi.get.mockResolvedValue({
      data: { data: { config: { platform: [] } } },
    });
    const auth = useAuthStore();
    await auth.finishAuthenticatedSession({
      username: 'u',
      token: 't',
      password_upgrade_required: true,
      md5_pwd_hint: true,
    });
    await auth.finishAuthenticatedSession({
      username: 'u',
      token: 't',
      change_pwd_hint: false,
      md5_pwd_hint: false,
    });

    api.chatApi.updateProject = vi.fn().mockRejectedValue(new Error('fail'));
    api.chatApi.deleteProject = vi.fn().mockRejectedValue(new Error('fail'));
    api.chatApi.addProjectSession = vi
      .fn()
      .mockRejectedValue(new Error('fail'));
    api.chatApi.removeProjectSession = vi
      .fn()
      .mockRejectedValue(new Error('fail'));
    api.chatApi.listProjectSessions = vi
      .fn()
      .mockRejectedValue(new Error('fail'));
    api.chatApi.listProjects = vi.fn().mockRejectedValue(new Error('fail'));
    const { useProjects } = await import('@/composables/useProjects');
    const projects = useProjects();
    await projects.getProjects();
    await projects.updateProject('p', 't');
    await projects.deleteProject('p');
    await projects.addSessionToProject('s', 'p');
    await projects.removeSessionFromProject('s');
    await projects.getProjectSessions('p');

    class ThrowingRecorder {
      stream = { getTracks: () => [{ stop: vi.fn() }] };
      mimeType = 'audio/webm';
      ondataavailable = null;
      onstop = null;
      onerror = null;
      start() {}
      stop() {
        throw new Error('stop failed');
      }
      static isTypeSupported() {
        return true;
      }
    }
    vi.stubGlobal('MediaRecorder', ThrowingRecorder);
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
    await expect(recording.stopRecording()).rejects.toThrow(/stop failed/);
    vi.unstubAllGlobals();

    const dialog = useProviderModelConfigDialog({
      selectedProviderSource: ref({
        id: 'src',
        type: 'googlegenai_chat_completion',
      }),
      configSchema: ref({
        provider: {
          items: { id: {}, model: {}, custom_extra_body: {} },
        },
      }),
      buildModelProviderConfig: () => ({ id: 'n', model: 'n' }),
      modelAlreadyConfigured: () => false,
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage: vi.fn(),
      requestStepUp: async () => null,
    });
    expect(
      dialog.providerModelConfigSchema.value.provider.items.custom_extra_body
        .invisible,
    ).toBe(true);
    dialog.openModelAddDialog('m1');
    api.providerApi.createInSource.mockResolvedValue({
      data: { status: 'ok' },
    });
    await dialog.saveEditedProvider();

    api.personaApi.updateFolder.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    const persona = usePersonaStore();
    await expect(
      persona.updateFolder({ folder_id: 'a', name: 'n' }),
    ).rejects.toThrow();
    api.personaApi.deleteFolder.mockResolvedValue({
      data: { status: 'error', message: 'fail' },
    });
    await expect(persona.deleteFolder('a')).rejects.toThrow();

    const validator = new I18nValidator();
    expect(
      validator.validateInterpolation({
        'zh-CN': { a: 'hi {name}' },
        'en-US': { a: 'hi {title}' },
      }).length,
    ).toBeGreaterThan(0);

    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: true,
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: vi.fn(async () => {
          throw new Error('denied');
        }),
      },
    });
    document.execCommand = vi.fn(() => false) as typeof document.execCommand;
    const { copyToClipboard } = await import('@/utils/clipboard');
    expect(await copyToClipboard('x')).toBe(false);
  });

  it('covers pending conversation selection, breadcrumb misses, and 403 logs', async () => {
    api.chatApi.listSessions.mockResolvedValue({
      data: {
        data: [
          {
            session_id: 'c1',
            display_name: null,
            updated_at: 'bad',
          },
        ],
      },
    });
    const conversations = useConversations();
    conversations.pendingCid.value = 'c1';
    await conversations.getConversations();
    expect(conversations.selectedConversations.value).toContain('c1');
    conversations.pendingCid.value = null;
    conversations.currCid.value = '';
    await conversations.getConversations();

    const persona = usePersonaStore();
    persona.folderTree = [
      { folder_id: 'a', name: 'A', parent_id: null, children: [] },
    ];
    persona.updateBreadcrumb('missing');
    expect(persona.breadcrumbPath).toEqual([]);

    const { useCommandFilters } =
      await import('@/components/extension/componentPanel/composables/useCommandFilters');
    const filters = useCommandFilters(
      ref([
        {
          handler_full_name: 'g',
          is_group: true,
          type: 'group',
          reserved: false,
          enabled: true,
          has_conflict: false,
          plugin: 'p',
          action: 'command',
          effective_command: 'group',
          sub_commands: [
            {
              handler_full_name: 'g.s',
              is_group: false,
              type: 'sub_command',
              reserved: false,
              enabled: true,
              has_conflict: true,
              plugin: 'p',
              action: 'command',
              effective_command: 'sub',
              description: 'needle',
            },
          ],
        },
      ] as never),
    );
    filters.searchQuery.value = 'needle';
    filters.toggleGroupExpand({
      is_group: true,
      handler_full_name: 'g',
    } as never);
    expect(filters.filteredCommands.value.length).toBeGreaterThan(0);
    filters.statusFilter.value = 'enabled';
    filters.typeFilter.value = 'command';
    void filters.filteredCommands.value;

    const actions = useCommandActions(vi.fn(), vi.fn());
    expect(
      actions.getTypeInfo('command', {
        group: 'g',
        subCommand: 's',
        command: 'c',
      }).text,
    ).toBe('c');
    expect(
      actions.getStatusInfo({ has_conflict: false, enabled: false } as never, {
        conflict: 'c',
        enabled: 'e',
        disabled: 'd',
      }).text,
    ).toBe('d');
    expect(
      actions.getRowProps({
        item: {
          has_conflict: true,
          type: 'sub_command',
          is_group: true,
        } as never,
      }),
    ).toMatchObject({ class: expect.stringContaining('conflict') });

    localStorage.setItem('token', 't');
    vi.mocked(fetchWithAuth).mockResolvedValue(
      new Response('x', { status: 403 }),
    );
    const common = useCommonStore();
    await common.createEventSource();
    common.closeEventSource();

    vi.useFakeTimers();
    vi.mocked(fetchWithAuth).mockRejectedValue(new Error('offline'));
    await common.createEventSource();
    await vi.advanceTimersByTimeAsync(1100);
    vi.useRealTimers();
    common.closeEventSource();
  });
});

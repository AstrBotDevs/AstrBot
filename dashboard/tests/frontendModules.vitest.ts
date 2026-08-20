import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/router', () => ({
  router: { push: vi.fn(), replace: vi.fn() },
}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

const apiMocks = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
  listProjects: vi.fn(),
  createProject: vi.fn(),
  schema: vi.fn(),
  systemGet: vi.fn(),
  tree: vi.fn(),
  folders: vi.fn(),
  listPersonas: vi.fn(),
  startTime: vi.fn(),
  restart: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  authApi: { login: apiMocks.login, logout: apiMocks.logout },
  chatApi: {
    listSessions: apiMocks.listSessions,
    createSession: apiMocks.createSession,
    listProjects: apiMocks.listProjects,
    createProject: apiMocks.createProject,
    unifiedWebSocketUrl: (token: string) => `ws://example/${token}`,
  },
  providerApi: { schema: apiMocks.schema, listByProviderType: vi.fn() },
  systemConfigApi: { get: apiMocks.systemGet },
  personaApi: {
    tree: apiMocks.tree,
    folders: apiMocks.folders,
    list: apiMocks.listPersonas,
  },
  statsApi: {
    startTime: apiMocks.startTime,
    restart: apiMocks.restart,
  },
  pluginApi: { list: vi.fn(), collections: vi.fn() },
  logApi: { get: vi.fn() },
  UPGRADE_RECOVERY_EVENT: 'astrbot-upgrade-recovery',
  UPGRADE_RECOVERY_TOKEN_KEY: 'astrbot-upgrade-recovery-token',
}));

import { useConversations } from '@/composables/useConversations';
import { useProjects } from '@/composables/useProjects';
import { useSessions } from '@/composables/useSessions';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';
import { useCustomizerStore } from '@/stores/customizer';
import { usePersonaStore } from '@/stores/personaStore';
import { useToast } from '@/utils/toast';
import {
  buildWebchatUmoDetails,
  getStoredDashboardUsername,
  getStoredSelectedChatConfigId,
  setStoredSelectedChatConfigId,
} from '@/utils/chatConfigBinding';
import { copyToClipboard } from '@/utils/clipboard';
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime';
import {
  readGitHubProxyState,
  readSelectedGitHubProxy,
  writeGitHubProxyControl,
  writeGitHubProxyRadioValue,
  writeSelectedGitHubProxy,
} from '@/utils/githubProxyStorage';
import { normalizeTextInput } from '@/utils/inputValue';
import {
  buildSearchQuery,
  matchesPluginSearch,
  matchesText,
  normalizeLoose,
  normalizeStr,
  toInitials,
  toPinyinText,
} from '@/utils/pluginSearch';
import { getProviderDescription, getProviderIcon } from '@/utils/providerUtils';
import { restartAstrBot } from '@/utils/restartAstrBot';
import { stepUpHeaders } from '@/utils/stepUp';

describe('frontend modules', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('covers plugin search and github proxy helpers', () => {
    expect(normalizeStr('  Ab ')).toBe('ab');
    expect(normalizeLoose('a_b-c')).toBe('abc');
    const query = buildSearchQuery('astr');
    expect(query?.norm).toBe('astr');
    expect(matchesText('AstrBot', query)).toBe(true);
    expect(matchesText(null, query)).toBe(false);
    expect(toPinyinText('测试').length).toBeGreaterThan(0);
    expect(toInitials('测试').length).toBeGreaterThan(0);
    expect(
      matchesPluginSearch(
        { name: 'astrbot_plugin_demo', desc: 'demo', tags: ['ai'] },
        query,
      ),
    ).toBe(true);
    expect(matchesPluginSearch({ name: 'other' }, null)).toBe(true);

    writeSelectedGitHubProxy('https://ghproxy.example');
    writeGitHubProxyRadioValue('1');
    writeGitHubProxyControl('1');
    const state = readGitHubProxyState();
    expect(state.selectedProxy).toBe('https://ghproxy.example');
    expect(state.radioValue).toBe('1');
    expect(readSelectedGitHubProxy()).toBe('');
  });

  it('covers chat config, clipboard, and desktop helpers', async () => {
    localStorage.setItem('user', 'alice');
    setStoredSelectedChatConfigId('profile-1');
    expect(getStoredDashboardUsername()).toBe('alice');
    expect(getStoredSelectedChatConfigId()).toBe('profile-1');
    expect(buildWebchatUmoDetails('sess-1', true).umo).toContain(
      'GroupMessage',
    );
    expect(buildWebchatUmoDetails('sess-2').umo).toContain('FriendMessage');
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: false,
    });
    await copyToClipboard('hello');
    await copyToClipboard('');
    const desktop = await getDesktopRuntimeInfo();
    expect(desktop.isDesktopRuntime).toBe(false);
    expect(normalizeTextInput(1)).toBe('');
    expect(normalizeTextInput('ok')).toBe('ok');
    expect(stepUpHeaders('tok')['X-AstrBot-Step-Up']).toBe('tok');
    expect(getProviderIcon('openai')).toContain('openai');
    expect(
      getProviderDescription(
        { type: 'openai_chat_completions' },
        'X',
        (k) => k,
      ),
    ).toContain('openai_chat_completions');
    expect(
      getProviderDescription({ type: 'openai_responses' }, 'X', (k) => k),
    ).toContain('openai_responses');
    expect(getProviderDescription({ type: 'x' }, 'OpenAI', (k) => k)).toContain(
      'openai',
    );
    expect(
      getProviderDescription({ provider: 'kimi-code' }, 'Kimi', (k) => k),
    ).toContain('kimi');
    expect(
      getProviderDescription({ type: 'vllm' }, 'vLLM Rerank', (k) => k),
    ).toContain('vllm');
    expect(
      getProviderDescription({ type: 'other' }, 'Other', (k) => k),
    ).toContain('default');
  });

  it('covers toast and restart helpers', async () => {
    const { success, error, info, warning, toast } = useToast();
    toast('t');
    success('s');
    error('e');
    info('i');
    warning('w');
    await expect(restartAstrBot()).rejects.toThrow(/Reauthentication/);
    apiMocks.restart.mockResolvedValue({ data: { status: 'ok' } });
    await restartAstrBot(null, async () => 'step-up');
    expect(apiMocks.restart).toHaveBeenCalled();
  });

  it('covers auth, persona, common, and customizer stores', async () => {
    apiMocks.systemGet.mockResolvedValue({
      data: { data: { config: { platform: [{}] } } },
    });
    apiMocks.schema.mockResolvedValue({
      data: { data: { providers: [{ provider_type: 'chat_completion' }] } },
    });
    apiMocks.tree.mockResolvedValue({ data: { status: 'ok', data: [] } });
    apiMocks.folders.mockResolvedValue({ data: { status: 'ok', data: [] } });
    apiMocks.listPersonas.mockResolvedValue({
      data: { status: 'ok', data: [] },
    });
    apiMocks.logout.mockResolvedValue({ data: { status: 'ok' } });

    const auth = useAuthStore();
    await auth.finishAuthenticatedSession({
      username: 'astrbot',
      token: 'tok',
      change_pwd_hint: true,
      md5_pwd_hint: true,
    });
    expect(auth.has_token()).toBe(true);
    auth.logout();
    expect(auth.has_token()).toBe(false);

    const persona = usePersonaStore();
    persona.toggleFolderExpansion('folder-1');
    persona.setFolderExpansion('folder-1', true);
    persona.updateBreadcrumb(null);
    await persona.loadFolderTree();
    await persona.navigateToFolder(null);
    expect(persona.currentFolderName).toBeDefined();

    const common = useCommonStore();
    expect(common.log_cache).toEqual([]);

    const customizer = useCustomizerStore();
    customizer.SET_THEME_MODE('dark');
  });

  it('covers session, conversation, and project composables', async () => {
    apiMocks.listSessions.mockResolvedValue({
      data: {
        data: [
          {
            session_id: 's1',
            display_name: 'one',
            updated_at: '',
            platform_id: 'webchat',
            creator: 'u',
            is_group: 0,
            created_at: '',
          },
        ],
      },
    });
    apiMocks.createSession.mockResolvedValue({
      data: { data: { session_id: 's2', platform_id: 'webchat' } },
    });
    apiMocks.listProjects.mockResolvedValue({
      data: { status: 'ok', data: [] },
    });
    apiMocks.createProject.mockResolvedValue({
      data: { status: 'ok', data: { project_id: 'p1' } },
    });

    const sessions = useSessions();
    await sessions.getSessions();
    expect(sessions.sessions.value).toHaveLength(1);
    await sessions.newSession();

    const conversations = useConversations();
    await conversations.getConversations();
    expect(conversations.conversations.value.length).toBeGreaterThan(0);
    await conversations.newConversation();

    const projects = useProjects();
    await projects.getProjects();
    await projects.createProject('demo');
  });
});

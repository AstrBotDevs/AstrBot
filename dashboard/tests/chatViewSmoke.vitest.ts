import { defineComponent, ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import Chat from '@/components/chat/Chat.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  route: {
    path: '/chat',
    params: {} as Record<string, unknown>,
  },
  customizer: {
    uiTheme: 'AstrBotLight',
    chatSidebarOpen: true,
    SET_CHAT_SIDEBAR(value: boolean) {
      testState.customizer.chatSidebarOpen = value;
    },
    SET_THEME_MODE(mode: 'light' | 'dark' | 'system') {
      testState.customizer.uiTheme =
        mode === 'dark' ? 'AstrBotDark' : 'AstrBotLight';
    },
  },
  sessions: [] as Array<Record<string, unknown>>,
  projects: [] as Array<Record<string, unknown>>,
  selectedProjectId: null as string | null,
  activeMessages: [] as Array<Record<string, unknown>>,
  loadedSessions: {} as Record<string, boolean>,
  sessionProjects: {} as Record<string, unknown>,
  currSessionId: '',
  getSessionsMock: vi.fn(),
  newSessionMock: vi.fn(),
  getProjectsMock: vi.fn(),
  getProjectSessionsMock: vi.fn(),
  addSessionToProjectMock: vi.fn(),
  chatApiUpdateSessionMock: vi.fn(),
  regenerateMessageMock: vi.fn(),
  inputSelection: {
    providerId: 'current-provider',
    modelName: 'current-model',
  },
}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRoute: () => testState.route,
    useRouter: () => ({
      push: vi.fn(),
      replace: vi.fn(),
    }),
  };
});

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => testState.customizer,
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    updateSession: testState.chatApiUpdateSessionMock,
    createThread: vi.fn(),
    deleteThread: vi.fn(),
  },
  providerApi: {
    listByProviderType: vi.fn().mockResolvedValue({
      data: { status: 'ok', model_metadata: {} },
    }),
  },
}));

vi.mock('@/composables/useSessions', () => ({
  useSessions: () => ({
    sessions: ref(testState.sessions),
    currSessionId: ref(testState.currSessionId),
    getSessions: testState.getSessionsMock,
    newSession: testState.newSessionMock,
    newChat: vi.fn(),
    deleteSession: vi.fn(),
    updateSessionTitle: vi.fn(),
  }),
}));

vi.mock('@/composables/useProjects', () => ({
  useProjects: () => ({
    projects: ref(testState.projects),
    selectedProjectId: ref(testState.selectedProjectId),
    getProjects: testState.getProjectsMock,
    createProject: vi.fn(),
    updateProject: vi.fn(),
    deleteProject: vi.fn(),
    addSessionToProject: testState.addSessionToProjectMock,
    getProjectSessions: testState.getProjectSessionsMock,
  }),
}));

vi.mock('@/composables/useMediaHandling', () => ({
  useMediaHandling: () => ({
    stagedFiles: ref([]),
    stagedImagesUrl: ref([]),
    stagedAudioUrl: ref(''),
    stagedNonImageFiles: [],
    processAndUploadImage: vi.fn(),
    processAndUploadFile: vi.fn(),
    handlePaste: vi.fn(),
    removeImage: vi.fn(),
    removeAudio: vi.fn(),
    removeFile: vi.fn(),
    clearStaged: vi.fn(),
    cleanupMediaCache: vi.fn(),
  }),
}));

vi.mock('@/composables/useRecording', () => ({
  useRecording: () => ({
    isRecording: ref(false),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
  }),
}));

vi.mock('@/composables/useMessages', () => ({
  messageBlocks: vi.fn(() => []),
  useMessages: () => ({
    loadingMessages: ref(false),
    sending: ref(false),
    loadedSessions: testState.loadedSessions,
    sessionProjects: testState.sessionProjects,
    activeMessages: ref(testState.activeMessages),
    isSessionRunning: () => false,
    isUserMessage: (message: { content?: { type?: string } }) =>
      message.content?.type === 'user',
    messageParts: (message: { content?: { message?: unknown[] } }) =>
      message.content?.message || [],
    loadSessionMessages: vi.fn(),
    createLocalExchange: vi.fn(),
    sendMessageStream: vi.fn(),
    editMessage: vi.fn(),
    continueEditedMessage: vi.fn(),
    regenerateMessage: testState.regenerateMessageMock,
    stopSession: vi.fn(),
  }),
}));

vi.mock('@/i18n/composables', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
  useModuleI18n: () => ({
    tm: (key: string, params?: Record<string, unknown>) => {
      if (key === 'welcome.title') return 'How can AstrBot help?';
      if (key === 'conversation.noHistory') return 'No history';
      if (key === 'conversation.newConversation') return 'New conversation';
      if (key === 'actions.providerConfig') return 'Provider Config';
      if (key === 'actions.newChat') return 'New Chat';
      if (key === 'transport.title') return 'Transport';
      if (key === 'modes.darkMode') return 'Dark Mode';
      if (key === 'modes.lightMode') return 'Light Mode';
      if (key === 'thread.askInThread') return 'Ask in thread';
      if (key === 'conversation.confirmDelete')
        return `Delete ${params?.name || ''}`.trim();
      return key;
    },
  }),
  useLanguageSwitcher: () => ({
    languageOptions: [{ value: 'en-US', label: 'English', flag: 'EN' }],
    currentLanguage: { label: 'English' },
    switchLanguage: vi.fn(),
    locale: 'en-US',
  }),
}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn(),
  useConfirmDialog: () => undefined,
}));

vi.mock('@/utils/toast', () => ({
  useToast: () => ({
    error: vi.fn(),
    success: vi.fn(),
  }),
}));

vi.mock('@/components/shared/StyledMenu.vue', () => ({
  default: {
    template:
      '<div class="styled-menu-stub"><slot name="activator" :props="{}" /><slot /></div>',
  },
}));

vi.mock('@/components/chat/ProjectDialog.vue', () => ({
  default: {
    template: '<div class="project-dialog-stub"></div>',
  },
}));

vi.mock('@/components/chat/ProjectList.vue', () => ({
  default: {
    template: '<div class="project-list-stub"></div>',
  },
}));

vi.mock('@/components/chat/ProjectView.vue', () => ({
  default: {
    template: '<div class="project-view-stub"><slot /></div>',
  },
}));

vi.mock('@/components/chat/ChatInput.vue', () => ({
  default: {
    props: ['placeholder', 'prompt'],
    template:
      '<div class="chat-input-stub" :data-placeholder="placeholder"><input class="chat-input-draft" :value="prompt" @input="$emit(\'update:prompt\', $event.target.value)" /><button class="chat-input-send" @click="$emit(\'send\')">send</button></div>',
    setup(_props: unknown, { expose }: { expose: (value: unknown) => void }) {
      expose({
        getCurrentSelection: () => testState.inputSelection,
        focus: vi.fn(),
        focusInput: vi.fn(),
      });
      return {};
    },
  },
}));

vi.mock('@/components/chat/ChatMessageList.vue', () => ({
  default: {
    props: ['messages'],
    emits: ['open-refs', 'regenerate'],
    template:
      '<div class="chat-message-list-stub"><button class="open-refs-trigger" @click="$emit(\'open-refs\', { used: [{ title: \'Doc\', url: \'https://example.com\' }] })">open refs</button><button class="regenerate-trigger" @click="$emit(\'regenerate\', messages[0])">regenerate</button></div>',
  },
}));

vi.mock('@/components/chat/ReasoningSidebar.vue', () => ({
  default: {
    props: ['modelValue'],
    template:
      '<div v-if="modelValue" class="reasoning-sidebar-stub">reasoning sidebar</div>',
  },
}));

vi.mock('@/components/chat/ThreadPanel.vue', () => ({
  default: {
    props: ['modelValue'],
    template:
      '<div v-if="modelValue" class="thread-panel-stub">thread panel</div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/RefsSidebar.vue', () => ({
  default: {
    props: ['modelValue', 'refs'],
    template:
      '<div v-if="modelValue" class="refs-sidebar-stub">{{ refs?.used?.length || 0 }}</div>',
  },
}));

vi.mock('@/components/provider/ProviderChatCompletionPanel.vue', () => ({
  default: {
    template: '<div class="provider-workspace-stub">provider workspace</div>',
  },
}));

function mountChat() {
  const Host = defineComponent({
    components: { Chat },
    template:
      '<v-app><v-layout style="height: 100vh"><Chat /></v-layout></v-app>',
  });

  return mountWithVuetify(Host);
}

describe('Chat view smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    testState.route.path = '/chat';
    testState.route.params = {};
    testState.customizer.uiTheme = 'AstrBotLight';
    testState.customizer.chatSidebarOpen = true;
    testState.sessions = [];
    testState.projects = [];
    testState.selectedProjectId = null;
    testState.activeMessages = [];
    testState.loadedSessions = {};
    testState.sessionProjects = {};
    testState.currSessionId = '';
    testState.getSessionsMock.mockResolvedValue(undefined);
    testState.newSessionMock.mockResolvedValue('session-new');
    testState.getProjectsMock.mockResolvedValue(undefined);
    testState.getProjectSessionsMock.mockResolvedValue([]);
    testState.addSessionToProjectMock.mockResolvedValue(undefined);
    testState.chatApiUpdateSessionMock.mockResolvedValue(undefined);
    testState.regenerateMessageMock.mockResolvedValue(undefined);
    testState.inputSelection = {
      providerId: 'current-provider',
      modelName: 'current-model',
    };
  });

  it('renders the welcome chat state without crashing', async () => {
    const wrapper = mountChat();
    await flushPromises();

    expect(wrapper.find('.welcome-title').text()).toBe('How can AstrBot help?');
    expect(wrapper.find('.chat-input-stub').exists()).toBe(true);
  });

  it('renders the provider workspace route without mounting the welcome state', async () => {
    testState.route.path = '/chat/models';
    testState.route.params = { conversationId: 'models' };

    const wrapper = mountChat();
    await flushPromises();

    expect(wrapper.find('.provider-workspace-stub').exists()).toBe(true);
    expect(wrapper.find('.welcome-title').exists()).toBe(false);
  });

  it('passes the project placeholder only to the project composer', async () => {
    testState.projects = [
      {
        project_id: 'project-1',
        title: 'Planning',
        emoji: 'P',
      },
    ];
    testState.selectedProjectId = 'project-1';

    const wrapper = mountChat();
    await flushPromises();

    expect(
      wrapper
        .get('.project-view-stub .chat-input-stub')
        .attributes('data-placeholder'),
    ).toBe('input.projectPlaceholder');
    expect(wrapper.find('.composer-shell .chat-input-stub').exists()).toBe(
      false,
    );
  });

  it('refreshes sessions only after associating a new project session', async () => {
    const calls: string[] = [];
    testState.projects = [
      { project_id: 'project-1', title: 'Planning', emoji: 'P' },
    ];
    testState.selectedProjectId = 'project-1';
    testState.newSessionMock.mockImplementation(async () => {
      calls.push('new-session');
      return 'session-new';
    });
    testState.addSessionToProjectMock.mockImplementation(async () => {
      calls.push('associate-project');
    });
    testState.getProjectSessionsMock.mockImplementation(async () => {
      calls.push('refresh-project');
      return [];
    });
    testState.getSessionsMock.mockImplementation(async () => {
      calls.push('refresh-ordinary');
    });

    const wrapper = mountChat();
    await flushPromises();
    calls.length = 0;

    await wrapper
      .find('.project-view-stub .chat-input-draft')
      .setValue('Project task');
    await wrapper.find('.project-view-stub .chat-input-send').trigger('click');
    await flushPromises();

    expect(calls).toEqual([
      'new-session',
      'associate-project',
      'refresh-project',
      'refresh-ordinary',
    ]);
  });

  it('refreshes ordinary sessions after creating a non-project session', async () => {
    const calls: string[] = [];
    testState.newSessionMock.mockImplementation(async () => {
      calls.push('new-session');
      return 'session-new';
    });
    testState.getSessionsMock.mockImplementation(async () => {
      calls.push('refresh-ordinary');
    });

    const wrapper = mountChat();
    await flushPromises();
    calls.length = 0;

    await wrapper.find('.composer-shell .chat-input-draft').setValue('Hello');
    await wrapper.find('.composer-shell .chat-input-send').trigger('click');
    await flushPromises();

    expect(calls).toEqual(['new-session', 'refresh-ordinary']);
  });

  it('opens the refs sidebar from the message list interaction path', async () => {
    testState.currSessionId = 'session-1';
    testState.sessions = [
      {
        session_id: 'session-1',
        display_name: 'Session 1',
      },
    ];
    testState.activeMessages = [
      {
        id: 'msg-1',
        content: {
          type: 'bot',
          message: [{ type: 'plain', text: 'hello' }],
        },
      },
    ];

    const wrapper = mountChat();
    await flushPromises();

    await wrapper.find('.open-refs-trigger').trigger('click');

    expect(wrapper.find('.refs-sidebar-stub').text()).toBe('1');
  });

  it('uses the current input model when regenerating without an explicit selection', async () => {
    testState.currSessionId = 'session-1';
    testState.sessions = [
      {
        session_id: 'session-1',
        display_name: 'Session 1',
      },
    ];
    testState.activeMessages = [
      {
        id: 'msg-1',
        content: {
          type: 'bot',
          message: [{ type: 'plain', text: 'hello' }],
        },
      },
    ];
    localStorage.setItem('selectedProvider', 'stale-provider');
    localStorage.setItem('selectedProviderModel', 'stale-model');

    const wrapper = mountChat();
    await flushPromises();
    await wrapper.find('.regenerate-trigger').trigger('click');
    await flushPromises();

    expect(testState.regenerateMessageMock).toHaveBeenCalledWith(
      'session-1',
      expect.objectContaining({ id: 'msg-1' }),
      'current-provider',
      'current-model',
    );
  });
});

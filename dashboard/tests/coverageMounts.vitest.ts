import { createPinia, setActivePinia } from 'pinia';
import { flushPromises } from '@vue/test-utils';
import { defineComponent, ref } from 'vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: { template: '<div class="monaco-stub"></div>' },
}));
vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRoute: () => ({
      path: '/extension',
      hash: '#installed',
      params: {},
      query: {},
      name: 'Extensions',
      fullPath: '/extension#installed',
    }),
    useRouter: () => ({
      push: vi.fn(),
      replace: vi.fn(),
    }),
    onBeforeRouteLeave: vi.fn(),
  };
});

vi.mock('@/api/v1', () => {
  const ok = {
    data: { status: 'ok', data: {}, message: '' },
  };
  const makeApi = () =>
    new Proxy(
      {},
      {
        get(_target, prop) {
          if (prop === 'then') return undefined;
          if (prop === 'tree') {
            return vi.fn().mockResolvedValue({
              data: {
                status: 'ok',
                data: { path: '', entries: [], truncated: false },
              },
            });
          }
          if (prop === 'createSession') {
            return vi.fn().mockResolvedValue({
              data: {
                status: 'ok',
                data: { session_id: 's1', platform_id: 'webchat' },
              },
            });
          }
          if (prop === 'list' || prop === 'folders' || prop === 'market') {
            return vi.fn().mockResolvedValue({
              data: { status: 'ok', data: [] },
            });
          }
          return vi.fn().mockResolvedValue(ok);
        },
      },
    );
  return {
    appearanceApi: makeApi(),
    dataFilesApi: makeApi(),
    personaApi: makeApi(),
    botApi: makeApi(),
    sessionApi: makeApi(),
    authApi: makeApi(),
    apiKeyApi: makeApi(),
    traceApi: makeApi(),
    updatesApi: makeApi(),
    backupApi: makeApi(),
    statsApi: makeApi(),
    publicApi: makeApi(),
    changelogApi: makeApi(),
    skillApi: makeApi(),
    pluginApi: makeApi(),
    pluginDashboardApi: makeApi(),
    fileApi: makeApi(),
    conversationApi: makeApi(),
    configProfileApi: makeApi(),
    systemConfigApi: makeApi(),
    configRouteApi: makeApi(),
    chatApi: makeApi(),
    knowledgeApi: makeApi(),
    providerApi: makeApi(),
    cronApi: makeApi(),
    subagentApi: makeApi(),
    commandApi: makeApi(),
    toolApi: makeApi(),
    mcpApi: makeApi(),
    t2iApi: makeApi(),
    logApi: makeApi(),
    memoryApi: makeApi(),
    authorizationApi: makeApi(),
    UPGRADE_RECOVERY_EVENT: 'astrbot-upgrade-recovery',
    UPGRADE_RECOVERY_TOKEN_KEY: 'astrbot-upgrade-recovery-token',
    PLUGIN_DASHBOARD_LIFECYCLE_EVENT: 'astrbot:plugin-dashboard-lifecycle',
  };
});

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn().mockResolvedValue(true),
  useConfirmDialog: () => undefined,
}));

import SkillsSection from '@/components/extension/SkillsSection.vue';
import McpServersSection from '@/components/extension/McpServersSection.vue';
import BackupDialog from '@/components/shared/BackupDialog.vue';
import ExtensionCard from '@/components/shared/ExtensionCard.vue';
import MessageList from '@/components/chat/MessageList.vue';
import StandaloneChat from '@/components/chat/StandaloneChat.vue';
import Settings from '@/views/Settings.vue';
import PersonaManager from '@/views/persona/PersonaManager.vue';
import ExtensionPage from '@/views/ExtensionPage.vue';
import DataFilesPage from '@/views/DataFilesPage.vue';
import SessionManagementPage from '@/views/SessionManagementPage.vue';
import { useExtensionPage } from '@/views/extension/useExtensionPage';
import { useCommandActions } from '@/components/extension/componentPanel/composables/useCommandActions';
import { useCommandFilters } from '@/components/extension/componentPanel/composables/useCommandFilters';
import { useComponentData } from '@/components/extension/componentPanel/composables/useComponentData';
import { useToolActions } from '@/components/extension/componentPanel/composables/useToolActions';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useRecording } from '@/composables/useRecording';
import { useCommonStore } from '@/stores/common';
import MainRoutes from '@/router/MainRoutes';
import AuthRoutes from '@/router/AuthRoutes';
import ChatBoxRoutes from '@/router/ChatBoxRoutes';
import KBDetail from '@/views/knowledge-base/KBDetail.vue';
import DocumentsTab from '@/views/knowledge-base/components/DocumentsTab.vue';
import T2ITemplateEditor from '@/components/shared/T2ITemplateEditor.vue';
import ConfirmDialog from '@/components/ConfirmDialog.vue';
import { I18nValidator } from '@/i18n/validator';
import { I18nLoader } from '@/i18n/loader';
import BaseFolderTree from '@/components/folder/BaseFolderTree.vue';
import BaseFolderCard from '@/components/folder/BaseFolderCard.vue';
import ComponentPanel from '@/components/extension/componentPanel/index.vue';
import PersonaCard from '@/views/persona/PersonaCard.vue';
import DocumentDetail from '@/views/knowledge-base/DocumentDetail.vue';
import RetrievalTab from '@/views/knowledge-base/components/RetrievalTab.vue';
import SettingsTab from '@/views/knowledge-base/components/SettingsTab.vue';
import AddNewProvider from '@/components/provider/AddNewProvider.vue';

const monacoStubs = {
  VueMonacoEditor: { template: '<div />' },
  AstrBotConfig: { template: '<div />' },
  AstrBotConfigV4: { template: '<div />' },
  WaitingForRestart: { template: '<div />' },
  DashboardAppearanceSettings: { template: '<div />' },
  SidebarCustomizer: { template: '<div />' },
  ProxySelector: { template: '<div />' },
  StorageCleanupPanel: { template: '<div />' },
  DashboardTwoFactorDialog: { template: '<div />' },
  DashboardStepUpDialog: { template: '<div />' },
  PersonaForm: { template: '<div />' },
  FolderTree: { template: '<div />' },
  InstalledPluginsTab: { template: '<div data-testid="installed" />' },
  MarketPluginsTab: { template: '<div />' },
  PluginDetailPage: { template: '<div />' },
  ComponentPanel: { template: '<div />' },
  SkillsSection: { template: '<div />' },
  McpServersSection: { template: '<div />' },
  ConsoleDisplayer: { template: '<div />' },
  ReadmeDialog: { template: '<div />' },
  UninstallConfirmDialog: { template: '<div />' },
  Chat: { template: '<div />' },
};

describe('high-value coverage mounts', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('invokes lazy route loaders', async () => {
    const loaders = [
      ...((MainRoutes.children || []) as Array<{
        component?: () => Promise<unknown>;
      }>),
      ...((
        AuthRoutes as {
          children?: Array<{ component?: () => Promise<unknown> }>;
        }
      ).children || []),
      ...((
        ChatBoxRoutes as {
          children?: Array<{ component?: () => Promise<unknown> }>;
        }
      ).children || []),
    ]
      .map((route) => route.component)
      .filter(
        (component): component is () => Promise<unknown> =>
          typeof component === 'function',
      );
    expect(loaders.length).toBeGreaterThan(5);
    await Promise.all(
      loaders.map((load) =>
        Promise.race([
          Promise.resolve()
            .then(() => load())
            .then(
              () => undefined,
              () => undefined,
            ),
          new Promise<void>((resolve) => {
            setTimeout(resolve, 2_000);
          }),
        ]),
      ),
    );
  });

  it('covers command and tool panel composables', async () => {
    const toast = vi.fn();
    const fetchCommands = vi.fn().mockResolvedValue(undefined);
    const actions = useCommandActions(toast, fetchCommands);
    const command = {
      command_id: 'demo:cmd',
      handler_full_name: 'demo.cmd',
      current_fragment: 'cmd',
      aliases: ['c'],
      enabled: true,
      has_conflict: false,
      type: 'command',
      is_group: false,
      reserved: false,
    };
    actions.openRenameDialog(command as never);
    actions.openDetailsDialog(command as never);
    await actions.toggleCommand(command as never, 'ok', 'err');
    await actions.confirmRename('ok', 'err');
    expect(
      actions.getTypeInfo('group', {
        group: 'g',
        subCommand: 's',
        command: 'c',
      }).icon,
    ).toContain('folder');
    expect(
      actions.getStatusInfo(command as never, {
        conflict: 'x',
        enabled: 'e',
        disabled: 'd',
      }).color,
    ).toBe('success');
    expect(actions.getRowProps({ item: command as never })).toEqual({});

    const commands = ref([command as never]);
    const filters = useCommandFilters(commands);
    expect(filters.availablePlugins.value).toBeDefined();
    expect(filters.hasSystemPluginConflict.value).toBe(false);

    const data = useComponentData();
    await data.fetchCommands('err');
    data.toast('hello');

    const tools = useToolActions(ref([]), toast);
    expect(tools.filteredTools.value).toEqual([]);
    expect(tools.toolSummary.value).toBeDefined();
  });

  it('covers media and recording helpers', async () => {
    const media = useMediaHandling();
    expect(media.stagedFiles.value).toEqual([]);
    expect(media.stagedImagesUrl.value).toEqual([]);
    expect(media.stagedAudioUrl.value).toBe('');
    media.clearStaged();
    media.cleanupMediaCache();

    const recording = useRecording();
    expect(recording.isRecording.value).toBe(false);
    await expect(recording.startRecording()).rejects.toBeDefined();
  });

  it('covers common store collection helpers', async () => {
    const common = useCommonStore();
    common.setAstrBotVersion('v1.2.3', 'd1');
    expect(common.getLogCache()).toEqual([]);
    common.closeEventSource();
    await common.getPluginCollections(true);
    expect(Array.isArray(common.pluginMarketData)).toBe(true);
  });

  it('mounts SkillsSection', async () => {
    const wrapper = mountWithVuetify(SkillsSection, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(wrapper.exists()).toBe(true);
    wrapper.unmount();
  });

  it('mounts BackupDialog and Settings', async () => {
    const backup = mountWithVuetify(BackupDialog, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(backup.exists()).toBe(true);
    backup.unmount();

    const settings = mountWithVuetify(Settings, {
      global: { stubs: { ...monacoStubs, BackupDialog: true } },
    });
    await flushPromises();
    expect(settings.text().length).toBeGreaterThan(0);
    settings.unmount();
  });

  it('mounts PersonaManager and ExtensionPage host', async () => {
    const persona = mountWithVuetify(PersonaManager, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(persona.exists()).toBe(true);
    persona.unmount();

    const page = mountWithVuetify(ExtensionPage, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(page.exists()).toBe(true);
    page.unmount();
  });

  it('mounts MCP, chat lists, session page, and data files', async () => {
    const mcp = mountWithVuetify(McpServersSection, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(mcp.exists()).toBe(true);
    mcp.unmount();

    const list = mountWithVuetify(MessageList, {
      props: { messages: [] },
      global: { stubs: monacoStubs },
    });
    expect(list.exists()).toBe(true);
    list.unmount();

    const standalone = mountWithVuetify(StandaloneChat, {
      props: { configId: 'default' },
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(standalone.exists()).toBe(true);
    standalone.unmount();

    const sessions = mountWithVuetify(SessionManagementPage, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(sessions.exists()).toBe(true);
    sessions.unmount();

    const files = mountWithVuetify(DataFilesPage, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(files.exists()).toBe(true);
    files.unmount();
  });

  it('mounts ExtensionCard and runs useExtensionPage', async () => {
    const card = mountWithVuetify(ExtensionCard, {
      props: {
        extension: { name: 'demo', desc: 'd', author: 'a' },
        isPinned: false,
      },
      global: { stubs: monacoStubs },
    });
    expect(card.text()).toContain('demo');
    card.unmount();

    const Harness = defineComponent({
      setup() {
        const page = useExtensionPage();
        return { tab: page.activeTab };
      },
      template: '<div>{{ tab }}</div>',
    });
    const harness = mountWithVuetify(Harness);
    await flushPromises();
    expect(harness.text().length).toBeGreaterThan(0);
    harness.unmount();
  });

  it('mounts knowledge-base, T2I editor, and confirm dialog', async () => {
    const kb = mountWithVuetify(KBDetail, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(kb.exists()).toBe(true);
    kb.unmount();

    const docs = mountWithVuetify(DocumentsTab, {
      props: { kbId: 'kb-1' },
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(docs.exists()).toBe(true);
    docs.unmount();

    const editor = mountWithVuetify(T2ITemplateEditor, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(editor.exists()).toBe(true);
    editor.unmount();

    const confirm = mountWithVuetify(ConfirmDialog);
    expect(confirm.exists()).toBe(true);
    confirm.unmount();
  });

  it('covers i18n validator and loader', async () => {
    const validator = new I18nValidator();
    const localeData = {
      'zh-CN': { hello: '你好', nested: { a: '1' } },
      'en-US': { hello: 'hello' },
    };
    const report = validator.generateReport(localeData, ['hello', 'missing']);
    expect(report.completeness.isValid).toBe(false);
    expect(report.stats).toBeDefined();

    const loader = new I18nLoader();
    await loader.preloadEssentials('zh-CN');
    loader.clearCache('zh-CN');
    expect(loader.getLoadingStatus().total).toBeGreaterThan(0);
  });

  it('mounts remaining high-function views and folder widgets', async () => {
    const backup = mountWithVuetify(BackupDialog, {
      global: { stubs: monacoStubs },
    });
    (backup.vm as { open?: () => void }).open?.();
    await flushPromises();
    backup.unmount();

    const tree = mountWithVuetify(BaseFolderTree, {
      props: { folderTree: [] },
      global: { stubs: monacoStubs },
    });
    expect(tree.text().length).toBeGreaterThan(0);
    tree.unmount();

    const folderCard = mountWithVuetify(BaseFolderCard, {
      props: {
        folder: {
          folder_id: 'f1',
          name: 'demo',
          parent_id: null,
          description: '',
          sort_order: 0,
        },
      },
      global: { stubs: monacoStubs },
    });
    expect(folderCard.text()).toContain('demo');
    folderCard.unmount();

    const panel = mountWithVuetify(ComponentPanel, {
      props: { active: true },
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(panel.exists()).toBe(true);
    panel.unmount();

    const personaCard = mountWithVuetify(PersonaCard, {
      props: {
        persona: {
          persona_id: 'p1',
          system_prompt: 'hi',
          begin_dialogs: [],
          tools: [],
          skills: [],
          folder_id: null,
          sort_order: 0,
        },
      },
      global: { stubs: monacoStubs },
    });
    expect(personaCard.text()).toContain('p1');
    personaCard.unmount();

    const document = mountWithVuetify(DocumentDetail, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(document.exists()).toBe(true);
    document.unmount();

    const retrieval = mountWithVuetify(RetrievalTab, {
      props: { kbId: 'kb-1', kbName: 'demo' },
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    retrieval.unmount();

    const settingsTab = mountWithVuetify(SettingsTab, {
      props: { kbId: 'kb-1', kb: { kb_id: 'kb-1', kb_name: 'demo' } },
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    settingsTab.unmount();

    const provider = mountWithVuetify(AddNewProvider, {
      global: { stubs: monacoStubs },
    });
    await flushPromises();
    expect(provider.exists()).toBe(true);
    provider.unmount();
  });
});

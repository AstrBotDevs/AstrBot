<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import '@/utils/monacoLoader';
import { conversationApi } from '@/api/v1';
import MessageList from '@/components/chat/MessageList.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';
import { copyToClipboard } from '@/utils/clipboard';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import type { MessagePart } from '@/domain/chat';
import { getPlatformIcon } from '@/utils/platformUtils';
import { resolveErrorMessage } from '@/utils/errorUtils';

type UmoInfo = {
  umo?: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
};

type Conversation = {
  platform_id: string;
  user_id: string;
  cid: string;
  title?: string | null;
  created_at?: number | string;
  updated_at?: number | string;
  history?: string | unknown[];
  umo_info?: UmoInfo;
};

type BotOption = {
  id: string;
  type: string;
};

type SessionGroup = {
  userId: string;
  sample: Conversation;
  items: Conversation[];
  selectedCount: number;
};

type ConversationListEntry =
  | { kind: 'session'; key: string; group: SessionGroup }
  | {
      kind: 'conversation';
      key: string;
      item: Conversation;
      grouped: boolean;
    };

type HistoryContentPart = {
  type?: string;
  text?: string;
  image_url?: { url?: string };
};

type HistoryToolCall = {
  id?: string;
  name?: string;
  arguments?: unknown;
  function?: { name?: string; arguments?: unknown };
};

type HistoryMessage = {
  role?: string;
  content?: string | HistoryContentPart[] | Record<string, unknown>;
  tool_call_id?: string;
  tool_calls?: HistoryToolCall[];
};

function parseHistory(history: unknown): HistoryMessage[] {
  if (Array.isArray(history)) {
    return history as HistoryMessage[];
  }
  if (typeof history === 'string' && history.trim()) {
    const parsed: unknown = JSON.parse(history);
    return Array.isArray(parsed) ? (parsed as HistoryMessage[]) : [];
  }
  return [];
}

const { locale } = useI18n();
const { tm } = useModuleI18n('features/conversation');
const route = useRoute();
const router = useRouter();
const customizerStore = useCustomizerStore();
const confirmDialog = useConfirmDialog();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const conversations = ref<Conversation[]>([]);
const availableBots = ref<BotOption[]>([]);
const keyword = ref('');
const selectedBotIds = ref<string[]>([]);
const selectedTypes = ref<string[]>([]);
const initialUmoQuery = Array.isArray(route.query.umo)
  ? route.query.umo[0]
  : route.query.umo;
const umoQuery = ref(
  typeof initialUmoQuery === 'string' ? initialUmoQuery : '',
);
const sortValue = ref('updated_at:desc');
const groupBySession = ref(false);
const mobileFiltersOpen = ref(false);
const expandedSessions = ref<Record<string, boolean>>({});
const page = ref(1);
const pageSize = 30;
const total = ref(0);
const totalPages = ref(1);
const listLoading = ref(false);
const listError = ref(false);
const listAbortController = ref<AbortController | null>(null);
const listRequestId = ref(0);

const selectedByKey = ref<Record<string, Conversation>>({});
const activeConversation = ref<Conversation | null>(null);
const conversationHistory = ref<HistoryMessage[]>([]);
const previewLoading = ref(false);
const previewRequestId = ref(0);
const previewPageScroll = ref(0);
const previewMessagesRef = ref<HTMLElement | null>(null);
const rawDataDialog = ref(false);
const rawHistoryText = ref('');

const editDialog = ref(false);
const editedTitle = ref('');
const editedConversation = ref<Conversation | null>(null);
const actionLoading = ref(false);
const snackbar = ref({ show: false, message: '', color: 'success' });
let fetchTimer: number | null = null;

const isDark = computed(() => customizerStore.isDark);
const hasFilters = computed(
  () =>
    Boolean(keyword.value.trim()) ||
    Boolean(umoQuery.value.trim()) ||
    selectedBotIds.value.length > 0 ||
    selectedTypes.value.length > 0 ||
    sortValue.value !== 'updated_at:desc',
);
const selectedItems = computed(() => Object.values(selectedByKey.value));
const allPageSelected = computed(
  () =>
    conversations.value.length > 0 &&
    conversations.value.every(
      (item) => selectedByKey.value[conversationKey(item)],
    ),
);
const somePageSelected = computed(
  () =>
    !allPageSelected.value &&
    conversations.value.some(
      (item) => selectedByKey.value[conversationKey(item)],
    ),
);
const sessionGroups = computed<SessionGroup[]>(() => {
  const groups = new Map<string, Conversation[]>();
  for (const item of conversations.value) {
    const items = groups.get(item.user_id);
    if (items) items.push(item);
    else groups.set(item.user_id, [item]);
  }
  return Array.from(groups, ([userId, items]) => ({
    userId,
    sample: items[0],
    items,
    selectedCount: items.filter(
      (item) => selectedByKey.value[conversationKey(item)],
    ).length,
  }));
});
const conversationListEntries = computed<ConversationListEntry[]>(() => {
  if (!groupBySession.value) {
    return conversations.value.map((item) => ({
      kind: 'conversation',
      key: conversationKey(item),
      item,
      grouped: false,
    }));
  }

  const entries: ConversationListEntry[] = [];
  for (const group of sessionGroups.value) {
    entries.push({ kind: 'session', key: `session:${group.userId}`, group });
    if (expandedSessions.value[group.userId]) {
      entries.push(
        ...group.items.map((item) => ({
          kind: 'conversation' as const,
          key: conversationKey(item),
          item,
          grouped: true,
        })),
      );
    }
  }
  return entries;
});
const botTypes = computed(() =>
  Object.fromEntries(availableBots.value.map((bot) => [bot.id, bot.type])),
);
const sortItems = computed(() => [
  {
    title: tm('workspace.filters.updatedDesc'),
    value: 'updated_at:desc',
  },
  {
    title: tm('workspace.filters.createdDesc'),
    value: 'created_at:desc',
  },
  {
    title: tm('workspace.filters.updatedAsc'),
    value: 'updated_at:asc',
  },
  {
    title: tm('workspace.filters.createdAsc'),
    value: 'created_at:asc',
  },
]);
const messageTypes = computed(() => [
  { label: tm('messageTypes.friend'), value: 'FriendMessage' },
  { label: tm('messageTypes.group'), value: 'GroupMessage' },
]);

const formattedMessages = computed(() => {
  const toolResultsById: Record<string, unknown> = {};
  for (const message of conversationHistory.value) {
    if (message?.role === 'tool' && message.tool_call_id) {
      toolResultsById[message.tool_call_id] = message.content;
    }
  }

  return conversationHistory.value
    .filter(
      (message) => message?.role === 'user' || message?.role === 'assistant',
    )
    .map((message) => {
      const parts: MessagePart[] = [];
      const content = message.content;
      if (typeof content === 'string' && content.trim()) {
        parts.push({ type: 'plain', text: content });
      } else if (Array.isArray(content)) {
        for (const item of content) {
          if (item?.type === 'text' && item.text) {
            parts.push({ type: 'plain', text: item.text });
          } else if (item?.type === 'image_url' && item.image_url?.url) {
            parts.push({ type: 'image', embedded_url: item.image_url.url });
          }
        }
      } else if (content && typeof content === 'object') {
        const text = Object.values(content)
          .filter((value) => typeof value === 'string' && value.trim())
          .join('\n');
        if (text) parts.push({ type: 'plain', text });
      }

      if (
        message.role === 'assistant' &&
        Array.isArray(message.tool_calls) &&
        message.tool_calls.length
      ) {
        parts.push({
          type: 'tool_call',
          tool_calls: message.tool_calls.map((toolCall) => ({
            id: toolCall.id,
            name: toolCall.function?.name || toolCall.name,
            args: toolCall.function?.arguments ?? toolCall.arguments,
            result: toolCall.id ? toolResultsById[toolCall.id] : undefined,
            ts: 0,
            finished_ts: 1,
          })),
        });
      }

      return {
        content: {
          type: message.role === 'user' ? 'user' : 'bot',
          message: parts.length ? parts : [{ type: 'plain', text: '' }],
        },
      };
    });
});

watch([keyword, umoQuery], () => {
  listAbortController.value?.abort();
  scheduleFetch();
});

watch([selectedBotIds, selectedTypes, sortValue, groupBySession], () => {
  cancelScheduledFetch();
  page.value = 1;
  expandedSessions.value =
    groupBySession.value && activeConversation.value
      ? { [activeConversation.value.user_id]: true }
      : {};
  void fetchConversations();
});

onMounted(async () => {
  await Promise.all([fetchFilterOptions(), fetchConversations()]);
});

onBeforeUnmount(() => {
  cancelScheduledFetch();
  listAbortController.value?.abort();
  previewRequestId.value += 1;
});

function conversationKey(item: Conversation) {
  return `${item.user_id}\u0000${item.cid}`;
}

function cancelScheduledFetch() {
  if (fetchTimer !== null) {
    window.clearTimeout(fetchTimer);
    fetchTimer = null;
  }
}

function scheduleFetch() {
  cancelScheduledFetch();
  fetchTimer = window.setTimeout(() => {
    fetchTimer = null;
    page.value = 1;
    void fetchConversations();
  }, 320);
}

function getUmoInfo(item: Conversation | null): Required<UmoInfo> {
  const umo = item?.user_id || item?.umo_info?.umo || '';
  const parts = umo.split(':');
  const info = item?.umo_info || {};
  return {
    umo,
    platform: info.platform || parts[0] || '',
    message_type: info.message_type || parts[1] || '',
    session_id: info.session_id || parts.slice(2).join(':') || umo,
    auto_name: info.auto_name || '',
    user_alias: info.user_alias || '',
    display_name: info.display_name || umo,
  };
}

function conversationIdentity(item: Conversation) {
  const info = getUmoInfo(item);
  return info.user_alias || info.auto_name || info.session_id || info.umo;
}

function hasReadableIdentity(item: Conversation) {
  const info = getUmoInfo(item);
  return Boolean(info.user_alias || info.auto_name);
}

function messageTypeLabel(item: Conversation | null) {
  const messageType = getUmoInfo(item).message_type;
  if (['GroupMessage', 'group'].includes(messageType)) {
    return tm('messageTypes.group');
  }
  if (['FriendMessage', 'friend', 'private'].includes(messageType)) {
    return tm('messageTypes.friend');
  }
  return tm('messageTypes.unknown');
}

function platformIcon(item: Conversation | BotOption) {
  const platformId = 'platform_id' in item ? item.platform_id : item.id;
  const platformType =
    'type' in item ? item.type : botTypes.value[platformId] || platformId;
  return getPlatformIcon(platformType);
}

function formatTimestamp(timestamp?: number | string) {
  if (timestamp === undefined || timestamp === null || timestamp === '') {
    return tm('status.unknown');
  }
  const numeric = Number(timestamp);
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(timestamp));
  if (Number.isNaN(date.getTime())) return tm('status.unknown');
  return new Intl.DateTimeFormat(locale.value || 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function notify(message: string, color = 'success') {
  snackbar.value = { show: true, message, color };
}

async function fetchFilterOptions() {
  try {
    const response = await conversationApi.filterOptions();
    if (response.data.status === 'ok') {
      availableBots.value = response.data.data?.bots || [];
    }
  } catch (error) {
    console.error('Failed to load conversation filter options:', error);
  }
}

async function fetchConversations() {
  cancelScheduledFetch();
  listAbortController.value?.abort();
  const controller = new AbortController();
  const requestId = ++listRequestId.value;
  listAbortController.value = controller;
  listLoading.value = true;
  listError.value = false;

  const [sortBy, sortOrder] = sortValue.value.split(':') as [
    'created_at' | 'updated_at',
    'asc' | 'desc',
  ];
  const params: Record<string, string | number | boolean> = {
    page: page.value,
    page_size: pageSize,
    include_history: false,
    sort_by: sortBy,
    sort_order: sortOrder,
    group_by_session: groupBySession.value,
  };
  if (keyword.value.trim()) params.keyword = keyword.value.trim();
  if (umoQuery.value.trim()) {
    params.umo = umoQuery.value.trim();
  } else {
    params.exclude_ids = 'astrbot';
    params.exclude_platforms = 'webchat';
  }
  if (selectedBotIds.value.length) {
    params.platforms = selectedBotIds.value.join(',');
  }
  if (selectedTypes.value.length) {
    params.message_types = selectedTypes.value.join(',');
  }

  try {
    const response = await conversationApi.list(params, {
      signal: controller.signal,
    });
    if (requestId !== listRequestId.value) return;
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('messages.fetchError'));
    }

    const data = response.data.data || {};
    conversations.value = Array.isArray(data.conversations)
      ? (data.conversations as Conversation[])
      : [];
    total.value = data.pagination?.total || 0;
    totalPages.value = Math.max(data.pagination?.total_pages || 1, 1);
    if (activeConversation.value) {
      const current = conversations.value.find(
        (item) =>
          conversationKey(item) === conversationKey(activeConversation.value!),
      );
      if (current) {
        activeConversation.value = {
          ...activeConversation.value,
          ...current,
        };
      }
    }
  } catch (error: unknown) {
    if (controller.signal.aborted || requestId !== listRequestId.value) return;
    listError.value = true;
    notify(resolveErrorMessage(error, tm('messages.fetchError')), 'error');
  } finally {
    if (requestId === listRequestId.value) {
      listLoading.value = false;
      if (listAbortController.value === controller) {
        listAbortController.value = null;
      }
    }
  }
}

function resetFilters() {
  cancelScheduledFetch();
  keyword.value = '';
  clearUmoQuery();
  selectedBotIds.value = [];
  selectedTypes.value = [];
  sortValue.value = 'updated_at:desc';
  page.value = 1;
}

function clearUmoQuery() {
  umoQuery.value = '';
  if ('umo' in route.query) {
    const query = { ...route.query };
    delete query.umo;
    void router.replace({ query });
  }
}

function toggleConversation(item: Conversation) {
  const key = conversationKey(item);
  const next = { ...selectedByKey.value };
  if (next[key]) delete next[key];
  else next[key] = item;
  selectedByKey.value = next;
}

function toggleCurrentPage() {
  const next = { ...selectedByKey.value };
  if (allPageSelected.value) {
    for (const item of conversations.value) delete next[conversationKey(item)];
  } else {
    for (const item of conversations.value) next[conversationKey(item)] = item;
  }
  selectedByKey.value = next;
}

function toggleSessionSelection(group: SessionGroup) {
  const next = { ...selectedByKey.value };
  if (group.selectedCount === group.items.length) {
    for (const item of group.items) delete next[conversationKey(item)];
  } else {
    for (const item of group.items) next[conversationKey(item)] = item;
  }
  selectedByKey.value = next;
}

function toggleSessionExpanded(userId: string) {
  expandedSessions.value = {
    ...expandedSessions.value,
    [userId]: !expandedSessions.value[userId],
  };
}

async function openConversation(item: Conversation) {
  previewPageScroll.value = window.scrollY;
  rawDataDialog.value = false;
  activeConversation.value = item;
  conversationHistory.value = [];
  previewLoading.value = true;
  const requestId = ++previewRequestId.value;
  try {
    const response = await conversationApi.get(item.user_id, item.cid);
    if (requestId !== previewRequestId.value) return;
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('messages.historyError'));
    }
    const detail = response.data.data || {};
    activeConversation.value = { ...item, ...detail };
    conversationHistory.value = parseHistory(detail.history);
  } catch (error: unknown) {
    if (requestId !== previewRequestId.value) return;
    conversationHistory.value = [];
    notify(resolveErrorMessage(error, tm('messages.historyError')), 'error');
  } finally {
    if (requestId === previewRequestId.value) {
      previewLoading.value = false;
      await nextTick();
      if (requestId === previewRequestId.value && previewMessagesRef.value) {
        previewMessagesRef.value.scrollTop =
          previewMessagesRef.value.scrollHeight;
      }
    }
  }
}

function closePreview() {
  const pageScroll = previewPageScroll.value;
  previewRequestId.value += 1;
  rawDataDialog.value = false;
  activeConversation.value = null;
  conversationHistory.value = [];
  previewLoading.value = false;
  void nextTick(
    () => void window.scrollTo({ top: pageScroll, behavior: 'auto' }),
  );
}

function openRawData() {
  rawHistoryText.value = JSON.stringify(conversationHistory.value, null, 2);
  rawDataDialog.value = true;
}

function startEditing(item: Conversation) {
  editedConversation.value = item;
  editedTitle.value = item.title || '';
  editDialog.value = true;
}

async function saveTitle() {
  if (!editedConversation.value) return;
  actionLoading.value = true;
  try {
    const item = editedConversation.value;
    const response = await conversationApi.update(item.user_id, item.cid, {
      title: editedTitle.value.trim(),
    });
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('messages.saveError'));
    }
    for (const conversation of conversations.value) {
      if (conversationKey(conversation) === conversationKey(item)) {
        conversation.title = editedTitle.value.trim();
      }
    }
    if (
      activeConversation.value &&
      conversationKey(activeConversation.value) === conversationKey(item)
    ) {
      activeConversation.value.title = editedTitle.value.trim();
    }
    editDialog.value = false;
    notify(tm('messages.saveSuccess'));
  } catch (error: unknown) {
    notify(resolveErrorMessage(error, tm('messages.saveError')), 'error');
  } finally {
    actionLoading.value = false;
  }
}

async function exportSelected() {
  if (!selectedItems.value.length) return;
  const stepUp = await requestStepUp({
    action: 'data.export_all',
    resourceType: 'conversation',
    resourceId: 'export',
  });
  if (!stepUp) return;
  actionLoading.value = true;
  try {
    const response = await conversationApi.export(
      {
        conversations: selectedItems.value.map((item) => ({
          user_id: item.user_id,
          cid: item.cid,
        })),
      },
      stepUp,
    );
    const url = window.URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `astrbot_conversations_${new Date()
      .toISOString()
      .replace(/[:.]/g, '-')}.jsonl`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    notify(tm('messages.exportSuccess'));
  } catch (error: unknown) {
    notify(resolveErrorMessage(error, tm('messages.exportError')), 'error');
  } finally {
    actionLoading.value = false;
  }
}

async function deleteSelected() {
  if (!selectedItems.value.length) return;
  const confirmed = await askForConfirmationDialog(
    tm('dialogs.batchDelete.message', { count: selectedItems.value.length }),
    confirmDialog,
  );
  if (!confirmed) return;

  actionLoading.value = true;
  const selectedCount = selectedItems.value.length;
  const deletingKeys = new Set(selectedItems.value.map(conversationKey));
  try {
    const response = await conversationApi.batchDelete({
      conversations: selectedItems.value.map((item) => ({
        user_id: item.user_id,
        cid: item.cid,
      })),
    });
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('messages.batchDeleteError'));
    }
    const result = response.data.data || {};
    selectedByKey.value = {};
    if (
      activeConversation.value &&
      deletingKeys.has(conversationKey(activeConversation.value))
    ) {
      closePreview();
    }
    if (conversations.value.length === selectedCount && page.value > 1) {
      page.value -= 1;
    }
    await fetchConversations();
    if (result.failed_count) {
      notify(
        tm('messages.batchDeletePartial', {
          deleted: result.deleted_count ?? 0,
          failed: result.failed_count ?? 0,
        }),
        'error',
      );
    } else {
      notify(
        tm('messages.batchDeleteSuccess', {
          count: result.deleted_count || deletingKeys.size,
        }),
      );
    }
  } catch (error: unknown) {
    notify(
      resolveErrorMessage(error, tm('messages.batchDeleteError')),
      'error',
    );
  } finally {
    actionLoading.value = false;
  }
}

async function copyUmo() {
  if (!activeConversation.value) return;
  const copied = await copyToClipboard(activeConversation.value.user_id);
  notify(
    copied ? tm('messages.copySuccess') : tm('messages.copyError'),
    copied ? 'success' : 'error',
  );
}

async function copyRawData() {
  if (!rawHistoryText.value) return;
  const copied = await copyToClipboard(rawHistoryText.value);
  notify(
    copied ? tm('messages.copySuccess') : tm('messages.copyError'),
    copied ? 'success' : 'error',
  );
}

function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) {
    return;
  }
  page.value = nextPage;
  void fetchConversations();
}
</script>

<template>
  <div
    class="conversation-workspace"
    :class="{
      'is-dark': isDark,
      'conversation-workspace--preview-open': activeConversation,
    }"
  >
    <div class="workspace-actions">
      <v-btn
        class="mobile-filter-trigger"
        size="small"
        :variant="hasFilters ? 'tonal' : 'text'"
        :aria-expanded="mobileFiltersOpen"
        aria-haspopup="dialog"
        @click="mobileFiltersOpen = true"
      >
        <v-icon size="15" aria-hidden="true">mdi-tune</v-icon>
        <span>{{ tm('workspace.filters.title') }}</span>
        <span v-if="hasFilters" class="filter-status-dot" aria-hidden="true" />
      </v-btn>
      <v-btn
        size="small"
        variant="text"
        :loading="listLoading"
        @click="fetchConversations"
      >
        <v-icon size="15" aria-hidden="true">mdi-refresh</v-icon>
        <span>{{ tm('workspace.actions.refresh') }}</span>
      </v-btn>
    </div>

    <button
      v-if="mobileFiltersOpen"
      type="button"
      class="mobile-filter-backdrop"
      :aria-label="tm('workspace.filters.close')"
      @click="mobileFiltersOpen = false"
    />
    <button
      v-if="activeConversation"
      type="button"
      class="mobile-preview-backdrop"
      :aria-label="tm('workspace.preview.close')"
      @click="closePreview"
    />

    <main
      class="workspace-grid"
      :class="{ 'workspace-grid--preview': activeConversation }"
    >
      <aside
        class="workspace-card filter-panel"
        :class="{ 'filter-panel--mobile-open': mobileFiltersOpen }"
      >
        <div class="panel-heading">
          <span>{{ tm('workspace.filters.title') }}</span>
          <div class="filter-heading-actions">
            <v-btn
              v-if="hasFilters"
              icon
              size="x-small"
              variant="text"
              :aria-label="tm('workspace.filters.reset')"
              @click="resetFilters"
            >
              <v-icon size="15" aria-hidden="true">mdi-restore</v-icon>
              <v-tooltip activator="parent" location="top">
                {{ tm('workspace.filters.reset') }}
              </v-tooltip>
            </v-btn>
            <v-btn
              class="mobile-filter-close"
              icon
              size="x-small"
              variant="text"
              :aria-label="tm('workspace.filters.close')"
              @click="mobileFiltersOpen = false"
            >
              <v-icon size="17" aria-hidden="true">mdi-close</v-icon>
            </v-btn>
          </div>
        </div>

        <div class="filter-block filter-block--first">
          <label class="filter-label" for="conversation-keyword">
            {{ tm('workspace.filters.keyword') }}
          </label>
          <v-text-field
            id="conversation-keyword"
            v-model="keyword"
            :placeholder="tm('workspace.filters.keywordPlaceholder')"
            density="compact"
            variant="solo-filled"
            flat
            clearable
            hide-details
          >
            <template #prepend-inner>
              <v-icon size="16" aria-hidden="true">mdi-magnify</v-icon>
            </template>
          </v-text-field>
        </div>

        <div class="filter-block">
          <div class="filter-label">{{ tm('workspace.filters.robots') }}</div>
          <div v-if="availableBots.length" class="robot-options">
            <label
              v-for="botOption in availableBots"
              :key="botOption.id"
              class="robot-option"
            >
              <span class="robot-select">
                <v-checkbox-btn
                  v-model="selectedBotIds"
                  :value="botOption.id"
                  density="compact"
                  hide-details
                />
              </span>
              <img
                v-if="platformIcon(botOption)"
                :src="platformIcon(botOption)"
                alt=""
                class="platform-icon"
              />
              <span v-else class="platform-icon platform-icon--fallback">
                <v-icon size="15" aria-hidden="true">mdi-robot</v-icon>
              </span>
              <span class="robot-id">{{ botOption.id }}</span>
            </label>
          </div>
          <div v-else class="filter-empty">
            {{ tm('workspace.filters.robotEmpty') }}
          </div>
        </div>

        <div class="filter-block">
          <div class="filter-label">{{ tm('workspace.filters.types') }}</div>
          <div class="type-options">
            <button
              v-for="typeOption in messageTypes"
              :key="typeOption.value"
              type="button"
              class="type-option"
              :class="{
                'type-option--selected': selectedTypes.includes(
                  typeOption.value,
                ),
              }"
              @click="
                selectedTypes = selectedTypes.includes(typeOption.value)
                  ? selectedTypes.filter((value) => value !== typeOption.value)
                  : [...selectedTypes, typeOption.value]
              "
            >
              <v-icon
                v-if="selectedTypes.includes(typeOption.value)"
                size="14"
                aria-hidden="true"
                >mdi-check</v-icon
              >
              {{ typeOption.label }}
            </button>
          </div>
        </div>

        <div class="filter-block">
          <label class="filter-label" for="conversation-umo">
            {{ tm('workspace.filters.umo') }}
          </label>
          <v-text-field
            id="conversation-umo"
            v-model="umoQuery"
            :placeholder="tm('workspace.filters.umoPlaceholder')"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
          >
            <template #append-inner>
              <button
                v-if="umoQuery"
                type="button"
                class="filter-input-clear"
                :aria-label="tm('workspace.filters.reset')"
                @mousedown.prevent
                @click.stop="clearUmoQuery"
              >
                <v-icon size="18" aria-hidden="true">mdi-close</v-icon>
              </button>
            </template>
          </v-text-field>
        </div>

        <div class="filter-block filter-block--last">
          <label class="filter-label" for="conversation-sort">
            {{ tm('workspace.filters.sort') }}
          </label>
          <v-select
            id="conversation-sort"
            v-model="sortValue"
            :items="sortItems"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
          />
        </div>

        <div class="mobile-filter-footer">
          <v-btn block variant="tonal" @click="mobileFiltersOpen = false">
            {{ tm('workspace.filters.done') }}
          </v-btn>
        </div>
      </aside>

      <section class="workspace-card conversation-panel">
        <header class="conversation-toolbar">
          <div>
            <div class="panel-heading panel-heading--list">
              {{ tm('workspace.list.title') }}
            </div>
            <div class="toolbar-meta">
              {{
                selectedItems.length
                  ? tm('workspace.list.selected', {
                      count: selectedItems.length,
                    })
                  : tm(
                      groupBySession
                        ? 'workspace.list.sessionTotal'
                        : 'workspace.list.total',
                      { count: total },
                    )
              }}
            </div>
          </div>
          <div class="toolbar-actions">
            <div class="group-switch">
              <span>{{ tm('workspace.list.groupBySession') }}</span>
              <v-switch
                v-model="groupBySession"
                color="primary"
                density="compact"
                hide-details
                inset
                :aria-label="tm('workspace.list.groupBySession')"
              />
            </div>
            <template v-if="selectedItems.length">
              <v-btn
                icon
                size="small"
                variant="text"
                :disabled="actionLoading"
                :aria-label="tm('workspace.actions.export')"
                @click="exportSelected"
              >
                <v-icon size="17" aria-hidden="true">mdi-download</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ tm('workspace.actions.export') }}
                </v-tooltip>
              </v-btn>
              <v-btn
                icon
                size="small"
                color="error"
                variant="text"
                :disabled="actionLoading"
                :aria-label="tm('workspace.actions.delete')"
                @click="deleteSelected"
              >
                <v-icon size="17" aria-hidden="true">mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ tm('workspace.actions.delete') }}
                </v-tooltip>
              </v-btn>
            </template>
          </div>
        </header>

        <label class="select-page-row">
          <v-checkbox-btn
            :model-value="allPageSelected"
            :indeterminate="somePageSelected"
            density="compact"
            hide-details
            @update:model-value="toggleCurrentPage"
          />
          <span>{{ tm('workspace.list.selectPage') }}</span>
        </label>

        <div class="conversation-list">
          <div v-if="listLoading && !conversations.length" class="panel-state">
            <v-progress-circular indeterminate size="28" width="3" />
          </div>
          <div
            v-else-if="!conversations.length"
            class="panel-state panel-state--empty"
          >
            <v-icon size="26" aria-hidden="true">mdi-magnify</v-icon>
            <span>
              {{
                hasFilters
                  ? tm('workspace.list.filteredEmpty')
                  : tm('workspace.list.empty')
              }}
            </span>
            <v-btn
              v-if="listError"
              size="small"
              variant="tonal"
              @click="fetchConversations"
            >
              {{ tm('workspace.actions.refresh') }}
            </v-btn>
          </div>
          <template
            v-for="entry in conversationListEntries"
            v-else
            :key="entry.key"
          >
            <div
              v-if="entry.kind === 'session'"
              class="session-group-row"
              :class="{
                'session-group-row--active':
                  activeConversation?.user_id === entry.group.userId,
              }"
            >
              <span class="row-select" @click.stop>
                <v-checkbox-btn
                  :model-value="
                    entry.group.selectedCount === entry.group.items.length
                  "
                  :indeterminate="
                    entry.group.selectedCount > 0 &&
                    entry.group.selectedCount < entry.group.items.length
                  "
                  density="compact"
                  hide-details
                  @update:model-value="toggleSessionSelection(entry.group)"
                />
              </span>
              <span class="row-platform">
                <img
                  v-if="platformIcon(entry.group.sample)"
                  :src="platformIcon(entry.group.sample)"
                  alt=""
                  class="platform-icon platform-icon--row"
                />
                <span v-else class="platform-icon platform-icon--fallback">
                  <v-icon size="16" aria-hidden="true">mdi-robot</v-icon>
                </span>
              </span>
              <button
                type="button"
                class="session-group-main"
                :aria-expanded="Boolean(expandedSessions[entry.group.userId])"
                @click="toggleSessionExpanded(entry.group.userId)"
              >
                <span class="row-content">
                  <span
                    class="session-group-name"
                    :class="{
                      'row-identity--named': hasReadableIdentity(
                        entry.group.sample,
                      ),
                    }"
                    :title="entry.group.userId"
                  >
                    {{ conversationIdentity(entry.group.sample) }}
                  </span>
                  <span class="row-meta">
                    <span>{{ entry.group.sample.platform_id }}</span>
                    <span aria-hidden="true">·</span>
                    <span>{{ messageTypeLabel(entry.group.sample) }}</span>
                    <span aria-hidden="true">·</span>
                    <span>
                      {{
                        tm('workspace.list.conversationCount', {
                          count: entry.group.items.length,
                        })
                      }}
                    </span>
                  </span>
                </span>
                <v-icon
                  v-if="expandedSessions[entry.group.userId]"
                  size="16"
                  aria-hidden="true"
                  >mdi-chevron-down</v-icon
                >
                <v-icon v-else size="16" aria-hidden="true"
                  >mdi-chevron-right</v-icon
                >
              </button>
            </div>
            <button
              v-else
              type="button"
              class="conversation-row"
              :class="{
                'conversation-row--grouped': entry.grouped,
                'conversation-row--active':
                  activeConversation &&
                  conversationKey(activeConversation) ===
                    conversationKey(entry.item),
              }"
              @click="openConversation(entry.item)"
            >
              <span class="row-select" @click.stop>
                <v-checkbox-btn
                  :model-value="
                    Boolean(selectedByKey[conversationKey(entry.item)])
                  "
                  density="compact"
                  hide-details
                  @update:model-value="toggleConversation(entry.item)"
                />
              </span>
              <span v-if="!entry.grouped" class="row-platform">
                <img
                  v-if="platformIcon(entry.item)"
                  :src="platformIcon(entry.item)"
                  alt=""
                  class="platform-icon platform-icon--row"
                />
                <span v-else class="platform-icon platform-icon--fallback">
                  <v-icon size="16" aria-hidden="true">mdi-robot</v-icon>
                </span>
              </span>
              <span class="row-content">
                <span class="row-title-line">
                  <span class="row-title">
                    {{ entry.item.title || tm('status.noTitle') }}
                  </span>
                  <span
                    class="row-edit"
                    role="button"
                    tabindex="0"
                    :aria-label="tm('workspace.actions.editTitle')"
                    @click.stop="startEditing(entry.item)"
                    @keydown.enter.stop="startEditing(entry.item)"
                  >
                    <v-icon size="13" aria-hidden="true">mdi-pencil</v-icon>
                  </span>
                </span>
                <span class="row-meta">
                  <span>{{ entry.item.platform_id }}</span>
                  <span aria-hidden="true">·</span>
                  <span>{{ messageTypeLabel(entry.item) }}</span>
                  <template v-if="!entry.grouped">
                    <span aria-hidden="true">·</span>
                    <span
                      class="row-identity"
                      :class="{
                        'row-identity--named': hasReadableIdentity(entry.item),
                      }"
                      :title="entry.item.user_id"
                    >
                      {{ conversationIdentity(entry.item) }}
                    </span>
                  </template>
                </span>
              </span>
              <span class="row-time">
                {{ formatTimestamp(entry.item.updated_at) }}
              </span>
            </button>
          </template>
        </div>

        <footer class="pagination-bar">
          <v-btn
            icon
            size="x-small"
            variant="text"
            :disabled="page <= 1 || listLoading"
            :aria-label="tm('workspace.list.previous')"
            @click="changePage(page - 1)"
          >
            <v-icon size="17" aria-hidden="true">mdi-chevron-left</v-icon>
          </v-btn>
          <span>{{
            tm('workspace.list.page', { page, total: totalPages })
          }}</span>
          <v-btn
            icon
            size="x-small"
            variant="text"
            :disabled="page >= totalPages || listLoading"
            :aria-label="tm('workspace.list.next')"
            @click="changePage(page + 1)"
          >
            <v-icon size="17" aria-hidden="true">mdi-chevron-right</v-icon>
          </v-btn>
        </footer>
      </section>

      <section v-if="activeConversation" class="workspace-card preview-panel">
        <header class="preview-header">
          <div class="preview-heading">
            <span class="preview-eyebrow">{{
              tm('workspace.preview.title')
            }}</span>
            <span class="preview-title">
              {{ activeConversation.title || tm('status.noTitle') }}
            </span>
          </div>
          <div class="preview-actions">
            <v-btn
              icon
              size="small"
              variant="text"
              :disabled="previewLoading"
              :aria-label="tm('workspace.preview.rawData')"
              @click="openRawData"
            >
              <v-icon size="17" aria-hidden="true">mdi-code-braces</v-icon>
              <v-tooltip activator="parent" location="top">
                {{ tm('workspace.preview.rawData') }}
              </v-tooltip>
            </v-btn>
            <v-btn
              icon
              size="small"
              variant="text"
              :aria-label="tm('workspace.actions.editTitle')"
              @click="startEditing(activeConversation)"
            >
              <v-icon size="16" aria-hidden="true">mdi-pencil</v-icon>
            </v-btn>
            <v-btn
              icon
              size="small"
              variant="text"
              :aria-label="tm('workspace.preview.close')"
              @click="closePreview"
            >
              <v-icon size="18" aria-hidden="true">mdi-close</v-icon>
            </v-btn>
          </div>
        </header>

        <div class="preview-identity">
          <img
            v-if="platformIcon(activeConversation)"
            :src="platformIcon(activeConversation)"
            alt=""
            class="platform-icon platform-icon--preview"
          />
          <span v-else class="platform-icon platform-icon--fallback">
            <v-icon size="16" aria-hidden="true">mdi-robot</v-icon>
          </span>
          <div class="preview-identity-copy">
            <span
              class="preview-name"
              :class="{
                'preview-name--named': hasReadableIdentity(activeConversation),
              }"
              :title="activeConversation.user_id"
            >
              {{ conversationIdentity(activeConversation) }}
            </span>
            <span class="preview-meta">
              {{ activeConversation.platform_id }} ·
              {{ messageTypeLabel(activeConversation) }} ·
              {{ formatTimestamp(activeConversation.updated_at) }}
            </span>
          </div>
          <v-btn
            icon
            size="x-small"
            variant="text"
            :aria-label="tm('workspace.preview.copyUmo')"
            @click="copyUmo"
          >
            <v-icon size="16">mdi-content-copy</v-icon>
          </v-btn>
        </div>

        <div ref="previewMessagesRef" class="preview-messages">
          <div v-if="previewLoading" class="panel-state">
            <v-progress-circular indeterminate size="28" width="3" />
            <span>{{ tm('workspace.preview.loading') }}</span>
          </div>
          <div
            v-else-if="!formattedMessages.length"
            class="panel-state panel-state--empty"
          >
            <span>{{ tm('workspace.preview.empty') }}</span>
          </div>
          <MessageList v-else :messages="formattedMessages" :is-dark="isDark" />
        </div>
      </section>
    </main>

    <v-dialog v-model="rawDataDialog" max-width="900" scrollable>
      <v-card class="raw-data-card">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 raw-data-title">
          <span>{{ tm('workspace.preview.rawData') }}</span>
          <v-btn
            icon
            size="small"
            variant="text"
            :aria-label="tm('workspace.preview.copyRawData')"
            @click="copyRawData"
          >
            <v-icon size="17" aria-hidden="true">mdi-content-copy</v-icon>
            <v-tooltip activator="parent" location="top">
              {{ tm('workspace.preview.copyRawData') }}
            </v-tooltip>
          </v-btn>
        </v-card-title>
        <v-card-text class="pa-6">
          <div class="raw-data-editor">
            <VueMonacoEditor
              v-model:value="rawHistoryText"
              theme="vs-dark"
              language="json"
              :options="{
                automaticLayout: true,
                domReadOnly: true,
                fontSize: 13,
                minimap: { enabled: false },
                readOnly: true,
                scrollBeyondLastLine: false,
                tabSize: 2,
                wordWrap: 'on',
                wrappingIndent: 'indent',
              }"
            />
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="rawDataDialog = false">
            {{ tm('dialogs.view.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="editDialog" max-width="500">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm('dialogs.edit.title') }}
        </v-card-title>
        <v-card-text class="pa-6 pb-2">
          <v-text-field
            v-model="editedTitle"
            :label="tm('dialogs.edit.titleLabel')"
            :placeholder="tm('dialogs.edit.titlePlaceholder')"
            variant="solo-filled"
            flat
            autofocus
            @keyup.enter="saveTitle"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn
            variant="text"
            :disabled="actionLoading"
            @click="editDialog = false"
          >
            {{ tm('dialogs.edit.cancel') }}
          </v-btn>
          <v-btn
            variant="tonal"
            color="primary"
            :loading="actionLoading"
            @click="saveTitle"
          >
            {{ tm('dialogs.edit.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
    </v-snackbar>
    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />
  </div>
</template>

<style scoped>
.conversation-workspace {
  --workspace-card: #f5f6f7;
  --workspace-surface: rgb(var(--v-theme-surface));
  --workspace-muted: rgba(var(--v-theme-on-surface), 0.58);
  --workspace-subtle: rgba(var(--v-theme-on-surface), 0.08);
  min-height: 0;
  overflow: hidden;
  padding: 0 12px 8px;
}

.conversation-workspace.is-dark {
  --workspace-card: rgba(var(--v-theme-on-surface), 0.06);
  --workspace-surface: rgba(var(--v-theme-on-surface), 0.035);
  --workspace-subtle: rgba(var(--v-theme-on-surface), 0.1);
}

.workspace-actions {
  align-items: center;
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  min-height: 42px;
}

.workspace-actions :deep(.v-btn__content) {
  gap: 6px;
}

.mobile-filter-trigger,
.mobile-filter-backdrop,
.mobile-preview-backdrop,
.mobile-filter-close,
.mobile-filter-footer {
  display: none;
}

.filter-status-dot {
  background: rgb(var(--v-theme-primary));
  border-radius: 999px;
  height: 6px;
  width: 6px;
}

.workspace-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(220px, 252px) minmax(420px, 1fr);
  grid-template-rows: minmax(0, 1fr);
  height: calc(100dvh - 154px);
  margin: 0 auto;
  max-width: 1560px;
  min-height: 0;
}

.workspace-grid--preview {
  grid-template-columns:
    minmax(210px, 230px)
    minmax(340px, 0.78fr)
    minmax(430px, 1.22fr);
}

.workspace-card {
  background: var(--workspace-card);
  border: 0;
  border-radius: 16px;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.filter-panel {
  align-self: start;
  padding: 18px;
}

.filter-heading-actions {
  align-items: center;
  display: flex;
}

.panel-heading {
  align-items: center;
  display: flex;
  font-size: 0.92rem;
  font-weight: 650;
  justify-content: space-between;
  min-height: 28px;
}

.panel-heading--list {
  display: block;
  min-height: auto;
}

.filter-block {
  border-top: 1px solid var(--workspace-subtle);
  margin-top: 18px;
  padding-top: 18px;
}

.filter-block--first {
  border-top: 0;
  margin-top: 14px;
  padding-top: 0;
}

.filter-block--last {
  padding-bottom: 2px;
}

.filter-label {
  color: rgba(var(--v-theme-on-surface), 0.76);
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: 8px;
}

.filter-panel :deep(.v-field) {
  background: var(--workspace-surface);
  border-radius: 10px;
  box-shadow: none;
  font-size: 0.8rem;
}

.filter-panel :deep(.v-field__overlay) {
  opacity: 0;
}

.filter-input-clear {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 50%;
  color: rgba(var(--v-theme-on-surface), 0.54);
  cursor: pointer;
  display: inline-flex;
  height: 28px;
  justify-content: center;
  padding: 0;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;
  width: 28px;
}

.filter-input-clear:hover {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgba(var(--v-theme-on-surface), 0.82);
}

.robot-options {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-inline: -6px;
  max-height: clamp(112px, calc(100dvh - 666px), 238px);
  overflow-y: auto;
}

.robot-option {
  align-items: center;
  border-radius: 9px;
  cursor: pointer;
  display: grid;
  gap: 7px;
  grid-template-columns: 28px 22px minmax(0, 1fr);
  min-height: 38px;
  padding: 2px 7px 2px 0;
}

.robot-select {
  align-items: center;
  display: flex;
  grid-column: 1;
  grid-row: 1;
  justify-content: center;
  min-width: 28px;
}

.robot-option > .platform-icon {
  grid-column: 2;
  grid-row: 1;
}

.robot-option > .robot-id {
  grid-column: 3;
  grid-row: 1;
}

.robot-select :deep(.v-selection-control) {
  min-width: 28px;
}

.robot-option:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
}

.platform-icon {
  border-radius: 5px;
  display: block;
  height: 20px;
  object-fit: contain;
  width: 20px;
}

.platform-icon--fallback {
  align-items: center;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
  display: inline-flex;
  justify-content: center;
}

.robot-id {
  font-size: 0.78rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-empty {
  color: var(--workspace-muted);
  font-size: 0.75rem;
  line-height: 1.5;
  padding: 4px 0;
}

.type-options {
  display: grid;
  gap: 7px;
  grid-template-columns: 1fr 1fr;
}

.type-option {
  align-items: center;
  background: var(--workspace-surface);
  border: 0;
  border-radius: 9px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  cursor: pointer;
  display: flex;
  font-size: 0.76rem;
  gap: 5px;
  height: 34px;
  justify-content: center;
}

.type-option:hover {
  color: rgb(var(--v-theme-on-surface));
}

.type-option--selected {
  background: rgba(var(--v-theme-primary), 0.11);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

.conversation-panel,
.preview-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.conversation-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  min-height: 68px;
  padding: 14px 18px 10px;
}

.toolbar-meta {
  color: var(--workspace-muted);
  font-size: 0.72rem;
  margin-top: 3px;
}

.toolbar-actions {
  align-items: center;
  display: flex;
  min-height: 36px;
}

.group-switch {
  align-items: center;
  color: var(--workspace-muted);
  display: flex;
  font-size: 0.72rem;
  gap: 7px;
  margin-right: 4px;
  white-space: nowrap;
}

.group-switch :deep(.v-switch) {
  flex: 0 0 auto;
}

.group-switch :deep(.v-selection-control) {
  min-height: 32px;
}

.select-page-row {
  align-items: center;
  color: var(--workspace-muted);
  display: flex;
  font-size: 0.72rem;
  min-height: 36px;
  padding: 0 14px;
}

.conversation-list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  position: relative;
}

.session-group-row {
  align-items: center;
  border-top: 1px solid var(--workspace-subtle);
  display: grid;
  gap: 9px;
  grid-template-columns: 30px 28px minmax(0, 1fr);
  min-height: 62px;
  padding: 7px 15px 7px 10px;
  transition: background-color 0.15s ease;
}

.session-group-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.038);
}

.session-group-row--active {
  background: rgba(var(--v-theme-primary), 0.075);
}

.session-group-row--active:hover {
  background: rgba(var(--v-theme-primary), 0.1);
}

.session-group-main {
  align-items: center;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) auto;
  min-width: 0;
  padding: 0;
  text-align: left;
  width: 100%;
}

.session-group-name {
  font-size: 0.82rem;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-group-main:hover .session-group-name {
  color: rgb(var(--v-theme-primary));
}

.conversation-row {
  align-items: center;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--workspace-subtle);
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 9px;
  grid-template-columns: 30px 28px minmax(0, 1fr) auto;
  min-height: 66px;
  padding: 8px 15px 8px 10px;
  text-align: left;
  transition: background-color 0.15s ease;
  width: 100%;
}

.conversation-row--grouped {
  background: rgba(var(--v-theme-surface), 0.66);
  grid-template-columns: 30px minmax(0, 1fr) auto;
  min-height: 58px;
  padding-left: 38px;
}

.conversation-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.038);
}

.conversation-row--active {
  background: rgba(var(--v-theme-primary), 0.095);
}

.conversation-row--active:hover {
  background: rgba(var(--v-theme-primary), 0.12);
}

.row-select {
  display: inline-flex;
}

.row-platform {
  align-items: center;
  display: flex;
  justify-content: center;
}

.platform-icon--row {
  height: 23px;
  width: 23px;
}

.row-content,
.row-title-line,
.row-meta {
  min-width: 0;
}

.row-content {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.row-title-line {
  align-items: center;
  display: flex;
  gap: 4px;
}

.row-title {
  font-size: 0.82rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-edit {
  align-items: center;
  border-radius: 5px;
  color: var(--workspace-muted);
  display: inline-flex;
  flex: 0 0 auto;
  justify-content: center;
  opacity: 0;
  padding: 3px;
}

.conversation-row:hover .row-edit,
.row-edit:focus-visible {
  opacity: 1;
}

.row-meta {
  align-items: center;
  color: var(--workspace-muted);
  display: flex;
  font-size: 0.69rem;
  gap: 5px;
  overflow: hidden;
  white-space: nowrap;
}

.row-identity {
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-identity--named,
.preview-name--named {
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}

.row-time {
  align-self: start;
  color: var(--workspace-muted);
  font-size: 0.66rem;
  padding-top: 3px;
  white-space: nowrap;
}

.panel-state {
  align-items: center;
  color: var(--workspace-muted);
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 12px;
  justify-content: center;
  min-height: 240px;
  padding: 30px;
  text-align: center;
}

.panel-state--empty {
  font-size: 0.8rem;
}

.pagination-bar {
  align-items: center;
  border-top: 1px solid var(--workspace-subtle);
  color: var(--workspace-muted);
  display: flex;
  font-size: 0.7rem;
  gap: 8px;
  justify-content: center;
  min-height: 46px;
}

.preview-header {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
  min-height: 68px;
  padding: 14px 14px 10px 18px;
}

.preview-heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.preview-eyebrow {
  color: var(--workspace-muted);
  font-size: 0.67rem;
  margin-bottom: 4px;
}

.preview-title {
  font-size: 0.92rem;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-actions {
  display: flex;
  flex: 0 0 auto;
}

.preview-identity {
  align-items: center;
  background: var(--workspace-surface);
  border-radius: 11px;
  display: grid;
  gap: 10px;
  grid-template-columns: 28px minmax(0, 1fr) 28px;
  margin: 0 14px 12px;
  min-height: 54px;
  padding: 8px 10px;
}

.platform-icon--preview {
  height: 26px;
  width: 26px;
}

.preview-identity-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.preview-name {
  font-size: 0.78rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-meta {
  color: var(--workspace-muted);
  font-size: 0.67rem;
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-messages {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 2px 6px 10px;
}

.preview-messages :deep(.messages-list) {
  padding: 12px 8px 20px;
}

.preview-messages :deep(.message-row) {
  margin-bottom: 14px;
}

.preview-messages :deep(.bot-avatar) {
  display: none;
}

.raw-data-card {
  max-height: min(82dvh, 760px);
}

.raw-data-title {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.raw-data-editor {
  border-radius: 12px;
  height: min(62dvh, 580px);
  min-height: 360px;
  overflow: hidden;
}

@media (min-width: 801px) {
  :global(html:has(.conversation-workspace)),
  :global(body:has(.conversation-workspace)) {
    overflow: hidden;
  }
}

@media (max-width: 1260px) {
  .workspace-grid--preview {
    grid-template-columns:
      minmax(180px, 200px)
      minmax(290px, 0.82fr)
      minmax(340px, 1.18fr);
  }
}

@media (max-width: 800px) {
  :global(html:has(.conversation-workspace--preview-open)),
  :global(body:has(.conversation-workspace--preview-open)) {
    overflow: hidden;
  }

  .conversation-workspace {
    overflow: visible;
    padding-inline: 4px;
  }

  .workspace-grid,
  .workspace-grid--preview {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    min-height: 0;
  }

  .mobile-preview-backdrop {
    background: rgba(0, 0, 0, 0.42);
    border: 0;
    display: block;
    inset: 0;
    position: fixed;
    touch-action: none;
    z-index: 2290;
  }

  .workspace-grid--preview .preview-panel {
    border-radius: 20px;
    bottom: max(8px, env(safe-area-inset-bottom));
    box-shadow: 0 18px 52px rgba(0, 0, 0, 0.24);
    grid-column: auto;
    left: 8px;
    position: fixed;
    right: 8px;
    top: max(8px, env(safe-area-inset-top));
    z-index: 2300;
  }

  .mobile-filter-trigger {
    display: inline-flex;
  }

  .mobile-filter-backdrop {
    background: rgba(0, 0, 0, 0.42);
    border: 0;
    display: block;
    inset: 0;
    position: fixed;
    touch-action: none;
    z-index: 2990;
  }

  .filter-panel {
    border-radius: 20px 20px 0 0;
    bottom: 0;
    box-shadow: 0 -14px 40px rgba(0, 0, 0, 0.18);
    left: 0;
    max-height: min(86dvh, 760px);
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 18px 18px calc(16px + env(safe-area-inset-bottom));
    position: fixed;
    right: 0;
    transform: translateY(calc(100% + 20px));
    transition:
      transform 0.22s ease,
      visibility 0s linear 0.22s;
    visibility: hidden;
    z-index: 3000;
  }

  .filter-panel--mobile-open {
    transform: translateY(0);
    transition: transform 0.22s ease;
    visibility: visible;
  }

  .mobile-filter-close {
    display: inline-flex;
  }

  .mobile-filter-footer {
    background: var(--workspace-card);
    bottom: calc(-16px - env(safe-area-inset-bottom));
    display: block;
    margin: 18px -18px 0;
    padding: 12px 18px calc(12px + env(safe-area-inset-bottom));
    position: sticky;
  }

  .conversation-list {
    overflow-y: visible;
    overscroll-behavior: auto;
  }

  .robot-options {
    max-height: 238px;
  }
}

@media (max-width: 520px) {
  .workspace-actions {
    padding-inline: 4px;
  }

  .conversation-row {
    grid-template-columns: 30px 26px minmax(0, 1fr);
  }

  .conversation-row--grouped {
    grid-template-columns: 30px minmax(0, 1fr);
    padding-left: 24px;
  }

  .row-time {
    display: none;
  }

  .row-meta > span:first-child,
  .row-meta > span:nth-child(2) {
    display: none;
  }
}
</style>

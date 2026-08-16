<template>
  <div class="conversation-page">
    <v-container fluid class="pa-0">
      <!-- 对话列表部分 -->
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('history.title') }}</span>
          <v-chip size="small" class="ml-2">{{ pagination.total || 0 }}</v-chip>
          <v-row class="me-4 ms-4" density="comfortable">
            <v-col cols="12" sm="6" md="4">
              <v-combobox
                v-model="platformFilter"
                :label="tm('filters.platform')"
                :items="availablePlatforms"
                chips
                multiple
                clearable
                variant="solo-filled"
                flat
                density="compact"
                hide-details
              >
                <template #selection="{ item }">
                  <v-chip size="small" label>
                    {{ item.title }}
                  </v-chip>
                </template>
              </v-combobox>
            </v-col>

            <v-col cols="12" sm="6" md="4">
              <v-select
                v-model="messageTypeFilter"
                :label="tm('filters.type')"
                :items="messageTypeItems"
                chips
                multiple
                clearable
                variant="solo-filled"
                density="compact"
                hide-details
                flat
              >
                <template #selection="{ item }">
                  <v-chip size="small" variant="tonal" label>
                    {{ item.title }}
                  </v-chip>
                </template>
              </v-select>
            </v-col>

            <v-col cols="12" sm="12" md="4">
              <v-text-field
                v-model="search"
                prepend-inner-icon="mdi-magnify"
                :label="tm('filters.search')"
                hide-details
                density="compact"
                variant="solo-filled"
                flat
                clearable
              ></v-text-field>
            </v-col>
          </v-row>
          <v-btn
            color="primary"
            prepend-icon="mdi-refresh"
            variant="tonal"
            :loading="loading"
            size="small"
            class="mr-2"
            @click="fetchConversations"
          >
            {{ tm('history.refresh') }}
          </v-btn>
          <v-btn
            v-if="selectedItems.length > 0"
            color="success"
            prepend-icon="mdi-download"
            variant="tonal"
            :disabled="loading"
            size="small"
            class="mr-2"
            @click="requestConversationExport"
          >
            {{ tm('batch.exportSelected', { count: selectedItems.length }) }}
          </v-btn>
          <v-btn
            v-if="selectedItems.length > 0"
            color="error"
            prepend-icon="mdi-delete"
            variant="tonal"
            :disabled="loading"
            size="small"
            @click="confirmBatchDelete"
          >
            {{ tm('batch.deleteSelected', { count: selectedItems.length }) }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table
            v-model="selectedItems"
            :headers="tableHeaders"
            :items="conversations"
            :loading="loading"
            density="comfortable"
            hide-default-footer
            class="elevation-0 conversation-table"
            :items-per-page="pagination.page_size"
            :items-per-page-options="pageSizeOptions"
            show-select
            return-object
            :disabled="loading"
            @update:options="handleTableOptions"
          >
            <template #header.umo_source>
              <div class="umo-header-cell">
                <span>{{ tm('table.headers.umo') }}</span>
                <v-btn-toggle
                  v-model="umoDisplayMode"
                  mandatory
                  density="compact"
                  divided
                  variant="outlined"
                  class="umo-header-toggle"
                >
                  <v-btn value="parsed" size="x-small">
                    {{ tm('table.umoDisplay.parsed') }}
                  </v-btn>
                  <v-btn value="raw" size="x-small">
                    {{ tm('table.umoDisplay.raw') }}
                  </v-btn>
                </v-btn-toggle>
              </div>
            </template>

            <template #item.title="{ item }">
              <div class="conversation-title-cell">
                <div class="conversation-title-row">
                  <span class="conversation-title-text">{{
                    item.title || tm('status.noTitle')
                  }}</span>
                  <v-btn
                    icon
                    variant="plain"
                    size="x-small"
                    density="compact"
                    :ripple="false"
                    class="conversation-inline-edit"
                    :disabled="loading"
                    :aria-label="tm('actions.edit')"
                    @click.stop="editConversation(item)"
                  >
                    <v-icon size="14">mdi-pencil</v-icon>
                  </v-btn>
                </div>
                <span class="conversation-title-meta">{{
                  item.cid || tm('status.unknown')
                }}</span>
              </div>
            </template>

            <template #item.umo_source="{ item }">
              <div class="umo-source-cell">
                <div class="umo-source-content">
                  <template v-if="umoDisplayMode === 'parsed'">
                    <div class="conversation-umo-stack">
                      <UmoDisplay
                        v-if="hasConversationUmoReadableName(item)"
                        v-bind="getConversationUmoDisplayProps(item)"
                        compact
                        :show-info="false"
                        :show-platform="false"
                        :show-meta="false"
                        class="conversation-umo-display"
                      />
                      <div class="conversation-umo-parsed">
                        <v-chip size="x-small" label>
                          {{
                            getConversationUmoInfo(item).platform ||
                            tm('status.unknown')
                          }}
                        </v-chip>
                        <span class="umo-separator">:</span>
                        <v-chip size="x-small" label>
                          {{
                            getMessageTypeDisplay(
                              getConversationUmoInfo(item).message_type,
                            )
                          }}
                        </v-chip>
                        <span class="umo-separator">:</span>
                        <span class="umo-session-id">{{
                          getConversationUmoInfo(item).session_id ||
                          tm('status.unknown')
                        }}</span>
                      </div>
                    </div>
                  </template>
                  <span v-else class="umo-raw-text">{{
                    item.user_id || tm('status.unknown')
                  }}</span>
                </div>
                <v-btn
                  icon
                  variant="plain"
                  size="x-small"
                  class="umo-copy-button"
                  :aria-label="tm('actions.copy')"
                  @click.stop="copyUmoSource(item)"
                >
                  <v-icon size="16">mdi-content-copy</v-icon>
                </v-btn>
              </div>
            </template>

            <template #item.created_at="{ item }">
              {{ formatTimestamp(item.created_at) }}
            </template>

            <template #item.updated_at="{ item }">
              {{ formatTimestamp(item.updated_at) }}
            </template>

            <template #item.actions="{ item }">
              <div class="actions-wrapper">
                <v-btn
                  icon
                  variant="plain"
                  size="x-small"
                  class="action-button"
                  :disabled="loading"
                  :aria-label="tm('actions.view')"
                  @click="viewConversation(item)"
                >
                  <v-icon>mdi-eye</v-icon>
                </v-btn>
                <v-btn
                  icon
                  color="error"
                  variant="plain"
                  size="x-small"
                  class="action-button"
                  :disabled="loading"
                  :aria-label="tm('actions.delete')"
                  @click="confirmDeleteConversation(item)"
                >
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </div>
            </template>

            <template #no-data>
              <div class="d-flex flex-column align-center py-6">
                <v-icon size="64" color="on-surface-variant"
                  >mdi-chat-remove</v-icon
                >
                <span class="text-subtitle-1 text-disabled mt-3">{{
                  tm('status.noData')
                }}</span>
              </div>
            </template>
          </v-data-table>

          <!-- 分页控制 -->
          <div class="d-flex justify-center py-3">
            <!-- 每页大小选择器 -->
            <div
              class="conversation-pagination d-flex justify-between align-center px-4 py-2"
            >
              <div class="d-flex align-center">
                <span class="text-caption mr-2"
                  >{{ tm('pagination.itemsPerPage') }}:</span
                >
                <v-select
                  v-model="pagination.page_size"
                  :items="pageSizeOptions"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="conversation-page-size"
                  :disabled="loading"
                  @update:model-value="onPageSizeChange"
                ></v-select>
              </div>
              <div class="text-caption ml-4">
                {{
                  tm('pagination.showingItems', {
                    start: Math.min(
                      (pagination.page - 1) * pagination.page_size + 1,
                      pagination.total,
                    ),
                    end: Math.min(
                      pagination.page * pagination.page_size,
                      pagination.total,
                    ),
                    total: pagination.total,
                  })
                }}
              </div>
            </div>
            <v-pagination
              v-model="pagination.page"
              :length="pagination.total_pages"
              :disabled="loading"
              rounded="circle"
              :total-visible="7"
              @update:model-value="fetchConversations"
            ></v-pagination>
          </div>
        </v-card-text>
      </v-card>
    </v-container>

    <!-- 对话详情对话框 -->
    <v-dialog v-model="dialogView" max-width="900px" scrollable>
      <v-card class="app-dialog conversation-detail-card">
        <v-card-title class="ml-2 mt-2 conversation-detail-title">
          <div class="conversation-detail-heading">
            <span class="text-truncate">{{
              selectedConversation?.title || tm('status.noTitle')
            }}</span>
            <UmoDisplay
              v-if="
                selectedConversation?.user_id &&
                hasConversationUmoReadableName(selectedConversation)
              "
              v-bind="getConversationUmoDisplayProps(selectedConversation)"
              compact
              :show-info="false"
              :show-platform="false"
              :show-meta="false"
              class="conversation-umo-display"
            />
            <div
              v-if="selectedConversation?.user_id"
              class="conversation-umo-parsed conversation-detail-umo-parsed"
            >
              <v-chip size="x-small" label>
                {{
                  getConversationUmoInfo(selectedConversation).platform ||
                  tm('status.unknown')
                }}
              </v-chip>
              <span class="umo-separator">:</span>
              <v-chip size="x-small" label>
                {{
                  getMessageTypeDisplay(
                    getConversationUmoInfo(selectedConversation).message_type,
                  )
                }}
              </v-chip>
              <span class="umo-separator">:</span>
              <span class="umo-session-id">{{
                getConversationUmoInfo(selectedConversation).session_id ||
                tm('status.unknown')
              }}</span>
            </div>
          </div>
        </v-card-title>

        <div class="conversation-history-actions d-flex align-center">
          <v-btn
            color="secondary"
            variant="tonal"
            size="small"
            class="mr-2"
            @click="isEditingHistory = !isEditingHistory"
          >
            <v-icon class="mr-1">{{
              isEditingHistory ? 'mdi-eye' : 'mdi-pencil'
            }}</v-icon>
            {{
              isEditingHistory
                ? tm('dialogs.view.previewMode')
                : tm('dialogs.view.editMode')
            }}
          </v-btn>
          <v-btn
            v-if="isEditingHistory"
            color="success"
            variant="tonal"
            size="small"
            :loading="savingHistory"
            @click="saveHistoryChanges"
          >
            <v-icon class="mr-1">mdi-content-save</v-icon>
            {{ tm('dialogs.view.saveChanges') }}
          </v-btn>
        </div>

        <v-card-text>
          <!-- 编辑模式 - Monaco编辑器 -->
          <div v-if="isEditingHistory" class="monaco-editor-container">
            <VueMonacoEditor
              v-model:value="editedHistory"
              theme="vs-dark"
              language="json"
              :options="{
                automaticLayout: true,
                fontSize: 13,
                tabSize: 2,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
              }"
              @editor-did-mount="onMonacoMounted"
            />
          </div>

          <!-- 预览模式 - 聊天界面 -->
          <div v-else class="conversation-messages-container">
            <!-- 空对话提示 -->
            <div
              v-if="conversationHistory.length === 0"
              class="text-center py-5"
            >
              <v-icon size="48" color="on-surface-variant"
                >mdi-chat-remove</v-icon
              >
              <p class="text-disabled mt-2">{{ tm('status.emptyContent') }}</p>
            </div>

            <!-- 消息列表组件 -->
            <MessageList
              v-else
              :messages="formattedMessages"
              :is-dark="isDark"
            />
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeHistoryDialog">
            {{ tm('dialogs.view.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 编辑对话框 -->
    <v-dialog v-model="dialogEdit" max-width="500px" scrollable>
      <v-card
        class="app-dialog conversation-modal-card conversation-edit-dialog"
      >
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="on-primary" class="me-2">mdi-pencil</v-icon>
          <span>{{ tm('dialogs.edit.title') }}</span>
        </v-card-title>

        <v-card-text class="py-4 conversation-modal-body">
          <v-form ref="form" v-model="valid">
            <v-text-field
              v-model="editedItem.title"
              :label="tm('dialogs.edit.titleLabel')"
              :placeholder="tm('dialogs.edit.titlePlaceholder')"
              variant="outlined"
              density="comfortable"
              class="mb-3"
            ></v-text-field>
          </v-form>
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4 conversation-modal-actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" :disabled="loading" @click="dialogEdit = false">
            {{ tm('dialogs.edit.cancel') }}
          </v-btn>
          <v-btn color="primary" :loading="loading" @click="saveConversation">
            {{ tm('dialogs.edit.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="dialogDelete" max-width="500px" scrollable>
      <v-card
        class="app-dialog conversation-modal-card conversation-delete-dialog"
      >
        <v-card-title class="bg-error text-white py-3">
          <v-icon color="on-error" class="me-2">mdi-alert</v-icon>
          <span>{{ tm('dialogs.delete.title') }}</span>
        </v-card-title>

        <v-card-text class="py-4 conversation-modal-body">
          <p>
            {{
              tm('dialogs.delete.message', {
                title: selectedConversation?.title || tm('status.noTitle'),
              })
            }}
          </p>
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4 conversation-modal-actions">
          <v-spacer></v-spacer>
          <v-btn
            variant="text"
            :disabled="loading"
            @click="dialogDelete = false"
          >
            {{ tm('dialogs.delete.cancel') }}
          </v-btn>
          <v-btn color="error" :loading="loading" @click="deleteConversation">
            {{ tm('dialogs.delete.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 批量删除确认对话框 -->
    <v-dialog v-model="dialogBatchDelete" max-width="600px" scrollable>
      <v-card
        class="app-dialog conversation-modal-card conversation-batch-delete-dialog"
      >
        <v-card-title class="bg-error text-white py-3">
          <v-icon color="on-error" class="me-2">mdi-delete</v-icon>
          <span>{{ tm('dialogs.batchDelete.title') }}</span>
        </v-card-title>

        <v-card-text class="py-4 conversation-modal-body">
          <p class="mb-3">
            {{
              tm('dialogs.batchDelete.message', { count: selectedItems.length })
            }}
          </p>

          <!-- 显示前几个要删除的对话 -->
          <div v-if="selectedItems.length > 0" class="mb-3">
            <v-chip
              v-for="item in selectedItems.slice(0, 5)"
              :key="`${item.user_id}-${item.cid}`"
              size="small"
              class="mr-1 mb-1"
              closable
              :disabled="loading"
              @click:close="removeFromSelection(item)"
            >
              {{ item.title || tm('status.noTitle') }}
            </v-chip>
            <v-chip
              v-if="selectedItems.length > 5"
              size="small"
              class="mr-1 mb-1"
            >
              {{
                tm('dialogs.batchDelete.andMore', {
                  count: selectedItems.length - 5,
                })
              }}
            </v-chip>
          </div>

          <v-alert type="warning" variant="tonal" class="mb-3">
            {{ tm('dialogs.batchDelete.warning') }}
          </v-alert>
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4 conversation-modal-actions">
          <v-spacer></v-spacer>
          <v-btn
            variant="text"
            :disabled="loading"
            @click="dialogBatchDelete = false"
          >
            {{ tm('dialogs.batchDelete.cancel') }}
          </v-btn>
          <v-btn
            color="error"
            :loading="loading"
            @click="batchDeleteConversations"
          >
            {{ tm('dialogs.batchDelete.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />

    <!-- 消息提示 -->
    <v-snackbar
      v-model="showMessage"
      :timeout="3000"
      elevation="4"
      :color="messageType"
      location="top"
    >
      {{ message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { isCancel } from 'axios';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import '@/utils/monacoLoader';
import {
  conversationApi,
  type ConversationPaginationData,
  type ConversationRecordData,
} from '@/api/v1';
import { useCommonStore } from '@/stores/common';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import MessageList from '@/components/chat/MessageList.vue';
import UmoDisplay from '@/components/shared/UmoDisplay.vue';
import type { ChatRecord, MessagePart, ToolCall } from '@/domain/chat';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { copyToClipboard } from '@/utils/clipboard';
import { resolveErrorMessage } from '@/utils/errorUtils';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';

type SnackbarType = 'success' | 'error';
type UmoDisplayMode = 'parsed' | 'raw';
type MessageTypeFilter = 'GroupMessage' | 'FriendMessage';
type PlatformFilterItem = string | { title: string; value: string };

interface PaginationState {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

interface SessionIdInfo {
  platform: string;
  messageType: string;
  sessionId: string;
}

interface ConversationUmoPayload {
  umo?: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
}

interface ConversationSessionInfo {
  platform: string;
  messageType: string;
  sessionId: string;
}

interface ConversationRecord extends ConversationRecordData {
  cid: string;
  user_id: string;
  title?: string;
  history?: string;
  created_at?: number;
  updated_at?: number;
  umo_info?: ConversationUmoPayload;
  sessionInfo?: ConversationSessionInfo;
}

interface HistoryToolCallFunction {
  name?: string;
  arguments?: unknown;
}

interface HistoryToolCall {
  id?: string;
  name?: string;
  arguments?: unknown;
  function?: HistoryToolCallFunction;
}

interface HistoryMessage {
  role?: string;
  content?: unknown;
  tool_call_id?: string;
  tool_calls?: HistoryToolCall[];
}

interface TableOptionsLike {
  itemsPerPage?: number;
}

interface FormValidationResult {
  valid: boolean;
}

interface FormController {
  validate: () =>
    boolean | FormValidationResult | Promise<boolean | FormValidationResult>;
}

interface MonacoAction {
  run: () => unknown;
}

interface MonacoEditorLike {
  onDidChangeModelContent: (listener: () => void) => void;
  getAction: (actionId: string) => MonacoAction | null;
}

interface ApiErrorLike {
  message?: string;
  response?: {
    data?: {
      message?: string;
    };
    status?: number;
  };
}

interface DebouncedCallback {
  (): void;
  cancel: () => void;
}

const { locale } = useI18n();
const { tm } = useModuleI18n('features/conversation');
const customizerStore = useCustomizerStore();
const commonStore = useCommonStore();
const confirmDialog = useConfirmDialog();

const form = ref<FormController | null>(null);

const conversations = ref<ConversationRecord[]>([]);
const search = ref('');
const selectedItems = ref<ConversationRecord[]>([]);
const platformFilter = ref<PlatformFilterItem[]>([]);
const messageTypeFilter = ref<MessageTypeFilter[]>([]);
const pagination = reactive<PaginationState>({
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0,
});

const dialogView = ref(false);
const dialogEdit = ref(false);
const dialogDelete = ref(false);
const dialogBatchDelete = ref(false);
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const selectedConversation = ref<ConversationRecord | null>(null);
const conversationHistory = ref<HistoryMessage[]>([]);
const editedItem = reactive({
  user_id: '',
  cid: '',
  title: '',
});

const valid = ref(true);
const loading = ref(false);
const showMessage = ref(false);
const message = ref('');
const messageType = ref<SnackbarType>('success');
const isEditingHistory = ref(false);
const editedHistory = ref('');
const savingHistory = ref(false);
const umoDisplayMode = ref<UmoDisplayMode>('parsed');

const pageSizeOptions = [10, 20, 50, 100];

let listController: AbortController | null = null;

const tableHeaders = computed(() => [
  {
    title: tm('table.headers.title'),
    key: 'title',
    sortable: true,
    minWidth: '80px',
    width: '200px',
  },
  {
    title: tm('table.headers.umo'),
    key: 'umo_source',
    sortable: false,
    minWidth: '280px',
    width: '360px',
  },
  {
    title: tm('table.headers.createdAt'),
    key: 'created_at',
    sortable: true,
    width: '180px',
  },
  {
    title: tm('table.headers.updatedAt'),
    key: 'updated_at',
    sortable: true,
    width: '180px',
  },
  {
    title: tm('table.headers.actions'),
    key: 'actions',
    sortable: false,
    align: 'center' as const,
  },
]);

const availablePlatforms = computed(() => {
  const tutorialMap = getTutorialMap(commonStore);
  return Object.keys(tutorialMap).map((platform) => ({
    title: platform,
    value: platform,
  }));
});

const messageTypeItems = computed(() => [
  { title: tm('messageTypes.group'), value: 'GroupMessage' },
  { title: tm('messageTypes.friend'), value: 'FriendMessage' },
]);

const isDark = computed(() => customizerStore.uiTheme === 'AstrBotDark');

const formattedMessages = computed<ChatRecord[]>(() => {
  const toolResultsById: Record<string, unknown> = {};

  for (const msg of conversationHistory.value) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      toolResultsById[msg.tool_call_id] = msg.content;
    }
  }

  return conversationHistory.value
    .filter((msg) => msg.role === 'user' || msg.role === 'assistant')
    .map((msg) => {
      const messageParts = convertContentToMessageParts(msg.content).filter(
        (part) => part.type !== 'plain' || part.text?.trim(),
      );

      if (
        msg.role === 'assistant' &&
        Array.isArray(msg.tool_calls) &&
        msg.tool_calls.length > 0
      ) {
        const toolCalls: ToolCall[] = msg.tool_calls.map((toolCall) => {
          const fn = toolCall.function ?? {};
          return {
            id: toolCall.id,
            name: fn.name || toolCall.name,
            args: fn.arguments ?? toolCall.arguments,
            result: toolCall.id ? toolResultsById[toolCall.id] : undefined,
            ts: 0,
            finished_ts: 1,
          };
        });
        messageParts.push({ type: 'tool_call', tool_calls: toolCalls });
      }

      const finalParts =
        messageParts.length > 0 ? messageParts : [{ type: 'plain', text: '' }];

      return {
        content: {
          type: msg.role === 'user' ? 'user' : 'bot',
          message: finalParts,
        },
      };
    });
});

const debouncedApplyFilters = createDebouncedCallback(() => {
  pagination.page = 1;
  void fetchConversations();
}, 300);

watch(
  platformFilter,
  () => {
    debouncedApplyFilters();
  },
  { deep: true },
);

watch(
  messageTypeFilter,
  () => {
    debouncedApplyFilters();
  },
  { deep: true },
);

watch(search, () => {
  debouncedApplyFilters();
});

onMounted(() => {
  void fetchConversations();
});

onBeforeUnmount(() => {
  debouncedApplyFilters.cancel();
  listController?.abort();
});

function getTutorialMap(store: unknown): Record<string, unknown> {
  if (!store || typeof store !== 'object') {
    return {};
  }

  const tutorialMap = (store as Record<string, unknown>).tutorial_map;
  return tutorialMap && typeof tutorialMap === 'object'
    ? (tutorialMap as Record<string, unknown>)
    : {};
}

function createDebouncedCallback(
  callback: () => void,
  delayMs: number,
): DebouncedCallback {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const debounced = (() => {
    if (timer) {
      clearTimeout(timer);
    }

    timer = setTimeout(() => {
      timer = null;
      callback();
    }, delayMs);
  }) as DebouncedCallback;

  debounced.cancel = () => {
    if (!timer) {
      return;
    }

    clearTimeout(timer);
    timer = null;
  };

  return debounced;
}

function normalizeConversationRecord(
  record: ConversationRecordData | null | undefined,
): ConversationRecord {
  const normalized: ConversationRecord = {
    ...(record ?? {}),
    cid: typeof record?.cid === 'string' ? record.cid : '',
    user_id: typeof record?.user_id === 'string' ? record.user_id : '',
  };

  if (typeof record?.title === 'string') {
    normalized.title = record.title;
  }
  if (typeof record?.history === 'string') {
    normalized.history = record.history;
  }
  if (typeof record?.created_at === 'number') {
    normalized.created_at = record.created_at;
  }
  if (typeof record?.updated_at === 'number') {
    normalized.updated_at = record.updated_at;
  }
  if (record?.umo_info && typeof record.umo_info === 'object') {
    normalized.umo_info = record.umo_info;
  }

  const umoInfo = getConversationUmoInfo(normalized);
  normalized.sessionInfo = {
    platform: umoInfo.platform,
    messageType: umoInfo.message_type,
    sessionId: umoInfo.session_id,
  };

  return normalized;
}

function normalizeHistoryMessage(raw: unknown): HistoryMessage | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const toolCalls = Array.isArray(source.tool_calls)
    ? source.tool_calls
        .filter(
          (item): item is Record<string, unknown> =>
            Boolean(item) && typeof item === 'object',
        )
        .map((toolCall) => ({
          ...(toolCall as HistoryToolCall),
          function:
            toolCall.function && typeof toolCall.function === 'object'
              ? (toolCall.function as HistoryToolCallFunction)
              : undefined,
        }))
    : undefined;

  return {
    role: typeof source.role === 'string' ? source.role : undefined,
    content: source.content,
    tool_call_id:
      typeof source.tool_call_id === 'string' ? source.tool_call_id : undefined,
    tool_calls: toolCalls,
  };
}

function normalizeConversationHistory(raw: unknown): HistoryMessage[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .map((item) => normalizeHistoryMessage(item))
    .filter((item): item is HistoryMessage => item !== null);
}

function parseSessionId(userId: unknown): SessionIdInfo {
  if (typeof userId !== 'string' || !userId) {
    return { platform: 'default', messageType: 'default', sessionId: '' };
  }

  const parts = userId.split(':');
  if (parts.length >= 3) {
    return {
      platform: parts[0] || 'default',
      messageType: parts[1] || 'default',
      sessionId: parts.slice(2).join(':'),
    };
  }

  return { platform: 'default', messageType: 'default', sessionId: userId };
}

function getMessageTypeDisplay(messageTypeValue: unknown): string {
  const typeMap: Record<string, string> = {
    GroupMessage: tm('messageTypes.group'),
    group: tm('messageTypes.group'),
    FriendMessage: tm('messageTypes.friend'),
    friend: tm('messageTypes.friend'),
    private: tm('messageTypes.friend'),
    default: tm('messageTypes.unknown'),
  };

  if (typeof messageTypeValue !== 'string') {
    return typeMap.default;
  }

  return typeMap[messageTypeValue] || typeMap.default;
}

function getConversationUmoInfo(item: ConversationRecord | null | undefined) {
  const rawInfo =
    item?.umo_info && typeof item.umo_info === 'object' ? item.umo_info : {};
  const parsed = parseSessionId(item?.user_id || rawInfo.umo || '');

  return {
    umo: item?.user_id || rawInfo.umo || '',
    platform: rawInfo.platform || parsed.platform,
    message_type: rawInfo.message_type || parsed.messageType,
    session_id: rawInfo.session_id || parsed.sessionId,
    auto_name: rawInfo.auto_name || '',
    user_alias: rawInfo.user_alias || '',
    display_name: rawInfo.display_name || item?.user_id || '',
  };
}

function getConversationUmoDisplayProps(
  item: ConversationRecord | null | undefined,
) {
  const info = getConversationUmoInfo(item);
  return {
    umo: info.umo || tm('status.unknown'),
    platform: info.platform,
    messageType: info.message_type,
    sessionId: info.session_id,
    autoName: info.auto_name,
    userAlias: info.user_alias,
  };
}

function hasConversationUmoReadableName(
  item: ConversationRecord | null | undefined,
) {
  const info = getConversationUmoInfo(item);
  return Boolean(info.user_alias || info.auto_name);
}

function formatUmoSource(item: ConversationRecord | null | undefined): string {
  if (umoDisplayMode.value === 'raw') {
    return item?.user_id || tm('status.unknown');
  }

  const info = getConversationUmoInfo(item);
  const platform = info.platform || tm('status.unknown');
  const resolvedMessageType = getMessageTypeDisplay(info.message_type);
  const sessionId = info.session_id || tm('status.unknown');
  return `${platform}:${resolvedMessageType}:${sessionId}`;
}

async function copyUmoSource(item: ConversationRecord) {
  const ok = await copyToClipboard(formatUmoSource(item));
  if (ok) {
    showSuccessMessage(tm('messages.copySuccess'));
  } else {
    showErrorMessage(tm('messages.copyError'));
  }
}

function normalizePlatformFilters(items: PlatformFilterItem[]): string[] {
  return items
    .map((item) => {
      if (typeof item === 'string') {
        return item;
      }

      if (typeof item.value === 'string') {
        return item.value;
      }

      return '';
    })
    .filter(Boolean);
}

function normalizeHistoryPayload(
  raw: unknown,
): Array<Record<string, unknown>> | null {
  if (!Array.isArray(raw)) {
    return null;
  }

  return raw.filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === 'object',
  );
}

function updatePaginationState(data?: ConversationPaginationData) {
  pagination.page = data?.page || 1;
  pagination.page_size = data?.page_size || 20;
  pagination.total = data?.total || 0;
  pagination.total_pages = data?.total_pages || 1;
}

async function fetchConversations() {
  listController?.abort();
  listController = new AbortController();

  loading.value = true;
  try {
    const params: Record<string, string | number> = {
      page: pagination.page,
      page_size: pagination.page_size,
      exclude_ids: 'astrbot',
      exclude_platforms: 'webchat',
    };

    const platforms = normalizePlatformFilters(platformFilter.value);
    if (platforms.length > 0) {
      params.platforms = platforms.join(',');
    }
    if (messageTypeFilter.value.length > 0) {
      params.message_types = messageTypeFilter.value.join(',');
    }
    if (search.value.trim()) {
      params.search = search.value.trim();
    }

    const response = await conversationApi.list(params, {
      signal: listController.signal,
    });

    if (response.data.status !== 'ok') {
      showErrorMessage(response.data.message || tm('messages.fetchError'));
      return;
    }

    const data = response.data.data;
    if (!data?.conversations) {
      console.error('API 返回数据格式不符合预期:', data);
      showErrorMessage(tm('messages.fetchError'));
      return;
    }

    conversations.value = data.conversations.map((conversation) =>
      normalizeConversationRecord(conversation),
    );
    updatePaginationState(data.pagination);
  } catch (error) {
    if (isCancel(error)) {
      return;
    }

    console.error('获取对话列表出错:', error);
    if (error && typeof error === 'object') {
      const maybeError = error as ApiErrorLike;
      if (maybeError.response) {
        console.error('错误响应数据:', maybeError.response.data);
        console.error('错误状态码:', maybeError.response.status);
      }
    }
    showErrorMessage(resolveErrorMessage(error, tm('messages.fetchError')));
  } finally {
    loading.value = false;
  }
}

async function viewConversation(item: ConversationRecord) {
  selectedConversation.value = item;
  loading.value = true;
  isEditingHistory.value = false;

  try {
    const response = await conversationApi.get(item.user_id, item.cid);

    if (response.data.status !== 'ok') {
      showErrorMessage(response.data.message || tm('messages.historyError'));
      return;
    }

    const detailData = response.data.data || {};
    const mergedConversation = normalizeConversationRecord({
      ...item,
      ...detailData,
    });

    selectedConversation.value = mergedConversation;

    try {
      const historyData =
        typeof detailData.history === 'string' ? detailData.history : '[]';
      const parsedHistory = JSON.parse(historyData);
      conversationHistory.value = normalizeConversationHistory(parsedHistory);
      editedHistory.value = JSON.stringify(conversationHistory.value, null, 2);
    } catch (error) {
      conversationHistory.value = [];
      editedHistory.value = '[]';
      console.error('解析对话历史失败:', error);
    }

    dialogView.value = true;
  } catch (error) {
    console.error('获取对话详情出错:', error);
    showErrorMessage(resolveErrorMessage(error, tm('messages.historyError')));
  } finally {
    loading.value = false;
  }
}

async function saveHistoryChanges() {
  if (!selectedConversation.value) {
    return;
  }

  savingHistory.value = true;

  try {
    let historyJson: unknown;
    try {
      historyJson = JSON.parse(editedHistory.value);
    } catch {
      showErrorMessage(tm('messages.invalidJson'));
      return;
    }

    const historyPayload = normalizeHistoryPayload(historyJson);
    if (!historyPayload) {
      showErrorMessage(tm('messages.invalidJson'));
      return;
    }

    const response = await conversationApi.replaceMessages(
      selectedConversation.value.user_id,
      selectedConversation.value.cid,
      {
        history: historyPayload,
      },
    );

    if (response.data.status !== 'ok') {
      showErrorMessage(
        response.data.message || tm('messages.historySaveError'),
      );
      return;
    }

    conversationHistory.value = normalizeConversationHistory(historyPayload);
    showSuccessMessage(tm('messages.historySaveSuccess'));
    isEditingHistory.value = false;
  } catch (error) {
    console.error('更新对话历史出错:', error);
    showErrorMessage(
      resolveErrorMessage(error, tm('messages.historySaveError')),
    );
  } finally {
    savingHistory.value = false;
  }
}

async function closeHistoryDialog() {
  if (
    isEditingHistory.value &&
    !(await askForConfirmationDialog(
      tm('dialogs.view.confirmClose'),
      confirmDialog,
    ))
  ) {
    return;
  }

  dialogView.value = false;
}

function editConversation(item: ConversationRecord) {
  selectedConversation.value = item;
  editedItem.user_id = item.user_id;
  editedItem.cid = item.cid;
  editedItem.title = item.title || '';
  dialogEdit.value = true;
}

async function validateForm(): Promise<boolean> {
  const result = await form.value?.validate();
  if (typeof result === 'boolean') {
    return result;
  }
  return result?.valid ?? false;
}

async function saveConversation() {
  if (!(await validateForm())) {
    return;
  }

  loading.value = true;
  try {
    const response = await conversationApi.update(
      editedItem.user_id,
      editedItem.cid,
      {
        title: editedItem.title,
      },
    );

    if (response.data.status !== 'ok') {
      showErrorMessage(response.data.message || tm('messages.saveError'));
      return;
    }

    const index = conversations.value.findIndex(
      (item) =>
        item.user_id === editedItem.user_id && item.cid === editedItem.cid,
    );
    if (index !== -1) {
      conversations.value[index].title = editedItem.title;
    }

    dialogEdit.value = false;
    showSuccessMessage(tm('messages.saveSuccess'));
    void fetchConversations();
  } catch (error) {
    showErrorMessage(resolveErrorMessage(error, tm('messages.saveError')));
  } finally {
    loading.value = false;
  }
}

function confirmDeleteConversation(item: ConversationRecord) {
  selectedConversation.value = item;
  dialogDelete.value = true;
}

async function deleteConversation() {
  if (!selectedConversation.value) {
    return;
  }

  const targetConversation = selectedConversation.value;
  loading.value = true;

  try {
    const response = await conversationApi.delete(
      targetConversation.user_id,
      targetConversation.cid,
    );

    if (response.data.status !== 'ok') {
      showErrorMessage(response.data.message || tm('messages.deleteError'));
      return;
    }

    const index = conversations.value.findIndex(
      (item) =>
        item.user_id === targetConversation.user_id &&
        item.cid === targetConversation.cid,
    );
    if (index !== -1) {
      conversations.value.splice(index, 1);
    }

    dialogDelete.value = false;
    showSuccessMessage(tm('messages.deleteSuccess'));
  } catch (error) {
    showErrorMessage(resolveErrorMessage(error, tm('messages.deleteError')));
  } finally {
    loading.value = false;
    selectedItems.value = selectedItems.value.filter(
      (item) =>
        !(
          item.user_id === targetConversation.user_id &&
          item.cid === targetConversation.cid
        ),
    );
    selectedConversation.value = null;
  }
}

function onPageSizeChange() {
  pagination.page = 1;
  void fetchConversations();
}

function confirmBatchDelete() {
  if (selectedItems.value.length === 0) {
    showErrorMessage(tm('messages.noItemSelected'));
    return;
  }
  dialogBatchDelete.value = true;
}

function removeFromSelection(item: ConversationRecord) {
  const index = selectedItems.value.findIndex(
    (selected) =>
      selected.user_id === item.user_id && selected.cid === item.cid,
  );
  if (index !== -1) {
    selectedItems.value.splice(index, 1);
  }
}

async function batchDeleteConversations() {
  if (selectedItems.value.length === 0) {
    showErrorMessage(tm('messages.noItemSelected'));
    return;
  }

  loading.value = true;
  try {
    const response = await conversationApi.batchDelete({
      conversations: selectedItems.value.map((item) => ({
        user_id: item.user_id,
        cid: item.cid,
      })),
    });

    if (response.data.status !== 'ok') {
      showErrorMessage(
        response.data.message || tm('messages.batchDeleteError'),
      );
      return;
    }

    const result = response.data.data;
    dialogBatchDelete.value = false;
    selectedItems.value = [];

    if ((result.failed_count || 0) > 0) {
      showErrorMessage(
        tm('messages.batchDeletePartial', {
          deleted: result.deleted_count || 0,
          failed: result.failed_count || 0,
        }),
      );
    } else {
      showSuccessMessage(
        tm('messages.batchDeleteSuccess', {
          count: result.deleted_count || 0,
        }),
      );
    }

    void fetchConversations();
  } catch (error) {
    console.error('批量删除对话出错:', error);
    showErrorMessage(
      resolveErrorMessage(error, tm('messages.batchDeleteError')),
    );
  } finally {
    loading.value = false;
  }
}

function requestConversationExport() {
  if (selectedItems.value.length === 0) {
    showErrorMessage(tm('messages.noItemSelectedForExport'));
    return;
  }

  void (async () => {
    const stepUp = await requestStepUp({
      action: 'data.export_all',
      resourceType: 'conversation',
      resourceId: 'export',
    });
    if (stepUp) await exportConversations(stepUp);
  })();
}

async function exportConversations(stepUp: string) {
  loading.value = true;
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

    const timestamp = new Date()
      .toISOString()
      .replace(/[:.]/g, '-')
      .slice(0, -5);
    const filename = `conversations_export_${timestamp}.jsonl`;

    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);

    showSuccessMessage(tm('messages.exportSuccess'));
  } catch (error) {
    console.error(tm('messages.exportError'), error);
    showErrorMessage(resolveErrorMessage(error, tm('messages.exportError')));
  } finally {
    loading.value = false;
  }
}

function formatTimestamp(timestamp: unknown): string {
  if (typeof timestamp !== 'number' || timestamp <= 0) {
    return tm('status.unknown');
  }

  return new Intl.DateTimeFormat(locale.value || 'zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(timestamp * 1000));
}

function showSuccessMessage(successMessage: string) {
  message.value = successMessage;
  messageType.value = 'success';
  showMessage.value = true;
}

function showErrorMessage(errorMessage: string) {
  message.value = errorMessage;
  messageType.value = 'error';
  showMessage.value = true;
}

function convertContentToMessageParts(content: unknown): MessagePart[] {
  const parts: MessagePart[] = [];

  if (typeof content === 'string') {
    if (content.trim()) {
      parts.push({ type: 'plain', text: content });
    }
  } else if (Array.isArray(content)) {
    content.forEach((item) => {
      if (!item || typeof item !== 'object') {
        return;
      }

      const record = item as Record<string, unknown>;
      if (record.type === 'text' && typeof record.text === 'string') {
        parts.push({
          type: 'plain',
          text: record.text,
        });
        return;
      }

      const imageUrl =
        record.image_url &&
        typeof record.image_url === 'object' &&
        typeof (record.image_url as Record<string, unknown>).url === 'string'
          ? ((record.image_url as Record<string, unknown>).url as string)
          : '';

      if (record.type === 'image_url' && imageUrl) {
        parts.push({
          type: 'image',
          embedded_url: imageUrl,
        });
      }
    });
  } else if (content && typeof content === 'object') {
    const textParts = Object.values(content).filter(
      (value): value is string =>
        typeof value === 'string' && value.trim().length > 0,
    );
    if (textParts.length > 0) {
      parts.push({
        type: 'plain',
        text: textParts.join('\n'),
      });
    }
  }

  if (parts.length === 0) {
    parts.push({
      type: 'plain',
      text: '',
    });
  }

  return parts;
}

function onMonacoMounted(editor: MonacoEditorLike) {
  editor.onDidChangeModelContent(() => {
    try {
      JSON.parse(editedHistory.value);
      editor.getAction('editor.action.formatDocument')?.run();
    } catch {
      // Monaco will show the invalid JSON state itself.
    }
  });
}

function handleTableOptions(options: TableOptionsLike) {
  if (
    typeof options.itemsPerPage === 'number' &&
    options.itemsPerPage !== pagination.page_size
  ) {
    pagination.page_size = options.itemsPerPage;
    pagination.page = 1;
    void fetchConversations();
  }
}
</script>

<style>
.actions-wrapper {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.action-button {
  border-radius: 8px;
  font-weight: 500;
}

.monaco-editor-container {
  height: 500px;
  border-radius: 8px;
  overflow: hidden;
}

.conversation-messages-container {
  padding: var(--astrbot-space-2);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.conversation-history-actions {
  flex: 0 0 auto;
  padding: 16px 16px 8px 24px;
}

.conversation-messages-container .tool-call-inline-status {
  display: none;
}

.conversation-table {
  font-size: 12px;
}

.conversation-pagination {
  background: rgb(var(--v-theme-surface-variant));
}

.conversation-page-size {
  max-width: 100px;
}

/* 对话详情卡片 */
.conversation-detail-card {
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.conversation-modal-card {
  display: flex;
  flex-direction: column;
  max-height: min(85vh, 560px);
}

.conversation-modal-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.conversation-modal-actions {
  flex: 0 0 auto;
}

.conversation-detail-title {
  display: flex;
  align-items: center;
}

.conversation-detail-heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  width: 100%;
}

.text-truncate {
  display: inline-block;
  /* max-width: 100px; */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-title-cell {
  padding: 6px 0px;
  min-width: 100px;
  max-width: 145px;
}

.conversation-title-row {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}

.conversation-title-text {
  display: inline-block;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-inline-edit {
  width: 18px;
  height: 18px;
  min-width: 18px;
  flex-shrink: 0;
}

.conversation-title-meta {
  display: block;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-header-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.umo-header-toggle {
  flex-shrink: 0;
}

.umo-source-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.umo-source-content {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
}

.conversation-umo-display {
  min-width: 0;
}

.conversation-umo-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  width: 100%;
}

.conversation-umo-parsed {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
}

.conversation-detail-umo-parsed {
  max-width: 100%;
}

.umo-separator {
  color: rgba(var(--v-theme-on-surface), 0.5);
  flex-shrink: 0;
}

.umo-session-id,
.umo-raw-text {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-copy-button {
  flex-shrink: 0;
}

/* 动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

<template>
  <section class="memory-page">
    <header class="memory-page__header">
      <div>
        <h1 class="memory-page__title">{{ tm('title') }}</h1>
        <p class="memory-page__subtitle">{{ tm('subtitle') }}</p>
      </div>
      <v-btn
        color="primary"
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="refreshing"
        @click="loadAll"
      >
        {{ tm('actions.refresh') }}
      </v-btn>
    </header>

    <v-card class="memory-summary" variant="outlined">
      <v-card-text class="pa-0">
        <div class="memory-summary__grid">
          <div class="memory-summary__item">
            <span>{{ tm('stats.activeFacts') }}</span>
            <strong>{{ stats.facts ?? 0 }}</strong>
          </div>
          <div class="memory-summary__item">
            <span>{{ tm('stats.deletedFacts') }}</span>
            <strong>{{ stats.deleted_facts ?? 0 }}</strong>
          </div>
          <div class="memory-summary__item">
            <span>{{ tm('stats.profiles') }}</span>
            <strong>{{ stats.profiles ?? 0 }}</strong>
          </div>
          <div class="memory-summary__item">
            <span>{{ tm('stats.queue') }}</span>
            <strong>
              {{ stats.worker?.queue_size ?? 0 }}/{{
                stats.worker?.queue_max_size ?? 0
              }}
            </strong>
          </div>
          <div class="memory-summary__item memory-summary__item--worker">
            <span>{{ tm('stats.worker') }}</span>
            <v-chip
              :color="stats.worker?.running ? 'success' : 'warning'"
              size="small"
              variant="tonal"
            >
              {{
                stats.worker?.running
                  ? tm('stats.workerRunning')
                  : tm('stats.workerStopped')
              }}
            </v-chip>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card class="memory-card mt-6" variant="outlined">
      <v-card-title class="memory-card__title">
        <div class="d-flex align-center ga-2">
          <v-icon icon="mdi-dots-hexagon" size="20" />
          <span>{{ tm('memories.title') }}</span>
          <v-chip size="small" variant="tonal">{{ total }}</v-chip>
        </div>
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <form class="memory-filters" @submit.prevent="applyFilters">
          <v-row density="comfortable">
            <v-col cols="12" sm="6" lg="3">
              <v-text-field
                v-model="filters.person_id"
                data-testid="memory-person-filter"
                :label="tm('filters.personId')"
                clearable
                density="compact"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="6" lg="3">
              <v-text-field
                v-model="filters.chat_id"
                data-testid="memory-chat-filter"
                :label="tm('filters.chatId')"
                clearable
                density="compact"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="4" lg="2">
              <v-select
                v-model="filters.status"
                :items="statusOptions"
                :label="tm('filters.status')"
                density="compact"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="8" lg="2">
              <v-text-field
                v-model="filters.query"
                data-testid="memory-query-filter"
                :label="tm('filters.query')"
                clearable
                density="compact"
                hide-details
                prepend-inner-icon="mdi-magnify"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" lg="2" class="d-flex justify-end align-center">
              <v-btn
                class="mr-2"
                variant="text"
                type="button"
                :disabled="loading"
                @click="clearFilters"
              >
                {{ tm('actions.clearFilters') }}
              </v-btn>
              <v-btn
                color="primary"
                data-testid="memory-filter-submit"
                prepend-icon="mdi-magnify"
                type="submit"
                variant="tonal"
                :loading="loading"
              >
                {{ tm('actions.search') }}
              </v-btn>
            </v-col>
          </v-row>
        </form>
      </v-card-text>

      <v-data-table
        class="memory-table memory-table-desktop"
        :headers="tableHeaders"
        :items="facts"
        :items-per-page="pageSize"
        item-value="id"
        :loading="loading"
        hide-default-footer
      >
        <template #item.id="{ item }">
          <span class="memory-id">#{{ item.id }}</span>
        </template>
        <template #item.fact_text="{ item }">
          <span class="fact-text" :title="item.fact_text">
            {{ item.fact_text }}
          </span>
        </template>
        <template #item.person_id="{ item }">
          <span class="memory-identifier" :title="item.person_id">
            {{ item.person_id }}
          </span>
        </template>
        <template #item.scope_id="{ item }">
          <span class="scope-text" :title="item.scope_id">
            {{ item.scope_id }}
          </span>
        </template>
        <template #item.confidence="{ item }">
          {{ formatConfidence(item.confidence) }}
        </template>
        <template #item.status="{ item }">
          <v-chip
            size="small"
            :color="item.status === 'active' ? 'success' : 'grey'"
            variant="tonal"
          >
            {{ statusLabel(item.status) }}
          </v-chip>
        </template>
        <template #item.updated_at="{ item }">
          <span class="memory-date">{{ formatDate(item.updated_at) }}</span>
        </template>
        <template #item.actions="{ item }">
          <div class="memory-table__actions">
            <v-tooltip :text="tm('actions.view')">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon="mdi-eye"
                  size="small"
                  variant="text"
                  :aria-label="tm('actions.view')"
                  @click="openDetail(item)"
                />
              </template>
            </v-tooltip>
            <v-tooltip
              :text="
                item.status === 'active'
                  ? tm('actions.delete')
                  : tm('actions.restore')
              "
            >
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  :icon="
                    item.status === 'active'
                      ? 'mdi-delete-outline'
                      : 'mdi-restore'
                  "
                  size="small"
                  variant="text"
                  :color="item.status === 'active' ? 'error' : 'primary'"
                  :aria-label="
                    item.status === 'active'
                      ? tm('actions.delete')
                      : tm('actions.restore')
                  "
                  @click="
                    confirmAction(
                      item,
                      item.status === 'active' ? 'delete' : 'restore',
                    )
                  "
                />
              </template>
            </v-tooltip>
          </div>
        </template>
        <template #no-data>
          <div class="memory-empty-state">
            <v-icon icon="mdi-brain" size="40" />
            <span>{{ tm('messages.emptyFacts') }}</span>
          </div>
        </template>
      </v-data-table>

      <v-card-text class="memory-cards-mobile pa-4">
        <div v-if="loading" class="memory-mobile-loading">
          <v-progress-circular color="primary" indeterminate size="28" />
        </div>
        <template v-else-if="facts.length > 0">
          <article
            v-for="fact in facts"
            :key="fact.id"
            class="memory-fact-card"
          >
            <div class="fact-card-head">
              <div>
                <div class="memory-identifier">{{ fact.person_id }}</div>
                <span class="memory-id">#{{ fact.id }}</span>
              </div>
              <v-chip
                size="small"
                :color="fact.status === 'active' ? 'success' : 'grey'"
                variant="tonal"
              >
                {{ statusLabel(fact.status) }}
              </v-chip>
            </div>
            <p class="fact-card-text">{{ fact.fact_text }}</p>
            <div class="fact-card-meta">
              <span :title="fact.scope_id">{{ fact.scope_id }}</span>
              <span>
                {{ formatConfidence(fact.confidence) }} ·
                {{ formatDate(fact.updated_at) }}
              </span>
            </div>
            <div class="fact-card-actions">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-eye"
                @click="openDetail(fact)"
              >
                {{ tm('actions.view') }}
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                :color="fact.status === 'active' ? 'error' : 'primary'"
                :prepend-icon="
                  fact.status === 'active'
                    ? 'mdi-delete-outline'
                    : 'mdi-restore'
                "
                @click="
                  confirmAction(
                    fact,
                    fact.status === 'active' ? 'delete' : 'restore',
                  )
                "
              >
                {{
                  fact.status === 'active'
                    ? tm('actions.delete')
                    : tm('actions.restore')
                }}
              </v-btn>
            </div>
          </article>
        </template>
        <div v-else class="memory-empty-state">
          <v-icon icon="mdi-brain" size="40" />
          <span>{{ tm('messages.emptyFacts') }}</span>
        </div>
      </v-card-text>

      <v-card-actions v-if="pageCount > 1" class="justify-center py-3">
        <v-pagination
          v-model="page"
          :length="pageCount"
          :disabled="loading"
          :total-visible="7"
          @update:model-value="loadFacts"
        />
      </v-card-actions>
    </v-card>

    <div class="memory-secondary-grid mt-6">
      <v-card class="memory-card memory-card--full-height" variant="outlined">
        <v-card-title class="memory-card__title">
          <div class="d-flex align-center ga-2">
            <v-icon icon="mdi-account" size="20" />
            <span>{{ tm('profiles.title') }}</span>
          </div>
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <form @submit.prevent="loadProfiles">
            <v-row density="comfortable">
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model="profileFilters.person_id"
                  :label="tm('filters.personId')"
                  clearable
                  density="compact"
                  hide-details
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model="profileFilters.chat_scope"
                  :label="tm('filters.scopeId')"
                  clearable
                  density="compact"
                  hide-details
                  variant="outlined"
                />
              </v-col>
              <v-col cols="12" class="d-flex justify-end">
                <v-btn
                  color="primary"
                  prepend-icon="mdi-magnify"
                  type="submit"
                  variant="tonal"
                  :loading="profilesLoading"
                >
                  {{ tm('actions.search') }}
                </v-btn>
              </v-col>
            </v-row>
          </form>
        </v-card-text>
        <v-progress-linear
          v-if="profilesLoading"
          color="primary"
          indeterminate
        />
        <v-list v-else-if="profiles.length > 0" lines="three">
          <v-list-item v-for="profile in profiles" :key="profile.id">
            <v-list-item-title
              class="text-truncate"
              :title="`${profile.person_id} · ${profile.chat_scope}`"
            >
              {{ profile.person_id }} · {{ profile.chat_scope }}
            </v-list-item-title>
            <v-list-item-subtitle class="profile-text">
              {{ profile.profile_text }}
            </v-list-item-subtitle>
            <template #append>
              <v-tooltip :text="tm('profiles.refresh')">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    icon="mdi-refresh"
                    size="small"
                    variant="text"
                    :aria-label="tm('profiles.refresh')"
                    @click="refreshProfile(profile)"
                  />
                </template>
              </v-tooltip>
            </template>
          </v-list-item>
        </v-list>
        <div v-else class="memory-section-empty">
          {{ tm('messages.emptyProfiles') }}
        </div>
      </v-card>

      <v-card class="memory-card memory-card--full-height" variant="outlined">
        <v-card-title class="memory-card__title">
          <div class="d-flex align-center ga-2">
            <v-icon icon="mdi-format-list-bulleted" size="20" />
            <span>{{ tm('operations.title') }}</span>
          </div>
        </v-card-title>
        <v-divider />
        <v-progress-linear
          v-if="operationsLoading"
          color="primary"
          indeterminate
        />
        <v-list v-else-if="operations.length > 0" density="comfortable">
          <v-list-item v-for="operation in operations" :key="operation.id">
            <template #prepend>
              <v-avatar
                :color="operationActionColor(operation.action)"
                size="28"
                variant="tonal"
              >
                <v-icon size="16">{{
                  operationActionIcon(operation.action)
                }}</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title>
              {{ operationTargetLabel(operation) }}
            </v-list-item-title>
            <v-list-item-subtitle>
              {{ operationActionLabel(operation.action) }} ·
              {{ operation.operator }} · {{ formatDate(operation.created_at) }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
        <div v-else class="memory-section-empty">
          {{ tm('messages.emptyOperations') }}
        </div>
      </v-card>
    </div>

    <v-dialog v-model="detailDialog" max-width="760" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <v-icon icon="mdi-dots-hexagon" />
          <span>{{ tm('detail.title') }}</span>
        </v-card-title>
        <v-card-text v-if="selectedDetail?.fact">
          <p class="text-body-1 mb-4">{{ selectedDetail.fact.fact_text }}</p>
          <v-row>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.person') }}:</strong>
              {{ selectedDetail.fact.person_id }}
            </v-col>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.chat') }}:</strong>
              {{ selectedDetail.fact.chat_id }}
            </v-col>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.scope') }}:</strong>
              {{ selectedDetail.fact.scope_id }}
            </v-col>
            <v-col cols="12" md="6" class="d-flex align-center ga-2">
              <strong>{{ tm('memories.status') }}:</strong>
              <v-chip
                size="small"
                :color="
                  selectedDetail.fact.status === 'active' ? 'success' : 'grey'
                "
                variant="tonal"
              >
                {{ statusLabel(selectedDetail.fact.status) }}
              </v-chip>
            </v-col>
          </v-row>
          <v-divider class="my-4" />
          <h2 class="text-subtitle-1 mb-2">{{ tm('operations.title') }}</h2>
          <v-list density="compact">
            <v-list-item
              v-for="operation in selectedDetail.operation_logs || []"
              :key="operation.operation_id"
            >
              <v-list-item-title>
                {{ operationActionLabel(operation.action) }} ·
                {{ operation.reason || '-' }}
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ operation.operator }} ·
                {{ formatDate(operation.created_at) }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">
            {{ tm('actions.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="actionDialog" max-width="520">
      <v-card>
        <v-card-title>
          {{
            pendingAction === 'delete'
              ? tm('confirm.deleteTitle')
              : tm('confirm.restoreTitle')
          }}
        </v-card-title>
        <v-card-text>
          <p class="mb-2">{{ pendingFact?.fact_text }}</p>
          <p class="text-caption text-medium-emphasis">
            {{ pendingFact?.person_id }} · {{ pendingFact?.scope_id }}
          </p>
          <v-text-field
            v-model="actionReason"
            :label="tm('confirm.reason')"
            class="mt-4"
            density="compact"
            variant="outlined"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="actionDialog = false">
            {{ tm('actions.cancel') }}
          </v-btn>
          <v-btn
            :color="pendingAction === 'delete' ? 'error' : 'primary'"
            :loading="actionLoading"
            @click="runPendingAction"
          >
            {{
              pendingAction === 'delete'
                ? tm('actions.delete')
                : tm('actions.restore')
            }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  memoryApi,
  type MemoryFactData,
  type MemoryFactDetailData,
  type MemoryOperationData,
  type MemoryProfileData,
  type MemoryStatsData,
} from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useToastStore } from '@/stores/toast';

const { tm } = useModuleI18n('features/alkaid/memory');
const toastStore = useToastStore();

const facts = ref<MemoryFactData[]>([]);
const profiles = ref<MemoryProfileData[]>([]);
const operations = ref<MemoryOperationData[]>([]);
const stats = ref<MemoryStatsData>({});
const selectedDetail = ref<MemoryFactDetailData | null>(null);
const loading = ref(false);
const refreshing = ref(false);
const profilesLoading = ref(false);
const operationsLoading = ref(false);
const actionLoading = ref(false);
const detailDialog = ref(false);
const actionDialog = ref(false);
const pendingFact = ref<MemoryFactData | null>(null);
const pendingAction = ref<'delete' | 'restore'>('delete');
const actionReason = ref('');
const page = ref(1);
const pageSize = 10;
const total = ref(0);
type MemoryStatusFilter = 'active' | 'deleted' | 'all';

const filters = reactive<{
  person_id: string;
  chat_id: string;
  status: MemoryStatusFilter;
  query: string;
}>({
  person_id: '',
  chat_id: '',
  status: 'all',
  query: '',
});

const profileFilters = reactive({
  person_id: '',
  chat_scope: '',
});

const statusOptions = computed<
  Array<{ title: string; value: MemoryStatusFilter }>
>(() => [
  { title: tm('status.all'), value: 'all' },
  { title: tm('status.active'), value: 'active' },
  { title: tm('status.deleted'), value: 'deleted' },
]);

const tableHeaders = computed(() => [
  { title: tm('memories.id'), key: 'id', sortable: false },
  { title: tm('memories.content'), key: 'fact_text', sortable: false },
  { title: tm('memories.person'), key: 'person_id', sortable: false },
  { title: tm('memories.scope'), key: 'scope_id', sortable: false },
  { title: tm('memories.confidence'), key: 'confidence', sortable: false },
  { title: tm('memories.status'), key: 'status', sortable: false },
  { title: tm('memories.updatedAt'), key: 'updated_at', sortable: false },
  { title: tm('actions.title'), key: 'actions', sortable: false },
]);

const pageCount = computed(() =>
  Math.max(Math.ceil(total.value / pageSize), 1),
);

function compactParams<T extends Record<string, string | number>>(params: T) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== ''),
  ) as Partial<T>;
}

function showMessage(text: string, color: 'success' | 'error' = 'success') {
  toastStore.add({ message: text, color });
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-';
}

function formatConfidence(value?: number) {
  return typeof value === 'number' ? value.toFixed(2) : '-';
}

function statusLabel(status?: string) {
  if (status === 'deleted') return tm('status.deleted');
  if (status === 'active') return tm('status.active');
  return status || '-';
}

function operationActionLabel(action?: string) {
  const labels: Record<string, string> = {
    create: tm('operations.actions.create'),
    delete: tm('operations.actions.delete'),
    restore: tm('operations.actions.restore'),
    update: tm('operations.actions.update'),
  };
  return labels[action || ''] || action || '-';
}

function operationActionColor(action?: string) {
  if (action === 'delete') return 'error';
  if (action === 'restore') return 'primary';
  if (action === 'create') return 'success';
  return 'grey';
}

function operationActionIcon(action?: string) {
  if (action === 'delete') return 'mdi-delete-outline';
  if (action === 'restore') return 'mdi-restore';
  if (action === 'create') return 'mdi-plus';
  return 'mdi-pencil-outline';
}

function operationTargetLabel(operation: MemoryOperationData) {
  if (operation.target_type === 'memory_fact') {
    return tm('operations.memoryFact', { id: operation.target_id });
  }
  return operation.target_id || tm('operations.unknownTarget');
}

async function loadStats() {
  try {
    const response = await memoryApi.stats();
    stats.value = response.data.data || {};
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.loadStatsError'), 'error');
  }
}

async function loadFacts() {
  loading.value = true;
  try {
    const response = await memoryApi.facts({
      page: page.value,
      page_size: pageSize,
      status: filters.status,
      ...compactParams({
        person_id: filters.person_id,
        chat_id: filters.chat_id,
        query: filters.query,
      }),
    });
    facts.value = response.data.data?.items || [];
    total.value = response.data.data?.total || 0;
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.loadFactsError'), 'error');
  } finally {
    loading.value = false;
  }
}

async function loadProfiles() {
  profilesLoading.value = true;
  try {
    const response = await memoryApi.profiles({
      page: 1,
      page_size: 10,
      ...compactParams({
        person_id: profileFilters.person_id,
        chat_scope: profileFilters.chat_scope,
      }),
    });
    profiles.value = response.data.data?.items || [];
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.loadProfilesError'), 'error');
  } finally {
    profilesLoading.value = false;
  }
}

async function loadOperations() {
  operationsLoading.value = true;
  try {
    const response = await memoryApi.operations({ page: 1, page_size: 8 });
    operations.value = response.data.data?.items || [];
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.loadOperationsError'), 'error');
  } finally {
    operationsLoading.value = false;
  }
}

async function loadAll() {
  refreshing.value = true;
  try {
    await Promise.all([
      loadFacts(),
      loadProfiles(),
      loadOperations(),
      loadStats(),
    ]);
  } finally {
    refreshing.value = false;
  }
}

function applyFilters() {
  page.value = 1;
  void loadFacts();
}

function clearFilters() {
  filters.person_id = '';
  filters.chat_id = '';
  filters.status = 'all';
  filters.query = '';
  applyFilters();
}

async function openDetail(fact: MemoryFactData) {
  try {
    const response = await memoryApi.fact(fact.id);
    selectedDetail.value = response.data.data;
    detailDialog.value = true;
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.detailError'), 'error');
  }
}

function confirmAction(fact: MemoryFactData, action: 'delete' | 'restore') {
  pendingFact.value = fact;
  pendingAction.value = action;
  actionReason.value = '';
  actionDialog.value = true;
}

async function runPendingAction() {
  if (!pendingFact.value) return;
  actionLoading.value = true;
  try {
    const payload = actionReason.value
      ? { reason: actionReason.value }
      : undefined;
    if (pendingAction.value === 'delete') {
      await memoryApi.deleteFact(pendingFact.value.id, payload);
      showMessage(tm('messages.deleteSuccess'));
    } else {
      await memoryApi.restoreFact(pendingFact.value.id, payload);
      showMessage(tm('messages.restoreSuccess'));
    }
    actionDialog.value = false;
    await loadAll();
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.actionError'), 'error');
  } finally {
    actionLoading.value = false;
  }
}

async function refreshProfile(profile: MemoryProfileData) {
  try {
    await memoryApi.refreshProfile(profile.person_id, {
      chat_scope: profile.chat_scope,
    });
    showMessage(tm('messages.refreshQueued'));
    await loadStats();
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.refreshError'), 'error');
  }
}

onMounted(() => {
  void loadAll();
});
</script>

<style scoped>
.memory-page {
  margin: 0 auto;
  max-width: 1280px;
  padding: 24px;
  width: 100%;
}

.memory-page__header {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 24px;
}

.memory-page__title {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.2;
  margin: 0 0 4px;
}

.memory-page__subtitle {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.875rem;
  margin: 0;
}

.memory-summary__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.memory-summary__item {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 84px;
  padding: 16px 20px;
}

.memory-summary__item:last-child {
  border-right: 0;
}

.memory-summary__item > span {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.8125rem;
}

.memory-summary__item > strong {
  font-size: 1.25rem;
  line-height: 1.2;
}

.memory-summary__item--worker {
  justify-content: center;
}

.memory-card {
  background: rgb(var(--v-theme-surface));
}

.memory-card--full-height {
  height: 100%;
}

.memory-card__title {
  align-items: center;
  display: flex;
  font-size: 1rem;
  justify-content: space-between;
  min-height: 56px;
  padding: 0 16px;
}

.memory-filters {
  width: 100%;
}

.memory-table :deep(table) {
  table-layout: fixed;
}

.memory-table :deep(th:nth-child(1)),
.memory-table :deep(td:nth-child(1)) {
  width: 64px;
}

.memory-table :deep(th:nth-child(3)),
.memory-table :deep(td:nth-child(3)) {
  width: 164px;
}

.memory-table :deep(th:nth-child(4)),
.memory-table :deep(td:nth-child(4)) {
  width: 184px;
}

.memory-table :deep(th:nth-child(5)),
.memory-table :deep(td:nth-child(5)) {
  width: 96px;
}

.memory-table :deep(th:nth-child(6)),
.memory-table :deep(td:nth-child(6)) {
  width: 100px;
}

.memory-table :deep(th:nth-child(7)),
.memory-table :deep(td:nth-child(7)) {
  width: 156px;
}

.memory-table :deep(th:nth-child(8)),
.memory-table :deep(td:nth-child(8)) {
  width: 104px;
}

.memory-id,
.memory-identifier,
.memory-date,
.scope-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-id,
.memory-identifier,
.scope-text {
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    monospace;
  font-size: 0.8125rem;
}

.memory-id,
.scope-text {
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.fact-text {
  -webkit-box-orient: vertical;
  display: -webkit-box;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
}

.memory-table__actions {
  display: flex;
  justify-content: flex-end;
}

.memory-cards-mobile {
  display: none;
}

.memory-fact-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 14px;
}

.memory-fact-card + .memory-fact-card {
  margin-top: 12px;
}

.fact-card-head,
.fact-card-actions {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.fact-card-text {
  line-height: 1.6;
  margin: 12px 0;
}

.fact-card-meta {
  color: rgba(var(--v-theme-on-surface), 0.62);
  display: flex;
  flex-direction: column;
  font-size: 0.75rem;
  gap: 4px;
}

.fact-card-meta span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fact-card-actions {
  justify-content: flex-end;
  margin-top: 8px;
}

.memory-empty-state,
.memory-mobile-loading,
.memory-section-empty {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.6);
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: center;
  min-height: 152px;
  padding: 24px;
  text-align: center;
}

.memory-section-empty {
  min-height: 120px;
}

.profile-text {
  -webkit-box-orient: vertical;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
}

.memory-secondary-grid {
  display: grid;
  gap: 24px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 960px) {
  .memory-table-desktop {
    display: none;
  }

  .memory-cards-mobile {
    display: block;
  }

  .memory-summary__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .memory-summary__item:nth-child(3) {
    border-right: 0;
  }

  .memory-summary__item:nth-child(-n + 3) {
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  }
}

@media (max-width: 720px) {
  .memory-page {
    padding: 16px;
  }

  .memory-page__header {
    align-items: stretch;
    flex-direction: column;
  }

  .memory-page__header :deep(.v-btn) {
    align-self: flex-start;
  }

  .memory-summary__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-summary__item {
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    padding: 14px 16px;
  }

  .memory-summary__item:nth-child(2),
  .memory-summary__item:nth-child(4) {
    border-right: 0;
  }

  .memory-summary__item:nth-child(3) {
    border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  }

  .memory-summary__item:last-child {
    border-bottom: 0;
    border-right: 0;
    grid-column: 1 / -1;
  }

  .memory-secondary-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <div class="observer-page" :class="{ 'is-dark': isDark }">
    <section v-if="!selectedUmo" class="observer-home">
      <div class="home-center">
        <div class="home-copy">
          <h1>{{ tm("emptyTitle") }}</h1>
          <p>{{ tm("emptySubtitle") }}</p>
        </div>

        <div class="home-search-shell">
          <form class="home-search" @submit.prevent="selectFirstSearchResult">
            <Search :size="21" />
            <input v-model="searchQuery" :placeholder="tm('searchPlaceholder')" />
            <button
              class="home-search-submit"
              type="submit"
              :disabled="!searchSuggestionRows.length"
              :title="tm('actions.open')"
            >
              <ArrowRight :size="22" />
            </button>
          </form>

          <div v-if="hasSearchQuery" class="search-suggestions">
            <button
              v-for="umo in searchSuggestionRows"
              :key="umo.umo"
              class="suggestion-row"
              type="button"
              @click="selectUmo(umo.umo)"
            >
              <Search :size="17" />
              <span>
                <strong>{{ umo.display_name || umo.umo }}</strong>
                <small>{{ describeUmo(umo) }}</small>
              </span>
            </button>
            <div v-if="!searchSuggestionRows.length" class="inline-empty compact">
              {{ tm("home.noMatches") }}
            </div>
          </div>
        </div>

        <div class="home-resources">
          <div class="home-section-title">{{ tm("home.resources") }}</div>
          <div class="resource-card-grid">
            <button class="resource-card" type="button" @click="openRules">
              <SlidersHorizontal :size="24" />
              <strong>{{ tm("home.resourceCards.rules") }}</strong>
              <small>{{ tm("home.resourceCards.rulesHint") }}</small>
            </button>
            <button class="resource-card" type="button" @click="openRoute('/conversation')">
              <MessageSquare :size="24" />
              <strong>{{ tm("home.resourceCards.conversation") }}</strong>
              <small>{{ tm("home.resourceCards.conversationHint") }}</small>
            </button>
            <button class="resource-card" type="button" @click="openRoute('/trace')">
              <Activity :size="24" />
              <strong>{{ tm("home.resourceCards.trace") }}</strong>
              <small>{{ tm("home.resourceCards.traceHint") }}</small>
            </button>
            <button class="resource-card" type="button" @click="openRoute('/dashboard/default')">
              <BarChart3 :size="24" />
              <strong>{{ tm("home.resourceCards.stats") }}</strong>
              <small>{{ tm("home.resourceCards.statsHint") }}</small>
            </button>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="observer-detail">
      <div class="detail-shell">
        <main class="detail-main">
          <header class="observer-detail-head">
            <div class="detail-title-row">
              <button
                class="icon-button"
                type="button"
                :title="tm('actions.back')"
                @click="clearSelectedUmo"
              >
                <ArrowLeft :size="18" />
              </button>
              <h1>{{ tm("detail.title") }}</h1>
            </div>

            <div class="umo-strip">
              <UmoDisplay
                :umo="selectedUmo.umo"
                :platform="selectedUmo.platform"
                :message-type="selectedUmo.message_type"
                :session-id="selectedUmo.session_id"
                :auto-name="selectedUmo.auto_name"
                :user-alias="selectedUmo.user_alias"
                :show-info="false"
              />
              <div class="detail-actions">
                <button
                  class="icon-button"
                  type="button"
                  :title="tm('detail.copy')"
                  @click="copySelectedUmo"
                >
                  <Copy :size="16" />
                </button>
                <button
                  v-if="chatSessionId"
                  class="icon-button"
                  type="button"
                  :title="tm('detail.openChat')"
                  @click="openChat"
                >
                  <ExternalLink :size="16" />
                </button>
              </div>
            </div>
          </header>

          <div class="detail-grid">
            <aside class="conversation-selector">
              <div class="selector-head">
                <h2>{{ tm("conversation.title") }}</h2>
                <span>{{ tm("conversation.count", { count: conversationTotal }) }}</span>
              </div>
              <div class="conversation-list">
                <button
                  v-for="conversation in conversations"
                  :key="conversation.cid"
                  class="conversation-row"
                  :class="{ active: selectedConversationId === conversation.cid }"
                  type="button"
                  @click="selectConversation(conversation)"
                >
                  <span>{{ conversation.title || conversation.cid }}</span>
                  <small>{{ formatDate(conversation.updated_at || conversation.created_at) }}</small>
                </button>
                <div v-if="!conversations.length && !loadingConversations" class="inline-empty">
                  {{ tm("conversation.empty") }}
                </div>
              </div>
            </aside>

            <section class="chat-preview">
              <div v-if="loadingConversationDetail" class="center-state">
                <v-progress-circular indeterminate size="28" width="3" />
              </div>
              <ChatMessageList
                v-else-if="previewMessages.length"
                :messages="previewMessages"
                :is-dark="isDark"
                :enable-edit="false"
                :enable-regenerate="false"
                :enable-thread-selection="false"
                :manage-refs-sidebar="false"
                variant="main"
              />
              <div v-else class="center-state muted">
                {{ tm("conversation.select") }}
              </div>
            </section>
          </div>
        </main>

        <aside class="observer-inspector">
          <section class="inspector-card">
            <div class="card-head">
              <span>{{ tm("detail.config") }}</span>
              <button
                class="icon-button small"
                type="button"
                :title="tm('detail.openConfig')"
                @click="openConfigDrawer"
              >
                <ExternalLink :size="15" />
              </button>
            </div>
            <div class="config-title-line">
              <strong>{{ currentConfigLabel }}</strong>
              <v-chip
                class="override-count-chip"
                color="primary"
                size="x-small"
                variant="tonal"
                @click="openRules"
              >
                <span>{{ tm("overrides.count", { count: overrideRows.length }) }}</span>
                <ExternalLink :size="12" />
              </v-chip>
            </div>
            <small v-if="matchedRoute">{{ currentRouteLabel }}</small>
          </section>

          <section class="inspector-card token-card">
            <div class="card-head">
              <span>{{ tm("tokens.title") }}</span>
              <span class="status-pill">{{ tm("tokens.window") }}</span>
            </div>
            <strong>{{ loadingTokenStats ? "..." : selectedUmoTokenLabel }}</strong>
            <small>
              {{ tm("tokens.unit") }}
              <template v-if="latestConversationTime">
                · {{ tm("conversation.latest") }} {{ latestConversationTime }}
              </template>
            </small>
          </section>

          <section class="inspector-card workspace-card">
            <div class="card-head">
              <span>{{ tm("workspace.title") }}</span>
              <div class="workspace-actions">
                <button
                  class="icon-button small"
                  type="button"
                  :disabled="!workspace.absolute_path"
                  :title="tm('workspace.copyPath')"
                  @click="copyWorkspacePath"
                >
                  <Copy :size="15" />
                </button>
                <button
                  v-if="workspace.relative_path"
                  class="icon-button small"
                  type="button"
                  :title="tm('workspace.parent')"
                  @click="openWorkspaceParent"
                >
                  <ArrowUp :size="15" />
                </button>
              </div>
            </div>
            <div v-if="!workspace.exists" class="inline-empty compact">
              {{ tm("workspace.missing") }}
            </div>
            <div v-else-if="workspace.items.length" class="file-list">
              <button
                v-for="item in workspace.items.slice(0, 6)"
                :key="item.relative_path"
                class="file-row"
                type="button"
                :disabled="item.type !== 'directory'"
                @click="openWorkspaceItem(item)"
              >
                <Folder v-if="item.type === 'directory'" :size="15" />
                <FileText v-else :size="15" />
                <span>{{ item.name }}</span>
                <small>{{ item.type === "directory" ? "" : formatBytes(item.size_bytes) }}</small>
              </button>
            </div>
            <div v-else class="inline-empty compact">{{ tm("workspace.empty") }}</div>
          </section>

          <section class="inspector-card trace-card">
            <div class="card-head">
              <span>{{ tm("trace.title") }}</span>
              <small>{{ tm("trace.hint") }}</small>
            </div>
            <TraceDisplayer :max-items="24" />
          </section>
        </aside>
      </div>
    </section>

    <v-overlay
      v-model="showConfigDrawer"
      class="observer-config-drawer-overlay"
      location="right"
      transition="slide-x-reverse-transition"
      :scrim="true"
      @click:outside="closeConfigDrawer"
    >
      <v-card class="observer-config-drawer-card" elevation="12">
        <div class="observer-config-drawer-header">
          <div>
            <span class="text-h6">{{ tm("detail.configDrawerTitle") }}</span>
            <div class="text-caption text-grey">
              {{ tm("detail.configDrawerIdLabel") }}: {{ currentConfigId }}
            </div>
          </div>
          <v-btn icon variant="text" @click="closeConfigDrawer">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </div>
        <v-divider />
        <div class="observer-config-drawer-content">
          <ConfigPage
            v-if="showConfigDrawer"
            :initial-config-id="currentConfigId"
          />
        </div>
      </v-card>
    </v-overlay>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useTheme } from "vuetify";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BarChart3,
  Copy,
  ExternalLink,
  FileText,
  Folder,
  MessageSquare,
  Search,
  SlidersHorizontal,
} from "@lucide/vue";

import {
  configProfileApi,
  configRouteApi,
  conversationApi,
  sessionApi,
  statsApi,
  workspaceApi,
} from "@/api/v1";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";
import type { ChatRecord, MessagePart } from "@/composables/useMessages";
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import UmoDisplay from "@/components/shared/UmoDisplay.vue";
import { useModuleI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import ConfigPage from "@/views/ConfigPage.vue";

interface UmoInfo {
  umo: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  display_name?: string;
  auto_name?: string;
  user_alias?: string;
}

interface ConversationItem {
  cid: string;
  title?: string;
  user_id?: string;
  created_at?: string | number;
  updated_at?: string | number;
}

interface WorkspaceItem {
  name: string;
  type: "directory" | "file" | "symlink" | "other";
  relative_path: string;
  size_bytes?: number;
  modified_at?: string | null;
}

interface UmoTokenStat {
  umo: string;
  tokens: number;
}

const route = useRoute();
const router = useRouter();
const theme = useTheme();
const { tm } = useModuleI18n("features/observer");

const isDark = computed(() => theme.global.current.value.dark);
const searchQuery = ref("");
const selectedUmoId = ref("");
const loadingConversations = ref(false);
const loadingConversationDetail = ref(false);
const showConfigDrawer = ref(false);
const umos = ref<UmoInfo[]>([]);
const conversations = ref<ConversationItem[]>([]);
const selectedConversationId = ref("");
const previewMessages = ref<ChatRecord[]>([]);
const conversationTotal = ref(0);
const overrideRows = ref<Array<{ path: string; value: string }>>([]);
const configRoutes = ref<Record<string, string>>({});
const configProfiles = ref<Record<string, string>>({});
const loadingTokenStats = ref(false);
const umoTokenTotals = ref<Record<string, number>>({});
const workspace = reactive({
  absolute_path: "",
  relative_path: "",
  exists: false,
  items: [] as WorkspaceItem[],
});

const selectedUmo = computed(() =>
  umos.value.find((item) => item.umo === selectedUmoId.value),
);

const filteredUmos = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return umos.value;
  return umos.value.filter((item) =>
    [
      item.umo,
      item.display_name || "",
      item.auto_name || "",
      item.user_alias || "",
      item.platform || "",
      item.message_type || "",
      item.session_id || "",
    ].some((value) => value.toLowerCase().includes(query)),
  );
});

const hasSearchQuery = computed(() => Boolean(searchQuery.value.trim()));

const searchSuggestionRows = computed(() =>
  hasSearchQuery.value ? filteredUmos.value.slice(0, 5) : [],
);

const latestConversationTime = computed(() => {
  const first = conversations.value[0];
  return formatDate(first?.updated_at || first?.created_at);
});

const matchedRoute = computed(() => {
  const umo = selectedUmoId.value;
  if (!umo) return null;
  for (const [pattern, configId] of Object.entries(configRoutes.value)) {
    if (umoRouteMatches(pattern, umo)) {
      return { pattern, configId };
    }
  }
  return null;
});

const currentConfigId = computed(() => matchedRoute.value?.configId || "default");

const currentConfigLabel = computed(() => {
  const configId = currentConfigId.value;
  if (configId === "default") return tm("detail.defaultConfig");
  return configProfiles.value[configId]
    ? `${configProfiles.value[configId]} (${configId})`
    : configId;
});

const currentRouteLabel = computed(() =>
  matchedRoute.value?.pattern || tm("detail.noRoute"),
);

const selectedUmoTokenTotal = computed(() =>
  Math.max(0, Number(umoTokenTotals.value[selectedUmoId.value] || 0)),
);

const selectedUmoTokenLabel = computed(() =>
  formatCompactNumber(selectedUmoTokenTotal.value),
);

const chatSessionId = computed(() => {
  const umo = selectedUmoId.value;
  const sessionId = umo.split(":").slice(2).join(":");
  const parts = sessionId.split("!");
  if (!umo.startsWith("webchat:") || parts.length !== 3 || parts[0] !== "webchat") {
    return "";
  }
  return parts[2] || "";
});

watch(
  () => route.query.umo,
  (value) => {
    const next = Array.isArray(value) ? value[0] : value;
    selectedUmoId.value = typeof next === "string" ? next : "";
  },
  { immediate: true },
);

watch(selectedUmoId, (umo) => {
  if (!umo) return;
  loadUmoResources(umo);
});

onMounted(async () => {
  await refreshAll();
});

async function refreshAll() {
  await Promise.all([loadUmos(), loadConfigContext(), loadProviderTokenStats()]);
  if (selectedUmoId.value) {
    await loadUmoResources(selectedUmoId.value);
  }
}

async function loadUmos() {
  const response = await sessionApi.activeUmos();
  if (response.data.status !== "ok") return;
  const data = response.data.data || {};
  const infos = Array.isArray(data.umo_infos) ? data.umo_infos : [];
  const rawUmos = Array.isArray(data.umos) ? data.umos : [];
  const fromRaw = rawUmos.map((umo: string) => ({ umo }));
  umos.value = (infos.length ? infos : fromRaw).filter((item: UmoInfo) => item.umo);
}

async function loadConfigContext() {
  const [routesResponse, profilesResponse] = await Promise.all([
    configRouteApi.list(),
    configProfileApi.list(),
  ]);
  configRoutes.value = routesResponse.data.data?.routing || {};
  const profiles = profilesResponse.data.data?.info_list || [];
  configProfiles.value = Object.fromEntries(
    profiles.map((profile: any) => [
      String(profile.id || profile.conf_id || ""),
      String(profile.name || profile.id || profile.conf_id || ""),
    ]),
  );
}

async function loadProviderTokenStats() {
  loadingTokenStats.value = true;
  try {
    const response = await statsApi.providerTokens(1);
    if (response.data.status !== "ok") {
      umoTokenTotals.value = {};
      return;
    }
    const rows = response.data.data?.range_by_umo || [];
    umoTokenTotals.value = Object.fromEntries(
      rows.map((row: UmoTokenStat) => [
        String(row.umo || ""),
        Math.max(0, Number(row.tokens || 0)),
      ]),
    );
  } catch {
    umoTokenTotals.value = {};
  } finally {
    loadingTokenStats.value = false;
  }
}

async function loadUmoResources(umo: string) {
  await Promise.all([loadOverrides(umo), loadConversations(umo), loadWorkspace(umo)]);
}

async function loadOverrides(umo: string) {
  const response = await sessionApi.listConfigOverrides({
    page: 1,
    page_size: 1,
    umo,
  });
  if (response.data.status !== "ok") {
    overrideRows.value = [];
    return;
  }
  const row = (response.data.data?.rules || []).find((item: any) => item.umo === umo);
  overrideRows.value = flattenRules(row?.rules || {});
}

async function loadConversations(umo: string) {
  loadingConversations.value = true;
  try {
    const response = await conversationApi.list({
      page: 1,
      page_size: 12,
      user_id: umo,
      exclude_ids: "astrbot",
    });
    if (response.data.status !== "ok") return;
    const data = response.data.data || {};
    conversations.value = data.conversations || [];
    conversationTotal.value = data.pagination?.total || conversations.value.length;
    const first = conversations.value[0];
    if (first) {
      selectedConversationId.value = "";
      await selectConversation(first);
    } else {
      selectedConversationId.value = "";
      previewMessages.value = [];
    }
  } finally {
    loadingConversations.value = false;
  }
}

async function selectConversation(conversation: ConversationItem) {
  if (!conversation.cid || selectedConversationId.value === conversation.cid) return;
  selectedConversationId.value = conversation.cid;
  loadingConversationDetail.value = true;
  try {
    const response = await conversationApi.get(
      selectedUmoId.value,
      conversation.cid,
    );
    const history = JSON.parse(response.data.data?.history || "[]");
    previewMessages.value = conversationHistoryToChatRecords(history);
  } catch {
    previewMessages.value = [];
  } finally {
    loadingConversationDetail.value = false;
  }
}

async function loadWorkspace(umo: string, path = "") {
  try {
    const response = await workspaceApi.byUmo({ umo, path });
    const data = response.data.data || {};
    workspace.absolute_path = data.absolute_path || "";
    workspace.relative_path = data.relative_path || "";
    workspace.exists = Boolean(data.exists);
    workspace.items = Array.isArray(data.items) ? data.items : [];
  } catch {
    workspace.absolute_path = "";
    workspace.relative_path = "";
    workspace.exists = false;
    workspace.items = [];
  }
}

function selectUmo(umo: string) {
  selectedUmoId.value = umo;
  router.replace({ query: { ...route.query, umo } });
}

function selectFirstSearchResult() {
  const first = filteredUmos.value[0];
  if (!first?.umo) return;
  selectUmo(first.umo);
}

function clearSelectedUmo() {
  selectedUmoId.value = "";
  selectedConversationId.value = "";
  previewMessages.value = [];
  const nextQuery = { ...route.query };
  delete nextQuery.umo;
  router.replace({ query: nextQuery });
}

function describeUmo(umo: UmoInfo) {
  return [umo.platform, umo.message_type, umo.session_id]
    .filter(Boolean)
    .join(" / ");
}

function openRules() {
  router.push({
    path: "/session-management",
    query: selectedUmoId.value ? { search: selectedUmoId.value } : {},
  });
}

function openConfigDrawer() {
  showConfigDrawer.value = true;
}

function closeConfigDrawer() {
  showConfigDrawer.value = false;
}

function openChat() {
  if (!chatSessionId.value) return;
  router.push(`/chat/${encodeURIComponent(chatSessionId.value)}`);
}

function openRoute(path: string) {
  router.push(path);
}

async function copySelectedUmo() {
  await copyToClipboard(selectedUmoId.value);
}

async function copyWorkspacePath() {
  if (!workspace.absolute_path) return;
  await copyToClipboard(workspace.absolute_path);
}

function openWorkspaceItem(item: WorkspaceItem) {
  if (item.type !== "directory") return;
  loadWorkspace(selectedUmoId.value, item.relative_path);
}

function openWorkspaceParent() {
  const parts = workspace.relative_path.split("/").filter(Boolean);
  parts.pop();
  loadWorkspace(selectedUmoId.value, parts.join("/"));
}

function flattenRules(rules: Record<string, any>) {
  const rows: Array<{ path: string; value: string }> = [];
  const service = rules.session_service_config || {};
  const providers = [
    ["provider_settings.enable", service.llm_enabled],
    ["provider_tts_settings.enable", service.tts_enabled],
    ["provider_settings.default_personality", service.persona_id],
    ["platform_settings.id_blacklist", service.session_enabled === false],
    ["provider_settings.default_provider_id", rules.provider_perf_chat_completion],
    ["provider_stt_settings.provider_id", rules.provider_perf_speech_to_text],
    ["provider_tts_settings.provider_id", rules.provider_perf_text_to_speech],
    ["plugin_disabled_set", rules.session_plugin_config?.disabled_plugins],
    ["kb_names", rules.kb_config?.kb_names],
    ["kb_final_top_k", rules.kb_config?.top_k],
  ];
  for (const [path, value] of providers) {
    if (value === undefined || value === null || value === false || value === "") {
      continue;
    }
    rows.push({ path: String(path), value: formatValue(value) });
  }
  return rows;
}

function conversationHistoryToChatRecords(history: any[]): ChatRecord[] {
  const toolResultsById: Record<string, unknown> = {};
  for (const message of history) {
    if (message?.role === "tool" && message.tool_call_id) {
      toolResultsById[message.tool_call_id] = message.content;
    }
  }
  return history
    .filter((message) => message?.role === "user" || message?.role === "assistant")
    .map((message, index) => {
      const parts = contentToMessageParts(message.content).filter(
        (part) => part.type !== "plain" || String(part.text || "").trim(),
      );
      if (message.role === "assistant" && Array.isArray(message.tool_calls)) {
        parts.push({
          type: "tool_call",
          tool_calls: message.tool_calls.map((toolCall: any) => {
            const fn = toolCall.function || {};
            return {
              id: toolCall.id,
              name: fn.name || toolCall.name,
              args: fn.arguments ?? toolCall.arguments,
              result: toolResultsById[toolCall.id],
              ts: 0,
              finished_ts: 1,
            };
          }),
        });
      }
      return {
        id: `${message.role}-${index}`,
        content: {
          type: message.role === "user" ? "user" : "bot",
          message: parts.length ? parts : [{ type: "plain", text: "" }],
        },
      };
    });
}

function contentToMessageParts(content: unknown): MessagePart[] {
  if (typeof content === "string") {
    return content.trim() ? [{ type: "plain", text: content }] : [];
  }
  if (Array.isArray(content)) {
    return content.flatMap((item): MessagePart[] => {
      if (item?.type === "text" && item.text) {
        return [{ type: "plain", text: item.text }];
      }
      if (item?.type === "image_url" && item.image_url?.url) {
        return [{ type: "image", embedded_url: item.image_url.url }];
      }
      return [];
    });
  }
  if (content && typeof content === "object") {
    const text = Object.values(content)
      .filter((value) => typeof value === "string" && value.trim())
      .join("\n");
    return text ? [{ type: "plain", text }] : [];
  }
  return [];
}

function umoRouteMatches(pattern: string, umo: string) {
  const patternParts = splitUmo(pattern);
  const umoParts = splitUmo(umo);
  if (patternParts.length !== 3 || umoParts.length !== 3) return false;
  return patternParts.every((part, index) => {
    if (!part) return true;
    const escaped = part.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
    return new RegExp(`^${escaped}$`).test(umoParts[index]);
  });
}

function splitUmo(value: string) {
  const parts = value.split(":");
  if (parts.length < 3) return parts;
  return [parts[0], parts[1], parts.slice(2).join(":")];
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "[]";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function formatBytes(value?: number) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function formatCompactNumber(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
  return new Intl.NumberFormat().format(value);
}

function formatDate(value?: string | number) {
  if (!value) return "";
  const numericValue = typeof value === "number" ? value : Number(value);
  const date =
    Number.isFinite(numericValue) && numericValue > 0 && numericValue < 1_000_000_000_000
      ? new Date(numericValue * 1000)
      : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
</script>

<style scoped>
.observer-page {
  --observer-bg: rgb(var(--v-theme-background));
  --observer-surface: rgb(var(--v-theme-surface));
  --observer-card: rgb(var(--v-theme-surface));
  --observer-text: rgb(var(--v-theme-on-surface));
  --observer-muted: rgba(var(--v-theme-on-surface), 0.58);
  --observer-subtle: rgba(var(--v-theme-on-surface), 0.42);
  --observer-border: rgba(var(--v-theme-on-surface), 0.1);
  --observer-hover: rgba(var(--v-theme-on-surface), 0.045);
  --observer-active: rgba(var(--v-theme-on-surface), 0.075);
  height: calc(100vh - 60px);
  overflow: hidden;
  background: var(--observer-bg);
  color: var(--observer-text);
  font-family:
    -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC",
    "Microsoft YaHei", sans-serif;
}

.observer-page.is-dark {
  --observer-card: rgba(var(--v-theme-surface), 0.92);
  --observer-border: rgba(var(--v-theme-on-surface), 0.14);
  --observer-hover: rgba(var(--v-theme-on-surface), 0.07);
  --observer-active: rgba(var(--v-theme-on-surface), 0.1);
}

.observer-home,
.observer-detail {
  height: 100%;
  min-height: 0;
}

.observer-home {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 44px 24px 96px;
}

.home-center {
  display: flex;
  width: min(760px, 100%);
  flex-direction: column;
  align-items: center;
  margin-top: -4vh;
}

.home-copy {
  max-width: 600px;
  text-align: center;
}

.home-copy h1 {
  margin: 0;
  font-size: 34px;
  font-weight: 760;
  line-height: 1.2;
  letter-spacing: 0;
}

.home-copy p {
  margin: 16px 0 0;
  color: var(--observer-muted);
  font-size: 15px;
  line-height: 1.75;
}

.home-search-shell {
  position: relative;
  width: min(720px, 100%);
  margin-top: 34px;
}

.home-search {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  min-height: 58px;
  padding: 0 8px 0 20px;
  border-radius: 999px;
  background: var(--observer-hover);
  color: var(--observer-muted);
}

.home-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--observer-text);
  font: inherit;
  font-size: 15px;
}

.home-search-submit {
  display: inline-flex;
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  cursor: pointer;
}

.home-search-submit:disabled {
  cursor: default;
  opacity: 0.4;
}

.search-suggestions {
  position: absolute;
  z-index: 5;
  top: calc(100% + 10px);
  left: 0;
  display: grid;
  width: 100%;
  gap: 2px;
  padding: 8px;
  border: 1px solid var(--observer-border);
  border-radius: 8px;
  background: var(--observer-card);
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
}

.suggestion-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 58px;
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.suggestion-row:hover {
  background: var(--observer-hover);
}

.suggestion-row svg {
  color: rgb(var(--v-theme-primary));
}

.suggestion-row span {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.suggestion-row strong,
.suggestion-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.suggestion-row strong {
  font-size: 14px;
  font-weight: 650;
}

.home-resources {
  display: grid;
  width: min(560px, 100%);
  gap: 16px;
  margin-top: 54px;
}

.home-section-title {
  color: var(--observer-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-align: center;
  text-transform: uppercase;
}

.resource-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.resource-card {
  display: grid;
  min-height: 118px;
  align-content: center;
  justify-items: center;
  gap: 8px;
  border: 1px solid var(--observer-border);
  border-radius: 8px;
  padding: 14px 12px;
  background: var(--observer-card);
  color: inherit;
  cursor: pointer;
  text-align: center;
}

.resource-card:hover {
  background: var(--observer-hover);
}

.resource-card svg {
  color: rgb(var(--v-theme-primary));
}

.resource-card strong {
  max-width: 100%;
  overflow: hidden;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-card small,
.suggestion-row small,
.selector-head span,
.conversation-row small,
.card-head small,
.inspector-card > small,
.status-pill {
  color: var(--observer-muted);
  font-size: 12px;
  line-height: 1.45;
}

.observer-detail {
  min-height: 0;
}

.detail-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 370px);
  height: 100%;
  min-height: 0;
}

.detail-main {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}

.observer-detail-head {
  display: flex;
  min-height: 74px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--observer-border);
  background: var(--observer-surface);
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-title-row h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 740;
  letter-spacing: 0;
  white-space: nowrap;
}

.umo-strip {
  display: flex;
  width: min(560px, 58%);
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 8px 7px 12px;
  border-radius: 8px;
  background: var(--observer-active);
}

.umo-strip :deep(.umo-display) {
  min-width: 0;
}

.detail-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
}

.icon-button {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--observer-muted);
  cursor: pointer;
}

.icon-button.small {
  width: 28px;
  height: 28px;
}

.icon-button:hover {
  background: var(--observer-hover);
}

.icon-button:disabled {
  cursor: default;
  opacity: 0.42;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(190px, 230px) minmax(0, 1fr);
  min-height: 0;
  flex: 1;
}

.conversation-selector {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  border-right: 1px solid var(--observer-border);
  background: var(--observer-surface);
}

.selector-head {
  display: grid;
  min-height: 64px;
  align-content: center;
  gap: 3px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--observer-border);
}

.selector-head h2,
.card-head span {
  margin: 0;
  font-size: 13px;
  font-weight: 720;
  line-height: 1.25;
  letter-spacing: 0;
}

.conversation-list,
.file-list {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow-y: auto;
}

.conversation-row,
.file-row {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}

.conversation-row:hover,
.file-row:not(:disabled):hover {
  background: var(--observer-hover);
}

.conversation-row.active {
  background: var(--observer-active);
}

.conversation-list {
  gap: 2px;
  padding: 10px 8px 14px;
}

.conversation-row {
  display: grid;
  min-height: 54px;
  align-content: center;
  gap: 4px;
  border-radius: 9px;
  padding: 8px 10px;
  text-align: left;
}

.conversation-row span,
.conversation-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-row span {
  font-size: 13px;
  font-weight: 600;
}

.chat-preview {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 0;
  background: var(--observer-bg);
}

.chat-preview :deep(.chat-message-list) {
  min-height: 100%;
}

.chat-preview :deep(.messages-list) {
  width: min(760px, calc(100% - 32px));
  margin: 0 auto;
  gap: 14px;
}

.chat-preview :deep(.message-row) {
  gap: 0;
}

.chat-preview :deep(.message-row.from-bot .bot-avatar) {
  display: none;
}

.chat-preview :deep(.message-stack) {
  max-width: min(720px, 88%);
}

.chat-preview :deep(.from-user .message-stack) {
  max-width: 68%;
}

.chat-preview :deep(.message-bubble) {
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.55;
}

.chat-preview :deep(.message-bubble.user) {
  padding: 9px 13px;
  font-size: 13px;
}

.chat-preview :deep(.message-bubble.bot) {
  padding-left: 0;
}

.chat-preview :deep(.markdown-content) {
  font-size: 13px;
  line-height: 1.55;
}

.chat-preview :deep(.markdown-content p) {
  margin: 0.15rem 0;
}

.chat-preview :deep(.message-meta) {
  min-height: 20px;
  font-size: 11px;
}

.observer-inspector {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 14px;
  border-left: 1px solid var(--observer-border);
  background: var(--observer-surface);
}

.inspector-card {
  display: grid;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--observer-border);
  border-radius: 8px;
  background: var(--observer-card);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.workspace-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
}

.inspector-card > strong {
  min-width: 0;
  overflow: hidden;
  font-size: 21px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-title-line {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.config-title-line > strong {
  min-width: 0;
  overflow: hidden;
  font-size: 21px;
  font-weight: 760;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.override-count-chip {
  flex: 0 0 auto;
  cursor: pointer;
}

.override-count-chip :deep(.v-chip__content) {
  gap: 4px;
}

.token-card > strong {
  font-size: 30px;
}

.status-pill {
  border-radius: 999px;
  padding: 3px 7px;
  background: var(--observer-active);
  font-size: 11px;
  font-weight: 700;
}

.kv-list {
  display: grid;
}

.kv-row,
.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  border-bottom: 1px solid var(--observer-border);
  color: var(--observer-muted);
  font-size: 12px;
}

.kv-row {
  min-height: 36px;
}

.kv-row span,
.file-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kv-row strong,
.file-row small {
  flex: 0 0 auto;
  max-width: 45%;
  overflow: hidden;
  color: var(--observer-text);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-list {
  gap: 1px;
}

.file-row {
  width: 100%;
  justify-content: flex-start;
  border-radius: 8px;
  border-bottom: 0;
  padding: 0 8px;
  text-align: left;
}

.file-row:disabled {
  cursor: default;
}

.file-row svg {
  flex: 0 0 auto;
  color: var(--observer-subtle);
}

.file-row small {
  margin-left: auto;
  color: var(--observer-muted);
}

.trace-card {
  display: flex;
  flex-direction: column;
  min-height: 300px;
}

.trace-card :deep(.trace-wrapper) {
  min-height: 0;
  flex: 1;
  padding: 0;
}

.trace-card :deep(.trace-row) {
  grid-template-columns: 82px minmax(0, 1fr);
}

.trace-card :deep(.trace-stage),
.trace-card :deep(.trace-time),
.trace-card :deep(.trace-duration),
.trace-card :deep(.trace-id) {
  display: none;
}

.center-state,
.inline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--observer-muted);
  font-size: 13px;
}

.center-state {
  min-height: 240px;
}

.inline-empty {
  min-height: 96px;
  padding: 18px;
  text-align: center;
}

.inline-empty.compact {
  min-height: 58px;
  padding: 10px;
}

.muted {
  color: var(--observer-subtle);
}

.observer-config-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.observer-config-drawer-card {
  display: flex;
  width: clamp(340px, 60vw, 860px);
  height: calc(100vh - 32px);
  flex-direction: column;
  margin: 16px;
}

.observer-config-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px 12px;
}

.observer-config-drawer-content {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 24px;
}

@media (max-width: 1180px) {
  .resource-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-shell {
    grid-template-columns: minmax(0, 1fr) 320px;
  }

  .detail-grid {
    grid-template-columns: minmax(180px, 220px) minmax(0, 1fr);
  }
}

@media (max-width: 820px) {
  .observer-page {
    height: auto;
    min-height: calc(100vh - 60px);
    overflow: visible;
  }

  .observer-home {
    padding: 36px 16px 64px;
  }

  .home-copy h1 {
    font-size: 28px;
  }

  .home-resources {
    width: min(360px, 100%);
  }

  .resource-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-shell {
    grid-template-columns: 1fr;
  }

  .observer-detail-head {
    align-items: stretch;
    flex-direction: column;
    min-height: auto;
    padding: 14px;
  }

  .umo-strip {
    width: 100%;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .conversation-selector {
    border-bottom: 1px solid var(--observer-border);
    border-right: 0;
  }

  .conversation-list {
    max-height: 220px;
  }

  .chat-preview {
    min-height: 520px;
  }

  .observer-inspector {
    max-height: none;
    border-top: 1px solid var(--observer-border);
    border-left: 0;
  }
}
</style>

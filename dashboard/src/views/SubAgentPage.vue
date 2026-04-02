<template>
  <div class="subagent-page">
    <div class="subagent-topbar">
      <div class="topbar-left">
        <div class="topbar-eyebrow">{{ tm("header.eyebrow") }}</div>
        <div class="d-flex align-center flex-wrap" style="gap: 8px">
          <h1 class="topbar-title">{{ tm("page.title") }}</h1>
          <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>
            {{ tm("page.beta") }}
          </v-chip>
        </div>
        <p class="topbar-desc">{{ tm("page.subtitle") }}</p>
      </div>
      <div class="topbar-right">
        <v-btn
          variant="text"
          color="primary"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="reload"
        >
          {{ tm("actions.refresh") }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-content-save"
          :loading="saving"
          @click="save"
        >
          {{ tm("actions.save") }}
        </v-btn>
      </div>
    </div>

    <div v-if="hasUnsavedChanges" class="unsaved-banner">
      <v-icon size="18" color="warning">mdi-alert-circle-outline</v-icon>
      <span>{{ tm("messages.unsavedChangesNotice") }}</span>
    </div>

    <div class="subagent-section-head">
      <div>
        <div class="subagent-section-title">
          {{ tm("section.globalSettings") }}
        </div>
        <div class="subagent-section-subtitle">{{ mainStateDescription }}</div>
      </div>
    </div>

    <div class="subagent-settings-grid">
      <div class="subagent-setting-card">
        <div class="setting-card-head">
          <div>
            <div class="setting-title">{{ tm("switches.enable") }}</div>
            <div class="setting-subtitle">{{ tm("switches.enableHint") }}</div>
          </div>
          <v-switch
            v-model="cfg.main_enable"
            color="primary"
            hide-details
            inset
            density="comfortable"
          />
        </div>
      </div>

      <div class="subagent-setting-card">
        <div class="setting-card-head">
          <div>
            <div class="setting-title">{{ tm("switches.dedupe") }}</div>
            <div class="setting-subtitle">{{ tm("switches.dedupeHint") }}</div>
          </div>
          <v-switch
            v-model="cfg.remove_main_duplicate_tools"
            :disabled="!cfg.main_enable"
            color="primary"
            hide-details
            inset
            density="comfortable"
          />
        </div>
      </div>
    </div>

    <div class="subagent-section-head">
      <div>
        <div class="subagent-section-title">{{ tm("section.title") }}</div>
        <div class="subagent-section-subtitle">
          {{ tm("section.subtitle") }}
        </div>
      </div>
      <div class="subagent-section-actions">
        <div class="subagent-pill">
          <v-icon size="16">mdi-robot-outline</v-icon>
          <span>{{ cfg.agents.length }}</span>
        </div>
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="addAgent"
        >
          {{ tm("actions.add") }}
        </v-btn>
      </div>
    </div>

    <div
      v-if="cfg.agents.length === 0"
      class="subagent-content subagent-empty-card"
    >
      <div class="empty-wrap">
        <v-icon icon="mdi-robot-off" size="60" class="mb-4" />
        <div class="empty-title">{{ tm("empty.title") }}</div>
        <div class="empty-subtitle mb-4">{{ tm("empty.subtitle") }}</div>
        <v-btn color="primary" variant="tonal" @click="addAgent">
          {{ tm("empty.action") }}
        </v-btn>
      </div>
    </div>

    <div v-else class="subagent-list">
      <section
        v-for="(agent, idx) in cfg.agents"
        :key="agent.__key"
        class="subagent-content agent-panel"
      >
        <div class="agent-summary">
          <div class="agent-summary-main">
            <div class="agent-summary-top">
              <v-badge dot :color="agent.enabled ? 'success' : 'grey'" inline />
              <span class="agent-name">{{
                agent.name || tm("cards.unnamed")
              }}</span>
              <v-chip
                size="x-small"
                variant="tonal"
                :color="agent.enabled ? 'success' : 'default'"
              >
                {{
                  agent.enabled
                    ? tm("cards.statusEnabled")
                    : tm("cards.statusDisabled")
                }}
              </v-chip>
            </div>
            <div class="agent-summary-desc">
              {{ agent.public_description || tm("cards.noDescription") }}
            </div>
          </div>
          <div class="agent-summary-actions">
            <v-btn
              :append-icon="
                isAgentExpanded(agent.__key)
                  ? 'mdi-chevron-up'
                  : 'mdi-chevron-down'
              "
              variant="text"
              color="default"
              density="comfortable"
              @click="toggleAgentExpanded(agent.__key)"
            >
              {{
                isAgentExpanded(agent.__key)
                  ? tm("actions.collapse")
                  : tm("actions.expand")
              }}
            </v-btn>
            <v-switch
              v-model="agent.enabled"
              color="success"
              hide-details
              inset
              density="compact"
            />
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              color="error"
              density="comfortable"
              @click="removeAgent(idx)"
            />
          </div>
        </div>

        <v-expand-transition>
          <div v-show="isAgentExpanded(agent.__key)" class="agent-edit-grid">
            <section class="inner-card">
              <div class="subagent-section-title section-mini-title">
                {{ tm("section.agentSetup") }}
              </div>
              <div class="subagent-form-grid subagent-form-grid--single">
                <v-text-field
                  v-model="agent.name"
                  :label="tm('form.nameLabel')"
                  :rules="[
                    (v) => !!v || tm('messages.nameRequired'),
                    (v) =>
                      /^[a-z][a-z0-9_]*$/.test(v) || tm('messages.namePattern'),
                  ]"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />

                <div class="selector-wrap">
                  <div class="selector-label">
                    {{ tm("form.providerLabel") }}
                  </div>
                  <div class="selector-card">
                    <ProviderSelector
                      v-model="agent.provider_id"
                      provider-type="chat_completion"
                      variant="outlined"
                      density="comfortable"
                      clearable
                    />
                  </div>
                </div>

                <div class="selector-wrap">
                  <div class="selector-label">
                    {{ tm("form.personaLabel") }}
                  </div>
                  <div class="selector-card">
                    <PersonaSelector v-model="agent.persona_id" />
                  </div>
                </div>

                <v-textarea
                  v-model="agent.public_description"
                  :label="tm('form.descriptionLabel')"
                  variant="outlined"
                  density="comfortable"
                  auto-grow
                  hide-details="auto"
                />
              </div>
            </section>

            <section class="inner-card">
              <div class="subagent-section-title section-mini-title">
                {{ tm("cards.personaPreview") }}
              </div>
              <div class="subagent-section-subtitle">
                {{ tm("cards.previewHint") }}
              </div>
              <div class="persona-preview-wrap">
                <PersonaQuickPreview
                  :model-value="agent.persona_id"
                  class="h-100"
                />
              </div>
            </section>
          </div>
        </v-expand-transition>
      </section>
    </div>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">{{
          tm("actions.close")
        }}</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import axios from "@/utils/request";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { useTheme } from "vuetify";
import PersonaQuickPreview from "@/components/shared/PersonaQuickPreview.vue";
import PersonaSelector from "@/components/shared/PersonaSelector.vue";
import ProviderSelector from "@/components/shared/ProviderSelector.vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

type SubAgentItem = {
  __key: string;
  name: string;
  persona_id: string;
  public_description: string;
  enabled: boolean;
  provider_id?: string;
};

type SubAgentConfig = {
  main_enable: boolean;
  remove_main_duplicate_tools: boolean;
  agents: SubAgentItem[];
};

const { tm } = useModuleI18n("features/subagent");
const theme = useTheme();
const confirmDialog = useConfirmDialog();

const loading = ref(false);
const saving = ref(false);
const isDark = computed(() => theme.global.current.value.dark);

const snackbar = ref({ show: false, message: "", color: "success" });
const expandedAgents = ref<Record<string, boolean>>({});
const initialSnapshot = ref("");
const hasLoaded = ref(false);

function toast(
  message: string,
  color: "success" | "error" | "warning" = "success",
) {
  snackbar.value = { show: true, message, color };
}

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  remove_main_duplicate_tools: false,
  agents: [],
});

const mainStateDescription = computed(() =>
  cfg.value.main_enable
    ? tm("description.enabled")
    : tm("description.disabled"),
);
const hasUnsavedChanges = computed(
  () => hasLoaded.value && serializeConfig(cfg.value) !== initialSnapshot.value,
);

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable;
  const remove_main_duplicate_tools = !!raw?.remove_main_duplicate_tools;
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : [];
  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => ({
    __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
    name: (a?.name ?? "").toString(),
    persona_id: (a?.persona_id ?? "").toString(),
    public_description: (a?.public_description ?? "").toString(),
    enabled: a?.enabled !== false,
    provider_id: (a?.provider_id ?? undefined) as string | undefined,
  }));
  return { main_enable, remove_main_duplicate_tools, agents };
}

function serializeConfig(config: SubAgentConfig): string {
  return JSON.stringify({
    main_enable: config.main_enable,
    remove_main_duplicate_tools: config.remove_main_duplicate_tools,
    agents: config.agents.map((agent) => ({
      name: agent.name,
      persona_id: agent.persona_id,
      public_description: agent.public_description,
      enabled: agent.enabled,
      provider_id: agent.provider_id ?? null,
    })),
  });
}

async function loadConfig() {
  loading.value = true;
  try {
    const res = await axios.get("/api/subagent/config");
    if (res.data.status === "ok") {
      cfg.value = normalizeConfig(res.data.data);
      expandedAgents.value = Object.fromEntries(
        cfg.value.agents.map((agent) => [agent.__key, false]),
      );
      initialSnapshot.value = serializeConfig(cfg.value);
      hasLoaded.value = true;
    } else {
      toast(res.data.message || tm("messages.loadConfigFailed"), "error");
    }
  } catch (e: any) {
    toast(
      e?.response?.data?.message || tm("messages.loadConfigFailed"),
      "error",
    );
  } finally {
    loading.value = false;
  }
}

function addAgent() {
  const key = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  cfg.value.agents.push({
    __key: key,
    name: "",
    persona_id: "",
    public_description: "",
    enabled: true,
    provider_id: undefined,
  });
  expandedAgents.value[key] = false;
}

function removeAgent(idx: number) {
  const [removed] = cfg.value.agents.splice(idx, 1);
  if (removed) {
    delete expandedAgents.value[removed.__key];
  }
}

function isAgentExpanded(key: string): boolean {
  return expandedAgents.value[key] !== false;
}
function toggleAgentExpanded(key: string) {
  expandedAgents.value[key] = !isAgentExpanded(key);
}

function validateBeforeSave(): boolean {
  const nameRe = /^[a-z][a-z0-9_]{0,63}$/;
  const seen = new Set<string>();
  for (const agent of cfg.value.agents) {
    const name = (agent.name || "").trim();
    if (!name) {
      toast(tm("messages.nameMissing"), "warning");
      return false;
    }
    if (!nameRe.test(name)) {
      toast(tm("messages.nameInvalid"), "warning");
      return false;
    }
    if (seen.has(name)) {
      toast(tm("messages.nameDuplicate", { name }), "warning");
      return false;
    }
    seen.add(name);
    if (!agent.persona_id) {
      toast(tm("messages.personaMissing", { name }), "warning");
      return false;
    }
  }
  return true;
}

async function save() {
  if (!validateBeforeSave()) return;
  saving.value = true;
  try {
    const payload = {
      main_enable: cfg.value.main_enable,
      remove_main_duplicate_tools: cfg.value.remove_main_duplicate_tools,
      agents: cfg.value.agents.map((agent) => ({
        name: agent.name,
        persona_id: agent.persona_id,
        public_description: agent.public_description,
        enabled: agent.enabled,
        provider_id: agent.provider_id,
      })),
    };
    const res = await axios.post("/api/subagent/config", payload);
    if (res.data.status === "ok") {
      initialSnapshot.value = serializeConfig(cfg.value);
      hasLoaded.value = true;
      toast(res.data.message || tm("messages.saveSuccess"), "success");
    } else {
      toast(res.data.message || tm("messages.saveFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.saveFailed"), "error");
  } finally {
    saving.value = false;
  }
}

async function reload() {
  if (hasUnsavedChanges.value) {
    const confirmed = await askForConfirmation(
      tm("messages.unsavedChangesReloadConfirm"),
      confirmDialog,
    );
    if (!confirmed) return;
  }
  await loadConfig();
}

async function confirmLeaveIfNeeded(): Promise<boolean> {
  if (!hasUnsavedChanges.value) return true;
  return askForConfirmation(
    tm("messages.unsavedChangesLeaveConfirm"),
    confirmDialog,
  );
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges.value) return;
  event.preventDefault();
  event.returnValue = "";
}

onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload);
  reload();
});
onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
});
onBeforeRouteLeave(async () => {
  return await confirmLeaveIfNeeded();
});
</script>

<style scoped>
.subagent-page {
  --subagent-page-bg: transparent;
  --subagent-panel-bg: rgba(var(--v-theme-surface), 0.78);
  --subagent-card-bg: rgba(var(--v-theme-surface), 0.9);
  --subagent-record-bg: rgba(var(--v-theme-surface-variant), 0.38);
  --subagent-empty-surface: rgba(var(--v-theme-surface), 0.68);
  --subagent-primary: rgb(var(--v-theme-primary));
  --subagent-primary-soft: rgba(var(--v-theme-primary), 0.08);
  --subagent-primary-soft-strong: rgba(var(--v-theme-primary), 0.14);
  --subagent-border: rgba(var(--v-theme-borderLight), 0.22);
  --subagent-border-strong: rgba(var(--v-theme-borderLight), 0.4);
  --subagent-border-active: rgba(var(--v-theme-primary), 0.24);
  --subagent-track: rgba(var(--v-theme-borderLight), 0.78);
  --subagent-track-active: rgba(var(--v-theme-primary), 0.22);
  --subagent-title: rgb(var(--v-theme-on-surface));
  --subagent-text: rgba(var(--v-theme-on-surface), 0.92);
  --subagent-muted: rgba(var(--v-theme-on-surface), 0.7);
  --subagent-subtle: rgba(var(--v-theme-on-surface), 0.54);
  --subagent-empty-icon-bg: rgba(var(--v-theme-primary), 0.1);
  --subagent-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  position: relative;
  z-index: 1;
  isolation: isolate;
  gap: 16px;
  padding: 16px;
}

:global(.v-theme--bluebusinessdarktheme) .subagent-page {
  --subagent-panel-bg: rgba(var(--v-theme-surface), 0.72);
  --subagent-card-bg: rgba(var(--v-theme-surface-variant), 0.74);
  --subagent-record-bg: rgba(var(--v-theme-surface), 0.52);
  --subagent-empty-surface: rgba(var(--v-theme-surface-variant), 0.56);
  --subagent-border: rgba(var(--v-theme-borderLight), 0.46);
  --subagent-border-strong: rgba(var(--v-theme-borderLight), 0.66);
  --subagent-track: rgba(var(--v-theme-borderLight), 0.9);
  --subagent-shadow: none;
}

.subagent-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--subagent-panel-bg);
  border: 1px solid var(--subagent-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--subagent-shadow);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topbar-eyebrow {
  margin-bottom: 4px;
  color: var(--subagent-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.topbar-title {
  font-size: clamp(24px, 3vw, 32px);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--subagent-primary) !important;
  -webkit-text-fill-color: var(--subagent-primary);
}

.topbar-desc {
  font-size: 14px;
  color: var(--subagent-muted) !important;
  -webkit-text-fill-color: var(--subagent-muted);
  line-height: 1.5;
  max-width: 60ch;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.unsaved-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 1px solid rgba(var(--v-theme-warning), 0.22);
  border-radius: 12px;
  background: rgba(var(--v-theme-warning), 0.08);
  color: var(--subagent-text);
  font-size: 13px;
}

.subagent-section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}

.subagent-section-title {
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--subagent-text);
}

.subagent-section-subtitle {
  margin-top: 6px;
  color: var(--subagent-muted);
  font-size: 13px;
}

.subagent-section-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.subagent-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--subagent-border);
  border-radius: 999px;
  background: var(--subagent-panel-bg);
  color: var(--subagent-muted);
  font-size: 13px;
}

.subagent-settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.subagent-setting-card {
  padding: 18px;
  background: var(--subagent-panel-bg);
  border: 1px solid var(--subagent-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
}

.setting-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.setting-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--subagent-text);
}

.setting-subtitle {
  margin-top: 6px;
  color: var(--subagent-muted);
  font-size: 13px;
}

.subagent-content {
  background: var(--subagent-panel-bg);
  border: 1px solid var(--subagent-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
}

.subagent-empty-card {
  min-height: 280px;
  padding: 22px;
}

.empty-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--subagent-muted);
}

.empty-title {
  font-size: 20px;
  font-weight: 650;
  color: var(--subagent-text);
  margin-bottom: 8px;
}

.empty-subtitle {
  color: var(--subagent-muted);
  font-size: 14px;
}

.subagent-list {
  display: grid;
  gap: 16px;
}

.agent-panel {
  padding: 22px;
  display: grid;
  gap: 18px;
}

.agent-summary {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  width: 100%;
}

.agent-summary-main {
  min-width: 0;
  flex: 1;
}

.agent-summary-top {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.agent-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 18px;
  font-weight: 650;
  color: var(--subagent-text);
}

.agent-summary-desc {
  margin-top: 8px;
  color: var(--subagent-muted);
  font-size: 13px;
}

.agent-summary-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.agent-edit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.inner-card {
  padding: 18px;
  background: var(--subagent-card-bg);
  border: 1px solid var(--subagent-border);
  border-radius: 12px;
  min-width: 0;
}

.section-mini-title {
  margin-bottom: 10px;
}

.subagent-form-grid {
  display: grid;
  gap: 16px;
}
.subagent-form-grid--single {
  grid-template-columns: 1fr;
}

.selector-wrap {
  display: grid;
  gap: 8px;
}

.selector-label {
  color: var(--subagent-muted);
  font-size: 13px;
  font-weight: 500;
}

.selector-card {
  border: 1px solid var(--subagent-border);
  border-radius: 12px;
  padding: 14px;
  background: transparent;
}

.persona-preview-wrap {
  min-height: 320px;
}

@media (max-width: 1280px) {
  .subagent-settings-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1080px) {
  .agent-edit-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .subagent-topbar {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px;
  }
  .topbar-right {
    width: 100%;
  }
  .subagent-page {
    gap: 12px;
    padding: 12px;
  }
  .setting-card-head,
  .agent-summary {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

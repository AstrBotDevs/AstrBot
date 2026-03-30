<template>
  <div class="subagent-page">
    <section class="subagent-hero gel-panel">
      <div class="hero-copy">
        <div class="hero-heading-row">
          <div class="hero-title-wrap">
            <h2 class="hero-title">
              {{ tm("page.title") }}
            </h2>
            <v-chip
              size="x-small"
              color="orange-darken-2"
              variant="tonal"
              label
              class="font-weight-bold"
            >
              {{ tm("page.beta") }}
            </v-chip>
          </div>
          <div class="hero-subtitle">
            {{ tm("page.subtitle") }}
          </div>
        </div>

        <div class="hero-pill-row">
          <div class="hero-pill">
            <span class="hero-pill-label">{{ tm("section.title") }}</span>
            <strong class="hero-pill-value">{{ cfg.agents.length }}</strong>
          </div>
          <div class="hero-pill">
            <span class="hero-pill-label">{{ tm("description.enabled") }}</span>
            <strong class="hero-pill-value">{{ enabledAgentCount }}</strong>
          </div>
          <div class="hero-pill">
            <span class="hero-pill-label">{{ tm("form.providerLabel") }}</span>
            <strong class="hero-pill-value">{{ linkedProviderCount }}</strong>
          </div>
          <div class="hero-pill">
            <span class="hero-pill-label">{{ tm("form.personaLabel") }}</span>
            <strong class="hero-pill-value">{{
              configuredPersonaCount
            }}</strong>
          </div>
        </div>
      </div>

      <div class="hero-actions">
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
          variant="flat"
          color="primary"
          prepend-icon="mdi-content-save"
          :loading="saving"
          @click="save"
        >
          {{ tm("actions.save") }}
        </v-btn>
      </div>
      <div class="hero-orb hero-orb-a"></div>
      <div class="hero-orb hero-orb-b"></div>
    </section>

    <v-card class="gel-panel settings-panel" variant="flat">
      <v-card-text class="settings-panel-body">
        <div class="panel-heading">
          <div>
            <div class="panel-title">
              {{ tm("section.globalSettings") || "Global Settings" }}
            </div>
            <div class="panel-subtitle">
              {{ mainStateDescription }}
            </div>
          </div>
        </div>

        <div class="setting-grid">
          <div class="setting-tile" :class="{ 'is-active': cfg.main_enable }">
            <div class="setting-copy">
              <div class="setting-title">
                {{ tm("switches.enable") }}
              </div>
              <div class="setting-hint">
                {{ tm("switches.enableHint") }}
              </div>
            </div>
            <v-switch
              v-model="cfg.main_enable"
              color="primary"
              hide-details
              inset
              density="comfortable"
            />
          </div>

          <div
            class="setting-tile"
            :class="{
              'is-active': cfg.main_enable && cfg.remove_main_duplicate_tools,
              'is-muted': !cfg.main_enable,
            }"
          >
            <div class="setting-copy">
              <div class="setting-title">
                {{ tm("switches.dedupe") }}
              </div>
              <div class="setting-hint">
                {{ tm("switches.dedupeHint") }}
              </div>
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
      </v-card-text>
    </v-card>

    <section class="agents-shell gel-panel">
      <div class="agents-shell-head">
        <div class="agents-shell-copy">
          <div class="agents-shell-title">
            <v-icon icon="mdi-robot" color="primary" size="small" />
            <span>{{ tm("section.title") }}</span>
            <v-chip size="small" variant="tonal" color="primary">
              {{ cfg.agents.length }}
            </v-chip>
          </div>
          <div class="agents-shell-subtitle">
            {{ tm("cards.noDescription") }}
          </div>
        </div>
        <v-btn prepend-icon="mdi-plus" color="primary" @click="addAgent">
          {{ tm("actions.add") }}
        </v-btn>
      </div>

      <v-expansion-panels
        v-if="cfg.agents.length > 0"
        variant="popout"
        class="subagent-panels"
      >
      <v-expansion-panel
        v-for="(agent, idx) in cfg.agents"
        :key="agent.__key"
        elevation="0"
        class="agent-panel"
        :class="{ 'agent-panel--enabled': agent.enabled }"
      >
        <v-expansion-panel-title class="agent-panel-title">
          <div class="agent-title-layout">
            <div class="agent-leading">
              <div class="agent-index-badge">
                {{ String(idx + 1).padStart(2, "0") }}
              </div>
              <v-badge
                dot
                :color="agent.enabled ? 'success' : 'grey'"
                inline
              />
            </div>

            <div class="agent-summary">
              <div class="agent-name-row">
                <span class="agent-name">
                  {{ agent.name || tm("cards.unnamed") }}
                </span>
                <v-chip
                  size="x-small"
                  :color="agent.enabled ? 'success' : 'grey'"
                  variant="tonal"
                  label
                >
                  {{ agent.enabled ? tm("description.enabled") : tm("description.disabled") }}
                </v-chip>
              </div>
              <div class="agent-description">
                {{ agent.public_description || tm("cards.noDescription") }}
              </div>
              <div
                v-if="agent.provider_id || agent.persona_id"
                class="agent-meta-row"
              >
                <v-chip
                  v-if="agent.provider_id"
                  size="x-small"
                  variant="outlined"
                  color="primary"
                  label
                >
                  <v-icon start size="14">mdi-connection</v-icon>
                  {{ agent.provider_id }}
                </v-chip>
                <v-chip
                  v-if="agent.persona_id"
                  size="x-small"
                  variant="outlined"
                  color="secondary"
                  label
                >
                  <v-icon start size="14">mdi-account-box-outline</v-icon>
                  {{ agent.persona_id }}
                </v-chip>
              </div>
            </div>

            <div class="agent-controls" @click.stop>
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
        </v-expansion-panel-title>

        <v-expansion-panel-text>
          <v-divider class="agent-divider mb-4" />
          <v-row class="agent-editor-grid">
            <v-col cols="12" md="6">
              <div class="agent-field-stack">
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
                  prepend-inner-icon="mdi-account"
                />

                <div class="agent-field-group">
                  <div class="field-group-label">
                    {{ tm("form.providerLabel") }}
                  </div>
                  <v-card variant="flat" class="field-card">
                    <div class="field-card-body">
                      <ProviderSelector
                        v-model="agent.provider_id"
                        provider-type="chat_completion"
                        variant="outlined"
                        density="comfortable"
                        clearable
                      />
                    </div>
                  </v-card>
                </div>

                <div class="agent-field-group">
                  <div class="field-group-label">
                    {{ tm("form.personaLabel") }}
                  </div>
                  <v-card variant="flat" class="field-card">
                    <div class="field-card-body">
                      <PersonaSelector v-model="agent.persona_id" />
                    </div>
                  </v-card>
                </div>

                <v-textarea
                  v-model="agent.public_description"
                  :label="tm('form.descriptionLabel')"
                  variant="outlined"
                  density="comfortable"
                  auto-grow
                  hide-details="auto"
                  prepend-inner-icon="mdi-text"
                />
              </div>
            </v-col>

            <v-col cols="12" md="6">
              <div class="preview-card">
                <div class="preview-card-label">
                  {{ tm("cards.personaPreview") }}
                </div>
                <PersonaQuickPreview
                  :model-value="agent.persona_id"
                  class="preview-card-body"
                />
              </div>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
      </v-expansion-panels>

      <div v-else class="empty-state">
        <div class="empty-state-icon-wrap">
          <v-icon icon="mdi-robot-off" size="64" class="opacity-70" />
        </div>
        <div class="text-h6">
          {{ tm("empty.title") }}
        </div>
        <div class="text-body-2 mb-4">
          {{ tm("empty.subtitle") }}
        </div>
        <v-btn color="primary" variant="tonal" @click="addAgent">
          {{ tm("empty.action") }}
        </v-btn>
      </div>
    </section>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">
          {{ tm("actions.close") }}
        </v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import axios from "@/utils/request";
import ProviderSelector from "@/components/shared/ProviderSelector.vue";
import PersonaSelector from "@/components/shared/PersonaSelector.vue";
import PersonaQuickPreview from "@/components/shared/PersonaQuickPreview.vue";
import { useModuleI18n } from "@/i18n/composables";

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

const loading = ref(false);
const saving = ref(false);

const snackbar = ref({
  show: false,
  message: "",
  color: "success",
});

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

const enabledAgentCount = computed(
  () => cfg.value.agents.filter((agent) => agent.enabled).length,
);

const linkedProviderCount = computed(
  () => cfg.value.agents.filter((agent) => !!agent.provider_id).length,
);

const configuredPersonaCount = computed(
  () => cfg.value.agents.filter((agent) => !!agent.persona_id).length,
);

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable;
  const remove_main_duplicate_tools = !!raw?.remove_main_duplicate_tools;
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : [];

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => {
    const name = (a?.name ?? "").toString();
    const persona_id = (a?.persona_id ?? "").toString();
    const public_description = (a?.public_description ?? "").toString();
    const enabled = a?.enabled !== false;
    const provider_id = (a?.provider_id ?? undefined) as string | undefined;

    return {
      __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
      name,
      persona_id,
      public_description,
      enabled,
      provider_id,
    };
  });

  return { main_enable, remove_main_duplicate_tools, agents };
}

async function loadConfig() {
  loading.value = true;
  try {
    const res = await axios.get("/api/subagent/config");
    if (res.data.status === "ok") {
      cfg.value = normalizeConfig(res.data.data);
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
  cfg.value.agents.push({
    __key: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name: "",
    persona_id: "",
    public_description: "",
    enabled: true,
    provider_id: undefined,
  });
}

function removeAgent(idx: number) {
  cfg.value.agents.splice(idx, 1);
}

function validateBeforeSave(): boolean {
  const nameRe = /^[a-z][a-z0-9_]{0,63}$/;
  const seen = new Set<string>();
  for (const a of cfg.value.agents) {
    const name = (a.name || "").trim();
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
    if (!a.persona_id) {
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
      agents: cfg.value.agents.map((a) => ({
        name: a.name,
        persona_id: a.persona_id,
        public_description: a.public_description,
        enabled: a.enabled,
        provider_id: a.provider_id,
      })),
    };

    const res = await axios.post("/api/subagent/config", payload);
    if (res.data.status === "ok") {
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
  await Promise.all([loadConfig()]);
}

onMounted(() => {
  reload();
});
</script>

<style scoped>
.subagent-page {
  --subagent-surface: rgba(var(--v-theme-surface), 0.94);
  --subagent-surface-soft: rgba(var(--v-theme-surface), 0.8);
  --subagent-border: rgba(var(--v-theme-on-surface), 0.1);
  --subagent-border-strong: rgba(var(--v-theme-primary), 0.18);
  --subagent-text-muted: rgba(var(--v-theme-on-surface), 0.68);
  --subagent-text-soft: rgba(var(--v-theme-on-surface), 0.54);
  --subagent-accent-soft: rgba(var(--v-theme-primary), 0.08);
  padding: 24px;
  max-width: 1280px;
  margin: 0 auto 40px;
}

.gel-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--subagent-border) !important;
  border-radius: 28px !important;
  background:
    linear-gradient(
      145deg,
      rgba(var(--v-theme-surface), 0.98),
      rgba(var(--v-theme-surface), 0.9)
    ) !important;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px) saturate(1.04);
}

:global(.v-theme--dark) .subagent-page .gel-panel {
  background:
    linear-gradient(
      145deg,
      rgba(var(--v-theme-surface), 0.84),
      rgba(var(--v-theme-surface), 0.72)
    ) !important;
  box-shadow: 0 22px 48px rgba(0, 0, 0, 0.28);
}

.subagent-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 30px;
  margin-bottom: 20px;
}

.hero-copy,
.hero-actions {
  position: relative;
  z-index: 1;
}

.hero-copy {
  flex: 1;
  min-width: 0;
}

.hero-heading-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hero-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.hero-title {
  margin: 0;
  font-size: clamp(1.8rem, 2vw, 2.4rem);
  line-height: 1.05;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.hero-subtitle {
  max-width: 760px;
  color: var(--subagent-text-muted);
  font-size: 0.98rem;
  line-height: 1.6;
}

.hero-pill-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 22px;
}

.hero-pill {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.035);
}

.hero-pill-label {
  display: block;
  margin-bottom: 6px;
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--subagent-text-soft);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.hero-pill-value {
  display: block;
  font-size: 1.35rem;
  line-height: 1;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.hero-orb {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  filter: blur(8px);
  opacity: 0.55;
}

.hero-orb-a {
  width: 180px;
  height: 180px;
  right: -48px;
  top: -44px;
  background: radial-gradient(
    circle,
    rgba(var(--v-theme-primary), 0.22) 0%,
    rgba(var(--v-theme-primary), 0) 72%
  );
}

.hero-orb-b {
  width: 140px;
  height: 140px;
  right: 180px;
  bottom: -54px;
  background: radial-gradient(
    circle,
    rgba(var(--v-theme-secondary), 0.18) 0%,
    rgba(var(--v-theme-secondary), 0) 72%
  );
}

.settings-panel {
  margin-bottom: 20px;
}

.settings-panel-body {
  padding: 28px !important;
}

.panel-heading {
  margin-bottom: 18px;
}

.panel-title {
  font-size: 1.08rem;
  font-weight: 700;
}

.panel-subtitle {
  margin-top: 6px;
  color: var(--subagent-text-muted);
  font-size: 0.9rem;
}

.setting-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.setting-tile {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 22px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.025);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.setting-tile.is-active {
  border-color: var(--subagent-border-strong);
  background: rgba(var(--v-theme-primary), 0.08);
}

.setting-tile.is-muted {
  opacity: 0.72;
}

.setting-copy {
  min-width: 0;
}

.setting-title {
  font-weight: 700;
  line-height: 1.3;
}

.setting-hint {
  margin-top: 6px;
  color: var(--subagent-text-muted);
  font-size: 0.86rem;
  line-height: 1.5;
}

.agents-shell {
  padding: 28px;
}

.agents-shell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.agents-shell-copy {
  min-width: 0;
}

.agents-shell-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.08rem;
  font-weight: 700;
}

.agents-shell-subtitle {
  margin-top: 8px;
  color: var(--subagent-text-muted);
  font-size: 0.9rem;
}

.subagent-panels {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agent-panel {
  border: 1px solid var(--subagent-border) !important;
  border-radius: 24px !important;
  background: rgba(var(--v-theme-on-surface), 0.022) !important;
  overflow: hidden;
}

.agent-panel--enabled {
  border-color: rgba(var(--v-theme-primary), 0.22) !important;
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.04);
}

.agent-panel-title {
  padding: 18px 20px !important;
}

.agent-title-layout {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.agent-leading {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.agent-index-badge {
  min-width: 44px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
  font-weight: 700;
  font-size: 0.82rem;
  text-align: center;
  letter-spacing: 0.08em;
}

.agent-summary {
  min-width: 0;
  flex: 1;
}

.agent-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.agent-name {
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.3;
}

.agent-description {
  margin-top: 4px;
  color: var(--subagent-text-muted);
  font-size: 0.88rem;
  line-height: 1.5;
}

.agent-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.agent-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.agent-divider {
  border-color: rgba(var(--v-theme-on-surface), 0.08) !important;
}

.subagent-panels ::v-deep(.v-expansion-panel-text__wrapper) {
  padding: 0 20px 24px;
}

.agent-editor-grid {
  margin: 0;
}

.agent-field-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.agent-field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-group-label {
  padding-left: 4px;
  color: var(--subagent-text-muted);
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.field-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08) !important;
  border-radius: 20px !important;
  background: rgba(var(--v-theme-on-surface), 0.025) !important;
}

.field-card-body {
  padding: 16px;
}

.preview-card {
  height: 100%;
  min-height: 100%;
  padding: 14px;
  border-radius: 22px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background:
    linear-gradient(
      180deg,
      rgba(var(--v-theme-primary), 0.05),
      rgba(var(--v-theme-on-surface), 0.02)
    );
}

.preview-card-label {
  margin-bottom: 12px;
  padding-left: 4px;
  color: var(--subagent-text-muted);
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.preview-card-body {
  height: calc(100% - 28px);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 52px 16px 28px;
  color: var(--subagent-text-muted);
  text-align: center;
}

.empty-state-icon-wrap {
  display: grid;
  place-items: center;
  width: 88px;
  height: 88px;
  margin-bottom: 18px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.08);
}

.gap-2 {
  gap: 8px;
}

.gap-4 {
  gap: 16px;
}

@media (max-width: 960px) {
  .subagent-hero,
  .agents-shell-head,
  .agent-title-layout {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-actions,
  .agent-controls {
    justify-content: flex-end;
  }

  .hero-pill-row,
  .setting-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .subagent-page {
    padding: 16px;
  }

  .subagent-hero,
  .settings-panel-body,
  .agents-shell {
    padding: 20px;
  }

  .hero-pill-row,
  .setting-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .hero-actions > * {
    flex: 1 1 0;
    min-width: 0;
  }

  .agent-panel-title {
    padding: 16px !important;
  }

  .subagent-panels ::v-deep(.v-expansion-panel-text__wrapper) {
    padding: 0 16px 20px;
  }
}
</style>

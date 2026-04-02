<template>
  <div class="cron-page">
    <div class="cron-topbar">
      <div class="topbar-left">
        <div class="topbar-title">{{ tm("page.title") }}</div>
        <div class="topbar-desc">{{ tm("page.subtitle") }}</div>
      </div>
      <div class="topbar-right">
        <v-btn
          variant="text"
          color="primary"
          :loading="loading"
          prepend-icon="mdi-refresh"
          @click="loadJobs"
        >
          {{ tm("actions.refresh") }}
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-plus"
          @click="openCreate"
        >
          {{ tm("actions.create") }}
        </v-btn>
      </div>
    </div>

    <div class="cron-overview-grid">
      <div
        v-for="card in overviewCards"
        :key="card.label"
        class="cron-overview-card"
      >
        <div class="cron-card-icon">
          <v-icon size="18">{{ card.icon }}</v-icon>
        </div>
        <div class="cron-card-label">{{ card.label }}</div>
        <div class="cron-card-value">{{ card.value }}</div>
        <div class="cron-card-note">{{ card.note }}</div>
      </div>
    </div>

    <div class="cron-section-head">
      <div>
        <div class="cron-section-title">
          {{ tm("section.platforms.title") }}
        </div>
        <div class="cron-section-subtitle">
          {{
            proactivePlatforms.length
              ? tm("page.proactive.supported", {
                  platforms: proactivePlatformText,
                })
              : tm("page.proactive.unsupported")
          }}
        </div>
      </div>
    </div>

    <section v-if="proactivePlatforms.length" class="platform-section">
      <div class="platform-chip-wrap">
        <v-chip
          v-for="platform in proactivePlatforms"
          :key="platform.id"
          size="small"
          variant="tonal"
          color="primary"
        >
          {{ platform.display_name || platform.name }} · {{ platform.id }}
        </v-chip>
      </div>
    </section>
    <div v-else class="cron-empty">{{ tm("page.proactive.unsupported") }}</div>

    <div class="cron-section-head">
      <div>
        <div class="cron-section-title">{{ tm("table.title") }}</div>
        <div class="cron-section-subtitle">{{ tm("table.subtitle") }}</div>
      </div>
    </div>

    <div class="cron-content">
      <div v-if="loading && !jobs.length" class="state-panel">
        <v-progress-circular
          indeterminate
          size="22"
          width="2"
          color="primary"
        />
        <span>{{ tm("actions.refresh") }}...</span>
      </div>

      <div v-else-if="!jobs.length" class="state-panel">
        <v-icon size="20" color="primary">mdi-calendar-blank-outline</v-icon>
        <span>{{ tm("table.empty") }}</span>
      </div>

      <div v-else class="task-table-wrap">
        <table class="task-table">
          <colgroup>
            <col class="col-name" />
            <col class="col-type" />
            <col class="col-cron" />
            <col class="col-session" />
            <col class="col-next-run" />
            <col class="col-last-run" />
            <col class="col-actions" />
          </colgroup>
          <thead>
            <tr>
              <th>{{ tm("table.headers.name") }}</th>
              <th>{{ tm("table.headers.type") }}</th>
              <th>{{ tm("table.headers.cron") }}</th>
              <th>{{ tm("table.headers.session") }}</th>
              <th>{{ tm("table.headers.nextRun") }}</th>
              <th>{{ tm("table.headers.lastRun") }}</th>
              <th class="actions-col">{{ tm("table.headers.actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedJobs" :key="item.job_id">
              <td class="name-col">
                <div class="task-name">
                  {{ item.name || tm("table.notAvailable") }}
                </div>
                <div class="task-subline">
                  {{ item.description || item.job_id }}
                </div>
              </td>
              <td>
                <v-chip
                  size="small"
                  :color="item.run_once ? 'orange' : 'primary'"
                  variant="tonal"
                >
                  {{ jobTypeLabel(item) }}
                </v-chip>
              </td>
              <td>
                <div class="task-text">{{ scheduleLabel(item) }}</div>
                <div class="task-subline">{{ scheduleMeta(item) }}</div>
              </td>
              <td>
                <div class="task-session">
                  {{ item.session || tm("table.notAvailable") }}
                </div>
              </td>
              <td>
                <div class="task-text">
                  {{ formatTime(item.next_run_time) }}
                </div>
              </td>
              <td>
                <div class="task-text">{{ formatTime(item.last_run_at) }}</div>
              </td>
              <td class="actions-col">
                <div class="table-actions">
                  <v-switch
                    v-model="item.enabled"
                    inset
                    density="compact"
                    hide-details
                    color="primary"
                    class="mt-0"
                    @change="toggleJob(item)"
                  />
                  <v-btn
                    size="small"
                    variant="text"
                    color="error"
                    @click="deleteJob(item)"
                  >
                    {{ tm("actions.delete") }}
                  </v-btn>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
      {{ snackbar.message }}
    </v-snackbar>

    <v-dialog v-model="createDialog" max-width="640">
      <v-card class="cron-dialog-card">
        <v-card-title class="text-h6 pt-5 px-5">{{
          tm("form.title")
        }}</v-card-title>
        <v-card-subtitle class="px-5 text-body-2 text-medium-emphasis">{{
          tm("form.chatHint")
        }}</v-card-subtitle>
        <v-card-text class="px-5 pb-2">
          <div class="cron-form-grid cron-form-grid--single">
            <v-switch
              v-model="newJob.run_once"
              :label="tm('form.runOnce')"
              inset
              color="primary"
              hide-details
            />
            <v-text-field
              v-model="newJob.name"
              :label="tm('form.name')"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model="newJob.note"
              :label="tm('form.note')"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-if="!newJob.run_once"
              v-model="newJob.cron_expression"
              :label="tm('form.cron')"
              :placeholder="tm('form.cronPlaceholder')"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-else
              v-model="newJob.run_at"
              :label="tm('form.runAt')"
              type="datetime-local"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model="newJob.session"
              :label="tm('form.session')"
              variant="outlined"
              density="comfortable"
            />
            <v-text-field
              v-model="newJob.timezone"
              :label="tm('form.timezone')"
              variant="outlined"
              density="comfortable"
            />
            <v-switch
              v-model="newJob.enabled"
              :label="tm('form.enabled')"
              inset
              color="primary"
              hide-details
            />
          </div>
        </v-card-text>
        <v-card-actions class="justify-end px-5 pb-5">
          <v-btn variant="text" @click="createDialog = false">{{
            tm("actions.cancel")
          }}</v-btn>
          <v-btn
            variant="tonal"
            color="primary"
            :loading="creating"
            @click="createJob"
            >{{ tm("actions.submit") }}</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import axios from "@/utils/request";
import { computed, onMounted, ref } from "vue";
import { useTheme } from "vuetify";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/cron");
const theme = useTheme();

const isDark = computed(() => theme.global.current.value.dark);
const loading = ref(false);
const jobs = ref<any[]>([]);
const proactivePlatforms = ref<
  { id: string; name: string; display_name?: string }[]
>([]);
const createDialog = ref(false);
const creating = ref(false);
const newJob = ref({
  run_once: false,
  name: "",
  note: "",
  cron_expression: "",
  run_at: "",
  session: "",
  timezone: "",
  enabled: true,
});

const snackbar = ref({ show: false, message: "", color: "success" });

const proactivePlatformText = computed(() =>
  proactivePlatforms.value
    .map((p) => `${p.display_name || p.name}(${p.id})`)
    .join(" / "),
);

const enabledJobsCount = computed(
  () => jobs.value.filter((job) => job.enabled).length,
);
const runOnceCount = computed(
  () => jobs.value.filter((job) => job.run_once).length,
);
const recurringCount = computed(
  () => jobs.value.filter((job) => !job.run_once).length,
);

const sortedJobs = computed(() =>
  [...jobs.value].sort((a, b) => {
    if (a.enabled !== b.enabled) {
      return a.enabled ? -1 : 1;
    }
    const nextA = parseTimeValue(a.next_run_time ?? a.run_at);
    const nextB = parseTimeValue(b.next_run_time ?? b.run_at);
    if (nextA !== nextB) {
      if (!nextA) return 1;
      if (!nextB) return -1;
      return nextA - nextB;
    }
    return String(a.name || "").localeCompare(String(b.name || ""));
  }),
);

const overviewCards = computed(() => [
  {
    label: tm("overview.totalTasks"),
    value: String(jobs.value.length),
    note: tm("overview.totalTasksNote"),
    icon: "mdi-calendar-multiple",
  },
  {
    label: tm("overview.enabledTasks"),
    value: String(enabledJobsCount.value),
    note: tm("overview.enabledTasksNote"),
    icon: "mdi-check-circle-outline",
  },
]);

function toast(
  message: string,
  color: "success" | "error" | "warning" = "success",
) {
  snackbar.value = { show: true, message, color };
}

function parseTimeValue(value: any): number {
  if (!value) return 0;
  const ts = new Date(value).getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function formatTime(val: any): string {
  if (!val) return tm("table.notAvailable");
  try {
    return new Date(val).toLocaleString();
  } catch {
    return String(val);
  }
}

function jobTypeLabel(item: any): string {
  if (item.run_once) return tm("table.type.once");
  const type = item.job_type || "active_agent";
  const map: Record<string, string> = {
    active_agent: tm("table.type.activeAgent"),
    workflow: tm("table.type.workflow"),
  };
  return map[type] || tm("table.type.unknown", { type });
}

function scheduleLabel(item: any): string {
  if (item.run_once) return formatTime(item.run_at);
  return item.cron_expression || tm("table.notAvailable");
}

function scheduleMeta(item: any): string {
  if (item.run_once) return tm("table.type.once");
  return item.timezone || tm("table.timezoneLocal");
}

async function loadJobs() {
  loading.value = true;
  try {
    const res = await axios.get("/api/cron/jobs");
    if (res.data.status === "ok") {
      const data = Array.isArray(res.data.data) ? res.data.data : [];
      jobs.value = data.map((job: any) => ({
        ...job,
        session: job?.payload?.session || job?.session || "",
      }));
    } else {
      toast(res.data.message || tm("messages.loadFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.loadFailed"), "error");
  } finally {
    loading.value = false;
  }
}

async function loadPlatforms() {
  try {
    const res = await axios.get("/api/platform/stats");
    if (res.data.status === "ok" && Array.isArray(res.data.data?.platforms)) {
      proactivePlatforms.value = res.data.data.platforms
        .filter((p: any) => p?.meta?.support_proactive_message)
        .map((p: any) => ({
          id: p?.id || p?.meta?.id || "unknown",
          name: p?.meta?.name || p?.type || "",
          display_name: p?.meta?.display_name || p?.display_name,
        }));
    }
  } catch {
    /* Ignore */
  }
}

async function toggleJob(job: any) {
  try {
    const res = await axios.patch(`/api/cron/jobs/${job.job_id}`, {
      enabled: job.enabled,
    });
    if (res.data.status !== "ok") {
      toast(res.data.message || tm("messages.updateFailed"), "error");
      await loadJobs();
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.updateFailed"), "error");
    await loadJobs();
  }
}

async function deleteJob(job: any) {
  try {
    const res = await axios.delete(`/api/cron/jobs/${job.job_id}`);
    if (res.data.status === "ok") {
      toast(tm("messages.deleteSuccess"));
      jobs.value = jobs.value.filter((item) => item.job_id !== job.job_id);
    } else {
      toast(res.data.message || tm("messages.deleteFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.deleteFailed"), "error");
  }
}

function openCreate() {
  resetNewJob();
  createDialog.value = true;
}

function resetNewJob() {
  newJob.value = {
    run_once: false,
    name: "",
    note: "",
    cron_expression: "",
    run_at: "",
    session: "",
    timezone: "",
    enabled: true,
  };
}

async function createJob() {
  if (!newJob.value.session) {
    toast(tm("messages.sessionRequired"), "warning");
    return;
  }
  if (!newJob.value.note) {
    toast(tm("messages.noteRequired"), "warning");
    return;
  }
  if (!newJob.value.run_once && !newJob.value.cron_expression) {
    toast(tm("messages.cronRequired"), "warning");
    return;
  }
  if (newJob.value.run_once && !newJob.value.run_at) {
    toast(tm("messages.runAtRequired"), "warning");
    return;
  }
  creating.value = true;
  try {
    const res = await axios.post("/api/cron/jobs", { ...newJob.value });
    if (res.data.status === "ok") {
      toast(tm("messages.createSuccess"));
      createDialog.value = false;
      resetNewJob();
      await loadJobs();
    } else {
      toast(res.data.message || tm("messages.createFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.createFailed"), "error");
  } finally {
    creating.value = false;
  }
}

onMounted(() => {
  loadJobs();
  loadPlatforms();
});
</script>

<style scoped>
.cron-page {
  --cron-page-bg: transparent;
  --cron-panel-bg: rgba(var(--v-theme-surface), 0.78);
  --cron-card-bg: rgba(var(--v-theme-surface), 0.9);
  --cron-record-bg: rgba(var(--v-theme-surface-variant), 0.38);
  --cron-empty-surface: rgba(var(--v-theme-surface), 0.68);
  --cron-primary: rgb(var(--v-theme-primary));
  --cron-primary-soft: rgba(var(--v-theme-primary), 0.08);
  --cron-primary-soft-strong: rgba(var(--v-theme-primary), 0.14);
  --cron-border: rgba(var(--v-theme-borderLight), 0.22);
  --cron-border-strong: rgba(var(--v-theme-borderLight), 0.4);
  --cron-border-active: rgba(var(--v-theme-primary), 0.24);
  --cron-track: rgba(var(--v-theme-borderLight), 0.78);
  --cron-track-active: rgba(var(--v-theme-primary), 0.22);
  --cron-title: rgb(var(--v-theme-on-surface));
  --cron-text: rgba(var(--v-theme-on-surface), 0.92);
  --cron-muted: rgba(var(--v-theme-on-surface), 0.7);
  --cron-subtle: rgba(var(--v-theme-on-surface), 0.54);
  --cron-empty-icon-bg: rgba(var(--v-theme-primary), 0.1);
  --cron-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
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

:global(.v-theme--bluebusinessdarktheme) .cron-page {
  --cron-panel-bg: rgba(var(--v-theme-surface), 0.72);
  --cron-card-bg: rgba(var(--v-theme-surface-variant), 0.74);
  --cron-record-bg: rgba(var(--v-theme-surface), 0.52);
  --cron-empty-surface: rgba(var(--v-theme-surface-variant), 0.56);
  --cron-border: rgba(var(--v-theme-borderLight), 0.46);
  --cron-border-strong: rgba(var(--v-theme-borderLight), 0.66);
  --cron-track: rgba(var(--v-theme-borderLight), 0.9);
  --cron-shadow: none;
}

.cron-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--cron-panel-bg);
  border: 1px solid var(--cron-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--cron-shadow);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topbar-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--cron-primary) !important;
  -webkit-text-fill-color: var(--cron-primary);
  letter-spacing: 0.01em;
}

.topbar-desc {
  font-size: 13px;
  color: var(--cron-muted) !important;
  -webkit-text-fill-color: var(--cron-muted);
  line-height: 1.5;
  max-width: 60ch;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cron-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  flex-shrink: 0;
}

.cron-overview-card {
  padding: 20px 20px 18px;
  background: var(--cron-panel-bg);
  border: 1px solid var(--cron-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--cron-shadow);
}

.cron-card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: var(--cron-primary-soft);
  color: var(--cron-primary);
}

.cron-card-label {
  margin-top: 12px;
  color: var(--cron-muted);
  font-size: 13px;
  font-weight: 500;
}

.cron-card-value {
  margin-top: 8px;
  font-size: clamp(24px, 2vw, 34px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
  overflow-wrap: anywhere;
  color: var(--cron-text);
}

.cron-card-note {
  margin-top: 8px;
  color: var(--cron-subtle);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.cron-section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}

.cron-section-title {
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.cron-section-subtitle {
  margin-top: 6px;
  color: var(--cron-muted);
  font-size: 13px;
  line-height: 1.6;
}

.cron-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  z-index: 1;
  background: var(--cron-panel-bg);
  border: 1px solid var(--cron-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--cron-shadow);
}

.cron-empty {
  color: var(--cron-muted);
  font-size: 14px;
  padding: 16px 20px;
  background: var(--cron-panel-bg);
  border: 1px solid var(--cron-border);
  border-radius: 12px;
}

.platform-section {
  padding: 16px 20px;
  background: var(--cron-panel-bg);
  border: 1px solid var(--cron-border);
  border-radius: 12px;
}

.platform-chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-surface {
  min-width: 0;
}

.task-table-wrap {
  overflow: auto;
  background: var(--cron-card-bg);
}

.task-table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
}

.task-table .col-name {
  width: 220px;
}
.task-table .col-type {
  width: 120px;
}
.task-table .col-cron {
  width: 260px;
}
.task-table .col-session {
  width: 340px;
}
.task-table .col-next-run,
.task-table .col-last-run {
  width: 180px;
}
.task-table .col-actions {
  width: 170px;
}

.task-table th {
  padding: 14px 16px;
  text-align: left;
  background: var(--cron-primary-soft);
  color: var(--cron-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--cron-border);
  white-space: nowrap;
}

.task-table td {
  padding: 16px;
  vertical-align: top;
  border-bottom: 1px solid var(--cron-border);
  color: var(--cron-text);
}
.task-table tbody tr:last-child td {
  border-bottom: 0;
}

.name-col {
  min-width: 220px;
}

.task-name,
.task-text {
  color: var(--cron-text);
  font-size: 14px;
  line-height: 1.5;
}
.task-name {
  font-weight: 600;
}

.task-subline {
  margin-top: 6px;
  color: var(--cron-muted);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.task-session {
  max-width: 340px;
  color: var(--cron-text);
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.actions-col {
  width: 170px;
}

.table-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 140px;
}

.state-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 220px;
  border: 1px dashed var(--cron-border-strong);
  border-radius: 12px;
  color: var(--cron-muted);
  font-size: 14px;
  margin: 16px;
}

.cron-dialog-card {
  border: 1px solid var(--cron-border);
  border-radius: 18px;
}

.cron-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.cron-form-grid--single {
  grid-template-columns: 1fr;
}

@media (max-width: 1280px) {
  .cron-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .cron-topbar {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px;
  }
  .topbar-right {
    width: 100%;
  }
  .topbar-desc {
    max-width: none;
  }
  .cron-page {
    gap: 12px;
    padding: 12px;
  }
  .table-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .cron-overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>

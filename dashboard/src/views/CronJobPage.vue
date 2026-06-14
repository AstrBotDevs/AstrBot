<template>
  <div class="dashboard-page cron-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="dashboard-shell cron-shell pa-4 pa-md-6">
      <div class="cron-detail-width">
        <div class="cron-header mb-4 pb-4">
          <div class="cron-header-copy">
            <h1 class="dashboard-title">{{ tm("page.title") }}</h1>
            <div class="dashboard-subtitle">
              {{ tm("page.subtitle") }}
              <v-btn
                variant="text"
                color="primary"
                density="compact"
                class="supported-platform-link"
                @click="platformDialog = true"
              >
                {{ tm("page.proactive.link") }}
              </v-btn>
            </div>
          </div>

          <div class="cron-header-actions">
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

        <section class="task-surface">
          <v-progress-linear
            v-if="loading && !jobs.length"
            indeterminate
            color="primary"
          />

          <div v-else-if="!jobs.length" class="text-center pa-8">
            <v-icon size="64" color="grey-lighten-1">
              mdi-calendar-blank-outline
            </v-icon>
            <p class="text-grey mt-4">{{ tm("table.empty") }}</p>
          </div>

          <template v-else>
            <div class="task-filter-bar">
              <v-text-field
                v-model="taskSearch"
                :label="tm('filters.search')"
                prepend-inner-icon="mdi-magnify"
                variant="solo-filled"
                density="compact"
                clearable
                hide-details
              />
              <v-autocomplete
                v-model="selectedUmoFilter"
                :items="jobUmoFilterOptions"
                item-title="label"
                item-value="value"
                :label="tm('filters.umo')"
                prepend-inner-icon="mdi-send-outline"
                variant="solo-filled"
                density="compact"
                clearable
                hide-details
                :no-data-text="tm('filters.noUmos')"
              />
            </div>

            <div v-if="!sortedJobs.length" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">
                mdi-file-search-outline
              </v-icon>
              <p class="text-grey mt-4">{{ tm("filters.noMatches") }}</p>
            </div>

            <div v-else class="task-list pb-3">
              <OutlinedActionListItem
                v-for="item in sortedJobs"
                :key="item.job_id"
                :title="item.name || tm('table.notAvailable')"
                clickable
                @click="openEdit(item)"
              >
                <template #title-extra>
                  <v-chip
                    size="x-small"
                    :color="item.run_once ? 'orange' : 'primary'"
                    variant="tonal"
                  >
                    {{ scheduleProductLabel(item) }}
                  </v-chip>
                </template>

                <div class="task-description text-body-2 text-medium-emphasis">
                  {{ taskPreview(item) }}
                </div>

                <div class="task-meta text-caption text-medium-emphasis">
                  <span class="task-meta-item">
                    <v-icon size="small" class="me-1">mdi-send-outline</v-icon>
                    {{ deliveryTargetText(item) }}
                  </span>
                  <v-tooltip :text="lastRunTooltipText(item)" location="top">
                    <template #activator="{ props }">
                      <span v-bind="props" class="task-meta-item">
                        <v-icon size="small" class="me-1">
                          mdi-clock-time-four-outline
                        </v-icon>
                        {{ nextRunText(item) }}
                      </span>
                    </template>
                  </v-tooltip>
                </div>

                <template #actions>
                  <StyledMenu location="bottom end" offset="8">
                    <template #activator="{ props: menuProps }">
                      <v-btn
                        v-bind="menuProps"
                        icon="mdi-dots-horizontal"
                        variant="text"
                        size="small"
                        class="list-action-icon-btn"
                        :title="tm('actions.more')"
                        @click.stop
                      />
                    </template>
                    <v-list-item
                      class="styled-menu-item"
                      prepend-icon="mdi-pencil-outline"
                      @click.stop="openEdit(item)"
                    >
                      <v-list-item-title>
                        {{ tm("actions.edit") }}
                      </v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      class="styled-menu-item"
                      prepend-icon="mdi-play-circle-outline"
                      :disabled="runningJobIds.has(item.job_id)"
                      @click.stop="runJobNow(item)"
                    >
                      <v-list-item-title>
                        {{ tm("actions.runNow") }}
                      </v-list-item-title>
                    </v-list-item>
                    <v-list-item
                      class="styled-menu-item"
                      prepend-icon="mdi-delete-outline"
                      @click.stop="deleteJob(item)"
                    >
                      <v-list-item-title class="text-error">
                        {{ tm("actions.delete") }}
                      </v-list-item-title>
                    </v-list-item>
                  </StyledMenu>
                </template>

                <template #control>
                  <v-switch
                    v-model="item.enabled"
                    inset
                    density="compact"
                    hide-details
                    color="primary"
                    @click.stop
                    @change="toggleJob(item)"
                  />
                </template>
              </OutlinedActionListItem>
            </div>
          </template>
        </section>

        <v-dialog v-model="platformDialog" max-width="520">
          <v-card class="dashboard-dialog-card">
            <v-card-title class="text-h3 pt-5 px-5">
              {{ tm("platformDialog.title") }}
            </v-card-title>
            <v-card-text class="px-5 pb-2">
              <p class="platform-dialog-description">
                {{ tm("platformDialog.description") }}
              </p>
              <div v-if="proactivePlatforms.length" class="platform-list">
                <div
                  v-for="platform in proactivePlatforms"
                  :key="platform.id"
                  class="platform-list-item"
                >
                  <div class="platform-name">
                    {{ platform.display_name || platform.name }}
                  </div>
                  <div class="platform-id">{{ platform.id }}</div>
                </div>
              </div>
              <div v-else class="dashboard-empty platform-dialog-empty">
                {{ tm("page.proactive.unsupported") }}
              </div>
            </v-card-text>
            <v-card-actions class="justify-end px-5 pb-5">
              <v-btn variant="text" @click="platformDialog = false">
                {{ tm("actions.close") }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <v-snackbar
          v-model="snackbar.show"
          :color="snackbar.color"
          timeout="2600"
        >
          {{ snackbar.message }}
        </v-snackbar>

        <v-dialog v-model="createDialog" max-width="620">
          <v-card class="dashboard-dialog-card">
            <v-card-title class="text-h3 pt-5 px-5">{{
              dialogTitle
            }}</v-card-title>
            <v-card-text class="px-5 pb-2">
              <div class="dashboard-form-grid dashboard-form-grid--single">
                <v-text-field
                  v-model="newJob.name"
                  :label="tm('form.name')"
                  variant="outlined"
                  density="comfortable"
                />
                <v-textarea
                  v-model="newJob.note"
                  :label="tm('form.note')"
                  variant="outlined"
                  density="comfortable"
                  rows="5"
                />

                <div class="schedule-field">
                  <v-select
                    v-model="newJob.schedule_mode"
                    class="schedule-mode-select"
                    :items="scheduleModeOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('form.scheduleMode')"
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />

                  <v-text-field
                    v-if="newJob.schedule_mode === 'once'"
                    v-model="newJob.run_at"
                    :label="tm('form.runAt')"
                    type="datetime-local"
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />

                  <div
                    v-else-if="newJob.schedule_mode === 'interval'"
                    class="schedule-inline-fields"
                  >
                    <v-text-field
                      v-model.number="newJob.interval_value"
                      :label="tm('form.intervalEvery')"
                      type="number"
                      min="1"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                    <v-select
                      v-model="newJob.interval_unit"
                      :items="intervalUnitOptions"
                      item-title="label"
                      item-value="value"
                      :label="tm('form.intervalUnit')"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                  </div>

                  <v-text-field
                    v-else-if="newJob.schedule_mode === 'daily'"
                    v-model="newJob.daily_time"
                    :label="tm('form.dailyTime')"
                    type="time"
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />

                  <div
                    v-else-if="newJob.schedule_mode === 'weekly'"
                    class="schedule-inline-fields"
                  >
                    <v-select
                      v-model="newJob.weekly_day"
                      :items="weekdayOptions"
                      item-title="label"
                      item-value="value"
                      :label="tm('form.weeklyDay')"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                    <v-text-field
                      v-model="newJob.weekly_time"
                      :label="tm('form.weeklyTime')"
                      type="time"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                  </div>

                  <div
                    v-else-if="newJob.schedule_mode === 'monthly'"
                    class="schedule-inline-fields"
                  >
                    <v-text-field
                      v-model.number="newJob.monthly_day"
                      :label="tm('form.monthlyDay')"
                      type="number"
                      min="1"
                      max="31"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                    <v-text-field
                      v-model="newJob.monthly_time"
                      :label="tm('form.monthlyTime')"
                      type="time"
                      variant="outlined"
                      density="comfortable"
                      hide-details
                    />
                  </div>

                  <v-text-field
                    v-else
                    v-model="newJob.cron_expression"
                    :label="tm('form.cron')"
                    :placeholder="tm('form.cronPlaceholder')"
                    variant="outlined"
                    density="comfortable"
                    hide-details
                  />
                </div>

                <v-autocomplete
                  v-model="newJob.session"
                  :items="availableUmos"
                  :loading="loadingUmos"
                  :label="tm('form.session')"
                  variant="outlined"
                  density="comfortable"
                  clearable
                  hide-details
                  :no-data-text="tm('form.noUmos')"
                  @focus="loadUmos()"
                >
                  <template #item="{ props, item }">
                    <v-list-item v-bind="props">
                      <template #title>
                        <UmoDisplay
                          v-bind="getUmoDisplayProps(item.raw)"
                          compact
                          :show-info="false"
                          :show-platform="false"
                        />
                      </template>
                      <template #append>
                        <v-chip
                          v-if="getUmoInfo(item.raw).platform"
                          size="x-small"
                          :color="
                            getPlatformColor(getUmoInfo(item.raw).platform)
                          "
                          class="cron-umo-platform"
                        >
                          {{ getUmoInfo(item.raw).platform }}
                        </v-chip>
                      </template>
                    </v-list-item>
                  </template>
                  <template #selection="{ item }">
                    <v-chip
                      v-if="item && getUmoSelectionText(item.raw)"
                      size="small"
                      variant="tonal"
                      color="primary"
                      class="umo-selection-chip"
                    >
                      {{ getUmoSelectionText(item.raw) }}
                    </v-chip>
                  </template>
                </v-autocomplete>
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
                @click="submitJob"
              >
                {{ dialogSubmitText }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </div>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useTheme } from "vuetify";
import { botApi, cronApi, sessionApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import OutlinedActionListItem from "@/components/shared/OutlinedActionListItem.vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import UmoDisplay from "@/components/shared/UmoDisplay.vue";

const { tm } = useModuleI18n("features/cron");
const theme = useTheme();

const isDark = computed(() => theme.global.current.value.dark);
const loading = ref(false);
const jobs = ref<any[]>([]);
const taskSearch = ref("");
const selectedUmoFilter = ref<string | null>(null);
const proactivePlatforms = ref<
  { id: string; name: string; display_name?: string }[]
>([]);
const availableUmos = ref<string[]>([]);
const availableUmoInfoMap = ref<Record<string, UmoInfo>>({});
const loadingUmos = ref(false);
const platformDialog = ref(false);
const createDialog = ref(false);
const creating = ref(false);
const editingJobId = ref("");
const runningJobIds = ref(new Set<string>());
const NO_DELIVERY_TARGET_FILTER = "__astrbot_no_delivery_target__";
type ScheduleMode =
  | "once"
  | "interval"
  | "daily"
  | "weekly"
  | "monthly"
  | "cron";
type IntervalUnit = "minutes" | "hours" | "days";
type UmoInfo = {
  umo: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
};

const newJob = ref({
  schedule_mode: "once" as ScheduleMode,
  name: "",
  note: "",
  cron_expression: "",
  run_at: "",
  interval_value: 1,
  interval_unit: "hours" as IntervalUnit,
  daily_time: "09:00",
  weekly_day: 1,
  weekly_time: "09:00",
  monthly_day: 1,
  monthly_time: "09:00",
  session: "",
  timezone: "",
  enabled: true,
});

const snackbar = ref({ show: false, message: "", color: "success" });

const jobUmoFilterOptions = computed(() => [
  ...(jobs.value.some((job) => !getJobSession(job))
    ? [
        {
          label: tm("filters.noDeliveryTarget"),
          value: NO_DELIVERY_TARGET_FILTER,
        },
      ]
    : []),
  ...Array.from(new Set(jobs.value.map(getJobSession).filter(Boolean)))
    .sort((a, b) => a.localeCompare(b))
    .map((umo) => ({ label: umo, value: umo })),
]);

const filteredJobs = computed(() => {
  const query = taskSearch.value.trim().toLowerCase();
  const umo = selectedUmoFilter.value;
  return jobs.value.filter((job) => {
    const session = getJobSession(job);
    if (umo === NO_DELIVERY_TARGET_FILTER && session) {
      return false;
    }
    if (umo && umo !== NO_DELIVERY_TARGET_FILTER && session !== umo) {
      return false;
    }

    if (!query) {
      return true;
    }

    const title = String(job.name || "").toLowerCase();
    const content = String(job.note || job.description || "").toLowerCase();
    return title.includes(query) || content.includes(query);
  });
});

const sortedJobs = computed(() =>
  [...filteredJobs.value].sort((a, b) => {
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

const isEditing = computed(() => !!editingJobId.value);
const dialogTitle = computed(() =>
  tm(isEditing.value ? "form.editTitle" : "form.title"),
);
const dialogSubmitText = computed(() =>
  tm(isEditing.value ? "actions.save" : "actions.submit"),
);
const scheduleModeOptions = computed(() => [
  { label: tm("form.scheduleModes.once"), value: "once" },
  { label: tm("form.scheduleModes.interval"), value: "interval" },
  { label: tm("form.scheduleModes.daily"), value: "daily" },
  { label: tm("form.scheduleModes.weekly"), value: "weekly" },
  { label: tm("form.scheduleModes.monthly"), value: "monthly" },
  { label: tm("form.scheduleModes.cron"), value: "cron" },
]);
const intervalUnitOptions = computed(() => [
  { label: tm("form.intervalUnits.minutes"), value: "minutes" },
  { label: tm("form.intervalUnits.hours"), value: "hours" },
  { label: tm("form.intervalUnits.days"), value: "days" },
]);
const weekdayOptions = computed(() => [
  { label: tm("form.weekdays.sunday"), value: 0 },
  { label: tm("form.weekdays.monday"), value: 1 },
  { label: tm("form.weekdays.tuesday"), value: 2 },
  { label: tm("form.weekdays.wednesday"), value: 3 },
  { label: tm("form.weekdays.thursday"), value: 4 },
  { label: tm("form.weekdays.friday"), value: 5 },
  { label: tm("form.weekdays.saturday"), value: 6 },
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

function formatTime(val: any, fallback = tm("table.notAvailable")): string {
  if (!val) return fallback;
  try {
    const date = new Date(val);
    return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString();
  } catch {
    return String(val);
  }
}

function taskPreview(item: any): string {
  const text = String(item.note || item.description || "").trim();
  if (!text) return item.job_id || tm("table.notAvailable");
  return text.length > 86 ? `${text.slice(0, 86)}...` : text;
}

function getJobSession(job: any): string {
  return String(job.session || job?.payload?.session || "").trim();
}

function deliveryTargetText(item: any): string {
  return getJobSession(item) || tm("card.noDeliveryTarget");
}

function nextRunText(item: any): string {
  if (item.run_once) {
    return tm("card.runAt", { time: formatTime(item.run_at) });
  }
  return tm("card.nextRun", {
    time: formatTime(item.next_run_time, tm("table.notAvailable")),
  });
}

function lastRunTooltipText(item: any): string {
  const lastRun = `${tm("table.headers.lastRun")}: ${formatTime(
    item.last_run_at,
  )}`;
  const lastError = String(item.last_error || "").trim();
  if (!lastError) {
    return lastRun;
  }
  return `${lastRun} · ${lastError}`;
}

function scheduleProductLabel(item: any): string {
  if (item.run_once) {
    return tm("card.onceAt", { time: formatTime(item.run_at) });
  }

  const cron = String(item.cron_expression || "").trim();
  const parts = cron.split(/\s+/);
  if (parts.length !== 5) {
    return cron || tm("table.notAvailable");
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const minuteInterval = /^\*\/(\d+)$/.exec(minute);
  if (
    minuteInterval &&
    hour === "*" &&
    dayOfMonth === "*" &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return tm("card.everyMinutes", { count: Number(minuteInterval[1]) });
  }

  const hourInterval = /^\*\/(\d+)$/.exec(hour);
  if (
    minute === "0" &&
    hourInterval &&
    dayOfMonth === "*" &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return tm("card.everyHours", { count: Number(hourInterval[1]) });
  }

  const dayInterval = /^\*\/(\d+)$/.exec(dayOfMonth);
  if (
    minute === "0" &&
    hour === "0" &&
    dayInterval &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return tm("card.everyDays", { count: Number(dayInterval[1]) });
  }

  const minuteNumber = Number(minute);
  const hourNumber = Number(hour);
  const dayOfMonthNumber = Number(dayOfMonth);
  const dayOfWeekNumber = Number(dayOfWeek);
  if (!isCronTime(minuteNumber, hourNumber)) {
    return tm("card.customCron", { cron });
  }
  const time = `${padTimePart(hourNumber)}:${padTimePart(minuteNumber)}`;
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return tm("card.dailyAt", { time });
  }
  if (
    dayOfMonth === "*" &&
    month === "*" &&
    Number.isInteger(dayOfWeekNumber) &&
    dayOfWeekNumber >= 0 &&
    dayOfWeekNumber <= 6
  ) {
    return tm("card.weeklyAt", {
      day: weekdayText(dayOfWeekNumber),
      time,
    });
  }
  if (
    Number.isInteger(dayOfMonthNumber) &&
    dayOfMonthNumber >= 1 &&
    dayOfMonthNumber <= 31 &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return tm("card.monthlyAt", { day: dayOfMonthNumber, time });
  }
  return tm("card.customCron", { cron });
}

function weekdayText(value: number): string {
  const keyMap = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
  ];
  return tm(`form.weekdays.${keyMap[value]}`);
}

function parseUmoInfo(umo: string): UmoInfo {
  const parts = umo.split(":");
  return {
    umo,
    platform: parts[0] || "",
    message_type: parts[1] || "",
    session_id: parts.slice(2).join(":") || umo,
    auto_name: "",
    user_alias: "",
    display_name: umo,
  };
}

function mergeUmoInfos(infos: UmoInfo[] = []) {
  const next = { ...availableUmoInfoMap.value };
  for (const info of infos) {
    if (info?.umo) {
      next[info.umo] = { ...(next[info.umo] || {}), ...info };
    }
  }
  availableUmoInfoMap.value = next;
}

function getUmoInfo(umo: string): UmoInfo {
  return availableUmoInfoMap.value[umo] || parseUmoInfo(umo);
}

function getUmoDisplayProps(umo: string) {
  const info = getUmoInfo(umo);
  return {
    umo,
    platform: info.platform || "",
    messageType: info.message_type || "",
    sessionId: info.session_id || "",
    autoName: info.auto_name || "",
    userAlias: info.user_alias || "",
  };
}

function getPlatformColor(platform = "") {
  const colors: Record<string, string> = {
    aiocqhttp: "blue",
    qq_official: "purple",
    telegram: "light-blue",
    discord: "indigo",
    webchat: "orange",
  };
  return colors[platform] || "grey";
}

function getUmoSelectionText(value?: string | null): string {
  if (!value) return "";
  const info = getUmoInfo(value);
  const aliasName = info.user_alias || "";
  const autoName = info.auto_name || "";
  if (aliasName && autoName && aliasName !== autoName) {
    return `${aliasName}（${autoName}）`;
  }
  return aliasName || autoName || value || info.display_name || "";
}

async function loadUmos(force = false) {
  if (loadingUmos.value || (!force && availableUmos.value.length)) return;
  loadingUmos.value = true;
  try {
    const res = await sessionApi.activeUmos();
    if (res.data.status === "ok") {
      const loadedUmos = Array.isArray(res.data.data?.umos)
        ? res.data.data.umos
        : [];
      mergeUmoInfos(res.data.data?.umo_infos || []);
      availableUmos.value = Array.from(
        new Set([...availableUmos.value, ...loadedUmos]),
      );
    }
  } catch {
    // The field remains editable through free search only when a UMO list is available.
  } finally {
    loadingUmos.value = false;
  }
}

async function loadJobs() {
  loading.value = true;
  try {
    const res = await cronApi.list();
    if (res.data.status === "ok") {
      const data = Array.isArray(res.data.data) ? res.data.data : [];
      jobs.value = data.map((job: any) => ({
        ...job,
        session: job?.payload?.session || job?.session || "",
      }));
      mergeUmoInfos(
        jobs.value.map(getJobSession).filter(Boolean).map(parseUmoInfo),
      );
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
    const res = await botApi.stats();
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
    // Ignore platform fetch failures and keep the fallback state.
  }
}

async function toggleJob(job: any) {
  try {
    const res = await cronApi.update(job.job_id, {
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
    const res = await cronApi.delete(job.job_id);
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

async function runJobNow(job: any) {
  const jobId = String(job.job_id || "");
  if (!jobId || runningJobIds.value.has(jobId)) return;
  runningJobIds.value = new Set([...runningJobIds.value, jobId]);
  try {
    const res = await cronApi.run(jobId);
    if (res.data.status === "ok") {
      toast(tm("messages.runStarted"));
      await loadJobs();
    } else {
      toast(res.data.message || tm("messages.runFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.runFailed"), "error");
  } finally {
    const next = new Set(runningJobIds.value);
    next.delete(jobId);
    runningJobIds.value = next;
  }
}

function openCreate() {
  editingJobId.value = "";
  resetNewJob();
  createDialog.value = true;
  loadUmos();
}

function toDatetimeLocalValue(value: any): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

function toIsoDatetime(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function resetNewJob() {
  newJob.value = {
    schedule_mode: "once",
    name: "",
    note: "",
    cron_expression: "",
    run_at: "",
    interval_value: 1,
    interval_unit: "hours",
    daily_time: "09:00",
    weekly_day: 1,
    weekly_time: "09:00",
    monthly_day: 1,
    monthly_time: "09:00",
    session: "",
    timezone: "",
    enabled: true,
  };
}

function openEdit(job: any) {
  editingJobId.value = job.job_id;
  const schedule = readScheduleFromJob(job);
  if (job.session && !availableUmos.value.includes(job.session)) {
    availableUmos.value = [job.session, ...availableUmos.value];
    mergeUmoInfos([parseUmoInfo(job.session)]);
  }
  newJob.value = {
    schedule_mode: schedule.schedule_mode,
    name: job.name || "",
    note: job.note || job.description || "",
    cron_expression: schedule.cron_expression,
    run_at: toDatetimeLocalValue(job.run_at),
    interval_value: schedule.interval_value,
    interval_unit: schedule.interval_unit,
    daily_time: schedule.daily_time,
    weekly_day: schedule.weekly_day,
    weekly_time: schedule.weekly_time,
    monthly_day: schedule.monthly_day,
    monthly_time: schedule.monthly_time,
    session: job.session || job?.payload?.session || "",
    timezone: job.timezone || "",
    enabled: job.enabled !== false,
  };
  createDialog.value = true;
  loadUmos(true);
}

function parseTimeParts(
  value: string,
): { hour: number; minute: number } | null {
  const match = /^(\d{2}):(\d{2})(?::\d{2})?$/.exec(value || "");
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

function padTimePart(value: string | number): string {
  return String(value).padStart(2, "0");
}

function isCronTime(minute: number, hour: number): boolean {
  return (
    Number.isInteger(minute) &&
    minute >= 0 &&
    minute <= 59 &&
    Number.isInteger(hour) &&
    hour >= 0 &&
    hour <= 23
  );
}

function buildCronExpression(): string {
  const mode = newJob.value.schedule_mode;
  if (mode === "interval") {
    const value = Math.max(1, Number(newJob.value.interval_value || 1));
    if (newJob.value.interval_unit === "minutes") {
      return `*/${Math.min(value, 59)} * * * *`;
    }
    if (newJob.value.interval_unit === "hours") {
      return `0 */${Math.min(value, 23)} * * *`;
    }
    return `0 0 */${Math.min(value, 31)} * *`;
  }
  if (mode === "daily") {
    const time = parseTimeParts(newJob.value.daily_time);
    if (!time) return "";
    return `${time.minute} ${time.hour} * * *`;
  }
  if (mode === "weekly") {
    const time = parseTimeParts(newJob.value.weekly_time);
    if (!time) return "";
    const weekday = Math.min(Math.max(Number(newJob.value.weekly_day), 0), 6);
    return `${time.minute} ${time.hour} * * ${weekday}`;
  }
  if (mode === "monthly") {
    const time = parseTimeParts(newJob.value.monthly_time);
    if (!time) return "";
    const day = Math.min(
      Math.max(Number(newJob.value.monthly_day || 1), 1),
      31,
    );
    return `${time.minute} ${time.hour} ${day} * *`;
  }
  return newJob.value.cron_expression.trim();
}

function readScheduleFromJob(job: any) {
  const fallback = {
    schedule_mode: "cron" as ScheduleMode,
    cron_expression: job.cron_expression || "",
    interval_value: 1,
    interval_unit: "hours" as IntervalUnit,
    daily_time: "09:00",
    weekly_day: 1,
    weekly_time: "09:00",
    monthly_day: 1,
    monthly_time: "09:00",
  };
  if (job.run_once) {
    return { ...fallback, schedule_mode: "once" as ScheduleMode };
  }

  const cron = String(job.cron_expression || "").trim();
  const parts = cron.split(/\s+/);
  if (parts.length !== 5) {
    return fallback;
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const minuteNumber = Number(minute);
  const hourNumber = Number(hour);
  const dayOfMonthNumber = Number(dayOfMonth);
  const dayOfWeekNumber = Number(dayOfWeek);
  const hasCronTime = isCronTime(minuteNumber, hourNumber);
  const time = hasCronTime
    ? `${padTimePart(hourNumber)}:${padTimePart(minuteNumber)}`
    : "09:00";

  const minuteInterval = /^\*\/(\d+)$/.exec(minute);
  if (
    minuteInterval &&
    hour === "*" &&
    dayOfMonth === "*" &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return {
      ...fallback,
      schedule_mode: "interval" as ScheduleMode,
      interval_value: Number(minuteInterval[1]),
      interval_unit: "minutes" as IntervalUnit,
    };
  }

  const hourInterval = /^\*\/(\d+)$/.exec(hour);
  if (
    minute === "0" &&
    hourInterval &&
    dayOfMonth === "*" &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return {
      ...fallback,
      schedule_mode: "interval" as ScheduleMode,
      interval_value: Number(hourInterval[1]),
      interval_unit: "hours" as IntervalUnit,
    };
  }

  const dayInterval = /^\*\/(\d+)$/.exec(dayOfMonth);
  if (
    minute === "0" &&
    hour === "0" &&
    dayInterval &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return {
      ...fallback,
      schedule_mode: "interval" as ScheduleMode,
      interval_value: Number(dayInterval[1]),
      interval_unit: "days" as IntervalUnit,
    };
  }

  if (hasCronTime && dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return {
      ...fallback,
      schedule_mode: "daily" as ScheduleMode,
      daily_time: time,
    };
  }

  if (
    hasCronTime &&
    dayOfMonth === "*" &&
    month === "*" &&
    Number.isInteger(dayOfWeekNumber) &&
    dayOfWeekNumber >= 0 &&
    dayOfWeekNumber <= 6
  ) {
    return {
      ...fallback,
      schedule_mode: "weekly" as ScheduleMode,
      weekly_day: dayOfWeekNumber,
      weekly_time: time,
    };
  }

  if (
    hasCronTime &&
    Number.isInteger(dayOfMonthNumber) &&
    dayOfMonthNumber >= 1 &&
    dayOfMonthNumber <= 31 &&
    month === "*" &&
    dayOfWeek === "*"
  ) {
    return {
      ...fallback,
      schedule_mode: "monthly" as ScheduleMode,
      monthly_day: dayOfMonthNumber,
      monthly_time: time,
    };
  }

  return fallback;
}

function buildPayload() {
  const runOnce = newJob.value.schedule_mode === "once";
  const cronExpression = runOnce ? "" : buildCronExpression();
  return {
    run_once: runOnce,
    name: newJob.value.name.trim(),
    note: newJob.value.note.trim(),
    cron_expression: cronExpression,
    run_at: runOnce ? toIsoDatetime(newJob.value.run_at) : "",
    session: newJob.value.session,
    timezone: newJob.value.timezone,
    enabled: newJob.value.enabled,
  };
}

function validateJobForm(): boolean {
  if (!newJob.value.name.trim()) {
    toast(tm("messages.nameRequired"), "warning");
    return false;
  }
  if (!newJob.value.note.trim()) {
    toast(tm("messages.noteRequired"), "warning");
    return false;
  }
  return validateScheduleFields();
}

function validateScheduleFields(): boolean {
  const mode = newJob.value.schedule_mode;
  if (mode === "once") {
    if (!newJob.value.run_at) {
      toast(tm("messages.runAtRequired"), "warning");
      return false;
    }
    return true;
  }

  if (mode === "interval") {
    const value = Number(newJob.value.interval_value);
    const validUnit = ["minutes", "hours", "days"].includes(
      newJob.value.interval_unit,
    );
    if (!Number.isInteger(value) || value < 1 || !validUnit) {
      toast(tm("messages.intervalRequired"), "warning");
      return false;
    }
    return true;
  }

  if (mode === "daily") {
    if (!parseTimeParts(newJob.value.daily_time)) {
      toast(tm("messages.dailyTimeRequired"), "warning");
      return false;
    }
    return true;
  }

  if (mode === "weekly") {
    const weekday = Number(newJob.value.weekly_day);
    if (
      !parseTimeParts(newJob.value.weekly_time) ||
      !Number.isInteger(weekday) ||
      weekday < 0 ||
      weekday > 6
    ) {
      toast(tm("messages.weeklyTimeRequired"), "warning");
      return false;
    }
    return true;
  }

  if (mode === "monthly") {
    const day = Number(newJob.value.monthly_day);
    if (
      !parseTimeParts(newJob.value.monthly_time) ||
      !Number.isInteger(day) ||
      day < 1 ||
      day > 31
    ) {
      toast(tm("messages.monthlyTimeRequired"), "warning");
      return false;
    }
    return true;
  }

  if (!newJob.value.cron_expression.trim()) {
    toast(tm("messages.cronRequired"), "warning");
    return false;
  }
  return true;
}

async function createJob() {
  if (!validateJobForm()) {
    return;
  }

  creating.value = true;
  try {
    const payload = buildPayload();
    const res = await cronApi.create(payload);
    if (res.data.status === "ok") {
      toast(tm("messages.createSuccess"));
      createDialog.value = false;
      editingJobId.value = "";
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

async function updateJob() {
  if (!editingJobId.value) {
    return;
  }
  if (!validateJobForm()) {
    return;
  }

  creating.value = true;
  try {
    const payload = {
      ...buildPayload(),
      description: newJob.value.note,
    };
    const res = await cronApi.update(editingJobId.value, payload);
    if (res.data.status === "ok") {
      toast(tm("messages.updateSuccess"));
      createDialog.value = false;
      editingJobId.value = "";
      resetNewJob();
      await loadJobs();
    } else {
      toast(res.data.message || tm("messages.updateFailed"), "error");
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm("messages.updateFailed"), "error");
  } finally {
    creating.value = false;
  }
}

async function submitJob() {
  if (isEditing.value) {
    await updateJob();
    return;
  }
  await createJob();
}

onMounted(() => {
  loadJobs();
  loadPlatforms();
});
</script>

<style scoped>
@import "@/styles/dashboard-shell.css";

.cron-page {
  padding-bottom: 40px;
  background: transparent;
}

.cron-shell {
  max-width: none;
}

.cron-detail-width {
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
}

.cron-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.cron-header-copy {
  min-width: 0;
}

.cron-header-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.task-surface {
  min-width: 0;
}

.task-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}

.task-filter-bar :deep(.v-field) {
  box-shadow: none;
}

.task-filter-bar :deep(.v-input) {
  flex: 0 1 auto;
}

.task-filter-bar :deep(.v-text-field) {
  width: 260px;
}

.task-filter-bar :deep(.v-autocomplete) {
  width: 300px;
}

.supported-platform-link {
  min-width: 0;
  padding-inline: 4px;
  vertical-align: baseline;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-description {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  margin-top: 6px;
}

.task-meta-item {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cron-umo-platform {
  margin-inline-start: 12px;
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-selection-chip {
  max-width: 100%;
}

.umo-selection-chip :deep(.v-chip__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-action-icon-btn {
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.list-action-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.platform-dialog-description {
  margin: 0 0 16px;
  color: var(--dashboard-muted);
  font-size: 14px;
  line-height: 1.7;
}

.platform-list {
  display: grid;
  gap: 10px;
}

.platform-list-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--dashboard-border);
  border-radius: 8px;
}

.platform-name {
  min-width: 0;
  color: var(--dashboard-text);
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-id {
  color: var(--dashboard-muted);
  font-size: 12px;
}

.platform-dialog-empty {
  min-height: 120px;
}

.schedule-field {
  display: grid;
  grid-template-columns: minmax(150px, 180px) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  margin-bottom: 16px;
}

.schedule-mode-select {
  min-width: 0;
}

.schedule-inline-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

@media (max-width: 900px) {
  .cron-header {
    align-items: stretch;
    flex-direction: column;
  }

  .cron-header-actions {
    justify-content: flex-start;
  }

  .task-filter-bar {
    align-items: stretch;
  }

  .schedule-field,
  .schedule-inline-fields {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <div class="stats-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="stats-shell pa-4 pa-md-6">
      <v-alert
        v-if="errorMessage"
        type="error"
        variant="tonal"
        class="mb-4"
      >
        {{ errorMessage }}
      </v-alert>

      <div v-if="loading && !baseStats" class="loading-wrap">
        <v-progress-circular indeterminate color="grey-darken-1" />
      </div>

      <template v-else>
        <div class="overview-grid">
          <section
            v-for="card in overviewCards"
            :key="card.label"
            class="stat-card overview-card"
          >
            <div class="card-icon">
              <v-icon size="88">{{ card.icon }}</v-icon>
            </div>
            <div class="card-label">{{ card.label }}</div>
            <div class="card-value">{{ card.value }}</div>
          </section>
        </div>

        <div class="section-toolbar">
          <div>
            <div class="section-title">{{ t('messageOverview.title') }}</div>
          </div>
          <div class="range-switch">
            <button
              v-for="option in rangeOptions"
              :key="`toolbar-${option.value}`"
              type="button"
              class="range-chip"
              :class="{ active: selectedRange === option.value }"
              @click="selectedRange = option.value"
            >
              {{ t(option.labelKey) }}
            </button>
          </div>
        </div>

        <div class="panel-grid">
          <section class="stat-card chart-card chart-card-wide">
            <div class="card-head">
              <div>
                <div class="section-title">{{ t('messageTrend.title') }}</div>
              </div>
              <div class="card-head-actions">
                <div class="section-metric">
                  <span class="metric-label">{{ t('messageTrend.totalMessages') }}</span>
                  <span class="metric-value">{{ formatNumber(baseStats?.message_count ?? 0) }}</span>
                </div>
              </div>
            </div>
            <apexchart
              type="area"
              height="320"
              :options="messageChartOptions"
              :series="messageChartSeries"
            />
          </section>

          <section class="stat-card provider-list-card">
            <div class="card-head compact">
              <div>
                <div class="section-title">{{ t('platformRanking.title') }}</div>
              </div>
            </div>
            <div v-if="platformRanking.length" class="provider-list">
              <div
                v-for="platform in platformRanking"
                :key="platform.name"
                class="provider-row"
              >
                <div class="provider-identity">
                  <img
                    v-if="platform.icon"
                    :src="platform.icon"
                    alt=""
                    class="platform-icon"
                  />
                  <MessageCircle v-else :size="18" aria-hidden="true" />
                  <span class="provider-name">{{ platform.name }}</span>
                </div>
                <strong>{{ formatNumber(platform.count) }}</strong>
              </div>
            </div>
            <div v-else class="empty-state">{{ t('empty.platformStats') }}</div>
          </section>
        </div>

        <div class="token-section-head">
          <div>
            <div class="section-title">{{ t('modelCalls.title') }}</div>
          </div>
        </div>

        <div class="token-grid">
          <section class="stat-card chart-card chart-card-wide provider-trend-card">
            <div class="card-head">
              <div>
                <div class="section-title">{{ t('modelTrend.title') }}</div>
              </div>
            </div>
            <apexchart
              type="bar"
              height="420"
              :options="providerChartOptions"
              :series="providerTrendSeries"
            />
          </section>

          <section class="token-side-column">
            <section class="stat-card token-total-card">
              <div class="card-label">{{ t('modelTotal.title', { range: rangeLabel }) }}</div>
              <div class="token-total-value">{{ formatNumber(providerStats?.range_total_tokens ?? 0) }} <span style="font-size: 18px;">{{ t('units.tokens') }}</span></div>
              <div class="card-note">{{ t('modelTotal.callCount', { count: formatNumber(providerStats?.range_total_calls ?? 0) }) }}</div>
              <div class="token-meta-list">
                <div class="token-meta-item">
                  <span>{{ t('modelTotal.avgTtft') }}</span>
                  <strong>{{ rangeAvgTtftLabel }}</strong>
                </div>
                <div class="token-meta-item">
                  <span>{{ t('modelTotal.avgDuration') }}</span>
                  <strong>{{ rangeAvgDurationLabel }}</strong>
                </div>
                <div class="token-meta-item">
                  <span>{{ t('modelTotal.avgTpm') }}</span>
                  <strong>{{ rangeAvgTpmLabel }}</strong>
                </div>
                <div class="token-meta-item">
                  <span>{{ t('modelTotal.successRate') }}</span>
                  <strong>{{ rangeSuccessRateLabel }}</strong>
                </div>
              </div>
            </section>

            <section class="stat-card provider-list-card">
              <div class="card-head compact">
                <div>
                  <div class="section-title">{{ t('modelRanking.title') }}</div>
                </div>
              </div>
              <div
                v-if="rangeProviderRanking.length"
                class="provider-list provider-list--scrollable"
              >
                <div
                  v-for="provider in rangeProviderRanking"
                  :key="provider.provider_id"
                  class="provider-row"
                >
                  <span class="provider-name">{{ provider.provider_id }}</span>
                  <strong>{{ formatNumber(provider.tokens) }}</strong>
                </div>
              </div>
              <div v-else class="empty-state">{{ t('empty.modelCalls', { range: rangeLabel }) }}</div>
            </section>
          </section>
        </div>

        <section class="stat-card provider-list-card">
          <div class="card-head compact">
            <div>
              <div class="section-title">{{ t('sessionRanking.title', { range: rangeLabel }) }}</div>
            </div>
          </div>
          <div v-if="rangeUmoRanking.length" class="provider-list">
            <div
              v-for="item in rangeUmoRanking"
              :key="item.umo"
              class="provider-row"
            >
              <div class="provider-identity provider-identity--umo">
                <img
                  v-if="item.icon"
                  :src="item.icon"
                  alt=""
                  class="platform-icon"
                />
                <MessageCircle v-else :size="18" aria-hidden="true" />
                <v-tooltip
                  v-if="item.display_name && item.display_name !== item.umo"
                  location="top"
                  max-width="520"
                >
                  <template #activator="{ props }">
                    <span
                      v-bind="props"
                      class="provider-name provider-name--alias"
                    >
                      {{ item.display_name }}
                    </span>
                  </template>
                  <span class="umo-tooltip">{{ item.umo }}</span>
                </v-tooltip>
                <span v-else class="provider-name">{{ item.umo }}</span>
                <v-tooltip location="top">
                  <template #activator="{ props }">
                    <button
                      v-bind="props"
                      type="button"
                      class="umo-copy-button"
                      :class="{ 'umo-copy-button--copied': copiedUmo === item.umo }"
                      :aria-label="copiedUmo === item.umo
                        ? globalT('core.common.copied')
                        : globalT('core.common.copy')"
                      @click="copyUmo(item.umo)"
                    >
                      <Check v-if="copiedUmo === item.umo" :size="15" />
                      <Copy v-else :size="15" />
                    </button>
                  </template>
                  <span>
                    {{ failedCopyUmo === item.umo
                      ? globalT('core.common.copyFailed')
                      : copiedUmo === item.umo
                        ? globalT('core.common.copied')
                        : globalT('core.common.copy') }}
                  </span>
                </v-tooltip>
                <v-tooltip location="top">
                  <template #activator="{ props }">
                    <RouterLink
                      v-bind="props"
                      class="umo-conversation-link"
                      :to="{ name: 'Conversation', query: { umo: item.umo } }"
                      :aria-label="t('sessionRanking.openConversation')"
                    >
                      <MessageSquareText :size="15" aria-hidden="true" />
                    </RouterLink>
                  </template>
                  <span>{{ t('sessionRanking.openConversation') }}</span>
                </v-tooltip>
              </div>
              <strong>{{ formatNumber(item.tokens) }}</strong>
            </div>
          </div>
          <div v-else class="empty-state">{{ t('empty.sessionCalls', { range: rangeLabel }) }}</div>
        </section>
      </template>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import type { ApexOptions } from 'apexcharts'
import { Check, Copy, MessageCircle, MessageSquareText } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useTheme } from 'vuetify'
import { statsApi } from '@/api/v1'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { copyToClipboard } from '@/utils/clipboard'
import { getPlatformIcon } from '@/utils/platformUtils'

type TokenRange = 1 | 3 | 7
type ChartSeries = Array<{
  name: string
  data: unknown[]
}>

interface RunningStats {
  hours: number
  minutes: number
  seconds: number
}

interface BaseStatsResponse {
  message_count: number
  platform_count: number
  platform: Array<{
    name: string
    count: number
    timestamp: number
  }>
  message_time_series: Array<[number, number]>
  memory: {
    process: number
    system: number
  }
  cpu_percent: number
  running: RunningStats
  thread_count: number
  start_time: number
}

interface ProviderTrendItem {
  name: string
  data: Array<[number, number]>
  total_tokens: number
}

interface ProviderRankingItem {
  provider_id: string
  tokens: number
}

interface UmoRankingItem {
  umo: string
  display_name: string
  platform_type: string
  tokens: number
}

interface ProviderTokenStatsResponse {
  days: TokenRange
  trend: {
    series: ProviderTrendItem[]
    total_series: Array<[number, number]>
  }
  range_total_tokens: number
  range_total_calls: number
  range_avg_ttft_ms: number
  range_avg_duration_ms: number
  range_avg_tpm: number
  range_success_rate: number
  range_by_provider: ProviderRankingItem[]
  range_by_umo: UmoRankingItem[]
  today_total_tokens: number
  today_total_calls: number
  today_by_provider: ProviderRankingItem[]
}

const { locale, t: globalT } = useI18n()
const { tm: t } = useModuleI18n('features/stats')
const theme = useTheme()
const loading = ref(true)
const errorMessage = ref('')
const baseStats = ref<BaseStatsResponse | null>(null)
const providerStats = ref<ProviderTokenStatsResponse | null>(null)
const selectedRange = ref<TokenRange>(1)
const currentTimeMs = ref(Date.now())
const copiedUmo = ref('')
const failedCopyUmo = ref('')
const isDark = computed(() => theme.global.current.value.dark)
const themePalette = computed(() => {
  const colors = theme.global.current.value.colors as Record<string, string>
  return {
    primary: colors.primary,
    secondary: colors.secondary,
    info: colors.info,
    success: colors.success,
    warning: colors.warning,
    accent: colors.accent,
    border: colors.border ?? colors.borderLight ?? colors.primary,
    mutedText: colors.secondaryText ?? colors.primaryText ?? colors.primary,
    lightPrimary: colors.lightprimary ?? colors.surface ?? colors.background,
    lightSecondary: colors.lightsecondary ?? colors.surface ?? colors.background
  }
})

let refreshTimer: number | null = null
let uptimeTimer: number | null = null
let copyFeedbackTimer: number | null = null

function formatNumber(value: number): string {
  return new Intl.NumberFormat(locale.value).format(value)
}

function formatCompactNumber(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(2)}K`
  return formatNumber(value)
}

function formatMemory(memoryMb: number): string {
  if (memoryMb >= 1024) {
    return `${(memoryMb / 1024).toFixed(1)} ${t('units.gb')}`
  }
  return `${formatNumber(memoryMb)} ${t('units.mb')}`
}

function formatDurationMs(value: number): string {
  if (!value || value <= 0) return '—'
  if (value < 1000) return `${Math.round(value)} ${t('units.ms')}`
  return `${(value / 1000).toFixed(2)} ${t('units.secondsShort')}`
}

function formatTpm(value: number): string {
  if (!value || value <= 0) return '—'
  return `${value.toFixed(0) } ${t('units.tpm')}`
}

async function copyUmo(umo: string): Promise<void> {
  const copied = await copyToClipboard(umo)
  copiedUmo.value = copied ? umo : ''
  failedCopyUmo.value = copied ? '' : umo
  if (copyFeedbackTimer !== null) {
    window.clearTimeout(copyFeedbackTimer)
  }
  copyFeedbackTimer = window.setTimeout(() => {
    copiedUmo.value = ''
    failedCopyUmo.value = ''
  }, 2000)
}

function hexToRgba(color: string | undefined, alpha: number): string {
  if (!color) return `rgba(0, 0, 0, ${alpha})`
  if (!color.startsWith('#')) return color

  let hex = color.slice(1)
  if (hex.length === 3) {
    hex = hex
      .split('')
      .map((char) => char + char)
      .join('')
  }

  if (hex.length !== 6) return color

  const red = Number.parseInt(hex.slice(0, 2), 16)
  const green = Number.parseInt(hex.slice(2, 4), 16)
  const blue = Number.parseInt(hex.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

function formatRunningTime(running?: RunningStats | null): string {
  if (!running) return '—'
  const parts = [
    running.hours > 0 ? `${running.hours}${t('units.hoursShort')}` : '',
    running.minutes > 0 || running.hours > 0 ? `${running.minutes}${t('units.minutesShort')}` : '',
    `${running.seconds}${t('units.secondsShort')}`
  ].filter(Boolean)
  return parts.join(' ')
}

function aggregateOverflowSeries(series: ProviderTrendItem[]): ProviderTrendItem[] {
  if (series.length <= 5) return series
  const leading = series.slice(0, 4)
  const overflow = series.slice(4)
  const mergedPoints = overflow[0].data.map(([timestamp], index) => {
    const total = overflow.reduce((sum, item) => sum + (item.data[index]?.[1] ?? 0), 0)
    return [timestamp, total] as [number, number]
  })
  return [
    ...leading,
    {
      name: t('chart.others'),
      data: mergedPoints,
      total_tokens: overflow.reduce((sum, item) => sum + item.total_tokens, 0)
    }
  ]
}

async function fetchBaseStats(): Promise<void> {
  const response = await statsApi.get(selectedRange.value * 24 * 60 * 60)
  baseStats.value = response.data.data
}

async function fetchProviderStats(): Promise<void> {
  const response = await statsApi.providerTokens(selectedRange.value)
  providerStats.value = response.data.data
}

async function refreshStats(): Promise<void> {
  try {
    errorMessage.value = ''
    await Promise.all([fetchBaseStats(), fetchProviderStats()])
  } catch (error) {
    console.error('Failed to load stats page data:', error)
    errorMessage.value = t('errors.loadFailed')
  } finally {
    loading.value = false
  }
}

const rangeOptions = computed(() => [
  { labelKey: 'ranges.oneDay', value: 1 as TokenRange },
  { labelKey: 'ranges.threeDays', value: 3 as TokenRange },
  { labelKey: 'ranges.oneWeek', value: 7 as TokenRange }
])

const rangeLabel = computed(() => {
  if (selectedRange.value === 3) return t('rangeLabels.threeDays')
  if (selectedRange.value === 7) return t('rangeLabels.oneWeek')
  return t('rangeLabels.oneDay')
})

const uptimeLabel = computed(() => {
  const startTime = baseStats.value?.start_time
  if (!startTime) return '—'

  const elapsedSeconds = Math.max(0, Math.floor(currentTimeMs.value / 1000) - startTime)
  return formatRunningTime({
    hours: Math.floor(elapsedSeconds / 3600),
    minutes: Math.floor((elapsedSeconds % 3600) / 60),
    seconds: elapsedSeconds % 60
  })
})

const overviewCards = computed(() => [
  {
    label: t('overviewCards.platformCount.label'),
    value: formatNumber(baseStats.value?.platform_count ?? 0),
    icon: 'mdi-robot-outline'
  },
  {
    label: t('overviewCards.messageCount.label'),
    value: formatNumber(baseStats.value?.message_count ?? 0),
    icon: 'mdi-message-outline'
  },
  {
    label: t('overviewCards.todayModelCalls.label'),
    value: formatCompactNumber(providerStats.value?.today_total_tokens ?? 0),
    icon: 'mdi-creation-outline'
  },
  {
    label: t('overviewCards.cpu.label'),
    value: `${baseStats.value?.cpu_percent ?? 0}%`,
    icon: 'mdi-chip'
  },
  {
    label: t('overviewCards.memory.label'),
    value: formatMemory(baseStats.value?.memory?.process ?? 0),
    icon: 'mdi-memory'
  },
  {
    label: t('overviewCards.uptime.label'),
    value: uptimeLabel.value,
    icon: 'mdi-timer-outline'
  }
])

const messageChartSeries = computed<ChartSeries>(() => [
  {
    name: t('chart.messages'),
    data: (baseStats.value?.message_time_series ?? []).map(([timestamp, value]) => [
      timestamp * 1000,
      value
    ])
  }
])

const providerTrendSeries = computed<ChartSeries>(() =>
  aggregateOverflowSeries(providerStats.value?.trend.series ?? []).map((item) => ({
    name: item.name,
    data: item.data
  }))
)

const rangeProviderRanking = computed(() => providerStats.value?.range_by_provider ?? [])

const rangeUmoRanking = computed(() =>
  (providerStats.value?.range_by_umo ?? []).slice(0, 10).map((item) => ({
    ...item,
    icon: getPlatformIcon(item.platform_type)
  }))
)

const rangeAvgTtftLabel = computed(() =>
  formatDurationMs(providerStats.value?.range_avg_ttft_ms ?? 0)
)

const rangeAvgDurationLabel = computed(() =>
  formatDurationMs(providerStats.value?.range_avg_duration_ms ?? 0)
)

const rangeAvgTpmLabel = computed(() =>
  formatTpm(providerStats.value?.range_avg_tpm ?? 0)
)

const rangeSuccessRateLabel = computed(() => {
  if (!(providerStats.value?.range_total_calls ?? 0)) {
    return '—'
  }
  const rate = providerStats.value?.range_success_rate ?? 0
  return `${(rate * 100).toFixed(1)}%`
})

const platformRanking = computed(() =>
  [...(baseStats.value?.platform ?? [])]
    .sort((left, right) => right.count - left.count)
    .slice(0, 6)
    .map((platform) => ({
      ...platform,
      icon: getPlatformIcon(platform.name)
    }))
)

const providerChartColors = [
  '#008FFB',
  '#00C49F',
  '#FEB019',
  '#FF6B45',
  '#775DD0',
  '#8BC34A',
  '#D65AD1',
  '#2ED5C4',
  '#FF5CA8',
  '#2E7D32'
]

const messageChartOptions = computed<ApexOptions>(() => ({
  chart: {
    background: 'transparent',
    toolbar: { show: false },
    zoom: { enabled: false },
    fontFamily: '"SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
  },
  theme: {
    mode: isDark.value ? 'dark' : 'light'
  },
  colors: [themePalette.value.primary],
  stroke: {
    curve: 'smooth',
    width: 2.4
  },
  fill: {
    type: 'solid',
    opacity: 0.12
  },
  grid: {
    borderColor: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26),
    strokeDashArray: 0
  },
  dataLabels: { enabled: false },
  xaxis: {
    type: 'datetime',
    labels: {
      datetimeUTC: false,
      style: { colors: themePalette.value.mutedText }
    },
    axisBorder: { color: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26) },
    axisTicks: { color: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26) }
  },
  yaxis: {
    labels: {
      formatter: (value) => formatCompactNumber(Number(value)),
      style: { colors: themePalette.value.mutedText }
    }
  },
  tooltip: {
    theme: isDark.value ? 'dark' : 'light',
    x: {
      format: 'MM/dd HH:mm'
    }
  },
  legend: { show: false }
}))

const providerChartOptions = computed<ApexOptions>(() => ({
  chart: {
    background: 'transparent',
    toolbar: { show: false },
    zoom: { enabled: false },
    stacked: true,
    fontFamily: '"SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
  },
  theme: {
    mode: isDark.value ? 'dark' : 'light'
  },
  plotOptions: {
    bar: {
      horizontal: false,
      borderRadius: 4,
      columnWidth: '58%'
    }
  },
  colors: providerChartColors,
  dataLabels: { enabled: false },
  grid: {
    borderColor: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26)
  },
  xaxis: {
    type: 'datetime',
    labels: {
      datetimeUTC: false,
      style: { colors: themePalette.value.mutedText }
    },
    axisBorder: { color: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26) },
    axisTicks: { color: hexToRgba(themePalette.value.border, isDark.value ? 0.4 : 0.26) }
  },
  yaxis: {
    labels: {
      formatter: (value) => formatCompactNumber(Number(value)),
      style: { colors: themePalette.value.mutedText }
    }
  },
  tooltip: {
    theme: isDark.value ? 'dark' : 'light',
    x: {
      format: 'MM/dd HH:mm'
    }
  },
  legend: {
    position: 'top',
    horizontalAlign: 'left',
    labels: {
      colors: themePalette.value.mutedText
    }
  }
}))

watch(selectedRange, async () => {
  try {
    await Promise.all([fetchBaseStats(), fetchProviderStats()])
  } catch (error) {
    console.error('Failed to refresh stats range:', error)
    errorMessage.value = t('errors.rangeFailed')
  }
})

onMounted(async () => {
  await refreshStats()
  refreshTimer = window.setInterval(() => {
    void refreshStats()
  }, 60_000)
  uptimeTimer = window.setInterval(() => {
    currentTimeMs.value = Date.now()
  }, 1_000)
})

onBeforeUnmount(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
  }
  if (uptimeTimer !== null) {
    window.clearInterval(uptimeTimer)
  }
  if (copyFeedbackTimer !== null) {
    window.clearTimeout(copyFeedbackTimer)
  }
})
</script>

<style scoped>
.stats-page {
  --stats-bg: rgb(var(--v-theme-background));
  --stats-surface: rgb(var(--v-theme-surface));
  --stats-card: #f5f6f7;
  --stats-text: rgb(var(--v-theme-on-surface));
  --stats-muted: rgba(var(--v-theme-on-surface), 0.68);
  --stats-subtle: rgba(var(--v-theme-on-surface), 0.56);
  --stats-border: rgba(var(--v-theme-on-surface), 0.1);
  --stats-border-strong: rgba(var(--v-theme-on-surface), 0.14);
  --stats-soft: rgba(var(--v-theme-primary), 0.08);
  --stats-soft-strong: rgba(var(--v-theme-primary), 0.14);
  min-height: 100%;
  background: var(--stats-bg);
}

.stats-page.is-dark {
  --stats-card: rgba(var(--v-theme-on-surface), 0.06);
  --stats-border: rgba(var(--v-theme-on-surface), 0.14);
  --stats-border-strong: rgba(var(--v-theme-on-surface), 0.18);
  --stats-soft: rgba(var(--v-theme-primary), 0.12);
  --stats-soft-strong: rgba(var(--v-theme-primary), 0.2);
}

.stats-shell {
  max-width: 1560px;
  margin: 0 auto;
  padding-left: 12px !important;
  padding-right: 12px !important;
  color: var(--stats-text);
  font-family: "SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.stats-page.is-dark .metric-label,
.stats-page.is-dark .section-subtitle,
.stats-page.is-dark .card-note,
.stats-page.is-dark .empty-state {
  color: var(--stats-muted);
}

.loading-wrap {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.panel-grid,
.token-grid {
  display: grid;
  grid-template-columns: 1.6fr 0.9fr;
  gap: 20px;
  margin-bottom: 20px;
  align-items: stretch;
}

.panel-grid > *,
.token-grid > * {
  min-width: 0;
  width: 100%;
}

.token-side-column {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 20px;
  min-width: 0;
  width: 100%;
}

.token-side-column > * {
  min-width: 0;
}

.stat-card {
  border: 0;
  border-radius: 16px;
  background: var(--stats-card);
}

.overview-card {
  isolation: isolate;
  overflow: hidden;
  padding: 20px 20px 18px;
  position: relative;
}

.card-icon {
  align-items: center;
  bottom: -20px;
  color: rgb(var(--v-theme-primary));
  display: inline-flex;
  height: 96px;
  justify-content: center;
  opacity: 0.09;
  pointer-events: none;
  position: absolute;
  right: -18px;
  width: 96px;
  z-index: -1;
}

.stats-page.is-dark .card-icon {
  color: rgb(var(--v-theme-primary));
  opacity: 0.14;
}

.overview-card .card-label,
.overview-card .card-value {
  position: relative;
  z-index: 1;
}

.overview-card .card-label {
  margin-top: 0;
}

.card-label {
  margin-top: 8px;
  color: var(--stats-muted);
  font-size: 13px;
  font-weight: 500;
}

.stats-page.is-dark .card-label,
.stats-page.is-dark .system-row,
.stats-page.is-dark .system-meta-item,
.stats-page.is-dark .provider-name {
  color: var(--stats-muted);
}

.card-value {
  margin-top: 8px;
  font-size: clamp(24px, 2vw, 34px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.card-note {
  margin-top: 8px;
  color: var(--stats-subtle);
  font-size: 12px;
  line-height: 1.5;
}

.chart-card,
.system-card,
.provider-list-card,
.token-total-card {
  padding: 22px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
}

.section-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.card-head-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 14px;
  flex-wrap: wrap;
}

.card-head.compact {
  margin-bottom: 14px;
}

.section-title {
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.section-subtitle {
  margin-top: 6px;
  color: var(--stats-muted);
  font-size: 13px;
}

.section-metric {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.metric-label {
  color: var(--stats-subtle);
  font-size: 12px;
}

.metric-value {
  font-size: 22px;
  font-weight: 650;
}

.system-metric + .system-metric {
  margin-top: 18px;
}

.system-row,
.system-meta-item,
.provider-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.system-row {
  margin-bottom: 10px;
  color: var(--stats-muted);
  font-size: 14px;
}

.system-meta-list {
  margin-top: 20px;
  border-top: 1px solid var(--stats-border);
  padding-top: 14px;
}

.stats-page.is-dark .system-meta-list {
  border-top-color: var(--stats-border-strong);
}

.system-meta-item {
  padding: 10px 0;
  color: var(--stats-muted);
  font-size: 14px;
}

.system-meta-item + .system-meta-item {
  border-top: 1px solid var(--stats-border);
}

.stats-page.is-dark .system-meta-item + .system-meta-item,
.stats-page.is-dark .provider-row {
  border-color: var(--stats-border-strong);
}

.token-section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 16px;
}

.range-switch {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border: 1px solid var(--stats-border);
  border-radius: 999px;
  background: var(--stats-surface);
}

.stats-page.is-dark .range-switch {
  border-color: var(--stats-border-strong);
  background: var(--stats-surface);
}

.range-chip {
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--stats-muted);
  padding: 9px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.range-chip.active {
  background: var(--stats-soft);
  color: rgb(var(--v-theme-primary));
}

.stats-page.is-dark .range-chip {
  color: var(--stats-muted);
}

.stats-page.is-dark .range-chip.active {
  background: var(--stats-soft-strong);
  color: rgb(var(--v-theme-primary));
}

.token-total-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 170px;
  width: 100%;
}

.provider-trend-card {
  min-height: 520px;
}

.provider-list-card {
  width: 100%;
}

.token-total-value {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  font-size: clamp(32px, 3vw, 44px);
  line-height: 1.02;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.token-meta-list {
  margin-top: 18px;
  border-top: 1px solid var(--stats-border);
  padding-top: 14px;
  display: grid;
  gap: 10px;
}

.token-meta-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: var(--stats-muted);
  font-size: 14px;
}

.provider-list {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.provider-list--scrollable {
  max-height: 296px;
  overflow-y: auto;
  padding-right: 6px;
}

.provider-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--stats-border);
  font-size: 14px;
  min-width: 0;
  width: 100%;
}

.provider-row > strong {
  flex: 0 0 auto;
}

.provider-row:last-child {
  border-bottom: 0;
}

.provider-name {
  color: var(--stats-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-identity {
  align-items: center;
  display: flex;
  gap: 9px;
  min-width: 0;
}

.provider-identity--umo {
  flex: 1 1 auto;
}

.platform-icon {
  flex: 0 0 auto;
  height: 20px;
  object-fit: contain;
  width: 20px;
}

.provider-name--alias {
  border-bottom: 1px dotted currentColor;
  cursor: help;
}

.umo-tooltip {
  overflow-wrap: anywhere;
}

.umo-copy-button,
.umo-conversation-link {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 6px;
  color: var(--stats-subtle);
  cursor: pointer;
  display: inline-flex;
  flex: 0 0 auto;
  height: 26px;
  justify-content: center;
  padding: 0;
  text-decoration: none;
  transition: background-color 0.18s ease, color 0.18s ease;
  width: 26px;
}

.umo-copy-button:hover,
.umo-conversation-link:hover {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: var(--stats-text);
}

.umo-copy-button--copied {
  color: rgb(var(--v-theme-success));
}

.token-total-card .card-label,
.token-total-card .card-note,
.token-side-column .section-subtitle {
  overflow-wrap: anywhere;
}

.empty-state {
  color: var(--stats-muted);
  font-size: 14px;
}

.empty-state.large {
  padding: 56px 0;
  text-align: center;
}

@media (max-width: 1400px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1080px) {
  .panel-grid,
  .token-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .token-section-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .section-toolbar {
    justify-content: flex-start;
    align-items: flex-start;
    flex-direction: column;
  }

  .card-head,
  .card-head-actions {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .stats-shell {
    padding-left: 4px !important;
    padding-right: 4px !important;
  }

  .chart-card,
  .system-card,
  .provider-list-card,
  .token-total-card {
    padding: 18px;
    border-radius: 14px;
  }
}
</style>

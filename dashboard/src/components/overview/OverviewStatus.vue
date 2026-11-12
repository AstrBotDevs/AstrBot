<template>
  <v-btn
    :color="loadFailed ? 'warning' : issues.length ? 'error' : loaded ? 'success' : 'secondary'"
    variant="tonal" rounded="pill" class="overview-status" aria-haspopup="dialog"
    @click="showDialog = true"
  >
    <span class="status-dot" aria-hidden="true" />
    <span aria-live="polite">{{ statusLabel }}</span>
  </v-btn>

  <v-dialog v-model="showDialog" max-width="720" scrollable>
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('health.title') }}</v-card-title>
      <v-card-text class="pa-6">
        <v-alert v-if="loadFailed" type="warning" variant="tonal" class="mb-4">
          {{ tm('health.loadFailed') }}
        </v-alert>
        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
        <template v-if="loaded">
          <p class="text-medium-emphasis mb-4">{{ tm('health.description') }}</p>
          <v-alert v-if="!issues.length" type="success" variant="tonal">{{ tm('health.noIssues') }}</v-alert>
          <article v-for="bot in issues" :key="bot.id" class="bot-issue">
            <div class="d-flex align-center flex-wrap ga-2 mb-2">
              <v-icon color="error" size="20">mdi-alert-circle-outline</v-icon>
              <strong>{{ bot.display_name || bot.type }} · {{ bot.id }}</strong>
              <v-chip size="small" color="error" variant="tonal">
                {{ tm('health.errorCount', { count: bot.error_count || 1 }) }}
              </v-chip>
            </div>
            <p class="issue-message">{{ bot.last_error?.message || tm('health.noDetails') }}</p>
            <p v-if="bot.last_error?.timestamp" class="text-caption text-medium-emphasis mt-2">
              {{ new Date(bot.last_error.timestamp).toLocaleString(locale) }}
            </p>
            <details v-if="bot.last_error?.traceback" class="mt-3">
              <summary>{{ tm('health.traceback') }}</summary>
              <pre class="issue-traceback">{{ bot.last_error.traceback }}</pre>
            </details>
          </article>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4 flex-wrap">
        <v-btn variant="text" color="primary" to="/platforms">{{ tm('health.manageBots') }}</v-btn>
        <v-spacer />
        <v-btn variant="text" :loading="loading" @click="refresh">{{ tm('health.refresh') }}</v-btn>
        <v-btn variant="tonal" color="primary" @click="showDialog = false">{{ tm('onboard.step3HelpClose') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { botApi } from '@/api/v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/welcome');
const { locale } = useI18n();
type BotStatus = {
  id: string;
  type?: string;
  display_name?: string;
  status: string;
  error_count: number;
  last_error?: { message: string; timestamp: string; traceback?: string } | null;
};
const platforms = ref<BotStatus[]>([]);
const loaded = ref(false);
const loading = ref(false);
const loadFailed = ref(false);
const showDialog = ref(false);
let refreshTimer: ReturnType<typeof setInterval>;
const issues = computed(() => platforms.value.filter(bot => bot.status === 'error' || bot.error_count > 0));
const statusLabel = computed(() => {
  if (loadFailed.value) return tm('health.unavailable');
  if (!loaded.value) return tm('health.checking');
  return issues.value.length ? tm('health.issues', { count: issues.value.length }) : tm('health.healthy');
});

async function refresh() {
  if (loading.value) return;
  loading.value = true;
  try {
    const response = await botApi.stats();
    if (response.data.status !== 'ok') throw new Error(response.data.message || 'Failed to load bot status');
    platforms.value = (response.data.data.platforms || []) as BotStatus[];
    loaded.value = true;
    loadFailed.value = false;
  } catch (error) {
    loadFailed.value = true;
    console.error('Failed to load overview bot status:', error);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refresh();
  refreshTimer = setInterval(() => { if (!document.hidden) void refresh(); }, 30000);
});
onUnmounted(() => clearInterval(refreshTimer));
</script>

<style scoped>
.overview-status { flex-shrink: 0; height: 32px; padding-inline: 14px; font-size: 13px; letter-spacing: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; margin-inline-end: 9px; }
.bot-issue { padding: 18px; border: 1px solid rgba(var(--v-theme-error), .18); border-radius: 16px; margin-top: 12px; }
.issue-message, .issue-traceback { white-space: pre-wrap; overflow-wrap: anywhere; }
.issue-traceback { margin-top: 12px; padding: 12px; background: rgba(var(--v-theme-on-surface), .04); border-radius: 8px; font-size: 12px; }
summary { cursor: pointer; color: rgb(var(--v-theme-primary)); }
</style>

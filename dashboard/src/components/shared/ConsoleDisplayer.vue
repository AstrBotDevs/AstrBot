<template>
  <div ref="consoleWrapper" class="console-displayer-wrapper">
    <div v-if="props.showLevelBtns" class="filter-controls mb-2">
      <v-chip-group v-model="selectedLevels" column multiple>
        <v-chip
          v-for="level in logLevels"
          :key="level"
          :color="getLevelColor(level)"
          filter
          variant="flat"
          size="small"
          :text-color="
            level === 'DEBUG' || level === 'INFO' ? 'black' : 'white'
          "
          class="font-weight-medium"
        >
          {{ level }}
        </v-chip>
      </v-chip-group>
      <v-spacer></v-spacer>
      <v-btn
        :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
        variant="text"
        density="compact"
        class="me-4 fullscreen-btn"
        @click="toggleFullscreen"
      ></v-btn>
    </div>

    <div ref="termElement" class="console-term"></div>
  </div>
</template>

<script setup lang="ts">
import { logApi } from '@/api/v1';
import { useCommonStore } from '@/stores/common';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

interface ConsoleLogEntry {
  time: number;
  data: string;
  level: string;
  [key: string]: unknown;
}

type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

const props = withDefaults(
  defineProps<{
    showLevelBtns?: boolean;
    autoScroll?: boolean;
    hideUserChat?: boolean;
  }>(),
  {
    showLevelBtns: true,
    autoScroll: true,
    hideUserChat: true,
  },
);

const commonStore = useCommonStore();
const consoleWrapper = ref<HTMLElement | null>(null);
const termElement = ref<HTMLDivElement | null>(null);
const isFullscreen = ref(false);
const selectedLevels = ref<number[]>([0, 1, 2, 3, 4]);
const localLogCache = ref<ConsoleLogEntry[]>([]);
const eventSource = ref<EventSourcePolyfill | null>(null);
const retryTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);
const retryAttempts = ref(0);
const lastEventId = ref<string | null>(null);

const logColorAnsiMap: Record<string, string> = {
  '\u001b[1;34m': 'color: #6cb6d9; font-weight: bold;',
  '\u001b[1;36m': 'color: #72c4cc; font-weight: bold;',
  '\u001b[1;33m': 'color: #d4b95e; font-weight: bold;',
  '\u001b[31m': 'color: #d46a6a;',
  '\u001b[1;31m': 'color: #e06060; font-weight: bold;',
  '\u001b[0m': 'color: inherit; font-weight: normal;',
  '\u001b[32m': 'color: #6cc070;',
  default: 'color: #c8c8c8;',
};

const logLevels: LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
const levelColors: Record<LogLevel, string> = {
  DEBUG: 'grey',
  INFO: 'blue-lighten-3',
  WARNING: 'amber',
  ERROR: 'red',
  CRITICAL: 'purple',
};

const maxRetryAttempts = 10;
const baseRetryDelay = 1000;

function closeEventSource(): void {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
}

function clearRetryTimer(): void {
  if (retryTimer.value !== null) {
    clearTimeout(retryTimer.value);
    retryTimer.value = null;
  }
}

function normalizeLogEntry(raw: unknown): ConsoleLogEntry | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const candidate = raw as Record<string, unknown>;
  const data = candidate.data;
  const level = candidate.level;
  const time = candidate.time;
  return {
    ...candidate,
    data: typeof data === 'string' ? data : String(data ?? ''),
    level: typeof level === 'string' ? level : 'INFO',
    time: typeof time === 'number' ? time : Number(time ?? Date.now()),
  };
}

function getLevelColor(level: LogLevel): string {
  return levelColors[level] || 'grey';
}

function isLevelSelected(level: string): boolean {
  return selectedLevels.value.some((index) => logLevels[index] === level);
}

function isVisible(log: ConsoleLogEntry): boolean {
  return (
    isLevelSelected(log.level) &&
    !(props.hideUserChat && log.category === 'user_chat')
  );
}

function appendLogContent(element: HTMLPreElement, log: string): void {
  const levelMatch = log.match(
    /\[(DEBG|INFO|WARN|ERRO|CRIT|DEBUG|WARNING|ERROR|CRITICAL)\]/,
  );
  if (levelMatch?.index === undefined) {
    element.innerText = log;
    return;
  }

  const levelStart = levelMatch.index;
  const levelEnd = levelStart + levelMatch[0].length;
  const prefix = log.slice(0, levelStart).trimEnd();
  const message = log.slice(levelEnd).trimStart();

  const prefixSpan = document.createElement('span');
  prefixSpan.className = 'console-log-prefix';
  prefixSpan.innerText = prefix;

  const levelSpan = document.createElement('span');
  levelSpan.className = 'console-log-level';
  levelSpan.innerText = levelMatch[0];

  const messageSpan = document.createElement('span');
  messageSpan.className = 'console-log-message';
  messageSpan.innerText = message;

  element.classList.add('console-log-line--structured');
  element.appendChild(prefixSpan);
  element.appendChild(levelSpan);
  element.appendChild(messageSpan);
}

function printLog(log: string): void {
  const target = termElement.value;
  if (!target) {
    return;
  }

  const span = document.createElement('pre');
  let normalizedLog = log;
  let style = logColorAnsiMap.default;
  for (const [ansiPrefix, ansiStyle] of Object.entries(logColorAnsiMap)) {
    if (ansiPrefix !== 'default' && normalizedLog.startsWith(ansiPrefix)) {
      style = ansiStyle;
      normalizedLog = normalizedLog
        .replace(ansiPrefix, '')
        .replace('\u001b[0m', '');
      break;
    }
  }

  span.style.cssText = style;
  span.classList.add('console-log-line', 'fade-in');
  appendLogContent(span, normalizedLog);
  target.appendChild(span);
  if (props.autoScroll) {
    target.scrollTop = target.scrollHeight;
  }
}

function refreshDisplay(): void {
  const target = termElement.value;
  if (!target) {
    return;
  }
  target.innerHTML = '';
  for (const logItem of localLogCache.value) {
    if (isVisible(logItem)) {
      printLog(logItem.data);
    }
  }
}

function processNewLogs(newLogs: unknown[]): void {
  if (newLogs.length === 0) {
    return;
  }

  let hasUpdate = false;

  for (const rawLog of newLogs) {
    const log = normalizeLogEntry(rawLog);
    if (!log) {
      continue;
    }
    const exists = localLogCache.value.some(
      (existing) =>
        existing.time === log.time &&
        existing.data === log.data &&
        existing.level === log.level,
    );

    if (!exists) {
      localLogCache.value.push(log);
      hasUpdate = true;

      if (isVisible(log)) {
        printLog(log.data);
      }
    }
  }

  if (!hasUpdate) {
    return;
  }

  localLogCache.value.sort((a, b) => a.time - b.time);

  const maxSize = commonStore.log_cache_max_len || 200;
  if (localLogCache.value.length > maxSize) {
    localLogCache.value.splice(0, localLogCache.value.length - maxSize);
  }
}

async function fetchLogHistory(): Promise<void> {
  try {
    const res = await logApi.history();
    const logs = Array.isArray(res.data.data.logs) ? res.data.data.logs : [];
    if (logs.length > 0) {
      processNewLogs(logs);
    }
  } catch (error) {
    console.error('Failed to fetch log history:', error);
  }
}

function connectSSE(): void {
  closeEventSource();

  console.log(`正在连接日志流... (尝试次数: ${retryAttempts.value})`);

  const token = localStorage.getItem('token');

  eventSource.value = new EventSourcePolyfill(logApi.liveUrl(), {
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
    },
    heartbeatTimeout: 300000,
    withCredentials: true,
  });

  eventSource.value.onopen = () => {
    console.log('日志流连接成功！');
    retryAttempts.value = 0;

    if (!lastEventId.value) {
      void fetchLogHistory();
    }
  };

  eventSource.value.onmessage = (event: MessageEvent<string>) => {
    try {
      if (event.lastEventId) {
        lastEventId.value = event.lastEventId;
      }

      processNewLogs([JSON.parse(event.data)]);
    } catch (error) {
      console.error('解析日志失败:', error);
    }
  };

  eventSource.value.onerror = (error: unknown) => {
    const eventError = error as { status?: number };
    if (eventError.status === 401) {
      console.error('鉴权失败 (401)，可能是 Token 过期了。');
    } else {
      console.warn('日志流连接错误:', error);
    }

    closeEventSource();

    if (retryAttempts.value >= maxRetryAttempts) {
      console.error('❌ 已达到最大重试次数，停止重连。请刷新页面重试。');
      return;
    }

    const delay = Math.min(
      baseRetryDelay * Math.pow(2, retryAttempts.value),
      30000,
    );

    console.log(`⏳ ${delay}ms 后尝试第 ${retryAttempts.value + 1} 次重连...`);

    clearRetryTimer();
    retryTimer.value = window.setTimeout(async () => {
      retryAttempts.value += 1;

      if (!lastEventId.value) {
        await fetchLogHistory();
      }

      connectSSE();
    }, delay);
  };
}

function toggleFullscreen(): void {
  const container = consoleWrapper.value;
  if (!container) {
    return;
  }
  if (!document.fullscreenElement) {
    container.requestFullscreen().catch((error: unknown) => {
      const candidate = error as { message?: string };
      console.error(
        `Error attempting to enable full-screen mode: ${candidate.message || error}`,
      );
    });
    return;
  }
  void document.exitFullscreen();
}

function handleFullscreenChange(): void {
  isFullscreen.value = Boolean(document.fullscreenElement);
}

watch(
  selectedLevels,
  () => {
    refreshDisplay();
  },
  { deep: true },
);

onMounted(async () => {
  await fetchLogHistory();
  connectSSE();
  document.addEventListener('fullscreenchange', handleFullscreenChange);
});

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  closeEventSource();
  clearRetryTimer();
  retryAttempts.value = 0;
});
</script>

<style scoped>
.console-displayer-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.console-displayer-wrapper:fullscreen {
  background-color: #1e1e1e;
  padding: 20px;
}

.filter-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.console-term {
  background-color: #1e1e1e;
  border-radius: 8px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  padding: 16px;
}

.fullscreen-btn {
  color: rgba(255, 255, 255, 0.7) !important; /* 提高在深色背景下的对比度 */
}

:deep(.console-log-line) {
  display: block;
  margin: 0 0 2px;
  font-family: var(--astrbot-font-mono);
  font-size: 12px;
  white-space: pre-wrap;
}

:deep(.console-log-line--structured) {
  display: grid;
  grid-template-columns: max-content max-content minmax(0, 1fr);
  column-gap: 8px;
  align-items: start;
  white-space: normal;
}

:deep(.console-log-prefix),
:deep(.console-log-level),
:deep(.console-log-message) {
  min-width: 0;
  white-space: pre-wrap;
}

:deep(.console-log-level) {
  font-variant-numeric: tabular-nums;
}

:deep(.console-log-message) {
  overflow-wrap: anywhere;
}

@media (max-width: 768px) {
  :deep(.console-log-line--structured) {
    grid-template-columns: 1fr;
  }
  :deep(.console-log-prefix:empty),
  :deep(.console-log-level:empty) {
    display: none;
  }
}

:deep(.fade-in) {
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}
</style>

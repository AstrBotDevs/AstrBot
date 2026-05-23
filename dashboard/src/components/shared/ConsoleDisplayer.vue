<template>
  <div class="console-displayer-wrapper" id="console-wrapper">
    <div class="filter-controls mb-2" v-if="showLevelBtns">
      <v-chip-group v-model="selectedLevels" column multiple>
        <v-chip v-for="level in logLevels" :key="level" :color="getLevelColor(level)" filter variant="flat" size="small"
          :text-color="level === 'DEBUG' || level === 'INFO' ? 'black' : 'white'" class="font-weight-medium">
          {{ level }}
        </v-chip>
      </v-chip-group>
      <v-spacer></v-spacer>
      <v-btn
        :icon="flushMode ? 'mdi-format-columns' : 'mdi-format-align-left'"
        variant="text"
        density="compact"
        class="fullscreen-btn"
        @click="toggleFlushMode"
      ></v-btn>
      <v-btn
        :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
        variant="text"
        density="compact"
        class="me-4 fullscreen-btn"
        @click="toggleFullscreen"
      ></v-btn>
    </div>

    <div id="term" class="console-term" :class="{ 'console-term--flush': flushMode }">
    </div>
  </div>
</template>

<script>
import { useCustomizerStore } from '@/stores/customizer';

const lightColorAnsiMap = {
  '\u001b[1;34m': 'color: #39C5BB; font-weight: bold;',
  '\u001b[1;36m': 'color: #00FFFF; font-weight: bold;',
  '\u001b[1;33m': 'color: #FFFF00; font-weight: bold;',
  '\u001b[31m': 'color: #FF0000;',
  '\u001b[1;31m': 'color: #FF0000; font-weight: bold;',
  '\u001b[0m': 'color: inherit; font-weight: normal;',
  '\u001b[32m': 'color: #00FF00;',
  'default': 'color: #FFFFFF;'
};

const darkColorAnsiMap = {
  '\u001b[1;34m': 'color: #6cb6d9; font-weight: bold;',
  '\u001b[1;36m': 'color: #72c4cc; font-weight: bold;',
  '\u001b[1;33m': 'color: #d4b95e; font-weight: bold;',
  '\u001b[31m': 'color: #d46a6a;',
  '\u001b[1;31m': 'color: #e06060; font-weight: bold;',
  '\u001b[0m': 'color: inherit; font-weight: normal;',
  '\u001b[32m': 'color: #6cc070;',
  'default': 'color: #c8c8c8;'
};

export default {
  name: 'ConsoleDisplayer',
  data() {
    return {
      autoScroll: true,
      isFullscreen: false,
      flushMode: localStorage.getItem('console_flush_mode') === 'true',
      logColorAnsiMap: {
        '\u001b[1;34m': 'color: #6cb6d9; font-weight: bold;',
        '\u001b[1;36m': 'color: #72c4cc; font-weight: bold;',
        '\u001b[1;33m': 'color: #d4b95e; font-weight: bold;',
        '\u001b[31m': 'color: #d46a6a;',
        '\u001b[1;31m': 'color: #e06060; font-weight: bold;',
        '\u001b[0m': 'color: inherit; font-weight: normal;',
        '\u001b[32m': 'color: #6cc070;',
        'default': 'color: #c8c8c8;'
      },
      logLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      selectedLevels: [0, 1, 2, 3, 4],
      levelColors: {
        'DEBUG': 'grey',
        'INFO': 'blue-lighten-3',
        'WARNING': 'amber',
        'ERROR': 'red',
        'CRITICAL': 'purple'
      },
      localLogCache: [],
      eventSource: null,
      retryTimer: null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null,
    }
  },
  computed: {
    commonStore() {
      return useCommonStore();
    },
    logColorAnsiMap() {
      const customizerStore = useCustomizerStore();
      return customizerStore.uiTheme === 'PurpleThemeDark' ? darkColorAnsiMap : lightColorAnsiMap;
    },
  },
  props: {
    historyNum: {
      type: String,
      default: '-1'
    },
    showLevelBtns: {
      type: Boolean,
      default: true
    },
    enableAdvancedFilters: {
      type: Boolean,
      default: false
    },
    storageKey: {
      type: String,
      default: ''
    },
    autoScroll: {
      type: Boolean,
      default: true
    }
  },
  setup() {
    const commonStore = useCommonStore();
    const { tm } = useModuleI18n('features/console');
    return { commonStore, tm };
  },
  data() {
    return {
      logColorAnsiMap: {
        '\u001b[1;34m': 'color: #39C5BB; font-weight: bold;',
        '\u001b[1;36m': 'color: #00FFFF; font-weight: bold;',
        '\u001b[1;33m': 'color: #FFFF00; font-weight: bold;',
        '\u001b[31m': 'color: #FF0000;',
        '\u001b[1;31m': 'color: #FF0000; font-weight: bold;',
        '\u001b[0m': 'color: inherit; font-weight: normal;',
        '\u001b[32m': 'color: #00FF00;',
        default: 'color: #FFFFFF;'
      },
      logLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      selectedLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      selectedTags: [],
      tagSearch: '',
      keyword: '',
      levelColors: {
        DEBUG: 'grey',
        INFO: 'blue-lighten-3',
        WARNING: 'amber',
        ERROR: 'red',
        CRITICAL: 'purple'
      },
      availableTags: [],
      localLogCache: [],
      eventSource: null,
      retryTimer: null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null,
      knownLogIds: new Set(),
      filterSyncTimer: null,
      reloadSequence: 0,
      suspendFilterSync: false
    };
  },
  computed: {
    tagOptions() {
      return [...new Set([...this.availableTags, ...this.selectedTags].filter(Boolean))].sort();
    },
    selectedTagPreview() {
      if (this.tagSearch.trim() || this.selectedTags.length === 0) {
        return '';
      }

      const [firstTag, ...remainingTags] = this.selectedTags;
      return remainingTags.length > 0
        ? `${firstTag} +${remainingTags.length}`
        : firstTag;
    },
    hasActiveFilters() {
      return (
        this.selectedLevels.length !== this.logLevels.length ||
        this.selectedTags.length > 0 ||
        this.keyword.trim().length > 0
      );
    },
    emptyStateText() {
      if (this.hasActiveFilters) {
        return this.tm('filters.emptyFiltered');
      }
      return this.tm('filters.emptyIdle');
    }
  },
  watch: {
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true
    },
    flushMode(val) {
      localStorage.setItem('console_flush_mode', val);
    }
  },
  async mounted() {
    this.restorePersistedState();
    await this.reloadLogSource();
  },
  beforeUnmount() {
    this.teardownEventSource();
    if (this.filterSyncTimer) {
      clearTimeout(this.filterSyncTimer);
      this.filterSyncTimer = null;
    }
    this.retryAttempts = 0;
  },
  methods: {
    getStorageKey() {
      if (!this.storageKey) {
        return '';
      }
      return `console-displayer:${this.storageKey}`;
    },

    restorePersistedState() {
      const storageKey = this.getStorageKey();
      if (!storageKey || typeof window === 'undefined' || !window.localStorage) {
        return;
      }

      try {
        this.suspendFilterSync = true;
        const raw = localStorage.getItem(storageKey);
        if (!raw) {
          return;
        }

        const parsed = JSON.parse(raw);
        const selectedLevels = Array.isArray(parsed.selectedLevels)
          ? parsed.selectedLevels.filter((level) => this.logLevels.includes(level))
          : [];
        const selectedTags = Array.isArray(parsed.selectedTags)
          ? parsed.selectedTags.filter((tag) => typeof tag === 'string' && tag.trim())
          : [];

        this.selectedLevels = selectedLevels.length > 0 ? selectedLevels : [...this.logLevels];
        this.selectedTags = selectedTags;
        this.keyword = typeof parsed.keyword === 'string' ? parsed.keyword : '';
      } catch (error) {
        console.warn('Failed to restore console filter state:', error);
      } finally {
        this.suspendFilterSync = false;
      }
    },

    persistState() {
      const storageKey = this.getStorageKey();
      if (!storageKey || typeof window === 'undefined' || !window.localStorage) {
        return;
      }

      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            selectedLevels: this.selectedLevels,
            selectedTags: this.selectedTags,
            keyword: this.keyword
          })
        );
      } catch (error) {
        console.warn('Failed to persist console filter state:', error);
      }
    },

    getLogQueryParams() {
      return this.buildLogQueryParams();
    },

    buildLogQueryParams({
      includeTag = true,
      includeLimit = true
    } = {}) {
      const params = {};
      const historyLimit = Number.parseInt(this.historyNum, 10);

      if (includeLimit && !Number.isNaN(historyLimit) && historyLimit > 0) {
        params.limit = historyLimit;
      }

      if (this.selectedLevels.length !== this.logLevels.length) {
        params.levels = this.selectedLevels.length > 0 ? this.selectedLevels.join(',') : '__none__';
      }

      if (includeTag && this.selectedTags.length > 0) {
        params.tag = this.selectedTags.join(',');
      }

      const keyword = this.keyword.trim();
      if (keyword) {
        params.keyword = keyword;
      }

      return params;
    },

    buildLogStreamUrl() {
      const query = new URLSearchParams();
      const params = this.getLogQueryParams();

      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          query.set(key, String(value));
        }
      });

      return query.toString() ? `/api/live-log?${query.toString()}` : '/api/live-log';
    },

    teardownEventSource() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      console.log(`正在连接日志流... (尝试次数: ${this.retryAttempts})`);

      const token = localStorage.getItem('token');

    connectSSE() {
      this.teardownEventSource();

      const token = localStorage.getItem('token');
      const options = {
        headers: {
          Authorization: token ? `Bearer ${token}` : ''
        },
        heartbeatTimeout: 300000,
        withCredentials: true
      });

      this.eventSource.onopen = () => {
        this.retryAttempts = 0;
      };

      this.eventSource.onmessage = (event) => {
        try {
          if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
          }

          const payload = JSON.parse(event.data);
          this.appendLogs([payload]);
        } catch (error) {
          console.error('Failed to parse log stream payload:', error);
        }
      };

      this.eventSource.onerror = (error) => {
        if (error.status === 401) {
          console.error('Log stream authentication failed (401).');
        } else {
          console.warn('Log stream connection failed.', error);
        }

        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.retryAttempts >= this.maxRetryAttempts) {
            console.error('❌ 已达到最大重试次数，停止重连。请刷新页面重试。');
            return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000
        );

        console.log(`⏳ ${delay}ms 后尝试第 ${this.retryAttempts + 1} 次重连...`);

        if (this.retryTimer) {
          clearTimeout(this.retryTimer);
          this.retryTimer = null;
        }

        const sequence = this.reloadSequence;
        this.retryTimer = setTimeout(async () => {
          this.retryAttempts++;

          if (!this.lastEventId) {
             await this.fetchLogHistory();
          }

          this.connectSSE();
        }, delay);
      };
    },

    normalizeLogEntry(log) {
      if (!log || (log.type && log.type !== 'log')) {
        return null;
      }

      const rendered = typeof log.rendered === 'string'
        ? log.rendered
        : (typeof log.data === 'string' ? log.data : '');
      const message = typeof log.message === 'string' ? log.message : stripAnsi(rendered);
      const tag = typeof log.tag === 'string' && log.tag.trim()
        ? log.tag
        : 'core:astrbot';
      const sourceFile = typeof log.source_file === 'string' ? log.source_file : 'unknown';
      const uuid = log.uuid || [
        log.time,
        log.level,
        tag,
        log.logger_name || '',
        sourceFile,
        log.source_line || '',
        rendered || message
      ].join('|');

      return {
        ...log,
        type: 'log',
        uuid,
        rendered,
        data: rendered,
        message,
        tag,
        displayText: stripAnsi(rendered || message)
      };
    },

        const exists = this.localLogCache.some(existing =>
          existing.time === log.time &&
          existing.data === log.data &&
          existing.level === log.level
        );

        if (!exists) {
            this.localLogCache.push(log);
            hasUpdate = true;

            if (this.isLevelSelected(log.level)) {
              this.printLog(log.data);
            }
        }
      });

      if (hasUpdate) {
        this.localLogCache.sort((a, b) => a.time - b.time);

        const maxSize = this.commonStore.log_cache_max_len || 200;
        if (this.localLogCache.length > maxSize) {
           this.localLogCache.splice(0, this.localLogCache.length - maxSize);
        }

        knownLogIds.add(entry.uuid);
        normalizedLogs.push(entry);
      });

      normalizedLogs.sort((left, right) => left.time - right.time);

      const maxSize = this.commonStore.log_cache_max_len || 200;
      if (normalizedLogs.length > maxSize) {
        normalizedLogs.splice(0, normalizedLogs.length - maxSize);
      }

      this.localLogCache = normalizedLogs;
      this.knownLogIds = new Set(normalizedLogs.map((entry) => entry.uuid));
      this.updateAvailableTags(normalizedLogs);
      this.setLastEventIdFromLogs(normalizedLogs);
      this.scheduleAutoScroll();
    },

    appendLogs(newLogs) {
      if (!newLogs || newLogs.length === 0) {
        return;
      }

      const appendedLogs = [];
      let shouldSort = false;
      let lastTime = this.localLogCache.length > 0
        ? Number(this.localLogCache[this.localLogCache.length - 1].time || 0)
        : Number.NEGATIVE_INFINITY;

      newLogs.forEach((log) => {
        const entry = this.normalizeLogEntry(log);
        if (!entry || this.knownLogIds.has(entry.uuid)) {
          return;
        }

        const entryTime = Number(entry.time || 0);
        if (entryTime < lastTime) {
          shouldSort = true;
        } else {
          lastTime = entryTime;
        }

        this.knownLogIds.add(entry.uuid);
        appendedLogs.push(entry);
      });

      if (appendedLogs.length === 0) {
        return;
      }

      const nextCache = [...this.localLogCache, ...appendedLogs];
      if (shouldSort) {
        nextCache.sort((left, right) => left.time - right.time);
      }

      const maxSize = this.commonStore.log_cache_max_len || 200;
      let trimmed = false;
      if (nextCache.length > maxSize) {
        nextCache.splice(0, nextCache.length - maxSize);
        trimmed = true;
      }

      this.localLogCache = nextCache;
      if (trimmed) {
        this.rebuildKnownLogIds();
      }
      this.updateAvailableTags(appendedLogs);
      this.setLastEventIdFromLogs(nextCache);
      this.scheduleAutoScroll();
    },

    async fetchLogHistory(sequence = this.reloadSequence) {
      try {
        const response = await axios.get('/api/log-history', {
          params: this.getLogQueryParams()
        });
        if (sequence !== this.reloadSequence) {
          return;
        }

        const logs = response.data?.data?.logs || [];
        this.replaceLogHistory(logs);
      } catch (error) {
        console.error('Failed to fetch log history:', error);
      }
    },

    async fetchTagOptions(sequence = this.reloadSequence) {
      try {
        const response = await axios.get('/api/log-history', {
          params: this.buildLogQueryParams({
            includeTag: false,
            includeLimit: false
          })
        });
        if (sequence !== this.reloadSequence) {
          return;
        }

        const logs = response.data?.data?.logs || [];
        this.updateAvailableTags(logs);
      } catch (error) {
        console.error('Failed to fetch tag options:', error);
      }
    },

    getLevelColor(level) {
      return this.levelColors[level] || 'grey';
    },

    getLineStyle(entry) {
      const leadingAnsi = entry.rendered.match(LEADING_ANSI_PATTERN)?.[1];
      if (leadingAnsi && this.logColorAnsiMap[leadingAnsi]) {
        return this.logColorAnsiMap[leadingAnsi];
      }

    refreshDisplay() {
      const termElement = document.getElementById('term');
      if (termElement) {
        termElement.innerHTML = '';

        if (this.localLogCache && this.localLogCache.length > 0) {
          this.localLogCache.forEach(logItem => {
            if (this.isLevelSelected(logItem.level)) {
              this.printLog(logItem.data);
            }
          });
        }
      }
    },

    toggleAutoScroll() {
      this.autoScroll = !this.autoScroll;
    },

    toggleFlushMode() {
      this.flushMode = !this.flushMode;
    },

    toggleFullscreen() {
      const container = document.getElementById('console-wrapper');
      if (!document.fullscreenElement) {
        container.requestFullscreen().catch(err => {
          console.error(`Error attempting to enable full-screen mode: ${err.message}`);
        });
      } else {
        document.exitFullscreen();
      }
    },

    handleFullscreenChange() {
      this.isFullscreen = !!document.fullscreenElement;
    },

    appendLogContent(element, log) {
      const levelMatch = log.match(/\[(DBUG|INFO|WARN|ERRO|CRIT|DEBUG|WARNING|ERROR|CRITICAL)\]/);
      if (!levelMatch) {
        element.innerText = `${log}`;
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
    },

    printLog(log) {
      let ele = document.getElementById('term')
      if (!ele) {
        return;
      }

      let span = document.createElement('pre')
      let style = this.logColorAnsiMap['default']
      for (let key in this.logColorAnsiMap) {
        if (log.startsWith(key)) {
          style = this.logColorAnsiMap[key]
          log = log.replace(key, '').replace('\u001b[0m', '')
          break
        }
        element.scrollTop = element.scrollHeight;
      });
    }
  }
};
</script>

<style scoped>
.console-displayer {
  height: 100%;
}

.console-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

.filter-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: 20px;
}

.advanced-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.filter-input {
  min-width: 220px;
  max-width: 360px;
}

:deep(.filter-input-tags .v-field__input) {
  min-height: 40px;
  max-height: 40px;
  overflow: hidden;
  flex-wrap: nowrap;
  align-items: center;
}

:deep(.filter-input-tags .v-field__input input) {
  min-width: 36px;
}

.tag-selection-summary {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.88);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.tag-filter-menu .v-overlay__content) {
  border-radius: 12px;
}

:deep(.tag-filter-menu .v-list) {
  padding-top: 0;
}

.filter-summary {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 12px;
}

.console-terminal {
  background-color: #1e1e1e;
  border-radius: 8px;
  height: 100%;
  overflow-x: auto;
  overflow-y: auto;
  padding: 16px;
}

.fullscreen-btn {
    color: rgba(255, 255, 255, 0.7) !important;
}

:deep(.console-log-line) {
  display: block;
  margin: 0 0 2px;
  font-family:
    SFMono-Regular, Menlo, Monaco, Consolas, var(--astrbot-font-cjk-mono),
    monospace;
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

.console-term--flush :deep(.console-log-line--structured) {
  display: block;
  white-space: pre-wrap;
}

.console-term--flush :deep(.console-log-prefix),
.console-term--flush :deep(.console-log-level),
.console-term--flush :deep(.console-log-message) {
  display: inline;
}

.console-term--flush :deep(.console-log-prefix),
.console-term--flush :deep(.console-log-level) {
  margin-right: 4px;
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
  .console-term {
    padding: 12px;
  }

  :deep(.console-log-line--structured) {
    min-width: max-content;
  }

  :deep(.console-log-message) {
    overflow-wrap: normal;
    word-break: normal;
    white-space: pre;
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

@media (max-width: 900px) {
  .filter-input {
    min-width: 100%;
    max-width: 100%;
  }

  .advanced-filters {
    align-items: stretch;
  }
}
</style>

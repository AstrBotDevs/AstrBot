<template>
  <div class="console-displayer">
    <div v-if="showLevelBtns || enableAdvancedFilters" class="console-toolbar">
      <div v-if="showLevelBtns" class="filter-controls">
        <v-chip-group v-model="selectedLevels" column multiple>
          <v-chip
            v-for="level in logLevels"
            :key="level"
            :value="level"
            :color="getLevelColor(level)"
            filter
            variant="flat"
            size="small"
            :text-color="level === 'DEBUG' || level === 'INFO' ? 'black' : 'white'"
            class="font-weight-medium"
          >
            {{ level }}
          </v-chip>
        </v-chip-group>
      </div>

      <div v-if="enableAdvancedFilters" class="advanced-filters">
        <v-text-field
          v-model="keyword"
          label="Search"
          placeholder="Search message, tag, plugin, platform, or UMO"
          density="compact"
          hide-details
          clearable
          variant="outlined"
          class="filter-input"
        />
        <v-autocomplete
          v-model="selectedTags"
          :items="tagOptions"
          label="Tag"
          placeholder="Filter by logcat tag"
          density="compact"
          hide-details
          clearable
          chips
          closable-chips
          multiple
          variant="outlined"
          class="filter-input"
        />
        <v-btn variant="text" size="small" @click="clearFilters">
          Clear Filters
        </v-btn>
        <span class="filter-summary">
          {{ `${filteredLogs.length} / ${localLogCache.length} logs` }}
        </span>
      </div>
    </div>

    <div ref="term" class="console-terminal">
      <pre
        v-for="entry in filteredLogs"
        :key="entry.uuid"
        class="console-log-line fade-in"
        :style="getLineStyle(entry)"
      >{{ entry.displayText }}</pre>
      <div v-if="filteredLogs.length === 0" class="console-empty">
        {{ emptyStateText }}
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import { EventSourcePolyfill } from 'event-source-polyfill';

import { useCommonStore } from '@/stores/common';

const ANSI_PATTERN = /\u001b\[[0-9;]*m/g;
const LEADING_ANSI_PATTERN = /^(\u001b\[[0-9;]*m)/;

function stripAnsi(value) {
  return String(value || '').replace(ANSI_PATTERN, '');
}

export default {
  name: 'ConsoleDisplayer',
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
    }
  },
  setup() {
    const commonStore = useCommonStore();
    return { commonStore };
  },
  data() {
    return {
      autoScroll: true,
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
      keyword: '',
      levelColors: {
        DEBUG: 'grey',
        INFO: 'blue-lighten-3',
        WARNING: 'amber',
        ERROR: 'red',
        CRITICAL: 'purple'
      },
      localLogCache: [],
      eventSource: null,
      retryTimer: null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null
    };
  },
  computed: {
    filteredLogs() {
      const keyword = this.keyword.trim().toLowerCase();
      const selectedTags = new Set(this.selectedTags);

      return this.localLogCache.filter((entry) => {
        if (!this.selectedLevels.includes(entry.level)) {
          return false;
        }

        if (selectedTags.size > 0 && !selectedTags.has(entry.tag)) {
          return false;
        }

        if (keyword && !entry.searchIndex.includes(keyword)) {
          return false;
        }

        return true;
      });
    },
    tagOptions() {
      return [...new Set(this.localLogCache.map((entry) => entry.tag).filter(Boolean))].sort();
    },
    hasActiveFilters() {
      return this.selectedTags.length > 0 || this.keyword.trim().length > 0;
    },
    emptyStateText() {
      if (this.enableAdvancedFilters && this.hasActiveFilters) {
        return 'No logs match the active filters.';
      }
      return 'No logs yet.';
    }
  },
  watch: {
    selectedLevels() {
      this.scheduleAutoScroll();
    },
    selectedTags() {
      this.scheduleAutoScroll();
    },
    keyword() {
      this.scheduleAutoScroll();
    }
  },
  async mounted() {
    await this.fetchLogHistory();
    this.connectSSE();
  },
  beforeUnmount() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.retryAttempts = 0;
  },
  methods: {
    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      const token = localStorage.getItem('token');

      this.eventSource = new EventSourcePolyfill('/api/live-log', {
        headers: {
          Authorization: token ? `Bearer ${token}` : ''
        },
        heartbeatTimeout: 300000,
        withCredentials: true
      });

      this.eventSource.onopen = () => {
        this.retryAttempts = 0;

        if (!this.lastEventId) {
          this.fetchLogHistory();
        }
      };

      this.eventSource.onmessage = (event) => {
        try {
          if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
          }

          const payload = JSON.parse(event.data);
          this.processNewLogs([payload]);
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
          console.error('Log stream reached max retry attempts.');
          return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000
        );

        if (this.retryTimer) {
          clearTimeout(this.retryTimer);
          this.retryTimer = null;
        }

        this.retryTimer = setTimeout(async () => {
          this.retryAttempts += 1;
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
      const searchIndex = [
        message,
        rendered,
        tag,
        ...(Array.isArray(log.tags) ? log.tags : []),
        log.platform_id || '',
        log.plugin_name || '',
        log.plugin_display_name || '',
        log.umo || '',
        log.logger_name || '',
        sourceFile
      ].join(' ').toLowerCase();

      return {
        ...log,
        type: 'log',
        uuid,
        rendered,
        data: rendered,
        message,
        tag,
        displayText: stripAnsi(rendered || message),
        searchIndex
      };
    },

    processNewLogs(newLogs) {
      if (!newLogs || newLogs.length === 0) {
        return;
      }

      let hasUpdate = false;
      const nextCache = [...this.localLogCache];
      const existingKeys = new Set(nextCache.map((entry) => entry.uuid));

      newLogs.forEach((log) => {
        const entry = this.normalizeLogEntry(log);
        if (!entry || existingKeys.has(entry.uuid)) {
          return;
        }
        existingKeys.add(entry.uuid);
        nextCache.push(entry);
        hasUpdate = true;
      });

      if (!hasUpdate) {
        return;
      }

      nextCache.sort((left, right) => left.time - right.time);

      const maxSize = this.commonStore.log_cache_max_len || 200;
      if (nextCache.length > maxSize) {
        nextCache.splice(0, nextCache.length - maxSize);
      }

      this.localLogCache = nextCache;
      this.scheduleAutoScroll();
    },

    async fetchLogHistory() {
      try {
        const response = await axios.get('/api/log-history');
        const logs = response.data?.data?.logs || [];
        this.processNewLogs(logs);
      } catch (error) {
        console.error('Failed to fetch log history:', error);
      }
    },

    clearFilters() {
      this.selectedTags = [];
      this.keyword = '';
    },

    getLevelColor(level) {
      return this.levelColors[level] || 'grey';
    },

    getLineStyle(entry) {
      const leadingAnsi = entry.rendered.match(LEADING_ANSI_PATTERN)?.[1];
      if (leadingAnsi && this.logColorAnsiMap[leadingAnsi]) {
        return this.logColorAnsiMap[leadingAnsi];
      }

      switch (entry.level) {
        case 'DEBUG':
          return this.logColorAnsiMap['\u001b[1;34m'];
        case 'INFO':
          return this.logColorAnsiMap['\u001b[1;36m'];
        case 'WARNING':
          return this.logColorAnsiMap['\u001b[1;33m'];
        case 'ERROR':
          return this.logColorAnsiMap['\u001b[31m'];
        case 'CRITICAL':
          return this.logColorAnsiMap['\u001b[1;31m'];
        default:
          return this.logColorAnsiMap.default;
      }
    },

    scheduleAutoScroll() {
      if (!this.autoScroll) {
        return;
      }

      this.$nextTick(() => {
        const element = this.$refs.term;
        if (!element) {
          return;
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

.filter-summary {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 12px;
}

.console-terminal {
  background-color: #1e1e1e;
  padding: 16px;
  border-radius: 8px;
  overflow-y: auto;
  height: 100%;
}

:deep(.console-log-line) {
  display: block;
  margin-bottom: 2px;
  font-family: SFMono-Regular, Menlo, Monaco, Consolas, var(--astrbot-font-cjk-mono), monospace;
  font-size: 12px;
  white-space: pre-wrap;
}

.console-empty {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
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

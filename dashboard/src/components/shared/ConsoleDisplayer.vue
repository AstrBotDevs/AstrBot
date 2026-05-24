<template>
  <div class="console-displayer" id="console-wrapper">
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

      <div v-if="enableAdvancedFilters" class="advanced-filters">
        <v-text-field
          v-model="keyword"
          :label="tm('filters.searchLabel')"
          :placeholder="tm('filters.searchPlaceholder')"
          density="compact"
          hide-details
          clearable
          variant="outlined"
          class="filter-input"
        />
        <v-combobox
          v-model="selectedTags"
          v-model:search="tagSearch"
          :items="tagOptions"
          :label="tm('filters.tagLabel')"
          :placeholder="tm('filters.tagPlaceholder')"
          :menu-props="{ maxHeight: 360, contentClass: 'tag-filter-menu' }"
          density="compact"
          hide-details
          clearable
          multiple
          variant="outlined"
          class="filter-input filter-input-tags"
        >
          <template #selection="{ index }">
            <span
              v-if="index === 0 && selectedTagPreview"
              class="tag-selection-summary"
            >
              {{ selectedTagPreview }}
            </span>
          </template>
        </v-combobox>
        <v-btn variant="text" size="small" @click="clearFilters">
          {{ tm('filters.clearButton') }}
        </v-btn>
        <span class="filter-summary">
          {{ tm('filters.summary', { count: localLogCache.length }) }}
        </span>
      </div>
    </div>

    <div ref="term" class="console-terminal" :class="{ 'console-terminal--flush': flushMode }">
      <pre
        v-for="entry in localLogCache"
        :key="entry.uuid"
        class="console-log-line fade-in"
        :class="{ 'console-log-line--structured': !flushMode }"
        :style="getLineStyle(entry)"
      >{{ entry.displayText }}</pre>
      <div v-if="localLogCache.length === 0" class="console-empty">
        {{ emptyStateText }}
      </div>
    </div>
  </div>
</template>

<script>
import { EventSourcePolyfill } from "event-source-polyfill";
import { useModuleI18n } from "@/i18n/composables";
import { useCommonStore } from "@/stores/common";
import { useCustomizerStore } from "@/stores/customizer";
import axios, { resolveApiUrl } from "@/utils/request";

const LEADING_ANSI_PATTERN = new RegExp(String.raw`^(\u001b\[[0-9;]+m)`);
const ANSI_PATTERN = new RegExp(String.raw`\u001b\[[0-9;]+m`, "g");

const lightColorAnsiMap = {
  "\u001b[1;34m": "color: #39C5BB; font-weight: bold;",
  "\u001b[1;36m": "color: #00FFFF; font-weight: bold;",
  "\u001b[1;33m": "color: #FFFF00;",
  "\u001b[31m": "color: #FF0000;",
  "\u001b[1;31m": "color: #FF0000; font-weight: bold;",
  "\u001b[0m": "color: inherit; font-weight: normal;",
  "\u001b[32m": "color: #00FF00;",
  default: "color: #FFFFFF;",
};

const darkColorAnsiMap = {
  "\u001b[1;34m": "color: #6cb6d9; font-weight: bold;",
  "\u001b[1;36m": "color: #72c4cc; font-weight: bold;",
  "\u001b[1;33m": "color: #d4b95e;",
  "\u001b[31m": "color: #d46a6a;",
  "\u001b[1;31m": "color: #e06060; font-weight: bold;",
  "\u001b[0m": "color: inherit; font-weight: normal;",
  "\u001b[32m": "color: #6cc070;",
  default: "color: #c8c8c8;",
};

function stripAnsi(value) {
  return String(value || "").replace(ANSI_PATTERN, "");
}

export default {
  name: "ConsoleDisplayer",
  props: {
    historyNum: {
      type: String,
      default: "-1",
    },
    showLevelBtns: {
      type: Boolean,
      default: true,
    },
    enableAdvancedFilters: {
      type: Boolean,
      default: false,
    },
    storageKey: {
      type: String,
      default: "",
    },
    autoScroll: {
      type: Boolean,
      default: true,
    },
  },
  setup() {
    const commonStore = useCommonStore();
    const { tm } = useModuleI18n("features/console");
    return { commonStore, tm };
  },
  data() {
    return {
      isFullscreen: false,
      flushMode: localStorage.getItem("console_flush_mode") === "true",
      logLevels: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
      selectedLevels: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
      selectedTags: [],
      tagSearch: "",
      keyword: "",
      levelColors: {
        DEBUG: "grey",
        INFO: "blue-lighten-3",
        WARNING: "amber",
        ERROR: "red",
        CRITICAL: "purple",
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
      suspendFilterSync: false,
    };
  },
  computed: {
    logColorAnsiMap() {
      const customizerStore = useCustomizerStore();
      return customizerStore.uiTheme === "PurpleThemeDark" ? darkColorAnsiMap : lightColorAnsiMap;
    },
    tagOptions() {
      return [...new Set([...this.availableTags, ...this.selectedTags].filter(Boolean))].sort();
    },
    selectedTagPreview() {
      if (this.tagSearch.trim() || this.selectedTags.length === 0) {
        return "";
      }

      const [firstTag, ...remainingTags] = this.selectedTags;
      return remainingTags.length > 0 ? `${firstTag} +${remainingTags.length}` : firstTag;
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
        return this.tm("filters.emptyFiltered");
      }
      return this.tm("filters.emptyIdle");
    },
  },
  watch: {
    selectedLevels: {
      handler() {
        this.queueFilterReload();
        this.persistState();
      },
      deep: true,
    },
    selectedTags: {
      handler() {
        this.queueFilterReload();
        this.persistState();
      },
      deep: true,
    },
    keyword() {
      this.queueFilterReload();
      this.persistState();
    },
    flushMode(val) {
      localStorage.setItem("console_flush_mode", val);
    },
  },
  async mounted() {
    this.restorePersistedState();
    document.addEventListener("fullscreenchange", this.handleFullscreenChange);
    await this.reloadLogSource();
  },
  beforeUnmount() {
    document.removeEventListener("fullscreenchange", this.handleFullscreenChange);
    this.teardownEventSource();
    if (this.filterSyncTimer) {
      clearTimeout(this.filterSyncTimer);
      this.filterSyncTimer = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.retryAttempts = 0;
  },
  methods: {
    getStorageKey() {
      if (!this.storageKey) {
        return "";
      }
      return `console-displayer:${this.storageKey}`;
    },

    restorePersistedState() {
      const storageKey = this.getStorageKey();
      if (!storageKey || typeof window === "undefined" || !window.localStorage) {
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
          ? parsed.selectedTags.filter((tag) => typeof tag === "string" && tag.trim())
          : [];

        this.selectedLevels = selectedLevels.length > 0 ? selectedLevels : [...this.logLevels];
        this.selectedTags = selectedTags;
        this.keyword = typeof parsed.keyword === "string" ? parsed.keyword : "";
      } catch (error) {
        console.warn("Failed to restore console filter state:", error);
      } finally {
        this.suspendFilterSync = false;
      }
    },

    persistState() {
      const storageKey = this.getStorageKey();
      if (!storageKey || typeof window === "undefined" || !window.localStorage) {
        return;
      }

      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            selectedLevels: this.selectedLevels,
            selectedTags: this.selectedTags,
            keyword: this.keyword,
          }),
        );
      } catch (error) {
        console.warn("Failed to persist console filter state:", error);
      }
    },

    getLogQueryParams() {
      return this.buildLogQueryParams();
    },

    buildLogQueryParams({ includeTag = true, includeLimit = true } = {}) {
      const params = {};
      const historyLimit = Number.parseInt(this.historyNum, 10);

      if (includeLimit && !Number.isNaN(historyLimit) && historyLimit > 0) {
        params.limit = historyLimit;
      }

      if (this.selectedLevels.length !== this.logLevels.length) {
        params.levels = this.selectedLevels.length > 0 ? this.selectedLevels.join(",") : "__none__";
      }

      if (includeTag && this.selectedTags.length > 0) {
        params.tag = this.selectedTags.join(",");
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
        if (value !== undefined && value !== null && value !== "") {
          query.set(key, String(value));
        }
      });

      return resolveApiUrl(query.toString() ? `/api/live-log?${query.toString()}` : "/api/live-log");
    },

    teardownEventSource() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
    },

    connectSSE(sequence = this.reloadSequence) {
      this.teardownEventSource();

      this.eventSource = new EventSourcePolyfill(this.buildLogStreamUrl(), {
        heartbeatTimeout: 300000,
      });

      this.eventSource.onopen = () => {
        if (sequence !== this.reloadSequence) {
          return;
        }
        this.retryAttempts = 0;
      };

      this.eventSource.onmessage = (event) => {
        if (sequence !== this.reloadSequence) {
          return;
        }

        try {
          if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
          }

          const payload = JSON.parse(event.data);
          this.appendLogs([payload]);
        } catch (error) {
          console.error("Failed to parse log stream payload:", error);
        }
      };

      this.eventSource.onerror = (error) => {
        if (sequence !== this.reloadSequence) {
          return;
        }

        if (error.status === 401) {
          console.error("Log stream authentication failed (401).");
        } else {
          console.warn("Log stream connection failed.", error);
        }

        this.teardownEventSource();

        if (this.retryAttempts >= this.maxRetryAttempts) {
          console.error("Max log stream retry attempts reached.");
          return;
        }

        const delay = Math.min(this.baseRetryDelay * 2 ** this.retryAttempts, 30000);

        if (this.retryTimer) {
          clearTimeout(this.retryTimer);
          this.retryTimer = null;
        }

        this.retryTimer = setTimeout(async () => {
          if (sequence !== this.reloadSequence) {
            return;
          }

          this.retryAttempts++;
          if (!this.lastEventId) {
            await this.fetchLogHistory(sequence);
          }

          this.connectSSE(sequence);
        }, delay);
      };
    },

    normalizeLogEntry(log) {
      if (!log || (log.type && log.type !== "log")) {
        return null;
      }

      const rendered = typeof log.rendered === "string" ? log.rendered : typeof log.data === "string" ? log.data : "";
      const message = typeof log.message === "string" ? log.message : stripAnsi(rendered);
      const tag = typeof log.tag === "string" && log.tag.trim() ? log.tag : "core:astrbot";
      const sourceFile = typeof log.source_file === "string" ? log.source_file : "unknown";
      const uuid =
        log.uuid ||
        [log.time, log.level, tag, log.logger_name || "", sourceFile, log.source_line || "", rendered || message].join(
          "|",
        );

      return {
        ...log,
        type: "log",
        uuid,
        rendered,
        data: rendered,
        message,
        tag,
        displayText: stripAnsi(rendered || message),
      };
    },

    replaceLogHistory(logs) {
      const knownLogIds = new Set();
      const normalizedLogs = [];

      logs.forEach((log) => {
        const entry = this.normalizeLogEntry(log);
        if (!entry || knownLogIds.has(entry.uuid)) {
          return;
        }

        knownLogIds.add(entry.uuid);
        normalizedLogs.push(entry);
      });

      normalizedLogs.sort((left, right) => Number(left.time || 0) - Number(right.time || 0));

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
      let lastTime =
        this.localLogCache.length > 0
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
        nextCache.sort((left, right) => Number(left.time || 0) - Number(right.time || 0));
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
        const response = await axios.get("/api/log-history", {
          params: this.getLogQueryParams(),
        });
        if (sequence !== this.reloadSequence) {
          return;
        }

        const logs = response.data?.data?.logs || [];
        this.replaceLogHistory(logs);
      } catch (error) {
        console.error("Failed to fetch log history:", error);
      }
    },

    async fetchTagOptions(sequence = this.reloadSequence) {
      try {
        const response = await axios.get("/api/log-history", {
          params: this.buildLogQueryParams({
            includeTag: false,
            includeLimit: false,
          }),
        });
        if (sequence !== this.reloadSequence) {
          return;
        }

        const logs = response.data?.data?.logs || [];
        this.updateAvailableTags(logs);
      } catch (error) {
        console.error("Failed to fetch tag options:", error);
      }
    },

    getLevelColor(level) {
      return this.levelColors[level] || "grey";
    },

    getLineStyle(entry) {
      const leadingAnsi = entry.rendered.match(LEADING_ANSI_PATTERN)?.[1];
      if (leadingAnsi && this.logColorAnsiMap[leadingAnsi]) {
        return this.logColorAnsiMap[leadingAnsi];
      }

      return this.logColorAnsiMap.default;
    },

    toggleAutoScroll() {
      this.autoScroll = !this.autoScroll;
    },

    toggleFlushMode() {
      this.flushMode = !this.flushMode;
    },

    toggleFullscreen() {
      const container = document.getElementById("console-wrapper");
      if (!container) {
        return;
      }

      if (!document.fullscreenElement) {
        container.requestFullscreen().catch((error) => {
          console.error(`Error attempting to enable full-screen mode: ${error.message}`);
        });
      } else {
        document.exitFullscreen();
      }
    },

    handleFullscreenChange() {
      this.isFullscreen = !!document.fullscreenElement;
    },

    clearFilters() {
      this.selectedLevels = [...this.logLevels];
      this.selectedTags = [];
      this.keyword = "";
      this.tagSearch = "";
      this.persistState();
      this.queueFilterReload(0);
    },

    queueFilterReload(delay = 300) {
      if (this.suspendFilterSync) {
        return;
      }

      if (this.filterSyncTimer) {
        clearTimeout(this.filterSyncTimer);
      }

      this.filterSyncTimer = setTimeout(() => {
        this.filterSyncTimer = null;
        this.reloadLogSource();
      }, delay);
    },

    async reloadLogSource() {
      this.reloadSequence++;
      const sequence = this.reloadSequence;
      this.lastEventId = null;
      this.teardownEventSource();

      if (this.retryTimer) {
        clearTimeout(this.retryTimer);
        this.retryTimer = null;
      }

      this.retryAttempts = 0;
      await Promise.all([this.fetchLogHistory(sequence), this.fetchTagOptions(sequence)]);

      if (sequence === this.reloadSequence) {
        this.connectSSE(sequence);
      }
    },

    updateAvailableTags(logs) {
      const nextTags = new Set(this.availableTags);

      logs.forEach((log) => {
        const tag = typeof log.tag === "string" && log.tag.trim() ? log.tag.trim() : "";
        if (tag) {
          nextTags.add(tag);
        }
      });

      this.availableTags = [...nextTags].sort();
    },

    setLastEventIdFromLogs(logs) {
      if (!logs.length) {
        return;
      }

      const lastLog = logs[logs.length - 1];
      if (lastLog.uuid) {
        this.lastEventId = lastLog.uuid;
      }
    },

    rebuildKnownLogIds() {
      this.knownLogIds = new Set(this.localLogCache.map((entry) => entry.uuid));
    },

    scheduleAutoScroll() {
      if (!this.autoScroll) {
        return;
      }

      this.$nextTick(() => {
        const element = this.$refs.term;
        if (element) {
          element.scrollTop = element.scrollHeight;
        }
      });
    },
  },
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

#console-wrapper:fullscreen {
  background-color: #1e1e1e;
  padding: 20px;
}

.fullscreen-btn {
  color: rgba(255, 255, 255, 0.7) !important;
}

.console-log-line {
  display: block;
  margin: 0 0 2px;
  font-family:
    SFMono-Regular, Menlo, Monaco, Consolas, var(--astrbot-font-cjk-mono),
    monospace;
  font-size: 12px;
  white-space: pre-wrap;
}

.console-log-line--structured {
  display: block;
  white-space: pre-wrap;
}

.console-empty {
  color: rgba(255, 255, 255, 0.56);
  font-size: 13px;
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

@media (max-width: 768px) {
  .console-terminal {
    padding: 12px;
  }

  .console-log-line {
    white-space: pre;
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

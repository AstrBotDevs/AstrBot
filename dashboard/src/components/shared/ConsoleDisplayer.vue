<script setup>
import { logApi, pluginApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { normalizeTextInput } from "@/utils/inputValue";
import { EventSourcePolyfill } from "event-source-polyfill";

const { tm } = useModuleI18n("features/console");
</script>

<template>
  <div
    id="console-wrapper"
    class="console-displayer-wrapper"
    :class="{ 'console-displayer-wrapper--workspace': workspaceMode }"
  >
    <div class="filter-controls mb-2" v-if="showLevelBtns || showSearch">
      <v-chip-group
        v-if="showLevelBtns && !workspaceMode"
        v-model="selectedLevels"
        class="log-level-filters"
        column
        multiple
      >
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
          class="font-weight-medium log-level-chip"
        >
          {{ level }}
        </v-chip>
      </v-chip-group>
      <v-btn
        v-if="workspaceMode"
        class="filter-toggle-btn"
        size="small"
        :variant="filtersOpen || hasActiveFilters ? 'tonal' : 'text'"
        :aria-expanded="filtersOpen"
        @click="filtersOpen = !filtersOpen"
      >
        <v-icon icon="mdi-filter-variant" size="17" />
        <span>{{ tm("filters.button") }}</span>
        <span v-if="hasActiveFilters" class="filter-status-dot" />
      </v-btn>
      <v-text-field
        v-if="showSearch"
        :model-value="searchInput"
        @update:model-value="searchInput = normalizeTextInput($event)"
        class="log-search-field"
        density="compact"
        variant="solo-filled"
        flat
        hide-details
        single-line
        clearable
        prepend-inner-icon="mdi-magnify"
        :aria-label="tm('search.label')"
        :placeholder="tm('search.placeholder')"
      ></v-text-field>
      <v-spacer></v-spacer>
      <slot name="header-actions"></slot>
      <v-btn
        :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
        variant="text"
        density="compact"
        class="me-4 fullscreen-btn"
        @click="toggleFullscreen"
      ></v-btn>
    </div>

    <div class="console-body">
      <aside v-if="workspaceMode && filtersOpen" class="console-filter-panel">
        <div class="console-filter-heading">
          <span>{{ tm("filters.title") }}</span>
          <v-btn
            v-if="hasActiveFilters"
            size="small"
            variant="text"
            :aria-label="tm('filters.reset')"
            @click="resetFilters"
          >
            {{ tm("filters.reset") }}
          </v-btn>
        </div>

        <div class="console-filter-block console-filter-block--first">
          <div class="console-filter-label">{{ tm("filters.level") }}</div>
          <label
            v-for="(level, index) in logLevels"
            :key="level"
            class="console-filter-option"
          >
            <v-checkbox-btn
              v-model="selectedLevels"
              :value="index"
              density="compact"
              hide-details
            />
            <span
              class="level-indicator"
              :style="{ backgroundColor: getLevelIndicatorColor(level) }"
            />
            <span>{{ level }}</span>
          </label>
        </div>

        <div class="console-filter-block">
          <div class="console-filter-label">{{ tm("filters.source") }}</div>
          <v-radio-group
            v-model="selectedSource"
            hide-details
            density="compact"
          >
            <v-radio :label="tm('filters.allSources')" value="all" />
            <v-radio :label="tm('filters.core')" value="core" />
            <v-radio :label="tm('filters.plugins')" value="plugin" />
          </v-radio-group>
        </div>

        <div class="console-filter-block">
          <div class="console-filter-label">{{ tm("filters.plugin") }}</div>
          <v-select
            v-model="selectedPlugin"
            :items="pluginOptions"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            clearable
            item-title="title"
            item-value="value"
            :disabled="selectedSource === 'core' || pluginOptions.length === 0"
            :placeholder="tm('filters.allPlugins')"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
            </template>
          </v-select>
        </div>

        <div class="console-filter-block">
          <div class="console-filter-label">{{ tm("filters.platform") }}</div>
          <v-select
            v-model="selectedPlatform"
            :items="platformOptions"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            clearable
            item-title="title"
            item-value="value"
            :placeholder="tm('filters.allPlatforms')"
          />
        </div>

        <div class="console-filter-block console-filter-block--last">
          <v-switch
            :model-value="hideUserChat"
            :label="tm('hideUserChat.label')"
            hide-details
            density="compact"
            inset
            color="primary"
            @update:model-value="$emit('update:hideUserChat', $event)"
          />
        </div>
      </aside>

      <div
        id="term"
        class="console-term"
        :style="{ '--console-log-font-size': `${fontSize}px` }"
      ></div>
    </div>
  </div>
</template>

<script>
import { useModuleI18n as useConsoleI18n } from "@/i18n/composables";

const { tm: translateConsole } = useConsoleI18n("features/console");

export default {
  name: "ConsoleDisplayer",
  emits: ["update:hideUserChat"],
  data() {
    return {
      isFullscreen: false,
      filtersOpen: false,
      logColorAnsiMap: {
        "\u001b[1;34m": "color: #6cb6d9; font-weight: bold;",
        "\u001b[1;36m": "color: #72c4cc; font-weight: bold;",
        "\u001b[1;33m": "color: #d4b95e; font-weight: bold;",
        "\u001b[31m": "color: #d46a6a;",
        "\u001b[1;31m": "color: #e06060; font-weight: bold;",
        "\u001b[0m": "color: inherit; font-weight: normal;",
        "\u001b[32m": "color: #6cc070;",
        default: "color: #c8c8c8;",
      },
      logLevels: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
      selectedLevels: [0, 1, 2, 3, 4],
      levelColors: {
        DEBUG: "grey",
        INFO: "blue-lighten-3",
        WARNING: "amber",
        ERROR: "red",
        CRITICAL: "purple",
      },
      localLogCache: [],
      maxLogCacheLength: 1000,
      nextLogId: 1,
      pluginDisplayNames: {},
      selectedSource: "all",
      selectedPlugin: null,
      selectedPlatform: null,
      searchInput: "",
      // Trimmed keyword; an empty string disables filtering.
      searchKeyword: "",
      searchTimer: null,
      eventSource: null,
      retryTimer: null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null,
    };
  },
  computed: {
    hasActiveFilters() {
      return (
        this.selectedLevels.length !== this.logLevels.length ||
        this.selectedSource !== "all" ||
        Boolean(this.selectedPlugin) ||
        Boolean(this.selectedPlatform) ||
        this.hideUserChat
      );
    },
    pluginOptions() {
      const pluginNames = Array.from(
        new Set(
          this.localLogCache
            .map((log) => log.plugin_name)
            .filter((name) => typeof name === "string" && name.length > 0),
        ),
      );
      return pluginNames
        .map((value) => ({
          title: this.pluginDisplayNames[value] || value,
          subtitle: value,
          value,
        }))
        .sort(
          (a, b) =>
            a.title.localeCompare(b.title) || a.value.localeCompare(b.value),
        );
    },
    platformOptions() {
      const platforms = new Map();
      let hasUnscopedLogs = false;
      this.localLogCache.forEach((log) => {
        if (!log.platform_id) {
          hasUnscopedLogs = true;
          return;
        }
        const type = log.platform_type ? ` (${log.platform_type})` : "";
        platforms.set(log.platform_id, {
          title: `${log.platform_id}${type}`,
          value: log.platform_id,
        });
      });
      const options = Array.from(platforms.values()).sort((a, b) =>
        a.title.localeCompare(b.title),
      );
      if (hasUnscopedLogs) {
        options.unshift({
          title: translateConsole("filters.unscopedPlatform"),
          value: "__unscoped__",
        });
      }
      return options;
    },
  },
  props: {
    historyNum: {
      type: String,
      default: "-1",
    },
    showLevelBtns: {
      type: Boolean,
      default: true,
    },
    hideUserChat: {
      type: Boolean,
      default: false,
    },
    showSearch: {
      type: Boolean,
      default: false,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
    workspaceMode: {
      type: Boolean,
      default: false,
    },
  },
  watch: {
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true,
    },
    hideUserChat() {
      this.refreshDisplay();
    },
    selectedSource(value) {
      if (value === "core") {
        this.selectedPlugin = null;
      }
      this.refreshDisplay();
    },
    selectedPlugin() {
      this.refreshDisplay();
    },
    selectedPlatform() {
      this.refreshDisplay();
    },
    searchInput: {
      handler(value) {
        if (this.searchTimer) {
          clearTimeout(this.searchTimer);
        }
        this.searchTimer = setTimeout(() => {
          this.searchTimer = null;
          const keyword = (value || "").trim();
          if (keyword === this.searchKeyword) {
            return;
          }
          this.searchKeyword = keyword;
          this.refreshDisplay();
        }, 250);
      },
    },
  },
  async mounted() {
    await this.fetchLogHistory();
    if (this.workspaceMode) {
      await this.fetchPluginDisplayNames();
    }
    this.connectSSE();
    document.addEventListener("fullscreenchange", this.handleFullscreenChange);
  },
  beforeUnmount() {
    document.removeEventListener(
      "fullscreenchange",
      this.handleFullscreenChange,
    );
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.searchTimer) {
      clearTimeout(this.searchTimer);
      this.searchTimer = null;
    }
    this.retryAttempts = 0;
  },
  methods: {
    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      console.log(`正在连接日志流... (尝试次数: ${this.retryAttempts})`);

      const token = localStorage.getItem("token");

      this.eventSource = new EventSourcePolyfill(logApi.liveUrl(), {
        headers: {
          Authorization: token ? `Bearer ${token}` : "",
        },
        heartbeatTimeout: 300000,
        withCredentials: true,
      });

      this.eventSource.onopen = () => {
        console.log("日志流连接成功！");
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
        } catch (e) {
          console.error("解析日志失败:", e);
        }
      };

      this.eventSource.onerror = (err) => {
        if (err.status === 401) {
          console.error("鉴权失败 (401)，可能是 Token 过期了。");
        } else {
          console.warn("日志流连接错误:", err);
        }

        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.retryAttempts >= this.maxRetryAttempts) {
          console.error("❌ 已达到最大重试次数，停止重连。请刷新页面重试。");
          return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000,
        );

        console.log(
          `⏳ ${delay}ms 后尝试第 ${this.retryAttempts + 1} 次重连...`,
        );

        if (this.retryTimer) {
          clearTimeout(this.retryTimer);
          this.retryTimer = null;
        }

        this.retryTimer = setTimeout(async () => {
          this.retryAttempts++;

          if (!this.lastEventId) {
            await this.fetchLogHistory();
          }

          this.connectSSE();
        }, delay);
      };
    },

    processNewLogs(newLogs) {
      if (!newLogs || newLogs.length === 0) return;

      let hasUpdate = false;
      const termElement = document.getElementById("term");
      const shouldStickToBottom =
        !termElement ||
        termElement.scrollHeight -
          termElement.scrollTop -
          termElement.clientHeight <=
          24;
      // Batch the rendered log elements into a single fragment so that a large
      // history payload only triggers one reflow instead of one per log line.
      const fragment = termElement ? document.createDocumentFragment() : null;

      newLogs.forEach((log) => {
        const exists = this.localLogCache.some(
          (existing) =>
            existing.time === log.time &&
            existing.data === log.data &&
            existing.level === log.level,
        );

        if (!exists) {
          log._renderId = this.nextLogId++;
          this.localLogCache.push(log);
          hasUpdate = true;

          if (this.isLogVisible(log)) {
            if (fragment) {
              fragment.appendChild(this.buildLogElement(log));
            }
          }
        }
      });

      if (hasUpdate) {
        this.localLogCache.sort((a, b) => a.time - b.time);

        if (this.localLogCache.length > this.maxLogCacheLength) {
          const removed = this.localLogCache.splice(
            0,
            this.localLogCache.length - this.maxLogCacheLength,
          );
          removed.forEach((log) => {
            termElement
              ?.querySelector(`[data-log-id="${log._renderId}"]`)
              ?.remove();
          });
        }
      }

      if (fragment && fragment.childNodes.length > 0) {
        termElement.appendChild(fragment);
        if (shouldStickToBottom) {
          termElement.scrollTop = termElement.scrollHeight;
        }
      }
    },

    async fetchLogHistory() {
      try {
        const res = await logApi.history();
        if (res.data.data.logs && res.data.data.logs.length > 0) {
          this.processNewLogs(res.data.data.logs);
        }
      } catch (err) {
        console.error("Failed to fetch log history:", err);
      }
    },

    async fetchPluginDisplayNames() {
      try {
        const res = await pluginApi.list();
        const displayNames = {};
        for (const plugin of res.data?.data || []) {
          const name = String(plugin?.name || "").trim();
          const displayName = String(plugin?.display_name || "").trim();
          if (name && displayName) {
            displayNames[name] = displayName;
          }
        }
        this.pluginDisplayNames = displayNames;
      } catch (err) {
        console.warn("Failed to load plugin display names:", err);
      }
    },

    getLevelColor(level) {
      return this.levelColors[level] || "grey";
    },

    getLevelIndicatorColor(level) {
      const colors = {
        DEBUG: "#9aa0a6",
        INFO: "#67b7dc",
        WARNING: "#d4ad45",
        ERROR: "#df6262",
        CRITICAL: "#bb68d5",
      };
      return colors[level] || "#9aa0a6";
    },

    resetFilters() {
      this.selectedLevels = this.logLevels.map((_, index) => index);
      this.selectedSource = "all";
      this.selectedPlugin = null;
      this.selectedPlatform = null;
      this.$emit("update:hideUserChat", false);
    },

    isLevelSelected(level) {
      for (let i = 0; i < this.selectedLevels.length; ++i) {
        let level_ = this.logLevels[this.selectedLevels[i]];
        if (level_ === level) {
          return true;
        }
      }
      return false;
    },

    isHiddenByCategory(log) {
      return this.hideUserChat && log && log.category === "user_chat";
    },

    matchesSource(log) {
      if (this.selectedSource === "all") {
        return true;
      }
      return (log.source || "core") === this.selectedSource;
    },

    matchesPlugin(log) {
      return !this.selectedPlugin || log.plugin_name === this.selectedPlugin;
    },

    matchesPlatform(log) {
      if (!this.selectedPlatform) {
        return true;
      }
      if (this.selectedPlatform === "__unscoped__") {
        return !log.platform_id;
      }
      return log.platform_id === this.selectedPlatform;
    },

    isLogVisible(log) {
      return (
        this.isLevelSelected(log.level) &&
        !this.isHiddenByCategory(log) &&
        this.matchesSource(log) &&
        this.matchesPlugin(log) &&
        this.matchesPlatform(log) &&
        this.matchesKeyword(log)
      );
    },

    matchesKeyword(log) {
      if (!this.searchKeyword) {
        return true;
      }
      const text = (log.data || "")
        .replace(/\u001b\[[0-9;]*m/g, "")
        .toLowerCase();
      return text.includes(this.searchKeyword.toLowerCase());
    },

    // Appends `text` to `element`, wrapping keyword matches in a highlight span.
    appendHighlightedText(element, text) {
      const keyword = this.searchKeyword;
      if (!keyword || !text) {
        element.textContent = text || "";
        return;
      }

      // Strip ANSI escape sequences first so highlight offsets line up with
      // the same stripped text used by `matchesKeyword`, and so no control
      // codes are rendered.
      const cleanText = text.replace(/\u001b\[[0-9;]*m/g, "");
      const lowerText = cleanText.toLowerCase();
      const lowerKeyword = keyword.toLowerCase();
      let cursor = 0;
      let index = lowerText.indexOf(lowerKeyword);

      while (index !== -1) {
        if (index > cursor) {
          element.appendChild(
            document.createTextNode(cleanText.slice(cursor, index)),
          );
        }
        const highlight = document.createElement("span");
        highlight.className = "console-log-highlight";
        highlight.textContent = cleanText.slice(index, index + keyword.length);
        element.appendChild(highlight);
        cursor = index + keyword.length;
        index = lowerText.indexOf(lowerKeyword, cursor);
      }

      if (cursor < cleanText.length) {
        element.appendChild(document.createTextNode(cleanText.slice(cursor)));
      }
    },

    refreshDisplay() {
      const termElement = document.getElementById("term");
      if (!termElement) return;

      const shouldStickToBottom =
        termElement.scrollHeight -
          termElement.scrollTop -
          termElement.clientHeight <=
        24;
      const previousScrollTop = termElement.scrollTop;
      termElement.innerHTML = "";
      if (!this.localLogCache || this.localLogCache.length === 0) return;

      const fragment = document.createDocumentFragment();
      this.localLogCache.forEach((logItem) => {
        if (this.isLogVisible(logItem)) {
          fragment.appendChild(this.buildLogElement(logItem));
        }
      });
      termElement.appendChild(fragment);
      if (shouldStickToBottom) {
        termElement.scrollTop = termElement.scrollHeight;
      } else {
        termElement.scrollTop = previousScrollTop;
      }
    },

    toggleFullscreen() {
      const container = document.getElementById("console-wrapper");
      if (!document.fullscreenElement) {
        container.requestFullscreen().catch((err) => {
          console.error(
            `Error attempting to enable full-screen mode: ${err.message}`,
          );
        });
      } else {
        document.exitFullscreen();
      }
    },

    handleFullscreenChange() {
      this.isFullscreen = !!document.fullscreenElement;
    },

    appendLogContent(element, log) {
      const levelMatch = log.match(
        /\[(DEBG|INFO|WARN|ERRO|CRIT|DEBUG|WARNING|ERROR|CRITICAL)\]/,
      );
      if (!levelMatch) {
        this.appendHighlightedText(element, log);
        return;
      }

      const levelStart = levelMatch.index;
      const levelEnd = levelStart + levelMatch[0].length;
      const prefix = log.slice(0, levelStart).trimEnd();
      const message = log.slice(levelEnd).trimStart();

      const prefixSpan = document.createElement("span");
      prefixSpan.className = "console-log-prefix";
      this.appendHighlightedText(prefixSpan, prefix);

      const levelSpan = document.createElement("span");
      levelSpan.className = "console-log-level";
      this.appendHighlightedText(levelSpan, levelMatch[0]);

      const messageSpan = document.createElement("span");
      messageSpan.className = "console-log-message";
      this.appendHighlightedText(messageSpan, message);

      element.classList.add("console-log-line--structured");
      element.appendChild(prefixSpan);
      element.appendChild(levelSpan);
      element.appendChild(messageSpan);
    },

    buildLogElement(logItem) {
      const span = document.createElement("pre");
      span.dataset.logId = String(logItem._renderId);
      let log = logItem.data || "";
      let style = this.logColorAnsiMap["default"];
      for (const key in this.logColorAnsiMap) {
        if (log.startsWith(key)) {
          style = this.logColorAnsiMap[key];
          log = log.replace(key, "").replace("\u001b[0m", "");
          break;
        }
      }

      span.style = style;
      span.classList.add("console-log-line", "fade-in");
      this.appendLogContent(span, log);
      return span;
    },
  },
};
</script>

<style scoped>
.console-displayer-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.console-displayer-wrapper--workspace {
  background: var(--console-workspace-card, #f5f6f7);
  border-radius: 16px;
  overflow: hidden;
  padding: 12px;
}

#console-wrapper:fullscreen {
  --v-theme-on-surface: 255, 255, 255;
  background-color: #1e1e1e;
  color: #fff;
  padding: 20px;
}

#console-wrapper:fullscreen :deep(.v-switch__track) {
  --v-theme-surface-variant: 163, 163, 163;
}

#console-wrapper:fullscreen .log-search-field :deep(.v-field) {
  --v-theme-surface: 36, 36, 36;
  --v-theme-surface-variant: 36, 36, 36;
  --v-theme-on-surface: 255, 255, 255;
}

.filter-controls {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  margin-bottom: 8px;
}

.log-search-field {
  flex: 1 1 360px;
  max-width: 520px;
  min-width: 160px;
}

.filter-toggle-btn {
  flex: 0 0 auto;
}

.filter-toggle-btn :deep(.v-btn__content) {
  gap: 5px;
}

.filter-status-dot {
  background: rgb(var(--v-theme-primary));
  border-radius: 50%;
  height: 6px;
  width: 6px;
}

.console-body {
  display: flex;
  flex: 1 1 auto;
  gap: 10px;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  position: relative;
}

.console-term {
  background-color: #1e1e1e;
  border-radius: 8px;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  overflow-x: auto;
  overflow-y: auto;
  padding: 16px;
}

.console-displayer-wrapper--workspace .filter-controls {
  flex: 0 0 auto;
  gap: 8px;
  margin-bottom: 10px !important;
  min-height: 42px;
  overflow-x: auto;
  padding: 0 2px;
  scrollbar-width: none;
}

.console-displayer-wrapper--workspace .filter-controls::-webkit-scrollbar {
  display: none;
}

.console-filter-panel {
  background: rgba(var(--v-theme-surface), 0.96);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  border-radius: 12px;
  flex: 0 0 238px;
  overflow-y: auto;
  padding: 14px;
  width: 238px;
}

.console-filter-heading {
  align-items: center;
  display: flex;
  font-size: 0.95rem;
  font-weight: 650;
  justify-content: space-between;
  min-height: 32px;
}

.console-filter-heading .v-btn {
  margin-inline-end: -8px;
}

.console-filter-block {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  margin-top: 12px;
  padding-top: 12px;
}

.console-filter-block--first {
  margin-top: 8px;
}

.console-filter-block--last {
  padding-top: 8px;
}

.console-filter-label {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.72rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  margin-bottom: 5px;
}

.console-filter-option {
  align-items: center;
  cursor: pointer;
  display: flex;
  font-size: 0.78rem;
  min-height: 30px;
}

.console-filter-option :deep(.v-selection-control) {
  min-height: 30px;
}

.level-indicator {
  border-radius: 50%;
  flex: 0 0 auto;
  height: 7px;
  margin: 0 8px 0 2px;
  width: 7px;
}

.console-filter-panel :deep(.v-radio-group .v-selection-control) {
  min-height: 30px;
}

.console-filter-panel :deep(.v-label) {
  font-size: 0.78rem;
  opacity: 0.88;
}

.console-filter-panel :deep(.v-field) {
  border-radius: 9px;
  font-size: 0.78rem;
}

.console-filter-panel :deep(.v-switch .v-selection-control) {
  min-height: 34px;
}

.console-displayer-wrapper--workspace .console-term {
  background: #17191c;
  border-radius: 12px;
  flex: 1 1 auto;
  height: auto;
  min-height: 0;
  padding: 14px;
}

.console-displayer-wrapper--workspace .fullscreen-btn {
  margin-inline-end: 0 !important;
}

.console-displayer-wrapper--workspace :deep(.console-log-line) {
  border-radius: 4px;
  line-height: 1.55;
  margin: 0;
  padding: 2px 5px;
}

.console-displayer-wrapper--workspace :deep(.console-log-line:hover) {
  background: rgba(255, 255, 255, 0.04);
}

.console-displayer-wrapper--workspace :deep(.console-log-level) {
  font-weight: 700;
}

.fullscreen-btn {
  color: rgba(var(--v-theme-on-surface), 0.7) !important;
}

#console-wrapper:fullscreen .fullscreen-btn {
  color: rgba(255, 255, 255, 0.7) !important;
}

#console-wrapper:fullscreen .console-filter-panel {
  --v-theme-on-surface: 255, 255, 255;
  --v-theme-surface: 38, 38, 38;
  background: #262626;
  border-color: rgba(255, 255, 255, 0.12);
}

:deep(.console-log-line) {
  display: block;
  margin: 0 0 2px;
  font-family: SFMono-Regular, Menlo, Monaco, Consolas,
    var(--astrbot-font-cjk-mono), monospace;
  font-size: var(--console-log-font-size, 12px);
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

:deep(.console-log-highlight) {
  background: rgba(255, 213, 79, 0.35);
  border-radius: 2px;
}

@media (max-width: 768px) {
  .console-displayer-wrapper--workspace {
    border-radius: 14px;
    padding: 10px;
  }

  .console-displayer-wrapper--workspace .filter-controls {
    gap: 6px;
    padding: 0;
  }

  .console-displayer-wrapper--workspace .log-search-field {
    flex: 1 1 220px;
    min-width: 150px;
  }

  .console-filter-panel {
    bottom: 0;
    box-shadow: 8px 0 24px rgba(0, 0, 0, 0.18);
    left: 0;
    max-width: 82%;
    position: absolute;
    top: 0;
    z-index: 3;
  }

  .console-displayer-wrapper--workspace .console-term {
    padding: 10px;
  }

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

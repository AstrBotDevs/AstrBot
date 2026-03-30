<script setup lang="ts">
import { useCommonStore } from "@/stores/common";
import axios from "@/utils/request";
import { EventSourcePolyfill } from "event-source-polyfill";
import { resolveApiUrl } from "@/utils/request";
</script>

<template>
  <div class="reactor-console">
    <!-- Filter bar -->
    <div v-if="showLevelBtns" class="filter-bar">
      <v-chip-group v-model="selectedLevels" column multiple>
        <v-chip
          v-for="level in logLevels"
          :key="level"
          :class="['log-tag', `log-tag-${level.toLowerCase()}`]"
          filter
          variant="flat"
          size="small"
        >
          <span class="level-dot" />
          {{ level }}
        </v-chip>
      </v-chip-group>
    </div>

    <!-- Terminal with scanlines -->
    <div class="terminal-wrapper">
      <div class="scanline-overlay" />
      <div id="term" class="term" />
    </div>
  </div>
</template>

<script lang="ts">
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
  },
  data() {
    return {
      autoScroll: true,
      logLevels: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
      selectedLevels: [0, 1, 2, 3, 4],
      levelColors: {
        DEBUG: "#4A4A5A",
        INFO: "#00F2FF",
        WARNING: "#CC7000",
        ERROR: "#FF4D4D",
        CRITICAL: "#FF00AA",
      },
      localLogCache: [] as Array<{ time: number; data: string; level: string }>,
      eventSource: null as EventSourcePolyfill | null,
      retryTimer: null as ReturnType<typeof setTimeout> | null,
      retryAttempts: 0,
      maxRetryAttempts: 10,
      baseRetryDelay: 1000,
      lastEventId: null as string | null,
      isUnmounted: false,
    };
  },
  computed: {
    commonStore() {
      return useCommonStore();
    },
  },
  watch: {
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true,
    },
  },
  async mounted() {
    await this.fetchLogHistory();
    this.connectSSE();
  },
  beforeUnmount() {
    this.isUnmounted = true;
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
      if (this.isUnmounted) return;
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      this.eventSource = new EventSourcePolyfill(
        resolveApiUrl("/api/live-log"),
        { heartbeatTimeout: 300000 },
      );

      this.eventSource.onopen = () => {
        this.retryAttempts = 0;
        if (!this.lastEventId) {
          void this.fetchLogHistory();
        }
      };

      this.eventSource.onmessage = (event) => {
        try {
          if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
          }
          const payload = JSON.parse(event.data);
          this.processNewLogs([payload]);
        } catch {
          // silently ignore parse errors in production
        }
      };

      this.eventSource.onerror = () => {
        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.retryAttempts >= this.maxRetryAttempts) {
          return;
        }

        const delay = Math.min(
          this.baseRetryDelay * Math.pow(2, this.retryAttempts),
          30000,
        );

        this.retryTimer = setTimeout(async () => {
          if (this.isUnmounted) return;
          this.retryAttempts++;
          if (!this.lastEventId) {
            await this.fetchLogHistory();
          }
          this.connectSSE();
        }, delay);
      };
    },

    processNewLogs(newLogs: Array<{ time: number; data: string; level: string }>) {
      if (!newLogs || newLogs.length === 0) return;

      newLogs.forEach((log) => {
        const exists = this.localLogCache.some(
          (existing) =>
            existing.time === log.time &&
            existing.data === log.data &&
            existing.level === log.level,
        );
        if (!exists) {
          this.localLogCache.push(log);
          if (this.isLevelSelected(log.level)) {
            this.printLog(log.data, log.level);
          }
        }
      });

      this.localLogCache.sort((a, b) => a.time - b.time);
      const maxSize = this.commonStore.log_cache_max_len || 200;
      if (this.localLogCache.length > maxSize) {
        this.localLogCache.splice(0, this.localLogCache.length - maxSize);
      }
    },

    async fetchLogHistory() {
      try {
        const res = await axios.get("/api/log-history");
        if (res.data.data.logs && res.data.data.logs.length > 0) {
          this.processNewLogs(res.data.data.logs);
        }
      } catch {
        // silently ignore
      }
    },

    isLevelSelected(level: string) {
      return this.selectedLevels.some(
        (i) => this.logLevels[i] === level,
      );
    },

    refreshDisplay() {
      const termElement = document.getElementById("term");
      if (termElement) {
        termElement.innerHTML = "";
        this.localLogCache.forEach((logItem) => {
          if (this.isLevelSelected(logItem.level)) {
            this.printLog(logItem.data, logItem.level);
          }
        });
      }
    },

    parseAnsiLog(log: string): { text: string; color: string; borderColor?: string } {
      // ANSI color code map
      const ansiMap: Record<string, string> = {
        "\u001b[1;34m": "#39C5BB",
        "\u001b[1;36m": "#00FFFF",
        "\u001b[1;33m": "#FFD54F",
        "\u001b[31m": "#FF4D4D",
        "\u001b[1;31m": "#FF4D4D",
        "\u001b[0m": "inherit",
        "\u001b[32m": "#69F0AE",
      };

      // Content-based color differentiation: system, private, group, platform
      const lowerLog = log.toLowerCase();
      if (lowerLog.includes("· astrbot") || lowerLog.includes("· reactor")) {
        // System messages: cyan-teal
        return { text: log, color: "#00F2FF", borderColor: "system" };
      }
      if (lowerLog.includes("[private")) {
        // Private messages: warm green
        return { text: log, color: "#69F0AE", borderColor: "private" };
      }
      if (lowerLog.includes("[group")) {
        // Group messages: soft periwinkle blue
        return { text: log, color: "#8fb6d2", borderColor: "group" };
      }
      if (lowerLog.includes("telegram") || lowerLog.includes("discord") || lowerLog.includes("qq ") || lowerLog.includes("onebot")) {
        // Platform adapter messages: soft purple
        return { text: log, color: "#B39DDB", borderColor: "platform" };
      }
      if (lowerLog.includes("error") || lowerLog.includes("failed") || lowerLog.includes("exception")) {
        // Error indicators keep default treatment
      }

      let color = "rgba(255,255,255,0.75)";
      for (const [code, c] of Object.entries(ansiMap)) {
        if (log.startsWith(code)) {
          color = c;
          log = log.replace(code, "").replace("\u001b[0m", "");
          break;
        }
      }
      return { text: log, color };
    },

    printLog(log: string, level?: string) {
      const ele = document.getElementById("term");
      if (!ele) return;

      const { text, color, borderColor } = this.parseAnsiLog(log);

      const line = document.createElement("div");
      line.classList.add("log-line");

      if (level) {
        line.classList.add(`log-line-${level.toLowerCase()}`);
      }
      if (borderColor) {
        line.classList.add(`log-line-${borderColor}`);
      }

      line.innerText = text;
      line.style.color = color;

      ele.appendChild(line);
      if (this.autoScroll) {
        ele.scrollTop = ele.scrollHeight;
      }
    },
  },
};
</script>

<style scoped>
.reactor-console {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* === Filter bar: hollow indicator chips === */
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 4px;
}

:deep(.log-tag) {
  background: transparent !important;
  border: 1px solid currentColor !important;
  border-radius: 3px !important;
  padding: 2px 10px !important;
  font-size: 10px !important;
  letter-spacing: 1.2px !important;
  text-transform: uppercase !important;
  font-family: "JetBrains Mono", "Fira Code", monospace !important;
  font-weight: 500 !important;
  color: inherit !important;
  transition: all 0.2s ease;
  box-shadow: none !important;
}

:deep(.log-tag .v-chip__content) {
  padding: 0 !important;
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
  box-shadow: 0 0 4px currentColor;
}

:deep(.log-tag.DEBUG) {
  color: #4A4A5A !important;
  border-color: #4A4A5A !important;
}
:deep(.log-tag.INFO) {
  color: #00F2FF !important;
  border-color: #00F2FF !important;
}
:deep(.log-tag.INFO .level-dot) {
  box-shadow: 0 0 6px #00F2FF;
}
:deep(.log-tag.WARNING) {
  color: #CC7000 !important;
  border-color: #CC7000 !important;
}
:deep(.log-tag.ERROR) {
  color: #FF4D4D !important;
  border-color: #FF4D4D !important;
}
:deep(.log-tag.ERROR .level-dot) {
  box-shadow: 0 0 6px #FF4D4D;
}
:deep(.log-tag.CRITICAL) {
  color: #FF00AA !important;
  border-color: #FF00AA !important;
}
:deep(.log-tag.CRITICAL .level-dot) {
  box-shadow: 0 0 8px #FF00AA;
}

/* === Terminal wrapper: deep glass + scanlines === */
.terminal-wrapper {
  position: relative;
  flex: 1;
  border-radius: 6px;
  overflow: hidden;
  background: rgba(10, 10, 15, 0.6);
  backdrop-filter: blur(20px) saturate(1.2);
  border: 1px solid rgba(0, 242, 255, 0.06);
  box-shadow:
    inset 0 0 30px rgba(0, 0, 0, 0.9),
    0 0 0 0.5px rgba(0, 242, 255, 0.04);
}

/* CRT scanline overlay */
.scanline-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 10;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0px,
    transparent 3px,
    rgba(0, 0, 0, 0.08) 3px,
    rgba(0, 0, 0, 0.08) 4px
  );
  animation: scanlines 8s linear infinite;
}

@keyframes scanlines {
  0% { background-position: 0 0; }
  100% { background-position: 0 100vh; }
}

/* === Terminal content === */
.term {
  height: 100%;
  overflow-y: auto;
  padding: 12px 16px;
  box-sizing: border-box;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 242, 255, 0.2) transparent;
}

.term::-webkit-scrollbar {
  width: 4px;
}
.term::-webkit-scrollbar-track {
  background: transparent;
}
.term::-webkit-scrollbar-thumb {
  background: rgba(0, 242, 255, 0.2);
  border-radius: 2px;
}

:deep(.log-line) {
  display: block;
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code",
    SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  transition: background 0.15s ease;
}

/* ERROR: left red glow bar */
:deep(.log-line-error) {
  background: rgba(255, 20, 20, 0.04);
  box-shadow: inset 3px 0 0 #FF4D4D;
}
:deep(.log-line-error:hover) {
  background: rgba(255, 20, 20, 0.08);
}

/* CRITICAL: magenta glow bar */
:deep(.log-line-critical) {
  background: rgba(255, 0, 170, 0.05);
  box-shadow: inset 3px 0 0 #FF00AA;
}
:deep(.log-line-critical:hover) {
  background: rgba(255, 0, 170, 0.09);
}

/* WARNING: subtle amber bar */
:deep(.log-line-warning) {
  background: rgba(204, 112, 0, 0.04);
  box-shadow: inset 3px 0 0 #CC7000;
}

/* INFO: faint cyan bar */
:deep(.log-line-info) {
  background: rgba(0, 242, 255, 0.02);
  box-shadow: inset 2px 0 0 rgba(0, 242, 255, 0.3);
}

/* Content-type left border indicators */
:deep(.log-line-system) {
  box-shadow: inset 3px 0 0 #00F2FF !important;
}
:deep(.log-line-private) {
  box-shadow: inset 3px 0 0 #69F0AE !important;
}
:deep(.log-line-group) {
  box-shadow: inset 3px 0 0 #8fb6d2 !important;
}
:deep(.log-line-platform) {
  box-shadow: inset 3px 0 0 #B39DDB !important;
}

/* New entry pulse animation */
:deep(.log-line) {
  animation: entryPulse 0.25s ease-out;
}

@keyframes entryPulse {
  0% {
    background: rgba(0, 242, 255, 0.06);
  }
  100% {
    background: transparent;
  }
}
</style>

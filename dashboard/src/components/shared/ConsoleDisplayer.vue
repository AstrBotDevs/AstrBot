<script setup>
import { useCommonStore } from '@/stores/common';
import axios from 'axios';
</script>

<template>
  <div>
    <!-- 添加筛选级别控件 -->
    <div class="filter-controls mb-2" v-if="showLevelBtns">
      <v-chip-group v-model="selectedLevels" column multiple>
        <v-chip v-for="level in logLevels" :key="level" :color="getLevelColor(level)" filter variant="flat" size="small"
          :text-color="level === 'DEBUG' || level === 'INFO' ? 'black' : 'white'" class="font-weight-medium">
          {{ level }}
        </v-chip>
      </v-chip-group>
    </div>

    <div id="term" style="background-color: #1e1e1e; padding: 16px; border-radius: 8px; overflow-y:auto; height: 100%">
    </div>
  </div>
</template>

<script>
export default {
  name: 'ConsoleDisplayer',
  data() {
    return {
      autoScroll: true,
      logColorAnsiMap: {
        '\u001b[1;34m': 'color: #0000FF; font-weight: bold;',
        '\u001b[1;36m': 'color: #00FFFF; font-weight: bold;',
        '\u001b[1;33m': 'color: #FFFF00; font-weight: bold;',
        '\u001b[31m': 'color: #FF0000;',
        '\u001b[1;31m': 'color: #FF0000; font-weight: bold;',
        '\u001b[0m': 'color: inherit; font-weight: normal;',
        '\u001b[32m': 'color: #00FF00;',
        'default': 'color: #FFFFFF;'
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
    }
  },
  computed: {
    commonStore() {
      return useCommonStore();
    },
  },
  props: {
    historyNum: {
      type: String,
      default: "-1"
    },
    showLevelBtns: {
      type: Boolean,
      default: true
    }
  },
  watch: {
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true
    }
  },
  async mounted() {
    await this.fetchLogHistory();
    this.connectSSE();
  },
  beforeUnmount() {
    if (this.eventSource) {
      this.eventSource.close();
    }
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
    }
  },
  methods: {
    connectSSE() {
      if (this.eventSource) {
        this.eventSource.close();
      }

      this.eventSource = new EventSource('/api/live-log');

      this.eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.processNewLogs([payload]);
        } catch (e) {
          console.error('解析日志失败:', e);
        }
      };

      this.eventSource.onerror = (err) => {
        this.eventSource.close();
        
        this.retryTimer = setTimeout(async () => {
          await this.fetchLogHistory();
          this.connectSSE();
        }, 1000);
      };
    },

    processNewLogs(newLogs) {
      if (!newLogs || newLogs.length === 0) return;

      let hasUpdate = false;

      newLogs.forEach(log => {
        const exists = this.localLogCache.some(existing => existing.time === log.time);
        
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
      }
    },

    async fetchLogHistory() {
      try {
        const res = await axios.get('/api/log-history');
        if (res.data.data.logs && res.data.data.logs.length > 0) {
          this.processNewLogs(res.data.data.logs);
        }
      } catch (err) {
        console.error('Failed to fetch log history:', err);
      }
    },
    
    getLevelColor(level) {
      return this.levelColors[level] || 'grey';
    },

    isLevelSelected(level) {
      for (let i = 0; i < this.selectedLevels.length; ++i) {
        let level_ = this.logLevels[this.selectedLevels[i]]
        if (level_ === level) {
          return true;
        }
      }
      return false;
    },

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
      }

      span.style = style + 'display: block; font-size: 12px; font-family: Consolas, monospace; white-space: pre-wrap; margin-bottom: 2px;'
      span.classList.add('fade-in')
      span.innerText = `${log}`;
      ele.appendChild(span)
      if (this.autoScroll) {
        ele.scrollTop = ele.scrollHeight
      }
    }
  },
}
</script>

<style scoped>
.filter-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  margin-left: 20px;
}

.fade-in {
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

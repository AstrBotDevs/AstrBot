<script setup>
import { useCommonStore } from '@/stores/common';
import axios from 'axios';
import { EventSourcePolyfill } from 'event-source-polyfill';
</script>

<template>
  <div>
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

      console.log(`正在连接日志流... (尝试次数: ${this.retryAttempts})`);
      
      const token = localStorage.getItem('token');

      this.eventSource = new EventSourcePolyfill('/api/live-log', {
        headers: {
            'Authorization': token ? `Bearer ${token}` : ''
        },
        heartbeatTimeout: 300000, 
        withCredentials: true 
      });

      this.eventSource.onopen = () => {
        console.log('日志流连接成功！');
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
          console.error('解析日志失败:', e);
        }
      };

      this.eventSource.onerror = (err) => {

        if (err.status === 401) {
            console.error('鉴权失败 (401)，可能是 Token 过期了。');

        } else {
            console.warn('日志流连接错误:', err);
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

      newLogs.forEach(log => {

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

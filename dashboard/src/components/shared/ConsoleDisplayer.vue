<script setup>
import { useCommonStore } from '@/stores/common';
import { storeToRefs } from 'pinia';
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
      autoScroll: true,  // 默认开启自动滚动
      logColorAnsiMap: {
        '\u001b[1;34m': 'color: #0000FF; font-weight: bold;', // bold_blue
        '\u001b[1;36m': 'color: #00FFFF; font-weight: bold;', // bold_cyan
        '\u001b[1;33m': 'color: #FFFF00; font-weight: bold;', // bold_yellow
        '\u001b[31m': 'color: #FF0000;', // red
        '\u001b[1;31m': 'color: #FF0000; font-weight: bold;', // bold_red
        '\u001b[0m': 'color: inherit; font-weight: normal;', // reset
        '\u001b[32m': 'color: #00FF00;',  // green
        'default': 'color: #FFFFFF;'
      },
      historyNum_: -1,
      logLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      selectedLevels: [0, 1, 2, 3, 4], // 默认选中所有级别
      levelColors: {
        'DEBUG': 'grey',
        'INFO': 'blue-lighten-3',
        'WARNING': 'amber',
        'ERROR': 'red',
        'CRITICAL': 'purple'
      },
      lastProcessedTime: 0, // 记录最后处理的日志时间戳
      localLogCache: [], // 本地日志缓存
    }
  },
  computed: {
    commonStore() {
      return useCommonStore();
    },
    logCache() {
      return this.commonStore.log_cache;
    }
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
    logCache: {
      handler(newVal) {
        // 基于 timestamp 处理新增的日志
        if (newVal && newVal.length > 0) {
          // 确保 DOM 已经准备好
          this.$nextTick(() => {
            // 合并到本地缓存并按时间排序
            const newLogs = newVal.filter(log => log.time > this.lastProcessedTime);
            
            if (newLogs.length > 0) {
              this.localLogCache.push(...newLogs);
              // 按时间戳排序
              this.localLogCache.sort((a, b) => a.time - b.time);
              
              // 只保留最新的 log_cache_max_len 条
              if (this.localLogCache.length > this.commonStore.log_cache_max_len) {
                this.localLogCache.splice(0, this.localLogCache.length - this.commonStore.log_cache_max_len);
              }
              
              // 显示新日志
              newLogs.forEach(logItem => {
                if (this.isLevelSelected(logItem.level)) {
                  this.printLog(logItem.data);
                }
              });
              
              // 更新最后处理时间
              this.lastProcessedTime = Math.max(...newLogs.map(log => log.time));
            }
          });
        }
      },
      deep: true,
      immediate: false
    },
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true
    }
  },
  async mounted() {
    // 请求历史日志
    await this.fetchLogHistory();
    
    // 等待 DOM 准备好后，显示历史日志
    this.$nextTick(() => {
      if (this.localLogCache.length > 0) {
        this.localLogCache.forEach(logItem => {
          if (this.isLevelSelected(logItem.level)) {
            this.printLog(logItem.data);
          }
        });
        // 更新最后处理时间
        this.lastProcessedTime = Math.max(...this.localLogCache.map(log => log.time));
      }
    });
  },
  methods: {
    async fetchLogHistory() {
      try {
        const res = await axios.get('/api/log-history');
        if (res.data.data.logs && res.data.data.logs.length > 0) {
          this.localLogCache = [...res.data.data.logs];
          // 按时间戳排序
          this.localLogCache.sort((a, b) => a.time - b.time);
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
        
        // 重新显示所有符合筛选条件的日志
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
      // append 一个 span 标签到 term，block 的方式
      let ele = document.getElementById('term')
      if (!ele) {
        console.warn('term element not found, skipping log print');
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

      span.style = style + 'display: block; font-size: 12px; font-family: Consolas, monospace; white-space: pre-wrap;'
      span.classList.add('fade-in')
      span.innerText = `${log}`;
      ele.appendChild(span)
      if (this.autoScroll ) {
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
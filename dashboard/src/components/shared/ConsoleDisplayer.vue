<script setup>
import { useCommonStore } from '@/stores/common';
</script>

<template>
  <div>
    <!-- 添加筛选级别控件 -->
    <div class="filter-controls mb-2">
      <v-chip-group v-model="selectedLevels" column multiple>
        <v-chip v-for="level in logLevels" :key="level" :color="getLevelColor(level)" filter
          :text-color="level === 'DEBUG' || level === 'INFO' ? 'black' : 'white'">
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
      logCache: useCommonStore().getLogCache(),
      historyNum_: -1,
      logLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
      selectedLevels: [0, 1, 2, 3, 4], // 默认选中所有级别
      levelColors: {
        'DEBUG': 'grey',
        'INFO': 'blue-lighten-3',
        'WARNING': 'amber',
        'ERROR': 'red',
        'CRITICAL': 'purple'
      }
    }
  },
  props: {
    historyNum: {
      type: String,
      default: -1
    }
  },
  watch: {
    logCache: {
      handler(val) {
        const lastLog = val[this.logCache.length - 1];
        if (lastLog && this.isLevelSelected(lastLog.level)) {
          this.printLog(lastLog.data);
        }
      },
      deep: true
    },
    selectedLevels: {
      handler() {
        this.refreshDisplay();
      },
      deep: true
    }
  },
  mounted() {
    if (this.logCache.length === 0) {
      this.delayInit()
    } else {
      this.init()
    }
  },
  methods: {
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
      // 清空现有的显示
      const termElement = document.getElementById('term');
      if (termElement) {
        termElement.innerHTML = '';
      }

      // 重新显示符合筛选条件的日志
      this.init();
    },

    delayInit() {
      if (this.logCache.length === 0) {
        setTimeout(() => {
          this.delayInit()
        }, 500)
      } else {
        this.init()
      }
    },

    init() {
      this.historyNum_ = parseInt(this.historyNum)
      let i = 0
      for (let log of this.logCache) {
        if (this.isLevelSelected(log.level)) { // 只显示选中级别的日志
          if (this.historyNum_ != -1 && i >= this.logCache.length - this.historyNum_) {
            this.printLog(log.data)
            ++i
          } else if (this.historyNum_ == -1) {
            this.printLog(log.data)
          }
        }
      }
    },

    toggleAutoScroll() {
      this.autoScroll = !this.autoScroll;
    },

    printLog(log) {
      // append 一个 span 标签到 term，block 的方式
      let ele = document.getElementById('term')
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
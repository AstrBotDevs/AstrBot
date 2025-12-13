<script setup>
import { useCommonStore } from '@/stores/common';
import { storeToRefs } from 'pinia';
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
      lastLogLength: 0, // 记录上次处理的日志数量
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
        // 只处理新增的日志
        console.log('logCache changed, length:', newVal?.length, 'lastLength:', this.lastLogLength);
        if (newVal && newVal.length > this.lastLogLength) {
          const newLogs = newVal.slice(this.lastLogLength);
          console.log('Processing new logs:', newLogs);
          
          newLogs.forEach(logItem => {
            console.log('Log item:', logItem, 'Level selected:', this.isLevelSelected(logItem.level));
            if (this.isLevelSelected(logItem.level)) {
              this.printLog(logItem.data);
            }
          });
          
          this.lastLogLength = newVal.length;
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
  mounted() {
    // 初始化时显示所有历史日志
    console.log('ConsoleDisplayer mounted, logCache length:', this.logCache?.length);
    this.refreshDisplay();
    this.lastLogLength = this.logCache ? this.logCache.length : 0;
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
      const termElement = document.getElementById('term');
      console.log('refreshDisplay called, termElement:', termElement, 'logCache length:', this.logCache?.length);
      if (termElement) {
        termElement.innerHTML = '';
        
        // 重新显示所有符合筛选条件的日志
        if (this.logCache && this.logCache.length > 0) {
          console.log('Displaying', this.logCache.length, 'logs');
          this.logCache.forEach(logItem => {
            console.log('Processing log item:', logItem);
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
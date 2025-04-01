<script setup>
import { useCommonStore } from '@/stores/common';
</script>

<template>
  <div id="term"
    style="background-color: #1e1e1e; padding: 16px; border-radius: 8px; overflow-y: auto;">
  </div>
</template>

<script>
export default {
  name: 'ConsoleDisplayer',
  data() {
    return {
      autoScroll: true,  // 默认开启自动滚动
      logColorMap: {
        DEBG: 'color: #808080;', // 灰色
        INFO: 'color: #00FF00;',  // 绿色
        WARN: 'color: #FFFF00;',  // 黄色
        ERRO: 'color: #FF0000;', // 红色
        CRIT: 'color: #FF0000; font-weight: bold;', // 加粗红色
        default: 'color: #FFFFFF;' // 默认白色
      },
      logCache: useCommonStore().getLogCache(),
      historyNum_: -1
    };
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
        this.printLog(val[val.length - 1]);
      },
      deep: true
    }
  },
  mounted() {
    this.historyNum_ = parseInt(this.historyNum);
    let i = 0;
    for (let log of this.logCache) {
      if (this.historyNum_ !== -1 && i >= this.logCache.length - this.historyNum_) {
        this.printLog(log);
        ++i;
      } else if (this.historyNum_ === -1) {
        this.printLog(log);
      }
    }
  },
  methods: {
    toggleAutoScroll() {
      this.autoScroll = !this.autoScroll;
    },
    printLog(log) {
      // 假设日志格式为：[LEVEL] message
      const levelMatch = log.match(/^\[(DEBG|INFO|WARN|ERRO|CRIT)\]/);
      let level = 'default';
      if (levelMatch) {
        level = levelMatch[1];
      }

      // 创建一个 span 标签来显示日志
      const ele = document.getElementById('term');
      const span = document.createElement('pre');
      span.style = this.logColorMap[level] + 'display: block; font-size: 12px; font-family: Consolas, monospace; white-space: pre-wrap;';
      span.classList.add('fade-in');
      span.innerText = log;
      ele.appendChild(span);

      // 如果开启了自动滚动，则滚动到最底部
      if (this.autoScroll) {
        ele.scrollTop = ele.scrollHeight;
      }
    }
  }
};
</script>
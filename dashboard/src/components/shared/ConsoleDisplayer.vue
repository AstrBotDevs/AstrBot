<script setup>
import { useCommonStore } from '@/stores/common';
</script>

<template>
    <div id="term"
      style="background-color: #1e1e1e; padding: 16px; border-radius: 8px; overflow-y:auto">
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
      historyNum_: -1
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
        this.printLog(val[this.logCache.length - 1])
      },
      deep: true
    }
  },
  mounted() {
    this.historyNum_ = parseInt(this.historyNum)
    let i = 0
    for (let log of this.logCache) {
        if (this.historyNum_ != -1 && i >= this.logCache.length - this.historyNum_) {
          this.printLog(log)
          ++i
        } else if (this.historyNum_ == -1) {
          this.printLog(log)
        }
    }
  },
  methods: {
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
      span.innerText = log
      ele.appendChild(span)
      if (this.autoScroll) {
        ele.scrollTop = ele.scrollHeight
      }
    }
  },
}
</script>
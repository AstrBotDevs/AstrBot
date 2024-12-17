import { defineStore } from 'pinia';
import axios from 'axios';

export const useCommonStore = defineStore({
  id: 'common',
  state: () => ({
    // @ts-ignore
    websocket: null,
    log_cache: [],
    log_cache_max_len: 1000,
    startTime: -1,
  }),
  actions: {
    createWebSocket() {
      if (this.websocket) {
        return
      }
      let protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      let route = '/api/live-log'
      let port = window.location.port
      let url = `${protocol}://${window.location.hostname}:${port}${route}`
      console.log('websocket url:', url)
      this.websocket = new WebSocket(url)
      this.websocket.onmessage = (evt) => {
        this.log_cache.push(evt.data)
        if (this.log_cache.length > this.log_cache_max_len) {
          this.log_cache.shift()
        }
      }
    },
    getLogCache() {
      return this.log_cache
    },
    getStartTime() {
      if (this.startTime !== -1) {
        return this.startTime
      }
      axios.get('/api/stat/start-time').then((res) => {
          this.startTime = res.data.data.start_time
      })
    },
  }
});

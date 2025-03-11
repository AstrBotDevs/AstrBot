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

    tutorial_map: {
      "qq_official_webhook": "https://astrbot.app/deploy/platform/qqofficial/webhook.html",
      "qq_official": "https://astrbot.app/deploy/platform/qqofficial/websockets.html",
      "aiocqhttp": "https://astrbot.app/deploy/platform/aiocqhttp/napcat.html",
      "wecom": "https://astrbot.app/deploy/platform/wecom.html",
      "gewechat": "https://astrbot.app/deploy/platform/gewechat.html",
      "lark": "https://astrbot.app/deploy/platform/lark.html",
      "telegram": "https://astrbot.app/deploy/platform/telegram.html",
      "dingtalk": "https://astrbot.app/deploy/platform/dingtalk.html",
    },

    pluginMarketData: []

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
    getTutorialLink(platform) {
      return this.tutorial_map[platform]
    },
    async getPluginCollections(force = false) {
      // 获取插件市场数据
      if (!force && this.pluginMarketData.length > 0) {
        return Promise.resolve(this.pluginMarketData);
      }
      return axios.get('/api/plugin/market_list')
        .then((res) => {
          let data = []
          for (let key in res.data.data) {
            data.push({
              "name": key,
              "desc": res.data.data[key].desc,
              "author": res.data.data[key].author,
              "repo": res.data.data[key].repo,
              "installed": false,
              "version": res.data.data[key]?.version ? res.data.data[key].version : "未知",
              "social_link": res.data.data[key]?.social_link,
              "tags": res.data.data[key]?.tags ? res.data.data[key].tags : [],
              "logo": res.data.data[key]?.logo ? res.data.data[key].logo : "",
              "pinned": res.data.data[key]?.pinned ? res.data.data[key].pinned : false,
            })
          }
          this.pluginMarketData = data;
          return data;
        })
        .catch((err) => {
          this.toast("获取插件市场数据失败: " + err, "error");
          return Promise.reject(err);
        });
    },
  }
});

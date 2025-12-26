import { defineStore } from 'pinia';
import axios from 'axios';

export const useCommonStore = defineStore({
  id: 'common',
  state: () => ({
    // @ts-ignore
    eventSource: null,
    log_cache: [],
    sse_connected: false,

    log_cache_max_len: 1000,
    startTime: -1,

    pluginMarketData: [],
  }),
  actions: {
    async createEventSource() {
      if (this.eventSource) {
        return
      }
      const controller = new AbortController();
      const { signal } = controller;
      
      // 注意：这里如果之前改过 Polyfill 的话，可能需要保持原样
      // 如果是用 fetch 的话，这里是支持 Authorization Header 的
      const headers = {
        'Content-Type': 'multipart/form-data',
        'Authorization': 'Bearer ' + localStorage.getItem('token')
      };
      
      fetch('/api/live-log', {
        method: 'GET',
        headers,
        signal,
        cache: 'no-cache',
      }).then(response => {
        if (!response.ok) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        console.log('SSE stream opened');
        this.sse_connected = true;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let bufferedText = '';

        const processStream = ({ done, value }) => {
          if (done) {
            console.log('SSE stream closed');
            setTimeout(() => {
              this.eventSource = null;
              this.createEventSource();
            }, 2000);
            return;
          }

          // Accumulate partial chunks; SSE data may split JSON across reads.
          const text = decoder.decode(value, { stream: true });
          bufferedText += text;

          // Split completed events; keep the trailing partial in buffer.
          const segments = bufferedText.split('\n\n');
          bufferedText = segments.pop() || '';

          segments.forEach(segment => {
            const line = segment.trim();
            if (!line.startsWith('data: ')) {
              return;
            }

            const logLine = line.replace('data: ', '').trim();
            if (!logLine) {
              return;
            }

            try {
              const logObject = JSON.parse(logLine);
              
              // 修复：兼容 HTTP 环境的 UUID 生成 
              if (!logObject.uuid) {
                 if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
                    logObject.uuid = crypto.randomUUID();
                 } else {
                    // 手动生成 UUID v4
                    logObject.uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                        return v.toString(16);
                    });
                 }
              }

              this.log_cache.push(logObject);
              // Limit log cache size
              if (this.log_cache.length > this.log_cache_max_len) {
                this.log_cache.splice(0, this.log_cache.length - this.log_cache_max_len);
              }
            } catch (err) {
              console.warn('Failed to parse SSE log line, skipping:', err, logLine);
            }
          });
          
          return reader.read().then(processStream);
        };

        reader.read().then(processStream);
      }).catch(error => {
        console.error('SSE error:', error);
        // Attempt to reconnect after a delay
        this.log_cache.push({
            type: 'log',
            level: 'ERROR',
            time: Date.now() / 1000,
            data: 'SSE Connection failed, retrying in 5 seconds...',
            uuid: 'error-' + Date.now() 
        });
        setTimeout(() => {
          this.eventSource = null;
          this.createEventSource();
        }, 1000);
      });

      // Store controller to allow closing the connection
      this.eventSource = controller;
    },
    closeEventSourcet() {
      if (this.eventSource) {
        this.eventSource.abort();
        this.eventSource = null;
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
    async getPluginCollections(force = false, customSource = null) {
      // 获取插件市场数据
      if (!force && this.pluginMarketData.length > 0 && !customSource) {
        return Promise.resolve(this.pluginMarketData);
      }

      // 构建URL
      let url = force ? '/api/plugin/market_list?force_refresh=true' : '/api/plugin/market_list';
      if (customSource) {
        url += (url.includes('?') ? '&' : '?') + `custom_registry=${encodeURIComponent(customSource)}`;
      }

      return axios.get(url)
        .then((res) => {
          let data = []
          if (res.data.data && typeof res.data.data === 'object') {
            for (let key in res.data.data) {
              const pluginData = res.data.data[key];
              
              data.push({
                "name": pluginData.name || key, // 优先使用插件数据中的name字段，否则使用键名
                "desc": pluginData.desc,
                "author": pluginData.author,
                "repo": pluginData.repo,
                "installed": false,
                "version": pluginData?.version ? pluginData.version : "未知",
                "social_link": pluginData?.social_link,
                "tags": pluginData?.tags ? pluginData.tags : [],
                "logo": pluginData?.logo ? pluginData.logo : "",
                "pinned": pluginData?.pinned ? pluginData.pinned : false,
                "stars": pluginData?.stars ? pluginData.stars : 0,
                "updated_at": pluginData?.updated_at ? pluginData.updated_at : "",
                "display_name": pluginData?.display_name ? pluginData.display_name : "",
              })
            }
          }
          
          this.pluginMarketData = data;
          return data;
        })
        .catch((err) => {
          return Promise.reject(err);
        });
    },
  }
});

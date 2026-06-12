/**
 * 公告数据 Composable.
 *
 * 数据源: AstrBot Core 代理的更新服务器公告接口 (/api/system/announcement).
 * 该接口会透传更新服务器 /announcement 的状态码:
 *   - 200: 返回公告 JSON
 *   - 404: 无公告 / 公告已禁用
 *   - 502/503: 后端代理 / 上游异常
 *
 * 设计原则:
 *   - 静默失败: 任何错误都视为"无公告", 公告条不显示.
 *   - 单次加载: 进入页面拉一次即可, 不做轮询.
 *   - 集中缓存: 暴露 module 级单例, 多个组件共享同一份数据.
 *
 * 作者: AstrBot Agent Harness
 * 时间: 2026-06-12
 */
import { ref } from 'vue';
import axios from 'axios';

export interface AnnouncementData {
  title: string;
  content: string;
  enabled: boolean;
  version: number;
  published_at?: string;
  created_at?: string;
}

interface AnnouncementState {
  data: import('vue').Ref<AnnouncementData | null>;
  loading: import('vue').Ref<boolean>;
  error: import('vue').Ref<string | null>;
  reload: () => Promise<void>;
}

// --- module 级单例: 多组件共享同一份公告数据 ---
let _singleton: AnnouncementState | null = null;

function createAnnouncementState(): AnnouncementState {
  const data = ref<AnnouncementData | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const res = await axios.get('/api/system/announcement', {
        timeout: 5000,
      });
      const payload = res.data?.data ?? res.data;
      if (payload && typeof payload === 'object' && payload.title) {
        data.value = payload as AnnouncementData;
      } else {
        // 200 但 payload 异常: 静默置空
        data.value = null;
      }
    } catch (e: any) {
      // 404 (无公告) / 502 / 503 / 网络错误: 全部静默
      error.value = e?.response?.data?.message ?? e?.message ?? 'unknown';
      data.value = null;
    } finally {
      loading.value = false;
    }
  }

  // 立即触发首次加载
  void load();

  return { data, loading, error, reload: load };
}

export function useAnnouncement(): AnnouncementState {
  if (!_singleton) {
    _singleton = createAnnouncementState();
  }
  return _singleton;
}

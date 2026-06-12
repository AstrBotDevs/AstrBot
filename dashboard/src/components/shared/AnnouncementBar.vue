<template>
  <div v-if="visible" class="ann-bar-wrapper">
    <!-- 展开态: 完整滚动公告条 -->
    <div
      v-if="!collapsed"
      class="announcement-bar"
      role="region"
      :aria-label="tm('announcementBar.label')"
    >
      <div class="ann-left">
        <v-icon size="18" class="mr-2">mdi-bullhorn-variant</v-icon>
        <span class="ann-label">{{ tm('announcementBar.label') }}</span>
      </div>

      <div
        class="ann-middle"
        :title="data?.title"
        @click="open = true"
        @mouseenter="hover = true"
        @mouseleave="hover = false"
      >
        <div class="ann-track" :class="{ paused: hover }">
          <span class="ann-text">{{ summary }}</span>
          <span class="ann-text" aria-hidden="true">{{ summary }}</span>
        </div>
      </div>

      <div class="ann-right">
        <v-btn
          variant="text"
          density="comfortable"
          size="small"
          icon
          :aria-label="tm('announcementBar.viewDetail')"
          @click="open = true"
        >
          <v-icon size="18">mdi-open-in-new</v-icon>
        </v-btn>
        <v-btn
          variant="text"
          density="comfortable"
          size="small"
          icon
          :aria-label="tm('announcementBar.closeAriaLabel')"
          @click="collapsed = true"
        >
          <v-icon size="18">mdi-close</v-icon>
        </v-btn>
      </div>
    </div>

    <!-- 折叠态: 36x36 小按钮, 放在原公告条同位置, 点击恢复展开 -->
    <button
      v-else
      type="button"
      class="ann-toggle-btn"
      :aria-label="tm('announcementBar.expandAriaLabel')"
      :title="tm('announcementBar.expandAriaLabel')"
      @click="collapsed = false"
    >
      <v-icon size="20">mdi-bullhorn-variant</v-icon>
    </button>

    <v-dialog v-model="open" max-width="720" scrollable>
      <v-card>
        <v-card-title class="text-h6 font-weight-bold pa-4">
          {{ data?.title }}
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <MarkdownRender
            :content="data?.content || ''"
            :typewriter="false"
            class="ann-dialog-markdown markdown-content"
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn color="primary" variant="text" @click="open = false">
            {{ tm('announcementBar.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * 顶部滚动公告条 (可折叠).
 *
 * 数据流: useAnnouncement (composable) → 调 /api/system/announcement
 *   - 数据源: AstrBot Core 代理的更新服务器 /announcement
 *   - 无公告 / 加载失败时: visible = false (整个组件不挂载)
 *
 * 折叠/展开行为 (UI 状态, 不持久化):
 *   - 右侧 ✕ 按钮: 折叠为 36x36 小按钮 (collapsed = true)
 *   - 小按钮点击: 恢复完整横条 (collapsed = false)
 *   - 刷新页面后默认展开 (与"完全关闭"语义不同)
 *
 * 交互:
 *   - 鼠标 hover 横条中部: 暂停 marquee 滚动
 *   - 点击条身 / 右侧 ⤴ 按钮: 打开 v-dialog 查看完整 Markdown
 *   - 右侧 ✕ 按钮: 折叠
 *   - 折叠态小按钮: 展开
 *
 * 作者: AstrBot Agent Harness
 * 时间: 2026-06-12
 */
import { computed, ref } from 'vue';
import { useAnnouncement } from '@/composables/useAnnouncement';
import { useModuleI18n } from '@/i18n/composables';
import { MarkdownRender } from 'markstream-vue';
import 'markstream-vue/index.css';

const { tm } = useModuleI18n('features/welcome');
const { data } = useAnnouncement();

const hover = ref(false);
const open = ref(false);
const collapsed = ref(false);

const visible = computed(() => !!data.value);

const summary = computed(() => {
  if (!data.value) return '';
  const title = (data.value.title || '').trim();
  const text = stripMarkdown(data.value.content || '');
  const combined = title && text ? `${title}　·　${text}` : title || text;
  return combined.length > 200 ? combined.slice(0, 200) + '…' : combined;
});

function stripMarkdown(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, ' [代码] ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*?(.+?)\*\*?/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/\n+/g, ' ')
    .trim();
}
</script>

<style scoped>
.ann-bar-wrapper {
  /* 容器仅作切换, 不占视觉空间 */
  display: contents;
}

.announcement-bar {
  display: flex;
  align-items: center;
  height: 36px;
  padding: 0 12px;
  background: linear-gradient(90deg, #fff8e1 0%, #fffbf0 50%, #fff8e1 100%);
  border-bottom: 1px solid #ffe082;
  color: #b45309;
  font-size: 13px;
  /* 粘在 v-main 顶部: v-main 自带 padding 让出 toolbar (top) 和 sidebar (left),
     不会挡 toolbar 的 logo/按钮, 也不会覆盖 sidebar. */
  position: sticky;
  top: 0;
  z-index: 5;
}

.ann-left {
  display: flex;
  align-items: center;
  min-width: 96px;
  flex-shrink: 0;
}

.ann-label {
  font-weight: 700;
}

.ann-middle {
  flex: 1;
  overflow: hidden;
  margin: 0 12px;
  cursor: pointer;
  position: relative;
  min-width: 0;
}

.ann-track {
  display: inline-flex;
  white-space: nowrap;
  animation: ann-marquee 40s linear infinite;
  will-change: transform;
}

.ann-track.paused {
  animation-play-state: paused;
}

.ann-text {
  padding-right: 64px;
  user-select: none;
}

.ann-right {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

@keyframes ann-marquee {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}

/* 折叠态: 36x36 圆角小按钮, 紧贴 v-main 顶部, 同样 sticky 不挡 toolbar/sidebar. */
.ann-toggle-btn {
  position: sticky;
  top: 6px;
  z-index: 5;
  align-self: flex-start;
  width: 36px;
  height: 36px;
  margin: 0 0 6px 6px;
  padding: 0;
  border-radius: 10px;
  border: 1px solid #ffe082;
  background: linear-gradient(135deg, #fff8e1 0%, #fffbf0 100%);
  color: #b45309;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.12s ease;
  box-shadow: 0 1px 2px rgba(180, 83, 9, 0.06);
}

.ann-toggle-btn:hover {
  background: linear-gradient(135deg, #fff3cd 0%, #fff8e1 100%);
  box-shadow: 0 4px 10px rgba(255, 193, 7, 0.25);
  transform: translateY(-1px);
}

.ann-toggle-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(180, 83, 9, 0.1);
}

.ann-toggle-btn:focus-visible {
  outline: 2px solid #fbbf24;
  outline-offset: 2px;
}

.ann-dialog-markdown {
  line-height: 1.7;
}
</style>

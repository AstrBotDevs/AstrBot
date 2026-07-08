<!--
  Author: elecvoid243
  Date: 2026-07-07
  Spec: docs/superpowers/specs/2026-07-07-extra-content-field-amendment.md §3

  InteractiveChoiceProse: 候选框 prose 渲染壳,负责把 LLM 在
  InteractiveChoicePart.extra_content 写的 Markdown 渲染为"补充说明"区,
  放在 prompt 与 options 之间。

  设计选择(相对 MarkdownMessagePart):
  - 不接收 refs / customHtmlTags(LLM 上下文没有 web search 引用)
  - 关闭所有流式 / 打字机效果(候选框内容是凝固的最终态)
  - 强制剥离 ![](url) 图片(防 LLM 注入跟踪像素 / 不可信 URL)
  - 用 custom-id 避免与主聊天流的 markstream-vue 节点 id 冲突

  渲染层复用项目已统一的 markstream-vue,自动获得 shiki 代码高亮、
  KaTeX 公式、Mermaid 图表(全局 enableKatex / enableMermaid 已在
  MessageList.vue 调用)、深色模式与 XSS sanitize。
-->
<template>
  <div
    v-if="hasRenderableContent"
    class="choice-prose markdown-content"
    role="note"
    :aria-label="ariaLabel"
  >
    <MarkdownRender
      :custom-id="customId"
      :content="renderableContent"
      :is-dark="isDark"
      :final="true"
      :is-streaming="false"
      :smooth-streaming="false"
      :fade="false"
      :typewriter="false"
      :max-live-nodes="maxLiveNodes"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { MarkdownRender } from "markstream-vue";
import "markstream-vue/index.css";
import { MARKDOWN_RENDER_MAX_LIVE_NODES } from "@/components/chat/markdownRenderConfig";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  /**
   * LLM 在 spec.extra_content 写的 Markdown 文本。
   * 已由 truncateInteractiveChoice 在 parseInteractiveChoice 层完成
   * 长度截断(≤5000 字符)。
   */
  content?: string;
  /** 跟随父组件主题——isDark 来自 InteractiveChoiceBox */
  isDark?: boolean;
  /**
   * 唯一 id 前缀,用于 markstream-vue 内部 node id 命名空间隔离。
   * 必须由父组件传入稳定值(推荐 part.request_id),避免同一页面
   * 多个候选框之间节点 id 冲突。
   */
  uid: string;
}>();

const { tm } = useModuleI18n("features/chat");

// ── 图片剥离(后端 guide §3.3 硬性要求) ────────────────────────
//
// `![](url)` 是 LLM 注入不可信图片(跟踪像素、恶意 URL、幻觉 URL)
// 的最直接通道——必须显示为占位符,而不是真去 <img src=...>。
//
// 覆盖三种标准 Markdown 图片语法:
//   ![alt](url)
//   ![alt](url "title")
//   ![alt](url 'title')
//
// 不处理引用式 ![alt][ref](罕见,LLM 极少写),由 markstream-vue 自身的
// sanitize 兜底(降级为转义文本)。
const IMAGE_PATTERN = /!\[([^\]]*)\]\([^)\s]+(?:\s+["'][^"']*["'])?\)/g;

const trimmedContent = computed(() => {
  if (typeof props.content !== "string") return "";
  return props.content.trim();
});

const hasRenderableContent = computed(() => trimmedContent.value.length > 0);

const renderableContent = computed(() => {
  if (!hasRenderableContent.value) return "";
  return trimmedContent.value.replace(IMAGE_PATTERN, (_, alt) => {
    const trimmedAlt = typeof alt === "string" ? alt.trim() : "";
    return trimmedAlt ? `[图片: ${trimmedAlt}]` : "[图片]";
  });
});

const ariaLabel = computed(() => tm("interactiveChoice.extraContentLabel"));
const customId = computed(() => `choice-prose-${props.uid}`);
const maxLiveNodes = MARKDOWN_RENDER_MAX_LIVE_NODES;
</script>

<style scoped>
.choice-prose {
  /* 与候选框主体保持视觉柔和分离:左侧一道竖条 + 透明背景,
     让 prose 自然沿用候选框底色,不抢戏。 */
  margin: 6px 0 10px;
  padding: 8px 10px 8px 12px;
  border-left: 3px solid rgba(var(--v-theme-primary), 0.45);
  border-radius: 0 6px 6px 0;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.85);
  word-break: break-word;
  /* 防止长 prose 撑爆候选框 max-width:560px */
  max-width: 100%;
  /* 表格过宽时让 prose 自身横向滚动(而不是让整个候选框溢出) */
  overflow-x: auto;
}

/* 暗色主题:只加深左竖条,保持透明背景 */
.interactive-choice-box.is-dark .choice-prose,
.choice-prose:global(.is-dark) {
  border-left-color: rgba(var(--v-theme-primary), 0.6);
}

/* markstream-vue 默认 <p> 上下 margin 太大,收紧到适合小卡片的间距 */
.choice-prose :deep(p) {
  margin: 0.4em 0;
}
.choice-prose :deep(p:first-child) {
  margin-top: 0;
}
.choice-prose :deep(p:last-child) {
  margin-bottom: 0;
}

/* 标题层级在小卡片里不要太大,逐级递减 */
.choice-prose :deep(h1) {
  font-size: 1.15em;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}
.choice-prose :deep(h2) {
  font-size: 1.08em;
  font-weight: 600;
  margin: 0.5em 0 0.3em;
}
.choice-prose :deep(h3),
.choice-prose :deep(h4),
.choice-prose :deep(h5),
.choice-prose :deep(h6) {
  font-size: 1em;
  font-weight: 600;
  margin: 0.5em 0 0.25em;
}

/* 列表缩进与行距 */
.choice-prose :deep(ul),
.choice-prose :deep(ol) {
  padding-left: 1.4em;
  margin: 0.4em 0;
}
.choice-prose :deep(li) {
  margin: 0.15em 0;
}

/* 代码块:候选框宽度只有 560px,横向滚动而不是 wrap 撑爆布局 */
.choice-prose :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  font-size: 12px;
  border-radius: 4px;
}

/* 行内 code 用半透明灰底,跟按钮 description 同档而非主题色 */
.choice-prose :deep(code) {
  font-size: 0.9em;
}

/* 引用块稍微主题色 */
.choice-prose :deep(blockquote) {
  margin: 0.4em 0;
  padding: 0.2em 0.6em;
  border-left: 2px solid rgba(var(--v-theme-primary), 0.3);
  color: rgba(var(--v-theme-on-surface), 0.75);
}

/* 链接继承项目主色(与 .markdown-content a 规则保持一致) */
.choice-prose :deep(a) {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* 表格:候选框 max-width 只有 560px,过宽时由外层 .choice-prose 的
   overflow-x:auto 提供横向滚动。table 本身必须保持正常的 table 布局
   (display:table / auto),——之前用 display:block 会丢掉列宽自适应,
   导致 5 列窄表被压扁、右侧几列看似"被截断"。 */
.choice-prose :deep(table) {
  max-width: 100%;
  font-size: 12px;
  border-collapse: collapse;
}
.choice-prose :deep(th),
.choice-prose :deep(td) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  padding: 4px 8px;
  /* 长 token(<i 字符、enum、URL)允许在词内换行,避免窄列被撑爆 */
  overflow-wrap: anywhere;
  text-align: left;
}
.choice-prose :deep(th) {
  background: rgba(var(--v-theme-primary), 0.06);
  font-weight: 600;
}
</style>

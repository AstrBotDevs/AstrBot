<template>
  <div
    ref="messageContainer"
    class="messages-container"
    :class="{ 'is-dark': isDark }"
  >
    <!-- 加载指示器 -->
    <div
      v-if="isLoadingMessages"
      class="loading-overlay"
      :class="{ 'is-dark': isDark }"
    >
      <v-progress-circular indeterminate size="48" width="4" color="primary" />
    </div>
    <!-- 聊天消息列表 -->
    <div
      class="message-list"
      :class="{ 'loading-blur': isLoadingMessages }"
      @mouseup="handleTextSelection"
    >
      <div
        v-for="(msg, index) in messages"
        :key="index"
        class="message-item fade-in"
      >
        <!-- 用户消息 -->
        <div v-if="msg.content.type == 'user'" class="user-message">
          <div
            class="message-bubble user-bubble"
            :class="{ 'has-audio': hasAudio(msg.content.message) }"
            :style="{
              backgroundColor: 'var(--v-theme-chatMessageBubble)',
            }"
          >
            <!-- 遍历 message parts -->
            <template
              v-for="(part, partIndex) in msg.content.message"
              :key="partIndex"
            >
              <!-- 引用消息 -->
              <div
                v-if="part.type === 'reply'"
                class="reply-quote"
                @click="scrollToMessage(part.message_id)"
              >
                <v-icon size="small" class="reply-quote-icon">
                  mdi-reply
                </v-icon>
                <span class="reply-quote-text">{{
                  getReplyContent(part.message_id)
                }}</span>
              </div>

              <!-- 纯文本 -->
              <pre
                v-else-if="part.type === 'plain' && part.text"
                class="bubble-text"
                >{{ part.text }}</pre
              >

              <!-- 图片附件 -->
              <div
                v-else-if="part.type === 'image' && part.embedded_url"
                class="image-attachments"
              >
                <div class="image-attachment">
                  <img
                    :src="part.embedded_url"
                    class="attached-image"
                    @click="openImagePreview(part.embedded_url)"
                  />
                </div>
              </div>

              <!-- 音频附件 -->
              <div
                v-else-if="part.type === 'record' && part.embedded_url"
                class="audio-attachment"
              >
                <audio controls class="audio-player">
                  <source :src="part.embedded_url" type="audio/wav" />
                  {{ t("messages.errors.browser.audioNotSupported") }}
                </audio>
              </div>

              <!-- 文件附件 -->
              <div
                v-else-if="part.type === 'file' && part.embedded_file"
                class="file-attachments"
              >
                <div class="file-attachment">
                  <a
                    v-if="part.embedded_file.url"
                    :href="part.embedded_file.url"
                    :download="part.embedded_file.filename"
                    class="file-link"
                    :class="{ 'is-dark': isDark }"
                    :style="
                      isDark
                        ? {
                            backgroundColor: 'rgba(255, 255, 255, 0.05)',
                            borderColor: 'rgba(255, 255, 255, 0.1)',
                            color: 'var(--v-theme-secondary)',
                          }
                        : {}
                    "
                  >
                    <v-icon
                      size="small"
                      class="file-icon"
                      :style="
                        isDark ? { color: 'var(--v-theme-secondary)' } : {}
                      "
                      >mdi-file-document-outline</v-icon
                    >
                    <span class="file-name">{{
                      part.embedded_file.filename
                    }}</span>
                  </a>
                  <a
                    v-else
                    class="file-link file-link-download"
                    :class="{ 'is-dark': isDark }"
                    :style="
                      isDark
                        ? {
                            backgroundColor: 'rgba(255, 255, 255, 0.05)',
                            borderColor: 'rgba(255, 255, 255, 0.1)',
                            color: 'var(--v-theme-secondary)',
                          }
                        : {}
                    "
                    @click="downloadFile(part.embedded_file)"
                  >
                    <v-icon
                      size="small"
                      class="file-icon"
                      :style="
                        isDark ? { color: 'var(--v-theme-secondary)' } : {}
                      "
                      >mdi-file-document-outline</v-icon
                    >
                    <span class="file-name">{{
                      part.embedded_file.filename
                    }}</span>
                    <v-icon
                      v-if="
                        downloadingFiles.has(
                          part.embedded_file.attachment_id || '',
                        )
                      "
                      size="small"
                      class="download-icon"
                      >mdi-loading mdi-spin</v-icon
                    >

                    <v-icon v-else size="small" class="download-icon"
                      >mdi-download</v-icon
                    >
                  </a>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Bot Messages -->
        <div v-else class="bot-message">
          <v-avatar class="bot-avatar" size="36">
            <v-progress-circular
              v-if="isStreaming && index === messages.length - 1"
              :index="index"
              indeterminate
              size="28"
              width="2"
            />
            <v-icon
              v-else-if="messages[index - 1]?.content.type !== 'bot'"
              size="64"
              color="#8fb6d2"
            >
              mdi-star-four-points-small
            </v-icon>
          </v-avatar>
          <div class="bot-message-content">
            <div
              class="message-bubble bot-bubble"
              :style="{
                backgroundColor: 'var(--v-theme-chatAssistantBubble)',
              }"
            >
              <!-- Loading state -->
              <div v-if="msg.content.isLoading" class="loading-container">
                <span class="loading-text">{{ tm("message.loading") }}</span>
              </div>

              <template v-else>
                <!-- Reasoning Block (Collapsible) - 放在最前面 -->
                <ReasoningBlock
                  v-if="msg.content.reasoning && msg.content.reasoning.trim()"
                  :reasoning="msg.content.reasoning"
                  :is-dark="isDark"
                  class="mt-2"
                  :initial-expanded="isReasoningExpanded(index)"
                />

                <MessagePartsRenderer
                  :parts="msg.content.message"
                  :is-dark="isDark"
                  :current-time="currentTime"
                  :downloading-files="downloadingFiles"
                  @open-image-preview="openImagePreview"
                  @download-file="downloadFile"
                />
              </template>
            </div>
            <div
              v-if="!msg.content.isLoading || index === messages.length - 1"
              class="message-actions"
            >
              <span v-if="msg.created_at" class="message-time">{{
                formatMessageTime(msg.created_at)
              }}</span>
              <!-- Agent Stats Menu -->
              <v-menu
                v-if="msg.content.agentStats"
                location="bottom"
                open-on-hover
                :close-on-content-click="false"
              >
                <template #activator="{ props }">
                  <v-icon v-bind="props" size="x-small" class="stats-info-icon">
                    mdi-information-outline
                  </v-icon>
                </template>
                <v-card
                  class="stats-menu-card"
                  variant="elevated"
                  elevation="3"
                >
                  <v-card-text class="stats-menu-content">
                    <div class="stats-menu-row">
                      <span class="stats-menu-label">{{
                        tm("stats.inputTokens")
                      }}</span>
                      <span class="stats-menu-value">{{
                        getInputTokens(msg.content.agentStats.token_usage)
                      }}</span>
                    </div>
                    <div class="stats-menu-row">
                      <span class="stats-menu-label">{{
                        tm("stats.outputTokens")
                      }}</span>
                      <span class="stats-menu-value">{{
                        msg.content.agentStats.token_usage.output || 0
                      }}</span>
                    </div>
                    <div
                      v-if="msg.content.agentStats.token_usage.input_cached > 0"
                      class="stats-menu-row"
                    >
                      <span class="stats-menu-label">{{
                        tm("stats.cachedTokens")
                      }}</span>
                      <span class="stats-menu-value">{{
                        msg.content.agentStats.token_usage.input_cached
                      }}</span>
                    </div>
                    <div
                      v-if="msg.content.agentStats.time_to_first_token > 0"
                      class="stats-menu-row"
                    >
                      <span class="stats-menu-label">{{
                        tm("stats.ttft")
                      }}</span>
                      <span class="stats-menu-value">{{
                        formatTTFT(msg.content.agentStats.time_to_first_token)
                      }}</span>
                    </div>
                    <div class="stats-menu-row">
                      <span class="stats-menu-label">{{
                        tm("stats.duration")
                      }}</span>
                      <span class="stats-menu-value">{{
                        formatAgentDuration(msg.content.agentStats)
                      }}</span>
                    </div>
                  </v-card-text>
                </v-card>
              </v-menu>
              <v-btn
                :icon="getCopyIcon(index)"
                size="x-small"
                variant="text"
                class="copy-message-btn"
                :class="{
                  'copy-success': isCopySuccess(index),
                  'copy-failed': isCopyFailure(index),
                }"
                :title="getCopyTitle(index)"
                @click="copyBotMessage(msg.content.message, index)"
              />
              <v-btn
                icon="mdi-reply-outline"
                size="x-small"
                variant="text"
                class="reply-message-btn"
                :title="tm('actions.reply')"
                @click="$emit('replyMessage', msg, index)"
              />

              <!-- Refs Visualization -->
              <ActionRef
                :refs="msg.content.refs"
                @open-refs="openRefsSidebar"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 浮动引用按钮 -->
    <div
      v-if="selectedText.content && selectedText.messageIndex !== null"
      class="selection-quote-button"
      :style="{
        top: selectedText.position.top + 'px',
        left: selectedText.position.left + 'px',
        position: 'fixed',
      }"
    >
      <v-btn
        size="large"
        rounded="xl"
        class="quote-btn"
        :class="{ 'dark-mode': isDark }"
        @click="handleQuoteSelected"
      >
        <v-icon left small> mdi-reply </v-icon>
        引用
      </v-btn>
    </div>
  </div>

  <!-- 图片预览 Overlay -->
  <v-overlay
    v-model="imagePreview.show"
    class="image-preview-overlay"
    @click="closeImagePreview"
  >
    <div class="image-preview-container" @click.stop>
      <img
        :src="imagePreview.url"
        class="preview-image"
        @click="closeImagePreview"
      />
    </div>
  </v-overlay>
</template>

<script lang="ts">
import { defineComponent } from "vue";
import type { PropType } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import {
  enableKatex,
  enableMermaid,
  MarkdownCodeBlockNode,
  setCustomComponents,
} from "markstream-vue";
import "markstream-vue/index.css";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";
import type {
  ChatRecord,
  MessagePart,
  ToolCall,
} from "@/composables/useMessages";
import axios from "@/utils/request";
import { useToast } from "@/utils/toast";
import ReasoningBlock from "./message_list_comps/ReasoningBlock.vue";
import MessagePartsRenderer from "./message_list_comps/MessagePartsRenderer.vue";
import ActionRef from "./message_list_comps/ActionRef.vue";

enableKatex();
enableMermaid();

// 注册 message-list 专用组件：Shiki 代码块渲染（RefNode 映射已移除，若需要引用节点请在模板中直接使用组件）
setCustomComponents("message-list", {
  code_block: MarkdownCodeBlockNode,
});

export default defineComponent({
  name: "MessageList",
  components: {
    ReasoningBlock,
    MessagePartsRenderer,
    ActionRef,
  },
  provide() {
    return {
      isDark: this.isDark,
      webSearchResults: () => this.webSearchResults,
    };
  },
  props: {
    messages: {
      type: Array as PropType<ChatRecord[]>,
      required: true,
    },
    isDark: {
      type: Boolean,
      default: false,
    },
    isStreaming: {
      type: Boolean,
      default: false,
    },
    isLoadingMessages: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["openImagePreview", "replyMessage", "replyWithText", "openRefs"],
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n("features/chat");
    const toast = useToast();

    return {
      t,
      tm,
      toast,
    };
  },
  data() {
    return {
      copiedMessages: new Set(),
      copyFailedMessages: new Set(),
      isUserNearBottom: true,
      scrollThreshold: 1,
      scrollTimer: null as number | null,
      expandedReasoning: new Set(), // Track which reasoning blocks are expanded
      downloadingFiles: new Set<string>(), // Track which files are being downloaded
      elapsedTimeTimer: null as number | null, // Timer for updating elapsed time
      currentTime: Date.now() / 1000, // Current time for elapsed time calculation
      // 选中文本相关状态
      selectedText: {
        content: "",
        messageIndex: null as number | null,
        position: { top: 0, left: 0 },
      },
      // 图片预览
      imagePreview: {
        show: false,
        url: "",
      },
      // Web search results mapping: { 'uuid.idx': { url, title, snippet } }
      webSearchResults: {},
      isUnmounted: false,
    };
  },
  async mounted() {
    this.initCodeCopyButtons();
    this.initImageClickEvents();
    this.addScrollListener();
    this.scrollToBottom();
    this.startElapsedTimeTimer();
    this.extractWebSearchResults();
  },
  updated() {
    if (this.isUnmounted) return;
    this.initCodeCopyButtons();
    this.initImageClickEvents();
    if (this.isUserNearBottom) {
      this.scrollToBottom();
    }
    this.extractWebSearchResults();
  },
  methods: {
    // 从消息中提取 web_search_tavily 的搜索结果
    extractWebSearchResults(): void {
      const results: Record<
        string,
        { url: string; title: string; snippet: string }
      > = {};

      this.messages.forEach((msg: ChatRecord) => {
        if (msg.content.type !== "bot" || !Array.isArray(msg.content.message)) {
          return;
        }

        msg.content.message.forEach((part: MessagePart) => {
          if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) {
            return;
          }

          part.tool_calls.forEach((toolCall: ToolCall) => {
            if (toolCall.name !== "web_search_tavily" || !toolCall.result) {
              return;
            }

            try {
              const resultData = (
                typeof toolCall.result === "string"
                  ? JSON.parse(toolCall.result)
                  : toolCall.result
              ) as {
                results?: Array<{
                  index: string;
                  url: string;
                  title: string;
                  snippet: string;
                }>;
              };

              if (resultData.results && Array.isArray(resultData.results)) {
                resultData.results.forEach((item) => {
                  if (item.index) {
                    results[item.index] = {
                      url: item.url,
                      title: item.title,
                      snippet: item.snippet,
                    };
                  }
                });
              }
            } catch (e) {
              console.error("Failed to parse web search result:", e);
            }
          });
        });
      });

      this.webSearchResults = results;
    },

    // 处理文本选择
    handleTextSelection(): void {
      const selection = window.getSelection();
      if (!selection) return;
      const selectedText = selection.toString();

      if (!selectedText.trim()) {
        this.selectedText.content = "";
        this.selectedText.messageIndex = null;
        return;
      }

      if (selection.rangeCount === 0) return;
      const range = selection.getRangeAt(0);
      const startContainer = range.startContainer;
      let messageItem: HTMLElement | null = null;
      let node: HTMLElement | null = startContainer.parentElement;

      while (node && !node.classList.contains("message-item")) {
        node = node.parentElement;
      }

      messageItem = node;

      if (!messageItem) {
        this.selectedText.content = "";
        this.selectedText.messageIndex = null;
        return;
      }

      const messageItems = (
        this.$refs.messageContainer as HTMLElement | null
      )?.querySelectorAll(".message-item");
      let messageIndex = -1;
      if (messageItems) {
        for (let i = 0; i < messageItems.length; i++) {
          if (messageItems[i] === messageItem) {
            messageIndex = i;
            break;
          }
        }
      }

      if (messageIndex === -1) {
        this.selectedText.content = "";
        this.selectedText.messageIndex = null;
        return;
      }

      const rect = selection.getRangeAt(0).getBoundingClientRect();

      this.selectedText.content = selectedText;
      this.selectedText.messageIndex = messageIndex;
      this.selectedText.position = {
        top: Math.max(0, rect.bottom + 5),
        left: Math.max(0, (rect.left + rect.right) / 2),
      };
    },

    // 处理引用选中的文本
    handleQuoteSelected(): void {
      if (this.selectedText.messageIndex === null) return;

      const msg: ChatRecord | undefined =
        this.messages[this.selectedText.messageIndex];
      if (!msg || !msg.id) return;

      this.$emit("replyWithText", {
        messageId: msg.id,
        selectedText: this.selectedText.content,
        messageIndex: this.selectedText.messageIndex,
      });

      this.selectedText.content = "";
      this.selectedText.messageIndex = null;
      window.getSelection()?.removeAllRanges();
    },

    // 检查 message 中是否有音频
    hasAudio(messageParts: MessagePart[]): boolean {
      if (!Array.isArray(messageParts)) return false;
      return messageParts.some(
        (part) => part.type === "record" && part.embedded_url,
      );
    },

    // 获取被引用消息的内容
    getReplyContent(messageId: string | number | undefined): string {
      const replyMsg = this.messages.find(
        (m: ChatRecord) => m.id === messageId,
      );
      if (!replyMsg) {
        return this.tm("reply.notFound");
      }
      let content = "";
      if (Array.isArray(replyMsg.content.message)) {
        const textParts = replyMsg.content.message
          .filter((part: MessagePart) => part.type === "plain" && !!part.text)
          .map((part: MessagePart) => part.text || "");
        content = textParts.join("");
      }
      // 截断过长内容
      if (content.length > 50) {
        content = content.substring(0, 50) + "...";
      }
      return content || "[媒体内容]";
    },

    // 滚动到指定消息
    scrollToMessage(messageId: string | number | undefined): void {
      const msgIndex = this.messages.findIndex(
        (m: ChatRecord) => m.id === messageId,
      );
      if (msgIndex === -1) return;

      const container = this.$refs.messageContainer as HTMLElement | null;
      const messageItems = container?.querySelectorAll(".message-item");
      if (messageItems && messageItems[msgIndex]) {
        messageItems[msgIndex].scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
        (messageItems[msgIndex] as HTMLElement).classList.add(
          "highlight-message",
        );
        setTimeout(() => {
          (messageItems[msgIndex] as HTMLElement).classList.remove(
            "highlight-message",
          );
        }, 2000);
      }
    },

    // Toggle reasoning expansion state
    toggleReasoning(messageIndex: number): void {
      if (this.expandedReasoning.has(messageIndex)) {
        this.expandedReasoning.delete(messageIndex);
      } else {
        this.expandedReasoning.add(messageIndex);
      }
      this.expandedReasoning = new Set(this.expandedReasoning);
    },

    // Check if reasoning is expanded
    isReasoningExpanded(messageIndex: number): boolean {
      return this.expandedReasoning.has(messageIndex);
    },

    // 下载文件
    async downloadFile(file: {
      attachment_id?: string;
      filename?: string;
    }): Promise<void> {
      if (!file.attachment_id) return;

      this.downloadingFiles.add(file.attachment_id);
      this.downloadingFiles = new Set(this.downloadingFiles);

      try {
        const response = await axios.get(
          `/api/chat/get_attachment?attachment_id=${file.attachment_id}`,
          {
            responseType: "blob",
          },
        );

        const url = URL.createObjectURL(response.data);
        const a = document.createElement("a");
        a.href = url;
        a.download = file.filename || "file";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 100);
      } catch (err) {
        console.error("Download file failed:", err);
      } finally {
        this.downloadingFiles.delete(file.attachment_id);
        this.downloadingFiles = new Set(this.downloadingFiles);
      }
    },

    // 复制代码到剪贴板
    tryExecCommandCopy(text: string): boolean {
      let textArea: HTMLTextAreaElement | null = null;
      try {
        textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const ok = document.execCommand("copy");
        return ok;
      } catch (_) {
        return false;
      } finally {
        try {
          textArea?.remove?.();
        } catch (_) {
          // ignore cleanup errors
        }
      }
    },

    async copyTextToClipboard(
      text: string,
    ): Promise<{ ok: boolean; method: string; error?: unknown }> {
      if (this.tryExecCommandCopy(text)) {
        return { ok: true, method: "execCommand" };
      }

      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          return { ok: true, method: "clipboard" };
        } catch (error) {
          return { ok: false, method: "clipboard", error };
        }
      }

      return { ok: false, method: "unavailable" };
    },

    async copyWithFeedback(
      text: string,
      messageIndex: number | null = null,
    ): Promise<{ ok: boolean; method: string; error?: unknown }> {
      const result = await this.copyTextToClipboard(text);
      const ok = !!result?.ok;

      if (messageIndex !== null && messageIndex !== undefined) {
        if (ok) this.showCopySuccess(messageIndex);
        else this.showCopyFailure(messageIndex);
      }

      if (ok) {
        this.toast?.success?.(this.t("core.common.copied"));
      } else {
        this.toast?.error?.(this.t("core.common.copyFailed"));
      }

      return result;
    },

    buildCopyTextFromParts(messageParts: MessagePart[] | string): string {
      if (typeof messageParts === "string") {
        return messageParts.trim();
      }
      if (!Array.isArray(messageParts)) {
        return "";
      }

      const textContents = messageParts
        .filter(
          (part: unknown): part is MessagePart =>
            part != null &&
            typeof part === "object" &&
            (part as MessagePart).type === "plain" &&
            !!(part as MessagePart).text,
        )
        .map((part: MessagePart) => part.text || "");

      let textToCopy = textContents.join("\n");

      const imageCount = messageParts.filter(
        (part: MessagePart) => part?.type === "image" && part.embedded_url,
      ).length;
      if (imageCount > 0) {
        if (textToCopy) textToCopy += "\n\n";
        textToCopy += `[包含 ${imageCount} 张图片]`;
      }

      const hasAudio = messageParts.some(
        (part: MessagePart) => part?.type === "record" && part.embedded_url,
      );
      if (hasAudio) {
        if (textToCopy) textToCopy += "\n\n";
        textToCopy += "[包含音频内容]";
      }

      return String(textToCopy || "").trim();
    },

    async copyCodeToClipboard(
      code: string,
    ): Promise<{ ok: boolean; method: string }> {
      const text = String(code ?? "");
      if (!text) return { ok: false, method: "empty" };
      return await this.copyWithFeedback(text, null);
    },

    // 复制bot消息到剪贴板
    async copyBotMessage(
      messageParts: MessagePart[],
      messageIndex: number,
    ): Promise<void> {
      let textToCopy = this.buildCopyTextFromParts(messageParts);
      if (!textToCopy) textToCopy = "[媒体内容]";
      await this.copyWithFeedback(textToCopy, messageIndex);
    },

    // 显示复制成功提示
    showCopySuccess(messageIndex: number): void {
      if (this.copyFailedMessages.has(messageIndex)) {
        this.copyFailedMessages.delete(messageIndex);
        this.copyFailedMessages = new Set(this.copyFailedMessages);
      }
      this.copiedMessages.add(messageIndex);
      this.copiedMessages = new Set(this.copiedMessages);

      setTimeout(() => {
        this.copiedMessages.delete(messageIndex);
        this.copiedMessages = new Set(this.copiedMessages);
      }, 2000);
    },

    // 显示复制失败提示
    showCopyFailure(messageIndex: number): void {
      if (this.copiedMessages.has(messageIndex)) {
        this.copiedMessages.delete(messageIndex);
        this.copiedMessages = new Set(this.copiedMessages);
      }
      this.copyFailedMessages.add(messageIndex);
      this.copyFailedMessages = new Set(this.copyFailedMessages);

      setTimeout(() => {
        this.copyFailedMessages.delete(messageIndex);
        this.copyFailedMessages = new Set(this.copyFailedMessages);
      }, 2000);
    },

    // 获取复制按钮图标
    getCopyIcon(messageIndex: number): string {
      if (this.copiedMessages.has(messageIndex)) return "mdi-check";
      if (this.copyFailedMessages.has(messageIndex))
        return "mdi-alert-circle-outline";
      return "mdi-content-copy";
    },

    // 检查是否为复制成功状态
    isCopySuccess(messageIndex: number): boolean {
      return this.copiedMessages.has(messageIndex);
    },

    // 检查是否为复制失败状态
    isCopyFailure(messageIndex: number): boolean {
      return this.copyFailedMessages.has(messageIndex);
    },

    // 获取复制按钮提示文本
    getCopyTitle(messageIndex: number): string {
      if (this.isCopySuccess(messageIndex)) return this.t("core.common.copied");
      if (this.isCopyFailure(messageIndex))
        return this.t("core.common.copyFailed");
      return this.t("core.common.copy");
    },

    // 获取复制图标SVG
    getCopyIconSvg() {
      return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    },

    // 获取成功图标SVG
    getSuccessIconSvg() {
      return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>';
    },

    // 获取失败图标SVG
    getErrorIconSvg() {
      return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="13"></line><circle cx="12" cy="16.5" r="1"></circle></svg>';
    },

    // 初始化代码块复制按钮
    initCodeCopyButtons(): void {
      this.$nextTick(() => {
        if (this.isUnmounted) return;
        const container = this.$refs.messageContainer as HTMLElement | null;
        const codeBlocks = container?.querySelectorAll("pre code") || [];
        codeBlocks.forEach((codeBlock) => {
          const pre = codeBlock.parentElement;
          if (pre && !pre.querySelector(".copy-code-btn")) {
            const button = document.createElement("button");
            button.className = "copy-code-btn";
            button.innerHTML = this.getCopyIconSvg();
            button.title = this.t("core.common.copy");
            button.addEventListener("click", async () => {
              const res = await this.copyCodeToClipboard(
                codeBlock.textContent || "",
              );
              const ok = !!res?.ok;
              button.innerHTML = ok
                ? this.getSuccessIconSvg()
                : this.getErrorIconSvg();
              button.style.color = ok
                ? "rgb(var(--v-theme-success))"
                : "rgb(var(--v-theme-error))";
              button.setAttribute(
                "title",
                this.t(`core.common.${ok ? "copied" : "copyFailed"}`),
              );
              setTimeout(() => {
                button.innerHTML = this.getCopyIconSvg();
                button.style.color = "";
                button.setAttribute("title", this.t("core.common.copy"));
              }, 2000);
            });
            pre.style.position = "relative";
            pre.appendChild(button);
          }
        });
      });
    },

    initImageClickEvents(): void {
      this.$nextTick(() => {
        if (this.isUnmounted) return;
        const images = document.querySelectorAll<HTMLImageElement>(
          ".markdown-content img",
        );
        images.forEach((img: HTMLImageElement) => {
          if (!img.hasAttribute("data-click-enabled")) {
            img.style.cursor = "pointer";
            img.setAttribute("data-click-enabled", "true");
            img.onclick = () => this.openImagePreview(img.src);
          }
        });
      });
    },

    scrollToBottom(): void {
      this.$nextTick(() => {
        if (this.isUnmounted) return;
        const container = this.$refs.messageContainer as HTMLElement | null;
        if (container) {
          container.scrollTop = container.scrollHeight;
          this.isUserNearBottom = true;
        }
      });
    },

    // 添加滚动事件监听器
    addScrollListener(): void {
      const container = this.$refs.messageContainer as HTMLElement | null;
      if (container) {
        container.addEventListener("scroll", this.throttledHandleScroll);
      }
    },

    // 节流处理滚动事件
    throttledHandleScroll(): void {
      if (this.scrollTimer) return;

      this.scrollTimer = setTimeout(() => {
        this.handleScroll();
        this.scrollTimer = null;
      }, 50);
    },

    // 处理滚动事件
    handleScroll(): void {
      const container = this.$refs.messageContainer as HTMLElement | null;
      if (container) {
        const { scrollTop, scrollHeight, clientHeight } = container;
        const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);

        this.isUserNearBottom = distanceFromBottom <= this.scrollThreshold;
      }
    },

    // 组件销毁时移除监听器
    beforeUnmount(): void {
      this.isUnmounted = true;
      const container = this.$refs.messageContainer as HTMLElement | null;
      if (container) {
        container.removeEventListener("scroll", this.throttledHandleScroll);
      }
      if (this.scrollTimer) {
        clearTimeout(this.scrollTimer);
        this.scrollTimer = null;
      }
      if (this.elapsedTimeTimer) {
        clearInterval(this.elapsedTimeTimer);
        this.elapsedTimeTimer = null;
      }
    },

    // 格式化消息时间，支持别名显示
    formatMessageTime(dateStr: string): string {
      if (!dateStr) return "";

      const date = new Date(dateStr);
      const now = new Date();

      const dateDay = new Date(
        date.getFullYear(),
        date.getMonth(),
        date.getDate(),
      );
      const todayDay = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate(),
      );
      const yesterdayDay = new Date(todayDay);
      yesterdayDay.setDate(yesterdayDay.getDate() - 1);

      const hours = date.getHours().toString().padStart(2, "0");
      const minutes = date.getMinutes().toString().padStart(2, "0");
      const timeStr = `${hours}:${minutes}`;

      if (dateDay.getTime() === todayDay.getTime()) {
        return `${this.tm("time.today")} ${timeStr}`;
      } else if (dateDay.getTime() === yesterdayDay.getTime()) {
        return `${this.tm("time.yesterday")} ${timeStr}`;
      } else {
        const month = (date.getMonth() + 1).toString().padStart(2, "0");
        const day = date.getDate().toString().padStart(2, "0");
        return `${month}-${day} ${timeStr}`;
      }
    },

    // Start timer for updating elapsed time
    startElapsedTimeTimer(): void {
      let _fastUpdateCount = 0;
      const fastUpdateInterval = 12;
      const slowUpdateInterval = 1000;

      const updateTime = () => {
        this.currentTime = Date.now() / 1000;

        const hasRunningToolCalls = this.messages.some(
          (msg: ChatRecord) =>
            Array.isArray(msg.content.message) &&
            msg.content.message.some(
              (part: MessagePart) =>
                part.type === "tool_call" &&
                part.tool_calls?.some((tc: ToolCall) => !tc.finished_ts),
            ),
        );

        if (hasRunningToolCalls) {
          const hasSubSecondToolCall = this.messages.some(
            (msg: ChatRecord) =>
              Array.isArray(msg.content.message) &&
              msg.content.message.some(
                (part: MessagePart) =>
                  part.type === "tool_call" &&
                  part.tool_calls?.some(
                    (tc: ToolCall) =>
                      !tc.finished_ts && this.currentTime - (tc.ts ?? 0) < 1,
                  ),
              ),
          );

          if (hasSubSecondToolCall) {
            _fastUpdateCount++;
            this.elapsedTimeTimer = setTimeout(updateTime, fastUpdateInterval);
          } else {
            this.elapsedTimeTimer = setTimeout(updateTime, slowUpdateInterval);
          }
        } else {
          this.elapsedTimeTimer = setTimeout(updateTime, slowUpdateInterval);
        }
      };

      updateTime();
    },

    // Get elapsed time string for a tool call
    getElapsedTime(startTs: number): string {
      const elapsed = this.currentTime - startTs;
      return this.formatDuration(elapsed);
    },

    // Format duration in seconds to human readable string
    formatDuration(seconds: number): string {
      if (seconds < 1) {
        return `${Math.round(seconds * 1000)}ms`;
      } else if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
      } else {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${minutes}m ${secs}s`;
      }
    },

    // Get input tokens (input_other + input_cached)
    getInputTokens(
      tokenUsage:
        | { input_other?: number; input_cached?: number }
        | null
        | undefined,
    ): number {
      if (!tokenUsage) return 0;
      return (tokenUsage.input_other || 0) + (tokenUsage.input_cached || 0);
    },

    // Format agent duration
    formatAgentDuration(
      agentStats: { start_time: number; end_time: number } | null | undefined,
    ): string {
      if (!agentStats) return "";
      const duration = agentStats.end_time - agentStats.start_time;
      return this.formatDuration(duration);
    },

    // Format time to first token
    formatTTFT(ttft: number | null | undefined): string {
      if (!ttft || ttft <= 0) return "";
      return this.formatDuration(ttft);
    },

    // 打开图片预览
    openImagePreview(url: string): void {
      this.imagePreview.url = url;
      this.imagePreview.show = true;
    },

    // 关闭图片预览
    closeImagePreview(): void {
      this.imagePreview.show = false;
      setTimeout(() => {
        this.imagePreview.url = "";
      }, 300);
    },

    // Open refs sidebar
    openRefsSidebar(refs: unknown): void {
      this.$emit("openRefs", refs);
    },
  },
});
</script>

<style scoped>
:deep(.hr-node) {
  margin-top: 1.25rem;
  margin-bottom: 1.25rem;
  opacity: 0.5;
  border-top-width: 0.3px;
}

:deep(.paragraph-node) {
  margin: 0.5rem 0;
  line-height: 1.7;
  margin-block: 1rem;
}

:deep(.list-node) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
}

:deep(.mermaid-block-header) {
  gap: 8px;
}

:deep(code.bg-secondary) {
  background-color: #ececec !important;
  color: #0d0d0d !important;
}

:deep(code.rounded) {
  border-radius: 6px !important;
}

.messages-container.is-dark :deep(code.bg-secondary) {
  background-color: #424242 !important;
  color: #ffffff !important;
}

.messages-container.is-dark :deep(.code-block-container) {
  background-color: #1f1f1f !important;
}

/* 基础动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(0);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.messages-container {
  height: 100%;
  max-height: 100%;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  padding: 16px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  position: relative;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10;
  background-color: rgba(255, 255, 255, 0.7);
  transition: opacity 0.3s ease;
}

.loading-overlay.is-dark {
  background-color: rgba(30, 30, 30, 0.7);
}

.message-list.loading-blur {
  opacity: 0.5;
  transition: opacity 0.3s ease;
  pointer-events: none;
}

.message-bubble {
  padding: 2px 16px;
  border-radius: 12px;
}

.loading-container {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  margin-top: 8px;
}

.loading-text {
  font-size: 14px;
  color: var(--v-theme-on-surface-variant);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.6;
  }

  50% {
    opacity: 1;
  }
}

@media (max-width: 768px) {
  .messages-container {
    padding: 8px;
  }

  .message-list {
    max-width: 100%;
  }

  .message-item {
    padding: 0;
  }

  .message-bubble {
    padding: 2px 12px;
  }

  .bot-message {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    width: 100%;
  }

  .bot-message-content {
    max-width: 100% !important;
    width: 100% !important;
  }

  .bot-bubble {
    width: 100% !important;
    max-width: 100% !important;
  }

  .bot-avatar {
    margin-left: 4px;
  }
}

/* 消息列表样式 */
.message-list {
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.message-item {
  margin-bottom: 12px;
  animation: fadeIn 0.3s ease-out;
}

.user-message {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  gap: 12px;
}

.bot-message {
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
  gap: 12px;
}

.bot-message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: 80%;
  position: relative;
}

.message-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
  margin-left: 16px;
}

/* 最后一条消息始终显示操作按钮 */
.message-item:last-child .message-actions {
  opacity: 1;
}

.message-time {
  font-size: 12px;
  color: var(--v-theme-on-surface-variant);
  opacity: 0.7;
  white-space: nowrap;
}

/* Agent Stats Info Icon */
.stats-info-icon {
  margin-left: 6px;
  color: var(--v-theme-on-surface-variant);
  opacity: 0.6;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.stats-info-icon:hover {
  opacity: 1;
}

.bot-message:hover .message-actions {
  opacity: 1;
}

.copy-message-btn {
  opacity: 0.6;
  transition: all 0.2s ease;
  color: var(--v-theme-secondary);
}

.copy-message-btn:hover {
  opacity: 1;
  background-color: rgba(103, 58, 183, 0.1);
}

.copy-message-btn.copy-success {
  color: rgb(var(--v-theme-success));
  opacity: 1;
}

.copy-message-btn.copy-success:hover {
  color: rgb(var(--v-theme-success));
  background-color: rgba(var(--v-theme-success), 0.1);
}

.copy-message-btn.copy-failed {
  color: rgb(var(--v-theme-error));
  opacity: 1;
}

.copy-message-btn.copy-failed:hover {
  color: rgb(var(--v-theme-error));
  background-color: rgba(var(--v-theme-error), 0.1);
}

.reply-message-btn {
  opacity: 0.6;
  transition: all 0.2s ease;
  color: var(--v-theme-secondary);
}

.reply-message-btn:hover {
  opacity: 1;
  background-color: rgba(103, 58, 183, 0.1);
}

/* 引用消息显示样式 */
.reply-quote {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin-bottom: 8px;
  background-color: rgba(103, 58, 183, 0.08);
  border-left: 3px solid var(--v-theme-secondary);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.reply-quote:hover {
  background-color: rgba(103, 58, 183, 0.15);
}

.reply-quote-icon {
  color: var(--v-theme-secondary);
  flex-shrink: 0;
}

.reply-quote-text {
  font-size: 13px;
  color: var(--v-theme-on-surface-variant);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 消息高亮动画 */
.highlight-message {
  animation: highlightPulse 2s ease-out;
}

@keyframes highlightPulse {
  0% {
    background-color: rgba(103, 58, 183, 0.3);
  }

  100% {
    background-color: transparent;
  }
}

.user-bubble {
  color: var(--v-theme-on-surface);
  padding: 12px 18px;
  font-size: 15px;
  max-width: 60%;
  border-radius: 1.5rem;
}

.bot-bubble {
  border: 1px solid var(--v-theme-border);
  color: var(--v-theme-on-surface);
  font-size: 16px;
  max-width: 100%;
  padding-left: 12px;
}

.user-avatar,
.bot-avatar {
  align-self: flex-start;
  margin-top: 12px;
}

/* 附件样式 */
.image-attachments {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.image-attachment {
  position: relative;
  display: inline-block;
}

.attached-image {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 12px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s ease;
}

.audio-attachment {
  margin-top: 8px;
  min-width: 250px;
}

/* 包含音频的消息气泡最小宽度 */
.message-bubble.has-audio {
  min-width: 280px;
}

.audio-player {
  width: 100%;
  height: 36px;
  border-radius: 18px;
}

/* 文件附件样式 */
.file-attachments,
.embedded-files {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-attachment,
.embedded-file {
  display: flex;
  align-items: center;
}

.file-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background-color: rgba(var(--v-theme-primary), 0.08);
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
  border-radius: 8px;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s ease;
  max-width: 300px;
}

.file-link-download {
  cursor: pointer;
}

.download-icon {
  margin-left: 4px;
  opacity: 0.7;
}

.file-icon {
  flex-shrink: 0;
  color: rgb(var(--v-theme-primary));
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-link.is-dark:hover {
  background-color: rgba(255, 255, 255, 0.1) !important;
  border-color: rgba(255, 255, 255, 0.2) !important;
}

/* 动画类 */
.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

/* 浮动引用按钮样式 */
.selection-quote-button {
  position: fixed;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: all;
}

.quote-btn {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  font-size: 14px;
  padding: 4px 24px;
  background-color: #f6f4fa !important;
  color: #333333 !important;
}

.quote-btn:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  background-color: #f6f4fa !important;
}

/* 深色主题 */
.quote-btn.dark-mode {
  background-color: #2d2d2d !important;
  color: #ffffff !important;
}
</style>

<style>
.markdown-content {
  max-width: 100%;
  line-height: 1.6;
}

/* Bubble text: hardcoded for debugging - #E2E2E7 = BlueBusinessDark primaryText */
.bubble-text {
  color: inherit;
}

/* Stats Menu 样式 */
.stats-menu-card {
  border-radius: 8px !important;
  min-width: 160px;
}

.stats-menu-content {
  padding: 12px 16px !important;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stats-menu-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.stats-menu-label {
  font-size: 13px;
  color: var(--v-theme-on-surface-variant);
}

.stats-menu-value {
  font-size: 13px;
  font-weight: 600;
  font-family: "Fira Code", "Consolas", monospace;
  color: var(--v-theme-on-surface);
}

/* 图片预览样式 */
.image-preview-overlay {
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-preview-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.preview-image {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  cursor: pointer;
}

.close-preview-btn {
  position: fixed;
  top: 20px;
  right: 20px;
}
</style>

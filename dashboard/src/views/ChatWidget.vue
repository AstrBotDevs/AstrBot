<script lang="ts">
import { defineComponent, nextTick, ref } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import RefNode from '@/components/chat/message_list_comps/RefNode.vue';
import ThemeAwareMarkdownCodeBlock from '@/components/shared/ThemeAwareMarkdownCodeBlock.vue';
import { setCustomComponents } from 'markstream-vue';
import { type MessagePart, useMessages } from '@/composables/useMessages';
import type { Session } from '@/composables/useSessions';
import { useMediaHandling } from '@/composables/useMediaHandling';
import { useModuleI18n } from '@/i18n/composables';

export default defineComponent({
  name: 'PageChatWidget',
  setup() {
    const { tm } = useModuleI18n('features/chat');
    setCustomComponents('chat-message', {
      ref: RefNode,
      code_block: ThemeAwareMarkdownCodeBlock,
    });
    const currSessionId = ref('');
    const currentSession = ref<Session | null>(null);
    const shouldStickToBottom = ref(true);
    const messagesContainer = ref<HTMLElement | null>(null);

    function scrollToBottom() {
      nextTick(() => {
        const container = messagesContainer.value;
        if (!shouldStickToBottom.value || !container) return;
        container.scrollTop = container.scrollHeight;
      });
    }

    // 检测到用户操作后，取消自动滚动
    window.addEventListener(
      'wheel',
      () => {
        const container = messagesContainer.value;
        shouldStickToBottom.value = !!(container && container.scrollHeight - container.scrollTop == container.clientHeight);
      },
      { passive: true },
    );
    window.addEventListener('keydown', (e) => {
      const scrollKeys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Space', 'Home', 'End'];
      if (scrollKeys.includes(e.code)) {
        const container = messagesContainer.value;
        shouldStickToBottom.value = shouldStickToBottom.value = !!(container && container.scrollHeight - container.scrollTop == container.clientHeight);
      }
    });

    const {
      stagedFiles,
      stagedImagesUrl,
      stagedAudioUrl,
      stagedNonImageFiles,
      processAndUploadImage,
      processAndUploadFile,
      handlePaste,
      removeImage,
      removeAudio,
      removeFile,
      clearStaged,
      cleanupMediaCache,
      chatWidgetSetApiPackage,
    } = useMediaHandling();
    const { sending, activeMessages, isSessionRunning, createLocalExchange, sendMessageStream, stopSession, widgetSetApiPackage, loadSessionMessages } = useMessages({
      currentSessionId: currSessionId,
      onStreamUpdate: () => {
        scrollToBottom();
      },
    });

    return {
      tm,
      customizer: useCustomizerStore(),
      currSessionId,
      currentSession,
      shouldStickToBottom,
      inputRef: ref<InstanceType<typeof ChatInput> | null>(null),
      scrollToBottom,
      messagesContainer,

      stagedFiles,
      stagedImagesUrl,
      stagedAudioUrl,
      stagedNonImageFiles,
      processAndUploadImage,
      processAndUploadFile,
      handlePaste,
      removeImage,
      removeAudio,
      removeFile,
      clearStaged,
      cleanupMediaCache,
      chatWidgetSetApiPackage,

      sending,
      activeMessages,
      isSessionRunning,
      createLocalExchange,
      sendMessageStream,
      stopSession,
      widgetSetApiPackage,
      loadSessionMessages,
    };
  },
  components: {
    ChatMessageList,
    ChatInput,
  },
  data() {
    return {
      api_package: {
        appid: '',
        data: '',
        noise: '',
        expiry_date: '',
        signature: '',
      },
      de_package: {} as Record<any, any>,
      pageStatus: 'loading' as 'loading' | 'success' | 'error',
      pageMessage: '',
      welcomeTitle: '',
      attachmentEnabled: true,
      enableStreaming: true,
      draft: '',
      transportMode: 'see' as 'see' | 'websocket',
    };
  },
  computed: {
    isDark() {
      return this.customizer.uiTheme === 'PurpleThemeDark';
    },
  },
  watch:{
    activeMessages: {
      deep: true,
      handler: function() {
        setTimeout(() => { this.scrollToBottom(); }, 1000);
      }
    }
  },
  created() {
    try {
      this.api_package.appid = (this.$route.query?.appid as string) ?? '';
      this.api_package.data = (this.$route.query?.data as string) ?? '';
      this.api_package.noise = (this.$route.query?.noise as string) ?? '';
      this.api_package.expiry_date = (this.$route.query?.expiry_date as string) ?? '';
      this.api_package.signature = (this.$route.query?.signature as string) ?? '';
      if (!this.api_package.appid || !this.api_package.data || !this.api_package.noise || !this.api_package.expiry_date || !this.api_package.signature) {
        throw new Error('api request args is miss');
      }
      // 临时解包数据，实际签名验由后端完成
      this.de_package = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(this.api_package.data), (c) => c.charCodeAt(0))));
      // 检查必须的参数
      if (!this.de_package.session_id) throw new Error('args `session_id` is miss');
      if (!this.de_package.username) throw new Error('args `username` is miss');
      if (!this.de_package.config_id) throw new Error('args `config_id` is miss');
      if (!this.de_package.selected_provider) throw new Error('args `selected_provider` is miss');
      // 填充参数
      this.attachmentEnabled = this.de_package.file_upload === true;
      this.welcomeTitle = (this.$route.query?.welcomeTitle as string) ?? '';
      this.currSessionId = this.de_package.session_id;
    } catch (err) {
      this.pageMessage = err instanceof Error ? err.message : String(err);
      this.pageStatus = 'error';
      console.error(err);
    }
  },
  mounted() {
    this.inputRef?.focusInput();
    this.chatWidgetSetApiPackage(this.api_package);
    this.widgetSetApiPackage(this.api_package);
    this.loadSessionMessages(this.de_package?.session_id ?? '')
      .then()
      .finally(() => {
        this.pageStatus = 'success';
        setTimeout(() => { this.scrollToBottom(); }, 1000);
      });
  },
  methods: {
    async sendCurrentMessage() {
      if (!this.draft.trim() && !this.stagedFiles.length) return;
      this.shouldStickToBottom = true;
      const text = this.draft.trim();
      const parts = this.buildOutgoingParts(text);
      const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const { botRecord } = this.createLocalExchange({ sessionId: this.de_package.session_id, messageId, parts });

      this.clearStaged({ revokeUrls: false });
      this.scrollToBottom();

      this.sendMessageStream({
        sessionId: this.de_package.session_id,
        messageId,
        parts,
        transport: 'sse',
        enableStreaming: this.enableStreaming,
        selectedProvider: '',
        selectedModel: '',
        botRecord,
      });

      // 等半秒后再清理，有些浏览器清理太快会导致图片显示异常
      setTimeout(() => {
        this.draft = '';
        this.clearStaged({ revokeUrls: false });
      }, 500);
    },
    buildOutgoingParts(text: string): MessagePart[] {
      const parts: MessagePart[] = [];
      if (text) {
        parts.push({ type: 'plain', text });
      }
      this.stagedFiles.forEach((file) => {
        parts.push({
          type: file.type,
          attachment_id: file.attachment_id,
          filename: file.filename,
          embedded_url: file.url,
        });
      });
      return parts;
    },
    async handleFilesSelected(files: FileList) {
      const selectedFiles = Array.from(files || []);
      for (const file of selectedFiles) {
        if (file.type.startsWith('image/')) {
          await this.processAndUploadImage(file, this.currSessionId);
        } else {
          await this.processAndUploadFile(file, this.currSessionId);
        }
      }
    },
    async stopCurrentSession() {
      if (!this.currSessionId) return;
      await this.stopSession(this.currSessionId);
    },
  },
});
</script>

<style lang="scss">
.page-widget {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  position: absolute;
  overflow: auto;

  .api-error {
    font-size: 18px;
    color: #e83838;
    margin: 20px auto;
  }
  .center-state {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;

    .welcome-title {
      font-size: 24px;
      font-weight: 700;
    }
  }
  .message-list-content {
    padding: 14px;
    flex: 1;
  }
  .user-input-box {
    position: sticky;
    bottom: 0;
    z-index: 10;
    padding-bottom: 10px;

    .input-container {
      background: rgb(255 255 255 / 0.9);
      backdrop-filter: blur(50px);
    }
  }

  @media (max-width: 768px) {
    .user-input-box {
      padding-bottom: 0;
    }
  }
}
</style>

<template>
  <v-app :theme="customizer.uiTheme">
    <div class="page-widget" ref="messagesContainer">
      <div class="center-state" v-if="pageStatus == 'loading'">
        <v-progress-circular indeterminate size="28" width="3" />
      </div>
      <!-- 异常信息 -->
      <div v-else-if="pageStatus == 'error'" class="api-error">{{ pageMessage }}</div>
      <!-- 功能 -->
      <template v-else-if="pageStatus == 'success'">
        <div v-if="activeMessages?.length" class="message-list-content">
          <ChatMessageList
            :messages="activeMessages"
            :is-dark="isDark"
            :is-streaming="Boolean(currSessionId && isSessionRunning(currSessionId))"
            :enable-edit="false"
            :enable-regenerate="false"
            :enable-copy="true"
            :manage-refs-sidebar="false"
          />
        </div>
        <!-- 欢迎页 -->
        <div v-else class="center-state">
          <div class="welcome-title">
            {{ welcomeTitle ? welcomeTitle : tm('welcome.title') }}
          </div>
        </div>
        <!-- 输入框 -->
        <div class="user-input-box">
          <ChatInput
            ref="inputRef"
            v-model:prompt="draft"
            :staged-images-url="stagedImagesUrl"
            :staged-audio-url="stagedAudioUrl"
            :staged-files="stagedNonImageFiles"
            :disabled="sending"
            :enable-streaming="enableStreaming"
            :is-recording="false"
            :is-running="Boolean(currSessionId && isSessionRunning(currSessionId))"
            :session-id="currSessionId || null"
            :current-session="currentSession"
            :config-id="de_package.config_id"
            send-shortcut="enter"
            @send="sendCurrentMessage"
            @stop="stopCurrentSession"
            @toggle-streaming="enableStreaming = !enableStreaming"
            @remove-image="removeImage"
            @remove-audio="removeAudio"
            @remove-file="removeFile"
            @paste-image="(e: ClipboardEvent) => handlePaste(e, currSessionId)"
            @file-select="handleFilesSelected"
            :uploadFilesDisabled="!attachmentEnabled"
            :providerModelMenuDisabled="true"
            :config-selector-disabled="true"
            :recordDisabled="!attachmentEnabled"
          />
        </div>
      </template>
    </div>
  </v-app>
</template>

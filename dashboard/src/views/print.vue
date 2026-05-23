<script setup lang="ts">
import "markstream-vue/index.css";
import {MarkdownRender, setCustomComponents} from "markstream-vue";
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import ThreadNode from "@/components/chat/message_list_comps/ThreadNode.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import {onMounted, onUnmounted, ref} from "vue";
import {useCustomizerStore} from '@/stores/customizer';

const customizer = useCustomizerStore();
const customHtmlTags = ref([] as string[]);
const print_content = ref("");

setCustomComponents("chat-message", {
  ref: RefNode,
  thread: ThreadNode,
  code_block: ThemeAwareMarkdownCodeBlock,
});

const handleMessage = (event: any) => {
  if (event.data.type == 'PrintData.Send') {
    print_content.value = event.data.data;
    window.opener.postMessage('PrintData.Ready')
  }
};

onMounted(() => {
  window.addEventListener('message', handleMessage);
});
onUnmounted(() => {
  window.removeEventListener('message', handleMessage);
});
function printPage() {
  window.print();
}
</script>

<template>
  <v-app :theme="customizer.uiTheme" style="height: 100%; width: 100%;">
    <div style="padding: 20px;">
      <MarkdownRender
        custom-id="chat-message"
        :content="print_content"
        :custom-html-tags="customHtmlTags"
        :is-dark="false"
        :typewriter="false"
        :max-live-nodes="0"
    />
    <div class="bottom-print-bar">
      <div>
        <span>推荐打印参数：</span>
        <ol>
          <li>缩放比例：75%</li>
          <li>打印背景</li>
          <li>边距：无</li>
        </ol>
      </div>
      <div class="btn" @click="printPage">打印本页</div>
    </div>
    </div>
  </v-app>
</template>
<style lang="scss">
.bottom-print-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgb(0 0 0 / 0.5);
  padding: 30px;
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: center;
  gap: 40px;
  color: #fff;

  .btn {
    background: #43b48c;
    color: #fff;
    padding: 10px 20px;
    border-radius: 10px;
    cursor: pointer;
  }
}
@media print {
  .bottom-print-bar {
    display: none;
  }
}
</style>
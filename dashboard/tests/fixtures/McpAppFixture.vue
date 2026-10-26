<template>
  <v-app>
    <main style="max-width:760px;margin:40px auto;width:90%">
      <h1>AstrBot interactive tool</h1>
      <ToolCallCard session-id="session" message-id="message" :tool-call="call" @app-draft="append" />
      <label>Message draft
        <textarea aria-label="Message draft" v-model="draft" style="display:block;width:100%;min-height:120px;border:1px solid #bbb;padding:12px" />
      </label>
    </main>
  </v-app>
</template>
<script setup lang="ts">
import { ref } from 'vue';
import ToolCallCard from '../../src/components/chat/message_list_comps/ToolCallCard.vue';
const draft = ref('Existing draft');
const call = {id: 'call', name: 'show_photo_picker', args: {}, result: 'Three sample illustrations', ts: 1, finished_ts: 2, mcp_app: {uri:'ui://photo-picker/index.html'}};
const append = (text: string) => { draft.value += `\n\n${text}`; };
</script>

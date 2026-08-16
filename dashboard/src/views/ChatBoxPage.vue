<script setup>
import Chat from '@/components/chat/Chat.vue';
import { useCustomizerStore } from '@/stores/customizer';
const customizer = useCustomizerStore();
</script>

<template>
  <v-app :theme="customizer.uiTheme" class="chatbox-app">
    <div class="chatbox-app__content">
      <div id="container">
        <Chat :chatbox-mode="true"></Chat>
      </div>
    </div>
  </v-app>
</template>

<style scoped>
.chatbox-app,
.chatbox-app__content,
#container {
  width: 100%;
  min-height: 100%;
}

.chatbox-app__content {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}

#container {
  height: 100dvh;
}
</style>

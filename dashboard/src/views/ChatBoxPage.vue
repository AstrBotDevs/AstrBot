<script setup>
import Chat from '@/components/chat/Chat.vue'
import { useCustomizerStore } from '@/stores/customizer';
const customizer = useCustomizerStore();
</script>

<template>
    <v-app :theme="customizer.uiTheme" style="height: 100%; width: 100%;">
        <div
            style="height: 100%; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
            <div id="container">
                <Chat :chatbox-mode="true"></Chat>
            </div>
        </div>
    </v-app>
</template>

<style scoped>
#container {
    width: 100%;
    height: 100vh;
}
</style>
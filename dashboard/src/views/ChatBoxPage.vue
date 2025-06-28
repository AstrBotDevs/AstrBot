<script setup>
import ChatPage from './ChatPage.vue';
import { useCustomizerStore } from '@/stores/customizer';
const customizer = useCustomizerStore();
</script>

<template>
    <v-app :theme="customizer.uiTheme" style="height: 100%; width: 100%;">
        <div
            style="height: 100%; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
            <div id="container">
                <ChatPage :chatbox-mode="true"></ChatPage>
            </div>
        </div>
    </v-app>
</template>

<style scoped>
#container {
    width: 100%;
    height: 100%;
}

@media (min-width: 768px) {
    #container {
        min-width: 600px;
        min-height: 370px;
        max-width: 1100px;
        max-height: 860px;
        padding: 36px;
    }
}

@media (max-width: 767px) {
    #container {
        width: 100%;
        height: 100%;
        padding: 0;
    }
}
</style>
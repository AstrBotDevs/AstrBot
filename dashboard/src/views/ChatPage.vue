<script setup>
import Chat from '@/components/chat/Chat.vue'
</script>

<template>
    <div class="chat-container">
        <Chat />
    </div>
</template>

<style scoped>
.chat-container {
    height: 100%;
    min-height: calc(100vh - 66px);
    overflow: hidden;
}
</style>

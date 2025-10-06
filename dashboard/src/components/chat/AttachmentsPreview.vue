<template>
  <div class="attachments-preview" v-if="images.length > 0 || audio">
    <div v-for="(img, index) in images" :key="index" class="image-preview">
      <img :src="img" class="preview-image" />
      <v-btn @click="$emit('remove:image', index)" class="remove-attachment-btn" icon="mdi-close" size="small" color="error" variant="text" />
    </div>

    <div v-if="audio" class="audio-preview">
      <v-chip color="deep-purple-lighten-4" class="audio-chip">
        <v-icon start icon="mdi-microphone" size="small"></v-icon>
        {{ recordingText }}
      </v-chip>
      <v-btn @click="$emit('remove:audio')" class="remove-attachment-btn" icon="mdi-close" size="small" color="error" variant="text" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ images: string[]; audio: string | null; recordingText: string }>();
defineEmits<{ (e: 'remove:image', index: number): void; (e: 'remove:audio'): void }>();
</script>

<style scoped>
.attachments-preview {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  max-width: 900px;
  margin: 8px auto 0;
  flex-wrap: wrap;
}
.image-preview,
.audio-preview {
  position: relative;
  display: inline-flex;
}
.preview-image {
  width: 60px;
  height: 60px;
  object-fit: cover;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}
.audio-chip {
  height: 36px;
  border-radius: 18px;
}
.remove-attachment-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  opacity: 0.8;
  transition: opacity 0.2s;
}
.remove-attachment-btn:hover {
  opacity: 1;
}
</style>

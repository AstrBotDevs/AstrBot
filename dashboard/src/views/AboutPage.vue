<template>
  <div class="about-page">
    <div class="about-page__content">
      <div class="about-page__hero">
        <h1 class="font-weight-bold">{{ tm('hero.title') }}</h1>
        <p class="text-subtitle-1 text-medium-emphasis">
          {{ tm('hero.subtitle') }}
        </p>
        <div class="about-page__actions">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            prepend-icon="mdi-star"
            @click="open('https://github.com/AstrBotDevs/AstrBot')"
          >
            {{ tm('hero.starButton') }}
          </v-btn>
          <v-btn
            class="ml-4"
            color="secondary"
            size="small"
            variant="tonal"
            prepend-icon="mdi-comment-question"
            @click="open('https://github.com/AstrBotDevs/AstrBot/issues')"
          >
            {{ tm('hero.issueButton') }}
          </v-btn>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/about');

function open(url: string): void {
  window.open(url, '_blank');
}
</script>

<style scoped>
.about-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.about-page__content {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
}

.about-page__hero {
  max-width: 600px;
  text-align: center;
}

.about-page__actions {
  display: flex;
  justify-content: center;
  gap: var(--astrbot-space-4);
  margin-top: var(--astrbot-space-6);
}
</style>

<script setup lang="ts">
import { MarkdownRender } from 'markstream-vue'
import { enableGitHubLikeMarkdownIt } from '@/utils/markdownItHelpers'

type Props = {
  content: string
  headerIcon?: string
  headerLabel?: string
  typewriter?: boolean
  showHeader?: boolean
}

withDefaults(defineProps<Props>(), {
  headerIcon: 'mdi-book-open-outline',
  headerLabel: 'README.md',
  typewriter: false,
  showHeader: true
})
</script>

<template>
  <div class="github-style-container">
    <div v-if="showHeader" class="github-style-header">
      <v-icon size="16" class="mr-2">{{ headerIcon }}</v-icon>
      <span class="text-caption font-weight-bold">{{ headerLabel }}</span>
    </div>

    <div class="github-style-content">
      <div class="markdown-body">
        <MarkdownRender
          :content="content"
          :custom-markdown-it="enableGitHubLikeMarkdownIt"
          :typewriter="typewriter"
          class="markdown-content"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.github-style-container {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  background-color: rgb(var(--v-theme-surface));
  overflow: hidden;
}

.github-style-header {
  background-color: rgba(var(--v-theme-on-surface), 0.03);
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 8px 16px;
  display: flex;
  align-items: center;
}

.github-style-content {
  padding: 32px;
}

:deep(.markdown-body) {
  background-color: transparent !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif !important;
  font-size: 16px;
  line-height: 1.5;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2) {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-bottom: 0.3em;
  margin-top: 24px;
  margin-bottom: 16px;
}

@media (max-width: 767px) {
  .github-style-content {
    padding: 24px;
  }
}
</style>
<template>
  <div class="source-subtitle">
    <span>{{ apiBase || 'N/A' }}</span>
    <a v-if="sponsor?.website_url" :href="sponsor.website_url" target="_blank" rel="noopener noreferrer">
      {{ tm('providerSources.website') }}<v-icon icon="mdi-open-in-new" size="13" />
    </a>
    <a v-if="sponsor?.help_url" :href="sponsor.help_url" target="_blank" rel="noopener noreferrer">
      {{ tm('providerSources.setupGuide') }}<v-icon icon="mdi-open-in-new" size="13" />
    </a>
  </div>
</template>

<script setup lang="ts">
import type { SponsorPreset } from '@/utils/sponsorCatalog'

defineProps<{
  apiBase?: string
  sponsor?: SponsorPreset
  tm: (key: string) => string
}>()
</script>

<style scoped>
.source-subtitle {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 14px;
}

.source-subtitle > span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.source-subtitle a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

.source-subtitle a:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.source-subtitle a:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
  border-radius: 3px;
}
</style>

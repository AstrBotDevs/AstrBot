<script setup lang="ts">
import { computed } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { configDocsHref } from '@/utils/docsHref';

const props = defineProps<{
  docs?: unknown;
}>();

const { locale } = useI18n();
const { tm } = useModuleI18n('features/config');

const href = computed(() => configDocsHref(props.docs, locale.value));
</script>

<template>
  <v-btn
    v-if="href"
    class="config-docs-link"
    icon
    size="x-small"
    variant="text"
    :aria-label="tm('help.documentation')"
    :href="href"
    target="_blank"
    rel="noopener noreferrer"
    @click.stop
  >
    <v-icon size="18">mdi-help-circle-outline</v-icon>
  </v-btn>
</template>

<style scoped>
.config-docs-link {
  flex-shrink: 0;
  pointer-events: auto;
}
</style>

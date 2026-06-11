<template>
    <div class="readme-image-source">
        <v-switch
            v-model="readmeImageUseGitHub"
            class="readme-image-source-switch"
            color="primary"
            density="compact"
            hide-details
            :label="tm('network.proxySelector.readmeImages.useGitHub')">
        </v-switch>
        <div class="text-caption text-medium-emphasis mt-1">
            {{ tm('network.proxySelector.readmeImages.hint') }}
        </div>
    </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import {
    PLUGIN_README_IMAGE_SOURCE,
    getPluginReadmeImageSource,
    setPluginReadmeImageSource
} from '@/utils/githubProxy';

const { tm } = useModuleI18n('features/settings');

const readmeImageSource = ref(getPluginReadmeImageSource());

const readmeImageUseGitHub = computed({
    get() {
        return readmeImageSource.value === PLUGIN_README_IMAGE_SOURCE.GITHUB;
    },
    set(value) {
        readmeImageSource.value = value
            ? PLUGIN_README_IMAGE_SOURCE.GITHUB
            : PLUGIN_README_IMAGE_SOURCE.LOCAL;
    }
});

watch(readmeImageSource, (newVal) => {
    setPluginReadmeImageSource(newVal);
});
</script>

<style scoped>
.readme-image-source {
    max-width: 100%;
    overflow: visible;
    padding-left: 10px;
}

.readme-image-source-switch {
    overflow: visible;
}

.readme-image-source-switch :deep(.v-selection-control) {
    min-height: 32px;
    overflow: visible;
}

.readme-image-source-switch :deep(.v-selection-control__wrapper) {
    overflow: visible;
}

.readme-image-source-switch :deep(.v-label) {
    line-height: 1.35;
    white-space: normal;
}
</style>

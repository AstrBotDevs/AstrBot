<template>
    <div class="readme-image-source">
        <v-switch
            v-model="readmeImageUseGitHub"
            class="readme-image-source-switch"
            color="primary"
            density="compact"
            hide-details="true"
            :label="tm('network.proxySelector.readmeImages.useGitHub')">
        </v-switch>
        <div class="text-caption text-medium-emphasis mt-1">
            {{ tm('network.proxySelector.readmeImages.hint') }}
        </div>
    </div>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';
import {
    PLUGIN_README_IMAGE_SOURCE,
    getPluginReadmeImageSource,
    setPluginReadmeImageSource
} from '@/utils/githubProxy';

export default {
    setup() {
        const { tm } = useModuleI18n('features/settings');
        return { tm };
    },
    data() {
        return {
            readmeImageSource: PLUGIN_README_IMAGE_SOURCE.LOCAL,
            initializing: true,
        }
    },
    computed: {
        readmeImageUseGitHub: {
            get() {
                return this.readmeImageSource === PLUGIN_README_IMAGE_SOURCE.GITHUB;
            },
            set(value) {
                this.readmeImageSource = value
                    ? PLUGIN_README_IMAGE_SOURCE.GITHUB
                    : PLUGIN_README_IMAGE_SOURCE.LOCAL;
            }
        }
    },
    mounted() {
        this.readmeImageSource = getPluginReadmeImageSource();
        this.initializing = false;
    },
    watch: {
        readmeImageSource: function (newVal) {
            if (this.initializing) {
                return;
            }
            setPluginReadmeImageSource(newVal);
        }
    }
}
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

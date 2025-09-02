<template>
    <div style="display: flex; flex-direction: column; height: 100%;">
        <div style="flex-grow: 1; display: flex; align-items: center; justify-content: center; flex-direction: column;">
            <div style="text-align: center; max-width: 600px;">
                <h1 class="font-weight-bold">{{ tm('hero.title') }}</h1>
                <p class="text-subtitle-1" style="color: var(--v-theme-secondaryText);">{{ tm('hero.subtitle') }}</p>
                <div style="margin-top: 20px; display: flex; justify-content: center;">
                    <v-btn @click="open('https://github.com/Soulter/AstrBot')" color="primary" variant="tonal"
                        prepend-icon="mdi-star">
                        {{ tm('hero.starButton') }}
                    </v-btn>
                    <v-btn class="ml-4" @click="open('https://github.com/Soulter/AstrBot/issues')" color="secondary"
                        variant="tonal" prepend-icon="mdi-comment-question">
                        {{ tm('hero.issueButton') }}
                    </v-btn>
                </div>
            </div>
        </div>
    </div>

</template>

<script>
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';

export default {
    name: 'AboutPage',
    setup() {
        const { tm } = useModuleI18n('features/about');
        return { tm };
    },
    methods: {
        useCustomizerStore,
        open(url) {
            window.open(url, '_blank');
        }
    }
}
</script>
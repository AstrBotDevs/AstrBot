<template>
    <div class="persona-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-6">
                <div>
                    <h1 class="text-h1 font-weight-bold mb-2">
                        <v-icon color="black" class="me-2">mdi-heart</v-icon>{{ t('core.navigation.persona') }}
                    </h1>
                    <p class="text-subtitle-1 text-medium-emphasis mb-0">
                        {{ tm('page.description') }}
                    </p>
                </div>
            </v-row>

            <!-- 主容器组件 -->
            <PersonaManager />
        </v-container>
    </div>
</template>

<script>
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { PersonaManager } from '@/views/persona';

export default {
    name: 'PersonaPage',
    components: {
        PersonaManager
    },
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    }
};
</script>

<style scoped>
.persona-page {
    padding: 20px;
    padding-top: 8px;
}
</style>

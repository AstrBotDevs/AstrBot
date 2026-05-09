<template>
    <div class="persona-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row class="d-flex justify-space-between align-center py-3 pb-6">
                <div>
                    <h1 class="text-h2 mb-1">
                        {{ t('core.navigation.persona') }}
                    </h1>
                    <p class="text-body-2 text-medium-emphasis mb-0">
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
    margin: 0 auto;
    max-width: 1400px;
    padding: 24px;
    width: 100%;
}

@media (max-width: 768px) {
    .persona-page {
        padding: 16px;
    }
}
</style>

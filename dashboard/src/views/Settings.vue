<template>

    <div style="background-color: var(--v-theme-surface, #fff); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">

        <v-list lines="two">
            <v-list-subheader>{{ tm('network.title') }}</v-list-subheader>

            <v-list-item>
                <ProxySelector></ProxySelector>
            </v-list-item>

            <v-list-subheader>{{ tm('system.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('system.restart.subtitle')" :title="tm('system.restart.title')">
                <v-btn style="margin-top: 16px;" color="error" @click="restartAstrBot">{{ tm('system.restart.button') }}</v-btn>
            </v-list-item>

            <v-list-item :subtitle="tm('system.migration.subtitle')" :title="tm('system.migration.title')">
                <v-btn style="margin-top: 16px;" color="primary" @click="startMigration">{{ tm('system.migration.button') }}</v-btn>
            </v-list-item>
        </v-list>

    </div>

    <WaitingForRestart ref="wfr"></WaitingForRestart>
    <MigrationDialog ref="migrationDialog"></MigrationDialog>

</template>

<script setup>
import { ref } from 'vue';
import axios from 'axios';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import MigrationDialog from '@/components/shared/MigrationDialog.vue';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/settings');

const wfr = ref(null);
const migrationDialog = ref(null);

const restartAstrBot = () => {
    axios.post('/api/stat/restart-core').then(() => {
        wfr.value.check();
    })
}

const startMigration = async () => {
    if (migrationDialog.value) {
        try {
            const result = await migrationDialog.value.open();
            if (result.success) {
                console.log('Migration completed successfully:', result.message);
            }
        } catch (error) {
            console.error('Migration dialog error:', error);
        }
    }
}
</script>
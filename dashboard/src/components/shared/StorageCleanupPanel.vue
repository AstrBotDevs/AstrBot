<template>
    <div class="storage-cleanup-panel">
        <div class="storage-cleanup-card">
            <div class="storage-cleanup-row">
                <div class="storage-cleanup-info">
                    <div class="storage-cleanup-title">{{ tm('system.cleanup.title') }}</div>
                    <div class="storage-cleanup-hint">
                        {{ tm('system.cleanup.panel.subtitle', { size: formatBytes(storageStatus.total_bytes || 0) }) }}
                    </div>
                </div>
                <div class="storage-cleanup-control">
                    <v-chip size="small" variant="tonal" class="storage-cleanup-chip">
                        {{ formatBytes(storageStatus.total_bytes || 0) }}
                    </v-chip>
                    <v-menu location="bottom end">
                        <template #activator="{ props }">
                            <v-btn
                                v-bind="props"
                                size="small"
                                variant="tonal"
                                class="storage-cleanup-action"
                                :loading="Boolean(cleaningTarget)"
                            >
                                <v-icon class="mr-2">mdi-broom</v-icon>
                                {{ tm('system.cleanup.clean') }}
                            </v-btn>
                        </template>
                        <v-list density="compact" min-width="220">
                            <v-list-item
                                v-for="item in storageCards"
                                :key="item.key"
                                :prepend-icon="item.icon"
                                :title="item.buttonText"
                                :subtitle="formatBytes(item.sizeBytes)"
                                :disabled="Boolean(cleaningTarget)"
                                @click="cleanupStorage(item.key)"
                            />
                            <v-divider />
                            <v-list-item
                                prepend-icon="mdi-delete-sweep-outline"
                                :title="tm('system.cleanup.cleanAll')"
                                :subtitle="formatBytes(storageStatus.total_bytes || 0)"
                                :disabled="Boolean(cleaningTarget)"
                                @click="cleanupStorage('all')"
                            />
                        </v-list>
                    </v-menu>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { statsApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useToastStore } from '@/stores/toast';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

const { tm } = useModuleI18n('features/settings');
const toastStore = useToastStore();
const confirmDialog = useConfirmDialog();

const cleaningTarget = ref('');
const storageStatus = ref({
    logs: {
        size_bytes: 0,
        file_count: 0,
        path: '',
        exists: false
    },
    cache: {
        size_bytes: 0,
        file_count: 0,
        path: '',
        exists: false
    },
    total_bytes: 0
});

const showToast = (message, color = 'success') => {
    toastStore.add({
        message,
        color,
        timeout: 3000
    });
};

const formatBytes = (bytes) => {
    const value = Number(bytes || 0);
    if (value <= 0) return '0 B';

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = value;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex += 1;
    }

    const decimals = size >= 10 || unitIndex === 0 ? 0 : 1;
    return `${size.toFixed(decimals)} ${units[unitIndex]}`;
};

const storageCards = computed(() => [
    {
        key: 'cache',
        buttonText: tm('system.cleanup.targets.cache.button'),
        icon: 'mdi-database-refresh-outline',
        sizeBytes: storageStatus.value.cache?.size_bytes || 0
    },
    {
        key: 'logs',
        buttonText: tm('system.cleanup.targets.logs.button'),
        icon: 'mdi-file-document-outline',
        sizeBytes: storageStatus.value.logs?.size_bytes || 0
    }
]);

const loadStorageStatus = async () => {
    try {
        const res = await statsApi.storage();
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('system.cleanup.messages.statusFailed'), 'error');
            return;
        }
        storageStatus.value = res.data.data || storageStatus.value;
    } catch (error) {
        showToast(error?.response?.data?.message || tm('system.cleanup.messages.statusFailed'), 'error');
    }
};

const cleanupStorage = async (target) => {
    const confirmed = await askForConfirmation(
        tm('system.cleanup.confirm', { target: tm(`system.cleanup.targetNames.${target}`) }),
        confirmDialog
    );
    if (!confirmed) return;

    cleaningTarget.value = target;
    try {
        const res = await statsApi.cleanupStorage(target);
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('system.cleanup.messages.cleanupFailed'), 'error');
            return;
        }

        const cleanupData = res.data.data || {};
        storageStatus.value = cleanupData.status || storageStatus.value;
        showToast(
            tm('system.cleanup.messages.cleanupSuccess', {
                size: formatBytes(cleanupData.removed_bytes || 0),
                count: cleanupData.processed_files || 0
            })
        );
    } catch (error) {
        showToast(error?.response?.data?.message || tm('system.cleanup.messages.cleanupFailed'), 'error');
    } finally {
        cleaningTarget.value = '';
    }
};

onMounted(() => {
    loadStorageStatus();
});
</script>

<style scoped>
.storage-cleanup-panel {
    margin: 0;
}

.storage-cleanup-card {
    overflow: hidden;
    border: 1px solid var(--settings-border, rgba(17, 24, 39, 0.13));
    border-radius: 10px;
    background: rgb(var(--v-theme-surface));
    box-shadow: none;
}

.storage-cleanup-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(220px, 38%);
    gap: 18px;
    align-items: center;
    min-height: 60px;
    padding: 12px 16px;
}

.storage-cleanup-title {
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.88rem;
    font-weight: 700;
    letter-spacing: 0;
    line-height: 1.4;
}

.storage-cleanup-hint {
    margin-top: 4px;
    color: rgba(var(--v-theme-on-surface), 0.76);
    font-size: 0.78rem;
    line-height: 1.45;
}

.storage-cleanup-control {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    min-width: 0;
    justify-self: end;
}

.storage-cleanup-control :deep(.v-btn),
.storage-cleanup-control :deep(.v-chip) {
    border-radius: 10px;
}

.storage-cleanup-chip,
.storage-cleanup-action {
    background: rgba(var(--v-theme-on-surface), 0.06) !important;
    color: rgba(var(--v-theme-on-surface), 0.72) !important;
}

@media (max-width: 720px) {
    .storage-cleanup-row {
        grid-template-columns: 1fr;
        align-items: stretch;
        padding: 14px 16px;
    }

    .storage-cleanup-control {
        justify-content: flex-start;
        justify-self: stretch;
    }
}
</style>

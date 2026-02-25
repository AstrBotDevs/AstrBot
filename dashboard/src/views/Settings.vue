<template>

    <div style="background-color: var(--v-theme-surface, #fff); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">

        <v-list lines="two">
            <v-list-subheader>{{ tm('network.title') }}</v-list-subheader>

            <v-list-item>
                <ProxySelector></ProxySelector>
            </v-list-item>

            <v-list-subheader>{{ tm('sidebar.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('sidebar.customize.subtitle')" :title="tm('sidebar.customize.title')">
                <SidebarCustomizer></SidebarCustomizer>
            </v-list-item>

            <v-list-subheader>{{ tm('theme.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('theme.subtitle')" :title="tm('theme.customize.title')">
                <v-row class="mt-2" dense>
                    <v-col cols="4" sm="2">
                        <v-text-field
                            v-model="primaryColor"
                            type="color"
                            :label="tm('theme.customize.primary')"
                            hide-details
                            variant="outlined"
                            density="compact"
                            style="max-width: 220px;"
                        />
                    </v-col>
                    <v-col cols="4" sm="2   ">
                        <v-text-field
                            v-model="secondaryColor"
                            type="color"
                            :label="tm('theme.customize.secondary')"
                            hide-details
                            variant="outlined"
                            density="compact"
                            style="max-width: 220px;"
                        />
                    </v-col>
                    <v-col cols="12">
                        <v-btn size="small" variant="tonal" color="primary" @click="resetThemeColors">
                            <v-icon class="mr-2">mdi-restore</v-icon>
                            {{ tm('theme.customize.reset') }}
                        </v-btn>
                    </v-col>
                </v-row>
            </v-list-item>

            <v-list-subheader>{{ tm('system.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('system.backup.subtitle')" :title="tm('system.backup.title')">
                <v-btn style="margin-top: 16px;" color="primary" @click="openBackupDialog">
                    <v-icon class="mr-2">mdi-backup-restore</v-icon>
                    {{ tm('system.backup.button') }}
                </v-btn>
            </v-list-item>

            <v-list-item :subtitle="tm('system.restart.subtitle')" :title="tm('system.restart.title')">
                <v-btn style="margin-top: 16px;" color="error" @click="restartAstrBot">{{ tm('system.restart.button') }}</v-btn>
            </v-list-item>

            <v-list-subheader>{{ tm('apiKey.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('apiKey.subtitle')">
                <template #title>
                    <div class="d-flex align-center">
                        <span>{{ tm('apiKey.manageTitle') }}</span>
                        <v-tooltip location="top">
                            <template #activator="{ props }">
                                <v-btn
                                    v-bind="props"
                                    icon
                                    size="x-small"
                                    variant="text"
                                    class="ml-2"
                                    :aria-label="tm('apiKey.docsLink')"
                                    href="https://docs.astrbot.app/dev/openapi.html"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    <v-icon size="18">mdi-help-circle-outline</v-icon>
                                </v-btn>
                            </template>
                            <span>{{ tm('apiKey.docsLink') }}</span>
                        </v-tooltip>
                    </div>
                </template>
                <v-row class="mt-2" dense>
                    <v-col cols="12" md="4">
                        <v-text-field
                            v-model="newApiKeyName"
                            :label="tm('apiKey.name')"
                            variant="outlined"
                            density="compact"
                            hide-details
                        />
                    </v-col>
                    <v-col cols="12" md="3">
                        <v-select
                            v-model="newApiKeyExpiresInDays"
                            :items="apiKeyExpiryOptions"
                            :label="tm('apiKey.expiresInDays')"
                            variant="outlined"
                            density="compact"
                            hide-details
                        />
                    </v-col>
                    <v-col v-if="newApiKeyExpiresInDays === 'permanent'" cols="12">
                        <v-alert type="warning" variant="tonal" density="comfortable">
                            {{ tm('apiKey.permanentWarning') }}
                        </v-alert>
                    </v-col>
                    <v-col cols="12" md="5" class="d-flex align-center">
                        <v-btn color="primary" :loading="apiKeyCreating" @click="createApiKey">
                            <v-icon class="mr-2">mdi-key-plus</v-icon>
                            {{ tm('apiKey.create') }}
                        </v-btn>
                    </v-col>

                    <v-col cols="12">
                        <div class="text-caption text-medium-emphasis mb-1">{{ tm('apiKey.scopes') }}</div>
                        <v-chip-group v-model="newApiKeyScopes" multiple>
                            <v-chip
                                v-for="scope in availableScopes"
                                :key="scope.value"
                                :value="scope.value"
                                :color="newApiKeyScopes.includes(scope.value) ? 'primary' : undefined"
                                :variant="newApiKeyScopes.includes(scope.value) ? 'flat' : 'tonal'"
                            >
                                {{ scope.label }}
                            </v-chip>
                        </v-chip-group>
                    </v-col>

                    <v-col v-if="createdApiKeyPlaintext" cols="12">
                        <v-alert type="warning" variant="tonal">
                            <div class="d-flex align-center justify-space-between flex-wrap">
                                <span>{{ tm('apiKey.plaintextHint') }}</span>
                                <v-btn size="small" variant="text" color="primary" @click="copyCreatedApiKey">
                                    <v-icon class="mr-1">mdi-content-copy</v-icon>{{ tm('apiKey.copy') }}
                                </v-btn>
                            </div>
                            <code style="word-break: break-all;">{{ createdApiKeyPlaintext }}</code>
                        </v-alert>
                    </v-col>

                    <v-col cols="12">
                        <v-table density="compact">
                            <thead>
                                <tr>
                                    <th>{{ tm('apiKey.table.name') }}</th>
                                    <th>{{ tm('apiKey.table.prefix') }}</th>
                                    <th>{{ tm('apiKey.table.scopes') }}</th>
                                    <th>{{ tm('apiKey.table.status') }}</th>
                                    <th>{{ tm('apiKey.table.lastUsed') }}</th>
                                    <th>{{ tm('apiKey.table.createdAt') }}</th>
                                    <th>{{ tm('apiKey.table.actions') }}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="item in apiKeys" :key="item.key_id">
                                    <td>{{ item.name }}</td>
                                    <td><code>{{ item.key_prefix }}</code></td>
                                    <td>{{ (item.scopes || []).join(', ') }}</td>
                                    <td>
                                        <v-chip
                                            size="small"
                                            :color="item.is_revoked || item.is_expired ? 'error' : 'success'"
                                            variant="tonal"
                                        >
                                            {{ item.is_revoked || item.is_expired ? tm('apiKey.status.inactive') : tm('apiKey.status.active') }}
                                        </v-chip>
                                    </td>
                                    <td>{{ formatDate(item.last_used_at) }}</td>
                                    <td>{{ formatDate(item.created_at) }}</td>
                                    <td>
                                        <v-btn
                                            v-if="!item.is_revoked"
                                            size="x-small"
                                            color="warning"
                                            variant="tonal"
                                            class="mr-2"
                                            @click="revokeApiKey(item.key_id)"
                                        >
                                            {{ tm('apiKey.revoke') }}
                                        </v-btn>
                                        <v-btn
                                            size="x-small"
                                            color="error"
                                            variant="tonal"
                                            @click="deleteApiKey(item.key_id)"
                                        >
                                            {{ tm('apiKey.delete') }}
                                        </v-btn>
                                    </td>
                                </tr>
                                <tr v-if="apiKeys.length === 0">
                                    <td colspan="7" class="text-center text-medium-emphasis">
                                        {{ tm('apiKey.empty') }}
                                    </td>
                                </tr>
                            </tbody>
                        </v-table>
                    </v-col>
                </v-row>
            </v-list-item>
        </v-list>

            <v-list-item :subtitle="tm('system.migration.subtitle')" :title="tm('system.migration.title')">
                <v-btn style="margin-top: 16px;" color="primary" @click="startMigration">{{ tm('system.migration.button') }}</v-btn>
            </v-list-item>

    </div>

    <WaitingForRestart ref="wfr"></WaitingForRestart>
    <MigrationDialog ref="migrationDialog"></MigrationDialog>
    <BackupDialog ref="backupDialog"></BackupDialog>

</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import MigrationDialog from '@/components/shared/MigrationDialog.vue';
import SidebarCustomizer from '@/components/shared/SidebarCustomizer.vue';
import BackupDialog from '@/components/shared/BackupDialog.vue';
import { restartAstrBot as restartAstrBotRuntime } from '@/utils/restartAstrBot';
import { useModuleI18n } from '@/i18n/composables';
import { useTheme } from 'vuetify';
import { PurpleTheme } from '@/theme/LightTheme';
import { useToastStore } from '@/stores/toast';

const { tm } = useModuleI18n('features/settings');
const toastStore = useToastStore();
const theme = useTheme();

const getStoredColor = (key, fallback) => {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(key) : null;
    return stored || fallback;
};

const primaryColor = ref(getStoredColor('themePrimary', PurpleTheme.colors.primary));
const secondaryColor = ref(getStoredColor('themeSecondary', PurpleTheme.colors.secondary));

const resolveThemes = () => {
    if (theme?.themes?.value) return theme.themes.value;
    if (theme?.global?.themes?.value) return theme.global.themes.value;
    return null;
};

const applyThemeColors = (primary, secondary) => {
    const themes = resolveThemes();
    if (!themes) return;
    ['PurpleTheme', 'PurpleThemeDark'].forEach((name) => {
        const themeDef = themes[name];
        if (!themeDef?.colors) return;
        if (primary) themeDef.colors.primary = primary;
        if (secondary) themeDef.colors.secondary = secondary;
        if (primary && themeDef.colors.darkprimary) themeDef.colors.darkprimary = primary;
        if (secondary && themeDef.colors.darksecondary) themeDef.colors.darksecondary = secondary;
    });
};

applyThemeColors(primaryColor.value, secondaryColor.value);

watch(primaryColor, (value) => {
    if (!value) return;
    localStorage.setItem('themePrimary', value);
    applyThemeColors(value, secondaryColor.value);
});

watch(secondaryColor, (value) => {
    if (!value) return;
    localStorage.setItem('themeSecondary', value);
    applyThemeColors(primaryColor.value, value);
});

const wfr = ref(null);
const migrationDialog = ref(null);
const backupDialog = ref(null);
const apiKeys = ref([]);
const apiKeyCreating = ref(false);
const newApiKeyName = ref('');
const newApiKeyExpiresInDays = ref(30);
const newApiKeyScopes = ref(['chat', 'config', 'file', 'im']);
const createdApiKeyPlaintext = ref('');
const apiKeyExpiryOptions = computed(() => [
    { title: tm('apiKey.expiryOptions.day1'), value: 1 },
    { title: tm('apiKey.expiryOptions.day7'), value: 7 },
    { title: tm('apiKey.expiryOptions.day30'), value: 30 },
    { title: tm('apiKey.expiryOptions.day90'), value: 90 },
    { title: tm('apiKey.expiryOptions.permanent'), value: 'permanent' }
]);

const availableScopes = [
    { value: 'chat', label: 'chat' },
    { value: 'config', label: 'config' },
    { value: 'file', label: 'file' },
    { value: 'im', label: 'im' }
];

const showToast = (message, color = 'success') => {
    toastStore.add({
        message,
        color,
        timeout: 3000
    });
};

const formatDate = (value) => {
    if (!value) return '-';
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return '-';
    return dt.toLocaleString();
};

const loadApiKeys = async () => {
    try {
        const res = await axios.get('/api/apikey/list');
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('apiKey.messages.loadFailed'), 'error');
            return;
        }
        apiKeys.value = res.data.data || [];
    } catch (e) {
        showToast(e?.response?.data?.message || tm('apiKey.messages.loadFailed'), 'error');
    }
};

const tryExecCommandCopy = (text) => {
    let textArea = null;
    try {
        if (typeof document === 'undefined' || !document.body) return false;
        textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.setAttribute('readonly', '');
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        textArea.style.pointerEvents = 'none';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        textArea.setSelectionRange(0, text.length);
        return document.execCommand('copy');
    } catch (_) {
        return false;
    } finally {
        try {
            if (textArea?.parentNode) {
                textArea.parentNode.removeChild(textArea);
            }
        } catch (_) {
            // ignore cleanup errors
        }
    }
};

const copyTextToClipboard = async (text) => {
    if (!text) return false;
    if (tryExecCommandCopy(text)) return true;
    if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return false;
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (_) {
        return false;
    }
};

const copyCreatedApiKey = async () => {
    if (!createdApiKeyPlaintext.value) return;
    const ok = await copyTextToClipboard(createdApiKeyPlaintext.value);
    if (ok) {
        showToast(tm('apiKey.messages.copySuccess'), 'success');
    } else {
        showToast(tm('apiKey.messages.copyFailed'), 'error');
    }
};

const createApiKey = async () => {
    const selectedScopes = availableScopes
        .map((scope) => scope.value)
        .filter((scope) => newApiKeyScopes.value.includes(scope));

    if (selectedScopes.length === 0) {
        showToast(tm('apiKey.messages.scopeRequired'), 'warning');
        return;
    }
    apiKeyCreating.value = true;
    try {
        const payload = {
            name: newApiKeyName.value,
            scopes: selectedScopes
        };
        if (newApiKeyExpiresInDays.value !== 'permanent') {
            payload.expires_in_days = Number(newApiKeyExpiresInDays.value);
        }
        const res = await axios.post('/api/apikey/create', payload);
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('apiKey.messages.createFailed'), 'error');
            return;
        }
        createdApiKeyPlaintext.value = res.data.data?.api_key || '';
        newApiKeyName.value = '';
        newApiKeyExpiresInDays.value = 30;
        showToast(tm('apiKey.messages.createSuccess'), 'success');
        await loadApiKeys();
    } catch (e) {
        showToast(e?.response?.data?.message || tm('apiKey.messages.createFailed'), 'error');
    } finally {
        apiKeyCreating.value = false;
    }
};

const revokeApiKey = async (keyId) => {
    try {
        const res = await axios.post('/api/apikey/revoke', { key_id: keyId });
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('apiKey.messages.revokeFailed'), 'error');
            return;
        }
        showToast(tm('apiKey.messages.revokeSuccess'), 'success');
        await loadApiKeys();
    } catch (e) {
        showToast(e?.response?.data?.message || tm('apiKey.messages.revokeFailed'), 'error');
    }
};

const deleteApiKey = async (keyId) => {
    try {
        const res = await axios.post('/api/apikey/delete', { key_id: keyId });
        if (res.data.status !== 'ok') {
            showToast(res.data.message || tm('apiKey.messages.deleteFailed'), 'error');
            return;
        }
        showToast(tm('apiKey.messages.deleteSuccess'), 'success');
        await loadApiKeys();
    } catch (e) {
        showToast(e?.response?.data?.message || tm('apiKey.messages.deleteFailed'), 'error');
    }
};

const restartAstrBot = async () => {
    try {
        await restartAstrBotRuntime(wfr.value);
    } catch (error) {
        console.error(error);
    }
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

const openBackupDialog = () => {
    if (backupDialog.value) {
        backupDialog.value.open();
    }
}

const resetThemeColors = () => {
    primaryColor.value = PurpleTheme.colors.primary;
    secondaryColor.value = PurpleTheme.colors.secondary;
    localStorage.removeItem('themePrimary');
    localStorage.removeItem('themeSecondary');
    applyThemeColors(primaryColor.value, secondaryColor.value);
};

onMounted(() => {
    loadApiKeys();
});
</script>

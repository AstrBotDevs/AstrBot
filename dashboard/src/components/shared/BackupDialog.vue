<template>
    <v-dialog v-model="isOpen" persistent max-width="700" scrollable>
        <v-card>
            <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
                <v-icon class="mr-2">mdi-backup-restore</v-icon>
                {{ t('features.settings.backup.dialog.title') }}
            </v-card-title>

            <v-card-text class="pa-6">
                <!-- 备份导出目录设置条 -->
                <div class="backup-dir-card mb-4">
                    <div class="backup-dir-card__header">
                        <div class="backup-dir-card__title-group">
                            <v-icon size="18" color="primary">mdi-folder-cog-outline</v-icon>
                            <span class="backup-dir-card__title">
                                {{ t('features.settings.backup.settings.title') }}
                            </span>
                            <v-chip
                                size="x-small"
                                :color="backupDirBadgeColor"
                                variant="tonal"
                                :ripple="false"
                                class="non-interactive-chip"
                            >
                                {{ backupDirBadgeText }}
                            </v-chip>
                        </div>

                        <div v-if="!editingBackupDir" class="backup-dir-card__header-actions">
                            <v-btn
                                v-if="backupSettings.effective_backup_dir"
                                icon="mdi-content-copy"
                                variant="text"
                                size="x-small"
                                :title="t('features.settings.backup.settings.copyPath')"
                                :aria-label="t('features.settings.backup.settings.copyPath')"
                                @click="copyBackupDir"
                            />
                            <v-btn
                                size="small"
                                variant="tonal"
                                color="primary"
                                prepend-icon="mdi-pencil-outline"
                                :disabled="cannotEditBackupDir"
                                @click="startEditingBackupDir"
                            >
                                {{ t('features.settings.backup.settings.edit') }}
                            </v-btn>
                        </div>
                    </div>

                    <v-progress-linear
                        v-if="loadingSettings"
                        indeterminate
                        color="primary"
                        height="2"
                        class="mt-2"
                    />

                    <template v-else-if="!editingBackupDir">
                        <div
                            v-if="backupSettings.effective_backup_dir || backupSettings.default_backup_dir"
                            class="backup-dir-card__path"
                        >
                            <code>{{ backupSettings.effective_backup_dir || backupSettings.default_backup_dir }}</code>
                        </div>

                        <v-alert
                            v-if="!backupSettings.is_valid && backupSettings.validation_error"
                            type="error"
                            variant="tonal"
                            density="compact"
                            class="mt-2"
                        >
                            {{ backupSettings.validation_error }}
                        </v-alert>

                        <v-alert
                            v-else-if="settingsError"
                            type="error"
                            variant="tonal"
                            density="compact"
                            class="mt-2"
                        >
                            {{ settingsError }}
                        </v-alert>

                        <div
                            v-else-if="backupSettings.env_override"
                            class="backup-dir-card__note text-caption text-medium-emphasis mt-2"
                        >
                            <v-icon size="14" class="mr-1">mdi-information-outline</v-icon>
                            <span>{{ t('features.settings.backup.settings.envOverrideHint') }}</span>
                        </div>

                        <div
                            v-else-if="isProcessing || backupSettings.has_active_tasks"
                            class="backup-dir-card__note text-caption text-medium-emphasis mt-2"
                        >
                            <v-icon size="14" class="mr-1">mdi-clock-outline</v-icon>
                            <span>{{ t('features.settings.backup.settings.activeTaskHint') }}</span>
                        </div>
                    </template>

                    <template v-else>
                        <div class="backup-dir-card__input-row mt-3">
                            <v-text-field
                                v-model="backupDirInput"
                                :label="t('features.settings.backup.settings.inputLabel')"
                                :placeholder="t('features.settings.backup.settings.inputPlaceholder', { dir: backupSettings.default_backup_dir || 'data/backups' })"
                                :rules="[backupDirValidationRule]"
                                variant="outlined"
                                density="compact"
                                clearable
                                hide-details="auto"
                                :disabled="savingSettings || isProcessing"
                                class="backup-dir-card__input"
                                @keyup.enter="saveBackupDir"
                            />
                            <v-btn
                                v-if="canPickBackupDirectory"
                                variant="tonal"
                                color="primary"
                                height="40"
                                prepend-icon="mdi-folder-open-outline"
                                :loading="pickingBackupDirectory"
                                :disabled="savingSettings || isProcessing"
                                @click="handlePickBackupDirectory"
                            >
                                {{ t('features.settings.backup.settings.browse') }}
                            </v-btn>
                        </div>

                        <div class="backup-dir-card__hints mt-2">
                            <div class="backup-dir-card__note text-caption text-medium-emphasis">
                                <v-icon size="14" class="mr-1">mdi-information-outline</v-icon>
                                <span>
                                    {{ t('features.settings.backup.settings.hintDefault', { dir: backupSettings.default_backup_dir || 'data/backups' }) }}
                                </span>
                            </div>
                            <div class="backup-dir-card__note text-caption text-medium-emphasis mt-1">
                                <v-icon size="14" class="mr-1">mdi-folder-alert-outline</v-icon>
                                <span>{{ t('features.settings.backup.settings.hintNoAutoMove') }}</span>
                            </div>
                        </div>

                        <v-alert
                            v-if="settingsError"
                            type="error"
                            variant="tonal"
                            density="compact"
                            class="mt-2"
                        >
                            {{ settingsError }}
                        </v-alert>

                        <div class="backup-dir-card__actions mt-3">
                            <div>
                                <v-btn
                                    v-if="backupSettings.is_custom || (backupDirInput || '').trim()"
                                    variant="text"
                                    size="small"
                                    color="secondary"
                                    prepend-icon="mdi-restore"
                                    :disabled="savingSettings || isProcessing"
                                    @click="resetBackupDirToDefault"
                                >
                                    {{ t('features.settings.backup.settings.resetDefault') }}
                                </v-btn>
                            </div>
                            <div class="d-flex align-center ga-2">
                                <v-btn
                                    variant="text"
                                    size="small"
                                    color="grey-darken-1"
                                    :disabled="savingSettings"
                                    @click="cancelEditingBackupDir"
                                >
                                    {{ t('core.common.cancel') }}
                                </v-btn>
                                <v-btn
                                    color="primary"
                                    variant="tonal"
                                    size="small"
                                    :loading="savingSettings"
                                    :disabled="savingSettings || isProcessing || !canSaveBackupDir"
                                    @click="saveBackupDir"
                                >
                                    {{ t('core.common.save') }}
                                </v-btn>
                            </div>
                        </div>
                    </template>
                </div>

                <!-- 选项卡 -->
                <v-tabs v-model="activeTab" color="primary" class="mb-4">
                    <v-tab value="export">
                        <v-icon class="mr-2">mdi-export</v-icon>
                        {{ t('features.settings.backup.tabs.export') }}
                    </v-tab>
                    <v-tab value="import">
                        <v-icon class="mr-2">mdi-import</v-icon>
                        {{ t('features.settings.backup.tabs.import') }}
                    </v-tab>
                    <v-tab value="list">
                        <v-icon class="mr-2">mdi-format-list-bulleted</v-icon>
                        {{ t('features.settings.backup.tabs.list') }}
                    </v-tab>
                </v-tabs>

                <v-window v-model="activeTab">
                    <!-- 导出标签页 -->
                    <v-window-item value="export">
                        <div v-if="exportStatus === 'idle'" class="text-center py-8">
                            <v-icon size="64" color="primary" class="mb-4">mdi-cloud-upload</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.title') }}</h3>
                            <p class="mb-4 text-grey">{{ t('features.settings.backup.export.description') }}</p>
                            <v-alert type="info" variant="tonal" class="mb-4 text-left">
                                <template v-slot:prepend>
                                    <v-icon>mdi-information</v-icon>
                                </template>
                                {{ t('features.settings.backup.export.includes') }}
                            </v-alert>
                            <v-btn color="primary" variant="tonal" size="large" @click="startExport" :loading="exportStatus === 'processing'">
                                <v-icon class="mr-2">mdi-export</v-icon>
                                {{ t('features.settings.backup.export.button') }}
                            </v-btn>
                        </div>

                        <div v-else-if="exportStatus === 'processing'" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.processing') }}</h3>
                            <p class="text-grey">{{ exportProgress.message || t('features.settings.backup.export.wait') }}</p>
                            <v-progress-linear :model-value="exportProgress.current" :max="exportProgress.total" class="mt-4" color="primary"></v-progress-linear>
                        </div>

                        <div v-else-if="exportStatus === 'completed'" class="text-center py-8">
                            <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.completed') }}</h3>
                            <p class="mb-2">{{ exportResult?.filename }}</p>
                            <p
                                v-if="exportResult?.path"
                                class="backup-saved-path text-caption text-medium-emphasis mb-4"
                            >
                                {{ t('features.settings.backup.export.savedPath', { path: exportResult.path }) }}
                            </p>
                            <v-btn color="primary" variant="tonal" @click="downloadBackup(exportResult?.filename)" class="mr-2">
                                <v-icon class="mr-2">mdi-download</v-icon>
                                {{ t('features.settings.backup.export.download') }}
                            </v-btn>
                            <v-btn color="grey" variant="text" @click="resetExport">
                                {{ t('features.settings.backup.export.another') }}
                            </v-btn>
                        </div>

                        <div v-else-if="exportStatus === 'failed'" class="text-center py-8">
                            <v-icon size="64" color="error" class="mb-4">mdi-alert-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.failed') }}</h3>
                            <v-alert type="error" variant="tonal" class="mb-4">
                                {{ exportError }}
                            </v-alert>
                            <v-btn color="primary" variant="tonal" @click="resetExport">
                                {{ t('features.settings.backup.export.retry') }}
                            </v-btn>
                        </div>
                    </v-window-item>

                    <!-- 导入标签页 -->
                    <v-window-item value="import">
                        <!-- 步骤1: 选择文件 -->
                        <div v-if="importStatus === 'idle'" class="py-4">
                            <v-alert type="warning" variant="tonal" class="mb-4">
                                <template v-slot:prepend>
                                    <v-icon>mdi-alert</v-icon>
                                </template>
                                {{ t('features.settings.backup.import.warning') }}
                            </v-alert>

                            <v-file-input
                                v-model="importFile"
                                :label="t('features.settings.backup.import.selectFile')"
                                accept=".zip"
                                prepend-icon="mdi-file-upload"
                                show-size
                                class="mb-4"
                            ></v-file-input>

                            <div class="d-flex justify-center">
                                <v-btn
                                    color="primary"
                                    variant="tonal"
                                    size="large"
                                    @click="uploadAndCheck"
                                    :disabled="!importFile"
                                    :loading="importStatus === 'uploading'"
                                >
                                    <v-icon class="mr-2">mdi-upload</v-icon>
                                    {{ t('features.settings.backup.import.uploadAndCheck') }}
                                </v-btn>
                            </div>
                        </div>

                        <!-- 步骤1.5: 上传中 -->
                        <div v-else-if="importStatus === 'uploading'" class="text-center py-8">
                            <v-icon size="64" color="primary" class="mb-4">mdi-cloud-upload</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.uploading') }}</h3>
                            <p class="text-grey mb-2">
                                {{ uploadProgress.message || t('features.settings.backup.import.uploadWait') }}
                            </p>
                            <p class="text-grey-darken-1 mb-4">
                                {{ formatFileSize(uploadProgress.uploaded) }} / {{ formatFileSize(uploadProgress.total) }}
                                ({{ uploadProgress.percent }}%)
                            </p>
                            <v-progress-linear
                                :model-value="uploadProgress.percent"
                                :max="100"
                                class="mt-2"
                                color="primary"
                                height="8"
                                rounded
                            ></v-progress-linear>
                        </div>

                        <!-- 步骤2: 确认导入 -->
                        <div v-else-if="importStatus === 'confirm'" class="py-4">
                            <v-alert
                                :type="versionAlertType"
                                variant="tonal"
                                class="mb-4"
                            >
                                <template v-slot:prepend>
                                    <v-icon>{{ versionAlertIcon }}</v-icon>
                                </template>
                                <div class="confirm-message">
                                    <div class="text-h6 mb-2">{{ versionAlertTitle }}</div>
                                    <div class="mb-2">
                                        <strong>{{ t('features.settings.backup.import.version.backupVersion') }}:</strong> {{ checkResult?.backup_version }}<br>
                                        <strong>{{ t('features.settings.backup.import.version.currentVersion') }}:</strong> {{ checkResult?.current_version }}
                                    </div>
                                    <div v-if="checkResult?.backup_time && checkResult?.backup_time !== '未知'" class="mb-2">
                                        <strong>{{ t('features.settings.backup.import.version.backupTime') }}:</strong> {{ formatISODate(checkResult?.backup_time) }}
                                    </div>
                                    <div class="mt-3" style="white-space: pre-line;">{{ versionAlertMessage }}</div>
                                </div>
                            </v-alert>

                            <!-- 备份摘要 -->
                            <v-card variant="outlined" class="mb-4" v-if="checkResult?.backup_summary">
                                <v-card-title class="text-subtitle-1">
                                    <v-icon class="mr-2">mdi-package-variant</v-icon>
                                    {{ t('features.settings.backup.import.backupContents') }}
                                </v-card-title>
                                <v-card-text>
                                    <div class="d-flex flex-wrap ga-2">
                                        <v-chip v-if="checkResult.backup_summary.tables?.length" size="small" color="primary" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ checkResult.backup_summary.tables.length }} {{ t('features.settings.backup.import.tables') }}
                                        </v-chip>
                                        <v-chip v-if="checkResult.backup_summary.has_knowledge_bases" size="small" color="success" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ t('features.settings.backup.import.knowledgeBases') }}
                                        </v-chip>
                                        <v-chip v-if="checkResult.backup_summary.has_config" size="small" color="info" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ t('features.settings.backup.import.configFiles') }}
                                        </v-chip>
                                        <v-chip v-for="dir in (checkResult.backup_summary.directories || [])" :key="dir" size="small" color="warning" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ dir }}
                                        </v-chip>
                                    </div>
                                </v-card-text>
                            </v-card>

                            <!-- 警告信息 -->
                            <v-alert v-if="checkResult?.warnings?.length" type="warning" variant="tonal" class="mb-4">
                                <div v-for="(warning, idx) in checkResult.warnings" :key="idx">{{ warning }}</div>
                            </v-alert>

                            <div class="d-flex justify-center align-center mt-4" style="gap: 16px;">
                                <v-btn
                                    color="grey-darken-1"
                                    variant="text"
                                    size="large"
                                    @click="resetImport"
                                >
                                    <v-icon class="mr-2">mdi-close</v-icon>
                                    {{ t('core.common.cancel') }}
                                </v-btn>
                                <v-btn
                                    v-if="checkResult?.can_import"
                                    color="error"
                                    size="large"
                                    variant="tonal"
                                    @click="confirmImport"
                                >
                                    <v-icon class="mr-2">mdi-alert</v-icon>
                                    {{ t('features.settings.backup.import.confirmImport') }}
                                </v-btn>
                            </div>
                        </div>

                        <!-- 步骤3: 导入进行中 -->
                        <div v-else-if="importStatus === 'processing'" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.processing') }}</h3>
                            <p class="text-grey">{{ importProgress.message || t('features.settings.backup.import.wait') }}</p>
                            <v-progress-linear :model-value="importProgress.current" :max="importProgress.total" class="mt-4" color="primary"></v-progress-linear>
                        </div>

                        <div v-else-if="importStatus === 'completed'" class="text-center py-8">
                            <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.completed') }}</h3>
                            <v-alert type="info" variant="tonal" class="mb-4">
                                {{ t('features.settings.backup.import.restartRequired') }}
                            </v-alert>
                            <v-btn color="primary" variant="tonal" @click="restartAstrBot" class="mr-2">
                                <v-icon class="mr-2">mdi-restart</v-icon>
                                {{ t('features.settings.backup.import.restartNow') }}
                            </v-btn>
                            <v-btn color="grey" variant="text" @click="resetImport">
                                {{ t('core.common.close') }}
                            </v-btn>
                        </div>

                        <div v-else-if="importStatus === 'failed'" class="text-center py-8">
                            <v-icon size="64" color="error" class="mb-4">mdi-alert-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.failed') }}</h3>
                            <v-alert type="error" variant="tonal" class="mb-4">
                                {{ importError }}
                            </v-alert>
                            <v-btn
                                v-if="canResume"
                                color="primary"
                                variant="tonal"
                                class="mr-2"
                                @click="resumeAndCheck"
                            >
                                <v-icon class="mr-2">mdi-play</v-icon>
                                {{ t('features.settings.backup.import.resumeUpload') }}
                            </v-btn>
                            <v-btn color="grey-darken-1" variant="text" @click="resetImport">
                                {{ t('features.settings.backup.import.retry') }}
                            </v-btn>
                        </div>
                    </v-window-item>

                    <!-- 备份列表标签页 -->
                    <v-window-item value="list">
                        <div v-if="loadingList" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary"></v-progress-circular>
                        </div>

                        <div v-else-if="backupList.length === 0" class="text-center py-8">
                            <v-icon size="64" color="grey" class="mb-4">mdi-folder-open-outline</v-icon>
                            <p class="text-grey">{{ t('features.settings.backup.list.empty') }}</p>
                        </div>

                        <v-list v-else lines="two">
                            <v-list-item
                                v-for="backup in backupList"
                                :key="backup.filename"
                            >
                                <template v-slot:prepend>
                                    <v-icon :color="backup.type === 'uploaded' ? 'orange' : 'primary'">
                                        {{ backup.type === 'uploaded' ? 'mdi-upload' : 'mdi-zip-box' }}
                                    </v-icon>
                                </template>

                                <v-list-item-title>{{ backup.filename }}</v-list-item-title>
                                <v-list-item-subtitle>
                                    {{ formatFileSize(backup.size) }} · {{ formatDate(backup.created_at) }}
                                    <v-chip size="x-small" color="primary" variant="tonal" class="ml-2">
                                        v{{ backup.astrbot_version }}
                                    </v-chip>
                                    <v-chip v-if="backup.type === 'uploaded'" size="x-small" color="orange" variant="tonal" class="ml-1">
                                        {{ t('features.settings.backup.list.uploaded') }}
                                    </v-chip>
                                </v-list-item-subtitle>

                                <template v-slot:append>
                                    <v-btn
                                        icon="mdi-restore"
                                        variant="text"
                                        size="small"
                                        color="success"
                                        :title="t('features.settings.backup.list.restore')"
                                        @click="restoreFromList(backup.filename)"
                                    ></v-btn>
                                    <v-btn
                                        icon="mdi-pencil"
                                        variant="text"
                                        size="small"
                                        :title="t('features.settings.backup.list.rename')"
                                        @click="openRenameDialog(backup.filename)"
                                    ></v-btn>
                                    <v-btn icon="mdi-download" variant="text" size="small" @click="downloadBackup(backup.filename)"></v-btn>
                                    <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="deleteBackup(backup.filename)"></v-btn>
                                </template>
                            </v-list-item>
                        </v-list>

                        <div class="d-flex justify-center mt-4">
                            <v-btn color="primary" variant="text" @click="loadBackupList">
                                <v-icon class="mr-2">mdi-refresh</v-icon>
                                {{ t('features.settings.backup.list.refresh') }}
                            </v-btn>
                        </div>

                        <!-- 提示信息 -->
                        <p class="text-caption text-grey text-center mt-4 backup-ftp-hint">
                            <v-icon size="small" class="mr-1">mdi-information-outline</v-icon>
                            {{ t('features.settings.backup.list.ftpHintWithDir', { dir: backupSettings.effective_backup_dir || 'data/backups' }) }}
                        </p>
                    </v-window-item>
                </v-window>
            </v-card-text>

            <v-card-actions class="px-6 py-4">
                <v-spacer></v-spacer>
                <v-btn color="grey" variant="text" @click="handleClose" :disabled="isProcessing">
                    {{ t('core.common.close') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

    <!-- 重命名对话框 -->
    <v-dialog v-model="renameDialogOpen" max-width="450" persistent>
        <v-card>
            <v-card-title class="text-h3 pa-4 pb-0 pl-6">
                <v-icon class="mr-2">mdi-pencil</v-icon>
                {{ t('features.settings.backup.list.renameTitle') }}
            </v-card-title>
            <v-card-text>
                <v-text-field
                    v-model="renameNewName"
                    :label="t('features.settings.backup.list.newName')"
                    :rules="[renameValidationRule]"
                    :error-messages="renameError"
                    variant="outlined"
                    density="comfortable"
                    autofocus
                    @keyup.enter="confirmRename"
                >
                    <template v-slot:append-inner>
                        <span class="text-grey">.zip</span>
                    </template>
                </v-text-field>
                <p class="text-caption text-grey mt-1">
                    {{ t('features.settings.backup.list.renameHint') }}
                </p>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn color="grey" variant="text" @click="closeRenameDialog">
                    {{ t('core.common.cancel') }}
                </v-btn>
                <v-btn
                    color="primary"
                    variant="tonal"
                    @click="confirmRename"
                    :loading="renameLoading"
                    :disabled="!renameNewName || !!renameError"
                >
                    {{ t('core.common.confirm') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

    <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { backupApi } from '@/api/v1'
import { useChunkedUpload } from '@/composables/useChunkedUpload'
import { useI18n } from '@/i18n/composables'
import { useToastStore } from '@/stores/toast'
import { copyToClipboard } from '@/utils/clipboard'
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog'
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime'
import { restartAstrBot as restartAstrBotRuntime } from '@/utils/restartAstrBot'
import WaitingForRestart from './WaitingForRestart.vue'

const emit = defineEmits(['settings-updated'])

const { t } = useI18n()
const toastStore = useToastStore()
const confirmDialog = useConfirmDialog()

const isOpen = ref(false)
const activeTab = ref('export')
const wfr = ref(null)

// 备份目录设置状态
const loadingSettings = ref(false)
const savingSettings = ref(false)
const editingBackupDir = ref(false)
const backupDirInput = ref('')
const settingsError = ref('')
const canPickBackupDirectory = ref(false)
const pickingBackupDirectory = ref(false)
const backupSettings = ref({
    backup_dir: '',
    effective_backup_dir: '',
    default_backup_dir: '',
    is_custom: false,
    source: 'default',
    env_override: false,
    has_active_tasks: false,
    is_valid: true,
    validation_error: null
})

// 导出状态
const exportStatus = ref('idle') // idle, processing, completed, failed
const exportTaskId = ref(null)
const exportProgress = ref({ current: 0, total: 100, message: '' })
const exportResult = ref(null)
const exportError = ref('')

// 导入状态
const importStatus = ref('idle') // idle, uploading, confirm, processing, completed, failed
const importFile = ref(null)
const importTaskId = ref(null)
const importProgress = ref({ current: 0, total: 100, message: '' })
const importError = ref('')
const uploadedFilename = ref('')  // 已上传的文件名
const checkResult = ref(null)     // 预检查结果

// 分片上传状态（调度由 useChunkedUpload 管理）
const uploader = useChunkedUpload(backupApi)
const { canResume } = uploader
const uploadMessageOverride = ref('')  // 预检查阶段覆盖上传进度文案
const uploadProgress = computed(() => ({
    uploaded: uploader.uploadedBytes.value,
    total: uploader.totalBytes.value,
    percent: uploader.percent.value,
    message: uploadMessageOverride.value || {
        init: t('features.settings.backup.import.uploadInit'),
        chunks: t('features.settings.backup.import.uploadingChunks'),
        complete: t('features.settings.backup.import.uploadComplete')
    }[uploader.phase.value]
}))

// 备份列表
const loadingList = ref(false)
const backupList = ref([])

// 重命名对话框状态
const renameDialogOpen = ref(false)
const renameOldFilename = ref('')
const renameNewName = ref('')
const renameLoading = ref(false)
const renameError = ref('')

// 计算属性
const isProcessing = computed(() => {
    return exportStatus.value === 'processing' ||
           importStatus.value === 'processing' ||
           importStatus.value === 'uploading'
})

const cannotEditBackupDir = computed(() => {
    return loadingSettings.value ||
           savingSettings.value ||
           isProcessing.value ||
           backupSettings.value.env_override ||
           backupSettings.value.has_active_tasks
})

const backupDirBadgeText = computed(() => {
    if (backupSettings.value.env_override) {
        return t('features.settings.backup.settings.envBadge')
    }
    if (backupSettings.value.is_custom) {
        return t('features.settings.backup.settings.customBadge')
    }
    return t('features.settings.backup.settings.defaultBadge')
})

const backupDirBadgeColor = computed(() => {
    if (backupSettings.value.env_override) return 'info'
    if (backupSettings.value.is_custom) return 'primary'
    return 'secondary'
})

const backupDirValidationRule = (value) => {
    if (!value) return true
    if (/[\x00-\x1f]/.test(value)) {
        return t('features.settings.backup.settings.invalidControlChars')
    }
    return true
}

const canSaveBackupDir = computed(() => {
    const trimmed = (backupDirInput.value || '').trim()
    if (backupDirValidationRule(trimmed) !== true) {
        return false
    }
    if (!backupSettings.value.is_valid) {
        return true
    }
    return trimmed !== (backupSettings.value.backup_dir || '')
})

watch(backupDirInput, () => {
    if (settingsError.value) {
        settingsError.value = ''
    }
})

// 版本检查相关的计算属性
const versionAlertType = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return 'error'
    if (status === 'minor_diff') return 'warning'
    return 'info'
})

const versionAlertIcon = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return 'mdi-close-circle'
    if (status === 'minor_diff') return 'mdi-alert'
    return 'mdi-check-circle'
})

const versionAlertTitle = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return t('features.settings.backup.import.version.majorDiffTitle')
    if (status === 'minor_diff') return t('features.settings.backup.import.version.minorDiffTitle')
    return t('features.settings.backup.import.version.matchTitle')
})

const versionAlertMessage = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return t('features.settings.backup.import.version.majorDiffMessage')
    if (status === 'minor_diff') return t('features.settings.backup.import.version.minorDiffMessage')
    return t('features.settings.backup.import.version.matchMessage')
})

// 监听对话框打开
watch(isOpen, async (newVal) => {
    if (newVal) {
        canPickBackupDirectory.value = false
        loadBackupSettings()
        loadBackupList()
        const runtimeInfo = await getDesktopRuntimeInfo()
        canPickBackupDirectory.value =
            runtimeInfo.isDesktopRuntime &&
            typeof runtimeInfo.bridge?.pickDirectory === 'function'
    } else {
        resetAll()
    }
})

// 监听标签页切换
watch(activeTab, (newVal) => {
    if (newVal === 'list') {
        loadBackupList()
    }
})

const showBackupToast = (message, color = 'success') => {
    toastStore.add({
        message,
        color,
        timeout: 3000
    })
}

const applyBackupSettings = (data) => {
    if (!data || typeof data !== 'object') return
    backupSettings.value = {
        backup_dir: data.backup_dir || '',
        effective_backup_dir: data.effective_backup_dir || '',
        default_backup_dir: data.default_backup_dir || '',
        is_custom: Boolean(data.is_custom),
        source: data.source || 'default',
        env_override: Boolean(data.env_override),
        has_active_tasks: Boolean(data.has_active_tasks),
        is_valid: data.is_valid !== false,
        validation_error: data.validation_error || null
    }
}

const loadBackupSettings = async () => {
    loadingSettings.value = true
    settingsError.value = ''
    try {
        const response = await backupApi.getSettings()
        if (response.data.status === 'ok') {
            applyBackupSettings(response.data.data)
        } else {
            settingsError.value = response.data.message || t('features.settings.backup.settings.loadFailed')
        }
    } catch (error) {
        settingsError.value =
            error?.response?.data?.message ||
            error?.message ||
            t('features.settings.backup.settings.loadFailed')
    } finally {
        loadingSettings.value = false
    }
}

const startEditingBackupDir = () => {
    if (cannotEditBackupDir.value) return
    backupDirInput.value = backupSettings.value.backup_dir || ''
    settingsError.value = ''
    editingBackupDir.value = true
}

const cancelEditingBackupDir = () => {
    editingBackupDir.value = false
    backupDirInput.value = backupSettings.value.backup_dir || ''
    settingsError.value = ''
}

const handlePickBackupDirectory = async () => {
    const pickDirectory = window.astrbotDesktop?.pickDirectory
    if (!canPickBackupDirectory.value || !pickDirectory || pickingBackupDirectory.value) {
        return
    }
    pickingBackupDirectory.value = true
    try {
        const initialPath =
            (backupDirInput.value || '').trim() ||
            backupSettings.value.effective_backup_dir ||
            null
        const selectedPath = await pickDirectory(initialPath)
        if (selectedPath) {
            backupDirInput.value = selectedPath
        }
    } catch (error) {
        console.warn('[backup-dialog] Failed to pick backup directory.', error)
    } finally {
        pickingBackupDirectory.value = false
    }
}

const persistBackupDir = async (nextDir, isReset = false) => {
    if (savingSettings.value || isProcessing.value) return
    const trimmed = (nextDir || '').trim()
    const validationResult = backupDirValidationRule(trimmed)
    if (validationResult !== true) {
        settingsError.value = validationResult
        return
    }

    savingSettings.value = true
    settingsError.value = ''
    try {
        const response = await backupApi.updateSettings({
            backup_dir: trimmed
        })
        if (response.data.status !== 'ok') {
            settingsError.value =
                response.data.message || t('features.settings.backup.settings.saveFailed')
            return
        }
        applyBackupSettings(response.data.data)
        backupDirInput.value = backupSettings.value.backup_dir || ''
        editingBackupDir.value = false
        emit('settings-updated', { ...backupSettings.value })
        showBackupToast(
            isReset || !trimmed
                ? t('features.settings.backup.settings.resetSuccess')
                : t('features.settings.backup.settings.saveSuccess'),
            'success'
        )
        await loadBackupList()
    } catch (error) {
        settingsError.value =
            error?.response?.data?.message ||
            error?.message ||
            t('features.settings.backup.settings.saveFailed')
    } finally {
        savingSettings.value = false
    }
}

const saveBackupDir = async () => {
    if (!canSaveBackupDir.value) return
    await persistBackupDir(backupDirInput.value || '', false)
}

const resetBackupDirToDefault = async () => {
    await persistBackupDir('', true)
}

const copyBackupDir = async () => {
    const path = backupSettings.value.effective_backup_dir
    if (!path) return
    const ok = await copyToClipboard(path)
    showBackupToast(
        ok
            ? t('features.settings.backup.settings.copySuccess')
            : t('features.settings.backup.settings.copyFailed'),
        ok ? 'success' : 'error'
    )
}

// 加载备份列表
const loadBackupList = async () => {
    loadingList.value = true
    try {
        const response = await backupApi.list()
        if (response.data.status === 'ok') {
            backupList.value = response.data.data.items || []
            if (response.data.data.backup_dir && !backupSettings.value.effective_backup_dir) {
                backupSettings.value.effective_backup_dir = response.data.data.backup_dir
            }
        } else {
            backupList.value = []
        }
    } catch (error) {
        backupList.value = []
        console.error('Failed to load backup list:', error)
    } finally {
        loadingList.value = false
    }
}

// 开始导出
const startExport = async () => {
    editingBackupDir.value = false
    exportStatus.value = 'processing'
    exportProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await backupApi.create()
        if (response.data.status === 'ok') {
            exportTaskId.value = response.data.data.task_id
            pollExportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        exportStatus.value = 'failed'
        exportError.value = error.message || 'Export failed'
        loadBackupSettings()
    }
}

// 轮询导出进度
const pollExportProgress = async () => {
    if (!exportTaskId.value) return

    try {
        const response = await backupApi.progress(exportTaskId.value)

        if (response.data.status === 'ok') {
            const data = response.data.data
            
            if (data.status === 'processing' && data.progress) {
                exportProgress.value = {
                    current: data.progress.current || 0,
                    total: data.progress.total || 100,
                    message: data.progress.message || ''
                }
                setTimeout(pollExportProgress, 1000)
            } else if (data.status === 'completed') {
                exportStatus.value = 'completed'
                exportResult.value = data.result
                loadBackupSettings()
                loadBackupList()
            } else if (data.status === 'failed') {
                exportStatus.value = 'failed'
                exportError.value = data.error || 'Export failed'
                loadBackupSettings()
            } else {
                setTimeout(pollExportProgress, 1000)
            }
        }
    } catch (error) {
        exportStatus.value = 'failed'
        exportError.value = error.message || 'Failed to get export progress'
    }
}

// 重置导出状态
const resetExport = () => {
    exportStatus.value = 'idle'
    exportTaskId.value = null
    exportProgress.value = { current: 0, total: 100, message: '' }
    exportResult.value = null
    exportError.value = ''
}

// 上传并检查
const uploadAndCheck = async () => {
    if (!importFile.value) return

    editingBackupDir.value = false
    importStatus.value = 'uploading'
    uploadMessageOverride.value = ''

    const result = await uploader.start(importFile.value)
    if (!result) {
        if (uploader.status.value === 'error') {
            importStatus.value = 'failed'
            importError.value = uploader.errorMessage.value
        }
        loadBackupSettings()
        return
    }

    uploadedFilename.value = result.filename
    loadBackupSettings()
    await checkUploadedBackup()
}

// 断点续传：补传缺失分片后接着预检查
const resumeAndCheck = async () => {
    importStatus.value = 'uploading'
    importError.value = ''
    uploadMessageOverride.value = ''

    const result = await uploader.resume()
    if (!result) {
        if (uploader.status.value === 'error') {
            importStatus.value = 'failed'
            importError.value = uploader.errorMessage.value
        }
        loadBackupSettings()
        return
    }

    uploadedFilename.value = result.filename
    loadBackupSettings()
    await checkUploadedBackup()
}

// 上传完成后的预检查
const checkUploadedBackup = async () => {
    uploadMessageOverride.value = t('features.settings.backup.import.checking')

    try {
        const checkResponse = await backupApi.check(uploadedFilename.value)

        if (checkResponse.data.status !== 'ok') {
            throw new Error(checkResponse.data.message)
        }

        checkResult.value = checkResponse.data.data

        // 检查是否有效
        if (!checkResult.value.valid) {
            importStatus.value = 'failed'
            importError.value = checkResult.value.error || t('features.settings.backup.import.invalidBackup')
            return
        }

        // 显示确认对话框
        importStatus.value = 'confirm'

    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Upload failed'
    }
}

// 确认导入
const confirmImport = async () => {
    if (!uploadedFilename.value) return

    editingBackupDir.value = false
    importStatus.value = 'processing'
    importProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await backupApi.import(uploadedFilename.value, true)

        if (response.data.status === 'ok') {
            importTaskId.value = response.data.data.task_id
            pollImportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Import failed'
        loadBackupSettings()
    }
}

// 轮询导入进度
const pollImportProgress = async () => {
    if (!importTaskId.value) return

    try {
        const response = await backupApi.progress(importTaskId.value)

        if (response.data.status === 'ok') {
            const data = response.data.data
            
            if (data.status === 'processing' && data.progress) {
                importProgress.value = {
                    current: data.progress.current || 0,
                    total: data.progress.total || 100,
                    message: data.progress.message || ''
                }
                setTimeout(pollImportProgress, 1000)
            } else if (data.status === 'completed') {
                importStatus.value = 'completed'
                loadBackupSettings()
            } else if (data.status === 'failed') {
                importStatus.value = 'failed'
                importError.value = data.error || 'Import failed'
                loadBackupSettings()
            } else {
                setTimeout(pollImportProgress, 1000)
            }
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.message || 'Failed to get import progress'
        loadBackupSettings()
    }
}

// 重置导入状态
const resetImport = async () => {
    // 取消并清理可能存在的上传会话（包括失败后可续传的会话）
    await uploader.cancel()
    if (isOpen.value) {
        loadBackupSettings()
    }

    importStatus.value = 'idle'
    importFile.value = null
    importTaskId.value = null
    importProgress.value = { current: 0, total: 100, message: '' }
    importError.value = ''
    uploadedFilename.value = ''
    checkResult.value = null
    uploadMessageOverride.value = ''
}

// 下载备份（使用浏览器原生下载，可显示下载进度）
const downloadBackup = (filename) => {
    // 获取 token 用于鉴权（因为浏览器原生下载无法携带 Authorization header）
    const token = localStorage.getItem('token')
    if (!token) {
        alert(t('core.common.unauthorized'))
        return
    }
    
    // 直接使用浏览器下载，这样可以看到原生下载进度条
    const downloadUrl = backupApi.downloadUrl(filename, token)
    
    // 创建隐藏的 a 标签触发下载
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
}

// 从列表中恢复备份
const restoreFromList = async (filename) => {
    // 切换到导入标签页并设置文件名
    uploadedFilename.value = filename
    
    // 预检查
    try {
        const checkResponse = await backupApi.check(filename)

        if (checkResponse.data.status !== 'ok') {
            throw new Error(checkResponse.data.message)
        }

        checkResult.value = checkResponse.data.data
        
        if (!checkResult.value.valid) {
            alert(checkResult.value.error || t('features.settings.backup.import.invalidBackup'))
            return
        }

        // 切换到导入标签页并显示确认
        activeTab.value = 'import'
        importStatus.value = 'confirm'

    } catch (error) {
        alert(error.response?.data?.message || error.message || 'Check failed')
    }
}

// 删除备份
const deleteBackup = async (filename) => {
    if (!(await askForConfirmation(t('features.settings.backup.list.confirmDelete'), confirmDialog))) return

    try {
        const response = await backupApi.delete(filename)
        if (response.data.status === 'ok') {
            loadBackupList()
        } else {
            alert(response.data.message || 'Delete failed')
        }
    } catch (error) {
        alert(error.message || 'Delete failed')
    }
}

// 重命名相关函数
const openRenameDialog = (filename) => {
    renameOldFilename.value = filename
    // 移除 .zip 后缀，只显示文件名部分
    renameNewName.value = filename.replace(/\.zip$/i, '')
    renameError.value = ''
    renameDialogOpen.value = true
}

const closeRenameDialog = () => {
    renameDialogOpen.value = false
    renameOldFilename.value = ''
    renameNewName.value = ''
    renameError.value = ''
}

// 文件名验证规则
const renameValidationRule = (value) => {
    if (!value) return t('features.settings.backup.list.renameRequired')
    // 检查是否包含非法字符
    if (/[\\/:*?"<>|]/.test(value)) {
        return t('features.settings.backup.list.renameInvalidChars')
    }
    // 检查是否包含路径遍历字符
    if (value.includes('..')) {
        return t('features.settings.backup.list.renameInvalidChars')
    }
    return true
}

const confirmRename = async () => {
    if (!renameNewName.value || renameError.value) return
    
    // 前端验证
    const validationResult = renameValidationRule(renameNewName.value)
    if (validationResult !== true) {
        renameError.value = validationResult
        return
    }

    renameLoading.value = true
    renameError.value = ''

    try {
        const response = await backupApi.rename(renameOldFilename.value, {
            new_name: renameNewName.value
        })

        if (response.data.status === 'ok') {
            closeRenameDialog()
            loadBackupList()
        } else {
            renameError.value = response.data.message || t('features.settings.backup.list.renameFailed')
        }
    } catch (error) {
        renameError.value = error.response?.data?.message || error.message || t('features.settings.backup.list.renameFailed')
    } finally {
        renameLoading.value = false
    }
}

// 格式化文件大小
const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 格式化日期（从时间戳）
const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
}

// 格式化 ISO 日期字符串
const formatISODate = (isoString) => {
    if (!isoString) return ''
    try {
        return new Date(isoString).toLocaleString()
    } catch {
        return isoString
    }
}

// 重启 AstrBot
const restartAstrBot = async () => {
    try {
        await restartAstrBotRuntime(wfr.value)
    } catch (error) {
        console.error(error)
    }
}

// 重置所有状态
const resetAll = async () => {
    editingBackupDir.value = false
    settingsError.value = ''
    resetExport()
    await resetImport()
    activeTab.value = 'export'
}

// 关闭对话框
const handleClose = () => {
    if (isProcessing.value) return
    isOpen.value = false
}

// 打开对话框
const open = () => {
    isOpen.value = true
}

defineExpose({ open })
</script>

<style scoped>
.backup-dir-card {
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    border-radius: 12px;
    background: rgba(var(--v-theme-on-surface), 0.02);
    padding: 12px 14px;
}

.backup-dir-card__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
}

.backup-dir-card__title-group {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
}

.backup-dir-card__title {
    font-size: 0.9rem;
    font-weight: 600;
}

.backup-dir-card__header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

.backup-dir-card__path {
    margin-top: 8px;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    font-size: 0.82rem;
    line-height: 1.45;
    word-break: break-all;
}

.backup-dir-card__input-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    flex-wrap: wrap;
}

.backup-dir-card__input {
    flex: 1 1 280px;
}

.backup-dir-card__note {
    display: flex;
    align-items: flex-start;
    line-height: 1.45;
}

.backup-dir-card__note .v-icon {
    margin-top: 2px;
    flex-shrink: 0;
}

.backup-dir-card__actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
}

.backup-saved-path,
.backup-ftp-hint {
    word-break: break-all;
}

.v-list-item {
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.v-list-item:last-child {
    border-bottom: none;
}

/* 禁用 Chip 的交互效果 */
.non-interactive-chip {
    pointer-events: none;
    cursor: default;
}

.non-interactive-chip:hover {
    box-shadow: none !important;
}
</style>

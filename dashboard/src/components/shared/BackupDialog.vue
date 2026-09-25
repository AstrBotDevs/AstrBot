<template>
    <v-dialog v-model="isOpen" persistent max-width="700" scrollable>
        <v-card>
            <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
                <v-icon class="mr-2">mdi-backup-restore</v-icon>
                {{ t('features.settings.backup.dialog.title') }}
            </v-card-title>

            <v-card-text class="backup-content pa-4 pa-sm-6">
                <!-- 选项卡 -->
                <v-tabs v-model="activeTab" color="primary" class="backup-tabs mb-5">
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
                        <div v-if="exportStatus === 'idle'" class="py-2">
                            <div class="d-flex align-start ga-3 mb-5">
                                <v-avatar color="primary" variant="tonal" rounded="lg" size="44">
                                    <v-icon size="26">mdi-cloud-upload</v-icon>
                                </v-avatar>
                                <div>
                                    <h3 class="text-h4 mb-1">{{ t('features.settings.backup.export.title') }}</h3>
                                    <p class="backup-description text-medium-emphasis mb-0">{{ t('features.settings.backup.export.description') }}</p>
                                </div>
                            </div>
                            <div class="d-flex align-center flex-wrap ga-2 mb-3">
                                <span class="backup-section-title">{{ t('features.settings.backup.export.selectComponents') }}</span>
                                <v-spacer />
                                <div class="d-flex ga-1">
                                    <v-btn size="small" color="primary" variant="text" @click="exportComponents = [...BACKUP_COMPONENTS]">
                                        {{ t('features.settings.backup.export.selectAll') }}
                                    </v-btn>
                                    <v-btn size="small" variant="text" @click="exportComponents = []">
                                        {{ t('features.settings.backup.export.clearAll') }}
                                    </v-btn>
                                </div>
                            </div>
                            <BackupScopeSelector
                                v-model="exportComponents"
                                :groups="BACKUP_GROUPS"
                                :available-components="BACKUP_COMPONENTS"
                                class="mb-4"
                            />
                            <v-alert v-if="exportLinkWarnings.length" type="warning" variant="tonal" class="mb-4 text-left">
                                <div v-for="(w, i) in exportLinkWarnings" :key="i">{{ w }}</div>
                            </v-alert>
                            <div class="d-flex justify-end mt-5">
                                <v-btn color="primary" variant="tonal" size="large" @click="startExport" :loading="exportStatus === 'processing'" :disabled="exportComponents.length === 0">
                                    <v-icon class="mr-2">mdi-export</v-icon>
                                    {{ t('features.settings.backup.export.button') }}
                                </v-btn>
                            </div>
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
                            <p class="mb-4">{{ exportResult?.filename }}</p>
                            <div v-if="exportResult?.components?.length" class="d-flex flex-wrap justify-center ga-2 mb-4">
                                <v-chip v-for="comp in exportResult.components" :key="comp" size="small" color="success" variant="tonal" :ripple="false" class="non-interactive-chip">
                                    {{ t(`features.settings.backup.components.${comp}`) }}
                                </v-chip>
                            </div>
                            <v-alert v-if="exportResult?.skipped?.length" type="warning" variant="tonal" class="mb-4 text-left">
                                <div v-for="(s, i) in exportResult.skipped" :key="i">{{ s.entry }}: {{ s.reason }}</div>
                            </v-alert>
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

                            <h3 class="backup-section-title mb-3">{{ t('features.settings.backup.import.restoreScope') }}</h3>
                            <BackupScopeSelector
                                v-model="importComponents"
                                :groups="BACKUP_GROUPS"
                                :available-components="checkResult?.available_components || []"
                                :broken-components="checkResult?.broken_components || []"
                                :disabled="!checkResult?.can_import"
                                class="mb-4"
                            />
                            <v-alert v-if="checkResult?.can_import" type="warning" variant="tonal" class="mb-4" aria-live="polite">
                                <template v-if="importComponents.length">
                                    <div class="font-weight-medium">{{ t('features.settings.backup.import.replacementSummary') }}</div>
                                    <div>{{ importComponents.map(comp => t(`features.settings.backup.components.${comp}`)).join(', ') }}</div>
                                </template>
                                <template v-else>{{ t('features.settings.backup.scope.selectAtLeastOne') }}</template>
                            </v-alert>

                            <v-alert v-if="importLinkWarnings.length" type="warning" variant="tonal" class="mb-4">
                                <div v-for="(w, i) in importLinkWarnings" :key="i">{{ w }}</div>
                            </v-alert>

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
                                    :disabled="importComponents.length === 0"
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
                            <div v-if="importProgress.stages?.length" class="mt-4 text-left mx-auto" style="max-width: 420px;">
                                <div v-for="(s, i) in importProgress.stages" :key="i" class="text-caption text-grey d-flex align-center">
                                    <v-icon size="x-small" color="success" class="mr-1">mdi-check-circle</v-icon>
                                    <span>{{ s.message }}</span>
                                </div>
                            </div>
                        </div>

                        <div v-else-if="importStatus === 'completed'" class="text-center py-8">
                            <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.completed') }}</h3>
                            <v-alert v-if="importResult?.warnings?.length" type="warning" variant="tonal" class="mb-4 text-left">
                                <div v-for="(w, i) in importResult.warnings" :key="i">{{ w }}</div>
                            </v-alert>
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
                            <v-alert v-if="importResult?.warnings?.length" type="warning" variant="tonal" class="mb-4 text-left">
                                <div v-for="(w, i) in importResult.warnings" :key="i">{{ w }}</div>
                            </v-alert>
                            <v-card v-if="importRestoredStats.length" variant="outlined" class="mb-4 text-left">
                                <v-card-title class="text-subtitle-1">
                                    <v-icon class="mr-2">mdi-database-refresh</v-icon>
                                    {{ t('features.settings.backup.import.restoredBeforeFailure') }}
                                </v-card-title>
                                <v-card-text>
                                    <div v-for="(s, i) in importRestoredStats" :key="i" class="text-body-2">{{ s }}</div>
                                </v-card-text>
                            </v-card>
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
                        <p class="text-caption text-grey text-center mt-4">
                            <v-icon size="small" class="mr-1">mdi-information-outline</v-icon>
                            {{ t('features.settings.backup.list.ftpHint') }}
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
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog'
import { restartAstrBot as restartAstrBotRuntime } from '@/utils/restartAstrBot'
import WaitingForRestart from './WaitingForRestart.vue'
import BackupScopeSelector from './BackupScopeSelector.vue'

const { t } = useI18n()

const confirmDialog = useConfirmDialog()

const isOpen = ref(false)
const activeTab = ref('export')
const wfr = ref(null)

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

// Grouping affects presentation only; the API still receives individual components.
const BACKUP_GROUPS = [
    { id: 'main', components: ['database', 'knowledge_base', 'cmd_config', 'config', 'attachments'] },
    { id: 'extensions', components: ['plugins', 'plugin_data', 'skills', 't2i_templates'] },
    { id: 'temporary', components: ['temp'] },
]
const BACKUP_COMPONENTS = BACKUP_GROUPS.flatMap(group => group.components)
const exportComponents = ref(BACKUP_COMPONENTS.filter(component => component !== 'temp'))
// Restore all available components by default after checking the backup.
const importComponents = ref([])
// 导入结果（完成页展示 warnings）
const importResult = ref(null)

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

// 导出侧连锁警告：附件依赖主库；非全量备份旧版不可恢复
const exportLinkWarnings = computed(() => {
    const warnings = []
    const selected = exportComponents.value
    if (!selected.includes('database') && selected.includes('attachments')) {
        warnings.push(t('features.settings.backup.export.warningAttachmentsWithoutDb'))
    }
    if (selected.length > 0 && selected.length < BACKUP_COMPONENTS.length) {
        warnings.push(t('features.settings.backup.export.warningSelectiveOldVersion'))
    }
    return warnings
})

// 恢复侧连锁警告：单独恢复附件可能成为孤儿文件
const importLinkWarnings = computed(() => {
    if (!importComponents.value.includes('database') && importComponents.value.includes('attachments')) {
        return [t('features.settings.backup.import.warningAttachmentsWithoutDb')]
    }
    return []
})

// 失败前已恢复的内容统计（失败页展示，让用户判断哪些数据已被修改）
// 零计数项同样展示并标注"已清空"——恢复空表意味着旧数据已被清除
const importRestoredStats = computed(() => {
    const r = importResult.value
    if (!r) return []
    const annotate = (key, count) =>
        count > 0
            ? `${key}: ${count}`
            : `${key}: ${t('features.settings.backup.import.restoredEmpty')}`
    const stats = []
    for (const [table, count] of Object.entries(r.imported_tables || {})) {
        stats.push(annotate(table, count))
    }
    for (const [key, count] of Object.entries(r.imported_files || {})) {
        stats.push(annotate(key, count))
    }
    for (const [key, count] of Object.entries(r.imported_directories || {})) {
        stats.push(annotate(key, count))
    }
    return stats
})

// 监听对话框打开
watch(isOpen, (newVal) => {
    if (newVal) {
        loadBackupList()
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

// 加载备份列表
const loadBackupList = async () => {
    loadingList.value = true
    try {
        const response = await backupApi.list()
        if (response.data.status === 'ok') {
            backupList.value = response.data.data.items || []
        }
    } catch (error) {
        console.error('Failed to load backup list:', error)
    } finally {
        loadingList.value = false
    }
}

// 开始导出
const startExport = async () => {
    exportStatus.value = 'processing'
    exportProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await backupApi.create({ components: [...exportComponents.value] })
        if (response.data.status === 'ok') {
            exportTaskId.value = response.data.data.task_id
            pollExportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        exportStatus.value = 'failed'
        exportError.value = error.message || 'Export failed'
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
                loadBackupList()
            } else if (data.status === 'failed') {
                exportStatus.value = 'failed'
                exportError.value = data.error || 'Export failed'
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

    importStatus.value = 'uploading'
    uploadMessageOverride.value = ''

    const result = await uploader.start(importFile.value)
    if (!result) {
        if (uploader.status.value === 'error') {
            importStatus.value = 'failed'
            importError.value = uploader.errorMessage.value
        }
        return
    }

    uploadedFilename.value = result.filename
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
        return
    }

    uploadedFilename.value = result.filename
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

        // 恢复范围默认全选可用组件（broken 组件不可勾选）
        importComponents.value = [...(checkResult.value.available_components || [])]

        // 显示确认对话框
        importStatus.value = 'confirm'

    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Upload failed'
    }
}

// 确认导入
const confirmImport = async () => {
    if (!uploadedFilename.value || !checkResult.value?.can_import || !importComponents.value.length) return

    importStatus.value = 'processing'
    importProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await backupApi.import(
            uploadedFilename.value,
            true,
            [...importComponents.value]
        )

        if (response.data.status === 'ok') {
            importTaskId.value = response.data.data.task_id
            pollImportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Import failed'
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
                    message: data.progress.message || '',
                    stages: data.progress.stages || []
                }
                setTimeout(pollImportProgress, 1000)
            } else if (data.status === 'completed') {
                importStatus.value = 'completed'
                importResult.value = data.result
            } else if (data.status === 'failed') {
                importStatus.value = 'failed'
                importResult.value = data.result
                importError.value = data.error || 'Import failed'
            } else {
                setTimeout(pollImportProgress, 1000)
            }
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.message || 'Failed to get import progress'
    }
}

// 重置导入状态
const resetImport = async () => {
    // 取消并清理可能存在的上传会话（包括失败后可续传的会话）
    await uploader.cancel()

    importStatus.value = 'idle'
    importFile.value = null
    importTaskId.value = null
    importProgress.value = { current: 0, total: 100, message: '' }
    importError.value = ''
    uploadedFilename.value = ''
    checkResult.value = null
    importComponents.value = []
    importResult.value = null
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

        // 恢复范围默认全选可用组件（broken 组件不可勾选）
        importComponents.value = [...(checkResult.value.available_components || [])]

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
    resetExport()
    exportComponents.value = BACKUP_COMPONENTS.filter(component => component !== 'temp')
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
.backup-description,
.backup-content :deep(.v-alert__content) {
    font-size: 0.875rem;
    line-height: 1.65;
}

.backup-section-title {
    font-size: 0.875rem;
    font-weight: 600;
    line-height: 1.5;
}

@media (max-width: 599px) {
    .backup-tabs :deep(.v-tab) {
        min-width: 0;
        padding-inline: 12px;
        font-size: 0.8125rem;
    }

    .backup-tabs :deep(.v-tab .v-icon) {
        display: none;
    }
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

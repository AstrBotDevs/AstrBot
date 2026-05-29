<template>
  <div class="skills-page">
    <v-container fluid class="pa-0" elevation="0">
      <v-row
        v-if="neoEnabled"
        class="d-flex justify-end align-center px-4 py-3 pb-4"
      >
        <v-btn-toggle
          v-model="mode"
          mandatory
          divided
          density="comfortable"
        >
          <v-btn value="local">{{ tm("skills.modeLocal") }}</v-btn>
          <v-btn value="neo">{{ tm("skills.modeNeo") }}</v-btn>
        </v-btn-toggle>
      </v-row>

      <div v-if="mode === 'local'" class="px-2 pb-2 d-flex flex-column ga-2">
        <v-alert
          v-if="runtime === 'sandbox' && !sandboxCache.ready"
          type="info"
          variant="tonal"
          density="comfortable"
          border="start"
        >
          {{ tm("skills.sandboxDiscoveryPending") }}
        </v-alert>
      </div>

      <div v-if="mode === 'neo' && !neoEnabled" class="px-3 pb-3">
        <v-alert
          type="warning"
          variant="tonal"
          density="comfortable"
          border="start"
        >
          {{ neoUnavailableMessage }}
        </v-alert>
      </div>

      <template v-if="mode === 'local'">
        <v-progress-linear
          v-if="loading"
          indeterminate
          color="primary"
        ></v-progress-linear>

        <div v-else-if="skills.length === 0" class="text-center pa-8">
          <v-icon size="64" color="grey-lighten-1">mdi-folder-open</v-icon>
          <p class="text-grey mt-4">{{ tm("skills.empty") }}</p>
          <small class="text-grey">{{ tm("skills.emptyHint") }}</small>
        </div>

        <div v-else class="skills-list pb-3">
          <OutlinedActionListItem
            v-for="skill in skills"
            :key="skill.name"
            :title="skill.name"
            clickable
            @click="openSkillEditor(skill)"
          >
            <template #title-extra>
              <v-chip
                size="x-small"
                variant="tonal"
                :color="sourceTypeColor(skill.source_type)"
              >
                {{ sourceTypeLabel(skill.source_type, skill) }}
              </v-chip>
            </template>

            <div class="skill-description text-body-2 text-medium-emphasis">
              {{ skill.description || tm("skills.noDescription") }}
            </div>

            <div class="skill-path text-caption text-medium-emphasis">
              <v-icon size="small" class="me-1">mdi-file-document</v-icon>
              {{ tm("skills.path") }}: {{ skill.path }}
            </div>

            <template #actions>
              <v-tooltip :text="tm('skills.download')" location="top">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    icon="mdi-download-outline"
                    variant="text"
                    size="small"
                    class="list-action-icon-btn"
                    :disabled="itemLoading[skill.name] || isReadOnlySourceSkill(skill)"
                    @click.stop="downloadSkill(skill)"
                  />
                </template>
              </v-tooltip>

              <v-tooltip :text="t('core.common.itemCard.delete')" location="top">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    icon="mdi-delete-outline"
                    variant="text"
                    size="small"
                    class="list-action-icon-btn"
                    :disabled="itemLoading[skill.name] || isReadOnlySourceSkill(skill)"
                    @click.stop="confirmDelete(skill)"
                  />
                </template>
              </v-tooltip>
            </template>

            <template #control>
              <v-tooltip location="top">
                <template #activator="{ props }">
                  <v-switch
                    v-bind="props"
                    color="primary"
                    density="compact"
                    hide-details
                    inset
                    :model-value="skill.active"
                    :loading="itemLoading[skill.name] || false"
                    :disabled="itemLoading[skill.name] || isSandboxPresetSkill(skill)"
                    @click.stop
                    @update:model-value="toggleSkill(skill)"
                  />
                </template>
                <span>{{
                  skill.active
                    ? t("core.common.itemCard.enabled")
                    : t("core.common.itemCard.disabled")
                }}</span>
              </v-tooltip>
            </template>
          </OutlinedActionListItem>
        </div>
      </template>

      <template v-else-if="mode === 'neo' && neoEnabled">
        <v-card class="mx-3 mb-4 pa-4 neo-filter-card" variant="outlined">
          <div
            class="d-flex flex-wrap justify-space-between align-center ga-2 mb-3"
          >
            <div>
              <div class="text-subtitle-1 font-weight-bold">Neo Skills</div>
              <div class="text-caption text-medium-emphasis">
                {{ tm("skills.neoFilterHint") }}
              </div>
            </div>
          </div>

          <v-row class="ga-md-0 ga-2">
            <v-col cols="12" md="4">
              <v-text-field
                v-model="neoFilters.skill_key"
                :label="tm('skills.neoSkillKey')"
                prepend-inner-icon="mdi-key-outline"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-select
                v-model="neoFilters.status"
                :label="tm('skills.neoStatus')"
                :items="candidateStatusItems"
                item-title="title"
                item-value="value"
                prepend-inner-icon="mdi-progress-check"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-select
                v-model="neoFilters.stage"
                :label="tm('skills.neoStage')"
                :items="releaseStageItems"
                item-title="title"
                item-value="value"
                prepend-inner-icon="mdi-layers-outline"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
          </v-row>
        </v-card>

        <v-progress-linear
          v-if="neoLoading"
          indeterminate
          color="primary"
        ></v-progress-linear>

        <div class="mx-3 mb-3 d-flex flex-wrap ga-2">
          <v-chip size="small" color="primary" variant="tonal"
            >Candidates: {{ neoCandidates.length }}</v-chip
          >
          <v-chip size="small" color="indigo" variant="tonal"
            >Releases: {{ neoReleases.length }}</v-chip
          >
          <v-chip size="small" color="success" variant="tonal"
            >Active: {{ activeReleaseCount }}</v-chip
          >
        </div>

        <v-card class="mx-3 mb-4 neo-table-card" variant="outlined">
          <v-card-title class="text-subtitle-1 font-weight-bold">{{
            tm("skills.neoCandidates")
          }}</v-card-title>
          <v-data-table
            :headers="candidateHeaders"
            :items="neoCandidates"
            density="compact"
            :items-per-page="10"
            class="neo-data-table"
          >
            <template #item.latest_score="{ item }">
              {{ item.latest_score ?? "-" }}
            </template>
            <template #item.actions="{ item }">
              <div class="d-flex ga-1 flex-wrap">
                <v-btn
                  size="x-small"
                  color="success"
                  variant="tonal"
                  @click="evaluateCandidate(item, true)"
                >
                  {{ tm("skills.neoPass") }}
                </v-btn>
                <v-btn
                  size="x-small"
                  color="warning"
                  variant="tonal"
                  @click="evaluateCandidate(item, false)"
                >
                  {{ tm("skills.neoReject") }}
                </v-btn>
                <v-btn
                  size="x-small"
                  color="primary"
                  variant="tonal"
                  :loading="isCandidatePromoteLoading(item.id, 'canary')"
                  :disabled="isCandidatePromoting(item.id)"
                  @click="promoteCandidate(item, 'canary')"
                >
                  Canary
                </v-btn>
                <v-btn
                  size="x-small"
                  color="primary"
                  variant="tonal"
                  :loading="isCandidatePromoteLoading(item.id, 'stable')"
                  :disabled="isCandidatePromoting(item.id)"
                  @click="promoteCandidate(item, 'stable')"
                >
                  Stable
                </v-btn>
                <v-btn
                  size="x-small"
                  variant="tonal"
                  :disabled="!item.payload_ref"
                  @click="viewPayload(item.payload_ref)"
                >
                  Payload
                </v-btn>
                <v-btn
                  size="x-small"
                  color="error"
                  variant="tonal"
                  @click="deleteCandidate(item)"
                >
                  {{ tm("skills.neoDelete") }}
                </v-btn>
              </div>
            </template>
          </v-data-table>
        </v-card>

        <v-card class="mx-3 mb-4 neo-table-card" variant="outlined">
          <v-card-title class="text-subtitle-1 font-weight-bold">{{
            tm("skills.neoReleases")
          }}</v-card-title>
          <v-data-table
            :headers="releaseHeaders"
            :items="neoReleases"
            density="compact"
            :items-per-page="10"
            class="neo-data-table"
          >
            <template #item.is_active="{ item }">
              <v-chip
                size="small"
                :color="item.is_active ? 'success' : 'default'"
                variant="tonal"
              >
                {{ item.is_active ? "active" : "inactive" }}
              </v-chip>
            </template>
            <template #item.actions="{ item }">
              <div class="d-flex ga-1 flex-wrap">
                <v-btn
                  size="x-small"
                  color="warning"
                  variant="tonal"
                  @click="handleReleaseLifecycleAction(item)"
                >
                  {{
                    item.is_active
                      ? tm("skills.neoDeactivate")
                      : tm("skills.neoRollback")
                  }}
                </v-btn>
                <v-btn
                  size="x-small"
                  color="primary"
                  variant="tonal"
                  @click="syncRelease(item)"
                >
                  {{ tm("skills.neoSync") }}
                </v-btn>
                <v-btn
                  size="x-small"
                  color="error"
                  variant="tonal"
                  @click="deleteRelease(item)"
                >
                  {{ tm("skills.neoDelete") }}
                </v-btn>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </template>
    </v-container>

    <div class="skills-fab-stack">
      <v-tooltip :text="tm('skills.refresh')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="darkprimary"
            icon="mdi-refresh"
            size="x-large"
            variant="elevated"
            class="skills-fab"
            @click="refreshCurrentMode"
          />
        </template>
      </v-tooltip>
      <v-tooltip
        v-if="mode === 'local'"
        :text="tm('skills.upload')"
        location="left"
      >
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="darkprimary"
            icon="mdi-upload"
            size="x-large"
            variant="elevated"
            class="skills-fab"
            @click="openUploadDialog"
          />
        </template>
      </v-tooltip>
    </div>

    <v-dialog v-model="uploadDialog" max-width="880px" :persistent="uploading">
      <v-card class="skills-upload-dialog">
        <v-card-title class="skills-upload-dialog__header px-6 pt-6 pb-2">
          <div class="skills-upload-dialog__heading">
            <div class="text-h4 font-weight-medium">
              {{ tm("skills.uploadDialogTitle") }}
            </div>
          </div>
          <v-btn
            class="skills-upload-dialog__close"
            icon="mdi-close"
            variant="text"
            :disabled="uploading"
            @click="closeUploadDialog"
          />
        </v-card-title>

        <v-card-text class="skills-upload-dialog__body px-6 pb-5 pt-2">
          <p
            class="skills-upload-dialog__description skills-upload-dialog__description--body"
          >
            {{ tm("skills.uploadHint") }}
          </p>

          <div class="skills-upload-structure-note">
            <v-icon size="18">mdi-information-outline</v-icon>
            <span>{{ tm("skills.structureRequirement") }}</span>
          </div>

          <div class="skills-upload-capabilities">
            <div class="skills-upload-capability">
              <div class="skills-upload-capability__icon">
                <v-icon size="18">mdi-layers-outline</v-icon>
              </div>
              <span>{{ tm("skills.abilityMultiple") }}</span>
            </div>
            <div class="skills-upload-capability">
              <div class="skills-upload-capability__icon">
                <v-icon size="18">mdi-shield-check-outline</v-icon>
              </div>
              <span>{{ tm("skills.abilityValidate") }}</span>
            </div>
            <div class="skills-upload-capability">
              <div class="skills-upload-capability__icon">
                <v-icon size="18">mdi-skip-next-circle-outline</v-icon>
              </div>
              <span>{{ tm("skills.abilitySkip") }}</span>
            </div>
          </div>

          <div
            class="skills-dropzone"
            :class="{ 'skills-dropzone--dragover': isUploadDragging }"
            role="button"
            tabindex="0"
            :aria-label="tm('skills.dropzoneTitle')"
            @click="openUploadPicker"
            @keydown.enter="openUploadPicker"
            @keydown.space.prevent="openUploadPicker"
            @dragover.prevent="isUploadDragging = true"
            @dragleave.prevent="isUploadDragging = false"
            @drop.prevent="handleUploadDrop"
          >
            <div class="skills-dropzone__icon">
              <v-icon size="34">mdi-folder-zip-outline</v-icon>
            </div>
            <div class="text-h6 font-weight-medium">
              {{ tm("skills.dropzoneTitle") }}
            </div>
            <div class="skills-dropzone__subtitle">
              {{ tm("skills.dropzoneAction") }}
            </div>
            <div class="skills-dropzone__hint">
              {{ tm("skills.dropzoneHint") }}
            </div>
            <input
              ref="uploadInput"
              type="file"
              multiple
              hidden
              accept=".zip"
              @change="handleUploadSelection"
            />
          </div>

          <div v-if="uploadItems.length > 0" class="skills-upload-summary">
            <v-chip
              size="small"
              variant="flat"
              class="skills-upload-summary__chip"
            >
              {{
                tm("skills.summaryTotal", { count: uploadStateCounts.total })
              }}
            </v-chip>
            <v-chip
              size="small"
              variant="flat"
              class="skills-upload-summary__chip"
            >
              {{
                tm("skills.summaryReady", {
                  count:
                    uploadStateCounts.waiting + uploadStateCounts.uploading,
                })
              }}
            </v-chip>
            <v-chip
              size="small"
              variant="flat"
              class="skills-upload-summary__chip skills-upload-summary__chip--success"
            >
              {{
                tm("skills.summarySuccess", {
                  count: uploadStateCounts.success,
                })
              }}
            </v-chip>
            <v-chip
              size="small"
              variant="flat"
              class="skills-upload-summary__chip skills-upload-summary__chip--error"
            >
              {{
                tm("skills.summaryFailed", { count: uploadStateCounts.error })
              }}
            </v-chip>
            <v-chip
              size="small"
              variant="flat"
              class="skills-upload-summary__chip"
            >
              {{
                tm("skills.summarySkipped", {
                  count: uploadStateCounts.skipped,
                })
              }}
            </v-chip>
          </div>

          <div v-if="uploadItems.length > 0" class="skills-upload-list">
            <div class="skills-upload-list__header">
              <span>{{ tm("skills.fileListTitle") }}</span>
            </div>
            <div
              v-for="item in uploadItems"
              :key="item.id"
              class="skills-upload-row"
            >
              <div class="skills-upload-row__meta">
                <div class="skills-upload-row__name">{{ item.name }}</div>
                <div class="skills-upload-row__size">
                  {{ formatFileSize(item.size) }}
                </div>
                <div class="skills-upload-row__message">
                  {{ item.validationMessage }}
                </div>
              </div>
              <div class="skills-upload-row__actions">
                <v-chip
                  size="small"
                  variant="flat"
                  :class="statusChipClass(item.status)"
                >
                  {{ uploadStatusLabel(item.status) }}
                </v-chip>
                <v-btn
                  icon="mdi-close"
                  size="small"
                  variant="text"
                  :disabled="uploading || item.status === 'uploading'"
                  @click="removeUploadItem(item.id)"
                />
              </div>
            </div>
          </div>
          <div v-else class="skills-upload-empty">
            {{ tm("skills.fileListEmpty") }}
          </div>
        </v-card-text>

        <v-card-actions
          class="skills-upload-dialog__actions justify-end px-6 pb-3 pt-2"
        >
          <v-btn
            class="skills-upload-dialog__action-btn"
            variant="tonal"
            color="secondary"
            :disabled="uploading"
            @click="closeUploadDialog"
          >
            {{ tm("skills.cancel") }}
          </v-btn>
          <v-btn
            class="skills-upload-dialog__action-btn"
            variant="flat"
            color="primary"
            :loading="uploading"
            :disabled="!hasUploadableItems"
            @click="uploadSkillBatch"
          >
            {{ tm("skills.confirmUpload") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm("skills.deleteTitle") }}</v-card-title>
        <v-card-text>{{ tm("skills.deleteMessage") }}</v-card-text>
        <v-card-actions class="d-flex justify-end">
          <v-btn variant="text" @click="deleteDialog = false">{{
            tm("skills.cancel")
          }}</v-btn>
          <v-btn color="error" :loading="deleting" @click="deleteSkill">
            {{ t("core.common.itemCard.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog
      v-model="editorDialog.show"
      max-width="1180px"
      :persistent="editorDialog.saving"
    >
      <v-card class="skill-editor-dialog">
        <v-card-title class="skill-editor-dialog__header">
          <div>
            <div class="text-h3 font-weight-bold">
              {{ editorDialog.skillName }}
            </div>
          </div>
          <v-btn
            icon="mdi-close"
            variant="text"
            :disabled="editorDialog.saving"
            @click="closeSkillEditor"
          />
        </v-card-title>

        <v-card-text class="skill-editor-dialog__body">
          <div class="skill-editor">
            <div class="skill-editor__files">
              <div class="skill-editor__files-header">
                <v-btn
                  icon="mdi-arrow-up"
                  size="small"
                  variant="text"
                  :disabled="!editorDialog.currentDir || editorDialog.loadingFiles"
                  @click="openParentSkillDir"
                />
                <span>{{ editorDialog.currentDir || "/" }}</span>
              </div>

              <v-progress-linear
                v-if="editorDialog.loadingFiles"
                indeterminate
                color="primary"
              />

              <div v-else class="skill-editor__file-list">
                <button
                  v-for="entry in editorDialog.entries"
                  :key="`${entry.type}:${entry.path}`"
                  class="skill-editor__file-row"
                  :class="{
                    'skill-editor__file-row--active':
                      editorDialog.filePath === entry.path,
                  }"
                  type="button"
                  @click="openSkillEntry(entry)"
                >
                  <v-icon size="18">
                    {{
                      entry.type === "directory"
                        ? "mdi-folder-outline"
                        : "mdi-file-document-outline"
                    }}
                  </v-icon>
                  <span>{{ entry.name }}</span>
                  <v-chip
                    v-if="entry.type === 'file' && !entry.editable"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ tm("skills.readonly") }}
                  </v-chip>
                </button>
              </div>
            </div>

            <div class="skill-editor__content">
              <div class="skill-editor__content-header">
                <div class="skill-editor__path">
                  {{ editorDialog.filePath || tm("skills.noFileSelected") }}
                </div>
                <v-chip
                  v-if="editorDialog.fileDirty"
                  size="small"
                  color="warning"
                  variant="tonal"
                >
                  {{ tm("skills.unsaved") }}
                </v-chip>
              </div>

              <v-alert
                v-if="editorDialog.error"
                type="error"
                variant="tonal"
                density="compact"
                class="mb-3"
              >
                {{ editorDialog.error }}
              </v-alert>

              <div class="skill-editor__monaco">
                <VueMonacoEditor
                  v-model:value="editorDialog.content"
                  :theme="editorTheme"
                  :language="editorLanguage"
                  :options="editorOptions"
                  style="height: 100%; width: 100%;"
                  @change="editorDialog.fileDirty = true"
                />
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="skill-editor-dialog__actions">
          <v-spacer />
          <v-btn
            variant="text"
            :disabled="editorDialog.saving"
            @click="closeSkillEditor"
          >
            {{ tm("skills.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="editorDialog.saving"
            :disabled="
              !editorDialog.filePath ||
              !editorDialog.fileEditable ||
              !editorDialog.fileDirty
            "
            @click="saveSkillFile"
          >
            {{ tm("skills.saveFile") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="payloadDialog.show" max-width="820px">
      <v-card>
        <v-card-title>{{ tm("skills.neoPayloadTitle") }}</v-card-title>
        <v-card-text>
          <pre class="payload-preview">{{ payloadDialog.content }}</pre>
        </v-card-text>
        <v-card-actions class="d-flex justify-end">
          <v-btn variant="text" @click="payloadDialog.show = false">{{
            tm("skills.cancel")
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="snackbar.show"
      :timeout="3500"
      :color="snackbar.color"
      elevation="24"
    >
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from "axios";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import OutlinedActionListItem from "@/components/shared/OutlinedActionListItem.vue";
import { useCustomizerStore } from "@/stores/customizer";

const STATUS_WAITING = "waiting";
const STATUS_UPLOADING = "uploading";
const STATUS_SUCCESS = "success";
const STATUS_ERROR = "error";
const STATUS_SKIPPED = "skipped";

export default {
  name: "SkillsSection",
  components: { OutlinedActionListItem, VueMonacoEditor },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n("features/extension");
    const customizer = useCustomizerStore();

    const mode = ref("local");
    const skills = ref([]);
    const loading = ref(false);
    const runtime = ref("local");
    const sandboxCache = reactive({ ready: false, count: 0, updated_at: null });
    const uploading = ref(false);
    const uploadDialog = ref(false);
    const uploadInput = ref(null);
    const uploadItems = ref([]);
    const isUploadDragging = ref(false);
    const itemLoading = reactive({});
    const deleteDialog = ref(false);
    const deleting = ref(false);
    const skillToDelete = ref(null);
    const snackbar = reactive({ show: false, message: "", color: "success" });

    const neoLoading = ref(false);
    const neoCandidates = ref([]);
    const neoReleases = ref([]);
    const neoFilters = reactive({
      skill_key: "",
      status: "",
      stage: "",
    });
    const candidatePromoteLoading = reactive({});
    const payloadDialog = reactive({
      show: false,
      content: "",
    });
    const editorDialog = reactive({
      show: false,
      skillName: "",
      currentDir: "",
      entries: [],
      filePath: "",
      content: "",
      fileEditable: false,
      fileDirty: false,
      loadingFiles: false,
      loadingFile: false,
      saving: false,
      error: "",
    });

    const neoEnabled = ref(false);
    const neoUnavailableMessage = ref("");
    let nextUploadItemId = 0;

    const candidateStatusItems = computed(() => [
      { title: tm("skills.neoAll"), value: "" },
      { title: "draft", value: "draft" },
      { title: "evaluating", value: "evaluating" },
      { title: "promoted", value: "promoted" },
      { title: "promoted_canary", value: "promoted_canary" },
      { title: "promoted_stable", value: "promoted_stable" },
      { title: "rejected", value: "rejected" },
      { title: "rolled_back", value: "rolled_back" },
    ]);

    const releaseStageItems = computed(() => [
      { title: tm("skills.neoAll"), value: "" },
      { title: "canary", value: "canary" },
      { title: "stable", value: "stable" },
    ]);

    const activeReleaseCount = computed(
      () => neoReleases.value.filter((item) => item?.is_active).length,
    );
    const editorLanguage = computed(() => {
      const path = String(editorDialog.filePath || "").toLowerCase();
      if (path.endsWith(".json")) return "json";
      if (path.endsWith(".yaml") || path.endsWith(".yml")) return "yaml";
      if (path.endsWith(".toml") || path.endsWith(".ini")) return "ini";
      if (path.endsWith(".py")) return "python";
      if (path.endsWith(".js")) return "javascript";
      if (path.endsWith(".ts")) return "typescript";
      if (path.endsWith(".html")) return "html";
      if (path.endsWith(".css")) return "css";
      if (path.endsWith(".sh")) return "shell";
      if (path.endsWith(".md") || path.endsWith(".txt")) return "markdown";
      return "plaintext";
    });
    const editorTheme = computed(() =>
      customizer.uiTheme === "PurpleThemeDark" ? "vs-dark" : "vs-light",
    );
    const editorOptions = computed(() => ({
      automaticLayout: true,
      fontSize: 13,
      lineNumbers: "on",
      minimap: { enabled: false },
      readOnly: !editorDialog.fileEditable || editorDialog.loadingFile,
      scrollBeyondLastLine: false,
      tabSize: 2,
      wordWrap: "on",
    }));
    const uploadStateCounts = computed(() =>
      uploadItems.value.reduce(
        (counts, item) => {
          counts.total += 1;
          counts[item.status] += 1;
          return counts;
        },
        {
          total: 0,
          [STATUS_WAITING]: 0,
          [STATUS_UPLOADING]: 0,
          [STATUS_SUCCESS]: 0,
          [STATUS_ERROR]: 0,
          [STATUS_SKIPPED]: 0,
        },
      ),
    );
    const hasUploadableItems = computed(() =>
      uploadItems.value.some(
        (item) =>
          item.status === STATUS_WAITING || item.status === STATUS_ERROR,
      ),
    );

    const candidateHeaders = computed(() => [
      { title: "ID", key: "id", width: "180px" },
      { title: "skill_key", key: "skill_key" },
      { title: "status", key: "status", width: "130px" },
      { title: "score", key: "latest_score", width: "90px" },
      {
        title: tm("skills.actions"),
        key: "actions",
        sortable: false,
        width: "420px",
      },
    ]);

    const releaseHeaders = computed(() => [
      { title: "ID", key: "id", width: "180px" },
      { title: "skill_key", key: "skill_key" },
      { title: "stage", key: "stage", width: "100px" },
      { title: "version", key: "version", width: "90px" },
      { title: "active", key: "is_active", width: "110px" },
      {
        title: tm("skills.actions"),
        key: "actions",
        sortable: false,
        width: "220px",
      },
    ]);

    const showMessage = (message, color = "success") => {
      snackbar.message = message;
      snackbar.color = color;
      snackbar.show = true;
    };

    const normalizeSkillsPayload = (res) => {
      const payload = res?.data?.data || [];
      if (Array.isArray(payload)) {
        runtime.value = "local";
        sandboxCache.ready = false;
        sandboxCache.count = 0;
        sandboxCache.updated_at = null;
        return payload;
      }
      runtime.value = payload.runtime || "local";
      const cache = payload.sandbox_cache || {};
      sandboxCache.ready = !!cache.ready;
      sandboxCache.count = Number(cache.count || 0);
      sandboxCache.updated_at = cache.updated_at || null;
      return payload.skills || [];
    };

    const sourceTypeLabel = (sourceType, skill = null) => {
      if (sourceType === "plugin") {
        return tm("skills.sourcePlugin", {
          plugin: skill?.source_label || skill?.plugin_name || "",
        });
      }
      if (sourceType === "sandbox_only") return tm("skills.sourceSandboxOnly");
      if (sourceType === "both") return tm("skills.sourceBoth");
      return tm("skills.sourceLocalOnly");
    };

    const sourceTypeColor = (sourceType) => {
      if (sourceType === "sandbox_only") return "indigo";
      if (sourceType === "plugin") return "secondary";
      if (sourceType === "both") return "success";
      return "primary";
    };

    const isSandboxPresetSkill = (skill) =>
      skill?.source_type === "sandbox_only";
    const isPluginProvidedSkill = (skill) => skill?.source_type === "plugin";
    const isReadOnlySourceSkill = (skill) =>
      isSandboxPresetSkill(skill) || isPluginProvidedSkill(skill);

    const normalizeNeoItemsPayload = (res) => {
      const payload = res?.data?.data || [];
      if (Array.isArray(payload)) return payload;
      if (Array.isArray(payload.items)) return payload.items;
      return [];
    };

    const formatFileSize = (size) => {
      if (!Number.isFinite(size) || size <= 0) return "0 B";
      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
      return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    };

    const normalizeUploadName = (name) =>
      String(name || "")
        .trim()
        .toLowerCase();

    const buildUploadItem = (file, status, validationMessage) => ({
      id: `upload-${nextUploadItemId++}`,
      file,
      name: file.name,
      size: file.size,
      status,
      validationMessage,
      filenameKey: normalizeUploadName(file.name),
    });

    const uploadStatusLabel = (status) => {
      if (status === STATUS_UPLOADING) return tm("skills.statusUploading");
      if (status === STATUS_SUCCESS) return tm("skills.statusSuccess");
      if (status === STATUS_ERROR) return tm("skills.statusError");
      if (status === STATUS_SKIPPED) return tm("skills.statusSkipped");
      return tm("skills.statusWaiting");
    };

    const statusChipClass = (status) =>
      `skills-status-chip skills-status-chip--${status}`;

    const resetUploadState = () => {
      uploadItems.value = [];
      isUploadDragging.value = false;
      if (uploadInput.value) {
        uploadInput.value.value = "";
      }
    };

    const openUploadDialog = () => {
      uploadDialog.value = true;
    };

    const closeUploadDialog = () => {
      if (uploading.value) return;
      uploadDialog.value = false;
    };

    const openUploadPicker = () => {
      if (uploading.value) return;
      uploadInput.value?.click();
    };

    const addUploadFiles = (filesToAdd) => {
      const existingNames = new Set(
        uploadItems.value.map((item) => item.filenameKey),
      );
      const nextItems = [];

      for (const file of filesToAdd) {
        if (!file?.name) continue;
        const filenameKey = normalizeUploadName(file.name);

        if (existingNames.has(filenameKey)) {
          nextItems.push(
            buildUploadItem(
              file,
              STATUS_SKIPPED,
              tm("skills.validationDuplicate"),
            ),
          );
          continue;
        }

        existingNames.add(filenameKey);
        if (!/\.zip$/i.test(file.name)) {
          nextItems.push(
            buildUploadItem(
              file,
              STATUS_SKIPPED,
              tm("skills.validationZipOnly"),
            ),
          );
          continue;
        }

        nextItems.push(
          buildUploadItem(file, STATUS_WAITING, tm("skills.validationReady")),
        );
      }

      if (nextItems.length > 0) {
        uploadItems.value = [...uploadItems.value, ...nextItems];
      }
    };

    const handleUploadSelection = (event) => {
      const selected = Array.from(event?.target?.files || []);
      addUploadFiles(selected);
      if (uploadInput.value) {
        uploadInput.value.value = "";
      }
    };

    const handleUploadDrop = (event) => {
      isUploadDragging.value = false;
      if (uploading.value) {
        return;
      }
      addUploadFiles(Array.from(event?.dataTransfer?.files || []));
    };

    const removeUploadItem = (itemId) => {
      uploadItems.value = uploadItems.value.filter(
        (item) => item.id !== itemId,
      );
    };

    const takeFirstMatch = (matchMap, filenameKey) => {
      const matches = matchMap.get(filenameKey) || [];
      const entry = matches.shift() || null;
      if (matches.length === 0) {
        matchMap.delete(filenameKey);
      }
      return entry;
    };

    const buildResultMap = (items = []) => {
      const resultMap = new Map();
      for (const item of items) {
        const filenameKey = normalizeUploadName(item?.filename);
        if (!filenameKey) continue;
        if (!resultMap.has(filenameKey)) {
          resultMap.set(filenameKey, []);
        }
        resultMap.get(filenameKey).push(item);
      }
      return resultMap;
    };

    const applyUploadResults = (attemptedItems, payload) => {
      const succeededMap = buildResultMap(payload?.succeeded);
      const failedMap = buildResultMap(payload?.failed);
      const skippedMap = buildResultMap(payload?.skipped);

      for (const item of attemptedItems) {
        const successEntry = takeFirstMatch(succeededMap, item.filenameKey);
        if (successEntry) {
          item.status = STATUS_SUCCESS;
          item.validationMessage = tm("skills.validationUploadedAs", {
            name: successEntry.name || item.name,
          });
          continue;
        }

        const skippedEntry = takeFirstMatch(skippedMap, item.filenameKey);
        if (skippedEntry) {
          item.status = STATUS_SKIPPED;
          item.validationMessage =
            skippedEntry.error || tm("skills.validationDuplicate");
          continue;
        }

        const failedEntry = takeFirstMatch(failedMap, item.filenameKey);
        if (failedEntry) {
          item.status = STATUS_ERROR;
          item.validationMessage =
            failedEntry.error || tm("skills.validationUploadFailed");
          continue;
        }

        item.status = STATUS_ERROR;
        item.validationMessage = tm("skills.validationNoResult");
      }
    };

    const fetchSkills = async () => {
      loading.value = true;
      try {
        const res = await axios.get("/api/skills");
        skills.value = normalizeSkillsPayload(res);
      } catch (_err) {
        showMessage(tm("skills.loadFailed"), "error");
      } finally {
        loading.value = false;
      }
    };

    const handleApiResponse = (
      res,
      successMessage,
      failureMessageDefault,
      onSuccess,
    ) => {
      if (res && res.data && res.data.status === "ok") {
        showMessage(successMessage, "success");
        if (onSuccess) onSuccess();
      } else {
        const msg =
          (res && res.data && res.data.message) || failureMessageDefault;
        showMessage(msg, "error");
      }
    };

    const uploadSkillBatch = async () => {
      const attemptedItems = uploadItems.value.filter(
        (item) =>
          item.status === STATUS_WAITING || item.status === STATUS_ERROR,
      );
      if (attemptedItems.length === 0) return;

      uploading.value = true;
      for (const item of attemptedItems) {
        item.status = STATUS_UPLOADING;
        item.validationMessage = tm("skills.validationUploading");
      }

      try {
        const formData = new FormData();
        for (const item of attemptedItems) {
          formData.append("files", item.file);
        }

        const res = await axios.post("/api/skills/batch-upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });

        const payload = res?.data?.data || {};
        applyUploadResults(attemptedItems, payload);

        const succeededCount = Array.isArray(payload.succeeded)
          ? payload.succeeded.length
          : 0;
        const failedCount = Array.isArray(payload.failed)
          ? payload.failed.length
          : 0;
        const responseColor =
          res?.data?.status === "error"
            ? "error"
            : failedCount > 0
            ? "warning"
            : "success";
        showMessage(
          res?.data?.message || tm("skills.uploadSuccess"),
          responseColor,
        );

        if (succeededCount > 0) {
          await fetchSkills();
        }
      } catch (_err) {
        for (const item of attemptedItems) {
          item.status = STATUS_ERROR;
          item.validationMessage = tm("skills.validationUploadFailed");
        }
        showMessage(tm("skills.uploadFailed"), "error");
      } finally {
        uploading.value = false;
      }
    };

    const toggleSkill = async (skill) => {
      if (isSandboxPresetSkill(skill)) {
        showMessage(tm("skills.sandboxPresetReadonly"), "warning");
        return;
      }
      const nextActive = !skill.active;
      itemLoading[skill.name] = true;
      try {
        const res = await axios.post("/api/skills/update", {
          name: skill.name,
          active: nextActive,
        });
        handleApiResponse(
          res,
          tm("skills.updateSuccess"),
          tm("skills.updateFailed"),
          () => {
            skill.active = nextActive;
          },
        );
      } catch (_err) {
        showMessage(tm("skills.updateFailed"), "error");
      } finally {
        itemLoading[skill.name] = false;
      }
    };

    const confirmDelete = (skill) => {
      if (isSandboxPresetSkill(skill)) {
        showMessage(tm("skills.sandboxPresetReadonly"), "warning");
        return;
      }
      if (isPluginProvidedSkill(skill)) {
        showMessage(tm("skills.pluginReadonly"), "warning");
        return;
      }
      skillToDelete.value = skill;
      deleteDialog.value = true;
    };

    const deleteSkill = async () => {
      if (!skillToDelete.value) return;
      deleting.value = true;
      try {
        const res = await axios.post("/api/skills/delete", {
          name: skillToDelete.value.name,
        });
        handleApiResponse(
          res,
          tm("skills.deleteSuccess"),
          tm("skills.deleteFailed"),
          async () => {
            deleteDialog.value = false;
            await fetchSkills();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.deleteFailed"), "error");
      } finally {
        deleting.value = false;
      }
    };

    const downloadSkill = async (skill) => {
      if (isSandboxPresetSkill(skill)) {
        showMessage(tm("skills.sandboxPresetReadonly"), "warning");
        return;
      }
      if (isPluginProvidedSkill(skill)) {
        showMessage(tm("skills.pluginReadonly"), "warning");
        return;
      }
      itemLoading[skill.name] = true;
      try {
        const res = await axios.get("/api/skills/download", {
          params: { name: skill.name },
          responseType: "blob",
        });
        const blob = new Blob([res.data], { type: "application/zip" });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${skill.name}.zip`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        showMessage(tm("skills.downloadSuccess"), "success");
      } catch (_err) {
        showMessage(tm("skills.downloadFailed"), "error");
      } finally {
        itemLoading[skill.name] = false;
      }
    };

    const resetEditorDialog = () => {
      editorDialog.skillName = "";
      editorDialog.currentDir = "";
      editorDialog.entries = [];
      editorDialog.filePath = "";
      editorDialog.content = "";
      editorDialog.fileEditable = false;
      editorDialog.fileDirty = false;
      editorDialog.loadingFiles = false;
      editorDialog.loadingFile = false;
      editorDialog.saving = false;
      editorDialog.error = "";
    };

    const loadSkillDir = async (path = "") => {
      if (!editorDialog.skillName) return [];
      editorDialog.loadingFiles = true;
      editorDialog.error = "";
      try {
        const res = await axios.get("/api/skills/files", {
          params: { name: editorDialog.skillName, path },
        });
        if (res?.data?.status !== "ok") {
          editorDialog.error =
            res?.data?.message || tm("skills.editorLoadFailed");
          return [];
        }
        const payload = res.data.data || {};
        editorDialog.currentDir = payload.path || "";
        editorDialog.entries = Array.isArray(payload.entries)
          ? payload.entries
          : [];
        return editorDialog.entries;
      } catch (_err) {
        editorDialog.error = tm("skills.editorLoadFailed");
        return [];
      } finally {
        editorDialog.loadingFiles = false;
      }
    };

    const loadSkillFile = async (path) => {
      if (!editorDialog.skillName || !path) return;
      if (
        editorDialog.fileDirty &&
        !window.confirm(tm("skills.discardChanges"))
      ) {
        return;
      }
      editorDialog.loadingFile = true;
      editorDialog.error = "";
      try {
        const res = await axios.get("/api/skills/file", {
          params: { name: editorDialog.skillName, path },
        });
        if (res?.data?.status !== "ok") {
          editorDialog.error =
            res?.data?.message || tm("skills.editorLoadFailed");
          return;
        }
        const payload = res.data.data || {};
        editorDialog.filePath = payload.path || path;
        editorDialog.content = payload.content || "";
        editorDialog.fileEditable = payload.editable !== false;
        await nextTick();
        editorDialog.fileDirty = false;
      } catch (_err) {
        editorDialog.error = tm("skills.editorLoadFailed");
      } finally {
        editorDialog.loadingFile = false;
      }
    };

    const openSkillEditor = async (skill) => {
      if (isSandboxPresetSkill(skill)) {
        showMessage(tm("skills.sandboxPresetReadonly"), "warning");
        return;
      }
      resetEditorDialog();
      editorDialog.skillName = skill.name;
      editorDialog.show = true;
      const entries = await loadSkillDir("");
      const skillMd = entries.find((entry) => entry.path === "SKILL.md");
      if (skillMd?.editable) {
        await loadSkillFile(skillMd.path);
      }
    };

    const closeSkillEditor = () => {
      if (editorDialog.saving) return;
      if (
        editorDialog.fileDirty &&
        !window.confirm(tm("skills.discardChanges"))
      ) {
        return;
      }
      editorDialog.show = false;
      resetEditorDialog();
    };

    const openSkillEntry = async (entry) => {
      if (!entry) return;
      if (entry.type === "directory") {
        if (
          editorDialog.fileDirty &&
          !window.confirm(tm("skills.discardChanges"))
        ) {
          return;
        }
        await loadSkillDir(entry.path);
        return;
      }
      await loadSkillFile(entry.path);
    };

    const openParentSkillDir = async () => {
      if (!editorDialog.currentDir) return;
      if (
        editorDialog.fileDirty &&
        !window.confirm(tm("skills.discardChanges"))
      ) {
        return;
      }
      const parts = editorDialog.currentDir.split("/").filter(Boolean);
      parts.pop();
      await loadSkillDir(parts.join("/"));
    };

    const saveSkillFile = async () => {
      if (
        !editorDialog.skillName ||
        !editorDialog.filePath ||
        !editorDialog.fileEditable
      ) {
        return;
      }
      editorDialog.saving = true;
      editorDialog.error = "";
      try {
        const res = await axios.post("/api/skills/file", {
          name: editorDialog.skillName,
          path: editorDialog.filePath,
          content: editorDialog.content,
        });
        if (res?.data?.status !== "ok") {
          editorDialog.error =
            res?.data?.message || tm("skills.editorSaveFailed");
          showMessage(editorDialog.error, "error");
          return;
        }
        editorDialog.fileDirty = false;
        showMessage(tm("skills.editorSaveSuccess"), "success");
        await fetchSkills();
      } catch (_err) {
        editorDialog.error = tm("skills.editorSaveFailed");
        showMessage(tm("skills.editorSaveFailed"), "error");
      } finally {
        editorDialog.saving = false;
      }
    };

    const fetchNeoCandidates = async () => {
      const params = {
        skill_key: neoFilters.skill_key || undefined,
        status: neoFilters.status || undefined,
      };
      const res = await axios.get("/api/skills/neo/candidates", { params });
      neoCandidates.value = normalizeNeoItemsPayload(res);
    };

    const fetchNeoReleases = async () => {
      const params = {
        skill_key: neoFilters.skill_key || undefined,
        stage: neoFilters.stage || undefined,
      };
      const res = await axios.get("/api/skills/neo/releases", { params });
      neoReleases.value = normalizeNeoItemsPayload(res).map((item) => {
        if (!item || typeof item !== "object") {
          return item;
        }
        return {
          ...item,
          is_active: item.is_active ?? item.active ?? false,
        };
      });
    };

    const loadNeoAvailability = async () => {
      try {
        const res = await axios.get("/api/config/get");
        const config = res?.data?.data?.config || {};
        const providerSettings = config?.provider_settings || {};
        const currentRuntime =
          providerSettings?.computer_use_runtime || "local";
        const booter = providerSettings?.sandbox?.booter || "";
        neoEnabled.value =
          currentRuntime === "sandbox" && booter === "shipyard_neo";
      } catch (_err) {
        neoEnabled.value = false;
      }

      neoUnavailableMessage.value = tm("skills.neoRuntimeRequired");
      if (!neoEnabled.value && mode.value === "neo") {
        mode.value = "local";
      }
    };

    const fetchNeoData = async () => {
      neoLoading.value = true;
      try {
        await Promise.all([fetchNeoCandidates(), fetchNeoReleases()]);
      } catch (_err) {
        showMessage(tm("skills.neoLoadFailed"), "error");
      } finally {
        neoLoading.value = false;
      }
    };

    const evaluateCandidate = async (candidate, passed) => {
      try {
        const res = await axios.post("/api/skills/neo/evaluate", {
          candidate_id: candidate.id,
          passed,
          score: passed ? 1.0 : 0.0,
          report: passed ? "approved_from_webui" : "rejected_from_webui",
        });
        handleApiResponse(
          res,
          tm("skills.neoEvaluateSuccess"),
          tm("skills.neoEvaluateFailed"),
          async () => {
            await fetchNeoCandidates();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoEvaluateFailed"), "error");
      }
    };

    const candidatePromoteLoadingKey = (candidateId, stage) =>
      `${candidateId}:${stage}`;
    const isCandidatePromoteLoading = (candidateId, stage) =>
      !!candidatePromoteLoading[candidatePromoteLoadingKey(candidateId, stage)];
    const isCandidatePromoting = (candidateId) =>
      isCandidatePromoteLoading(candidateId, "canary") ||
      isCandidatePromoteLoading(candidateId, "stable");

    const promoteCandidate = async (candidate, stage) => {
      const candidateId = candidate?.id;
      if (!candidateId) return;
      const loadingKey = candidatePromoteLoadingKey(candidateId, stage);
      if (candidatePromoteLoading[loadingKey]) return;
      candidatePromoteLoading[loadingKey] = true;
      try {
        const res = await axios.post("/api/skills/neo/promote", {
          candidate_id: candidateId,
          stage,
          sync_to_local: true,
        });
        const ok = res?.data?.status === "ok";
        if (!ok) {
          showMessage(
            res?.data?.message || tm("skills.neoPromoteFailed"),
            "error",
          );
        } else {
          showMessage(tm("skills.neoPromoteSuccess"), "success");
        }
        await fetchNeoData();
        if (stage === "stable") {
          await fetchSkills();
        }
      } catch (_err) {
        showMessage(tm("skills.neoPromoteFailed"), "error");
      } finally {
        candidatePromoteLoading[loadingKey] = false;
      }
    };

    const rollbackRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/rollback", {
          release_id: release.id,
        });
        handleApiResponse(
          res,
          tm("skills.neoRollbackSuccess"),
          tm("skills.neoRollbackFailed"),
          async () => {
            await fetchNeoData();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoRollbackFailed"), "error");
      }
    };

    const deactivateRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/rollback", {
          release_id: release.id,
        });
        handleApiResponse(
          res,
          tm("skills.neoDeactivateSuccess"),
          tm("skills.neoDeactivateFailed"),
          async () => {
            await fetchNeoData();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoDeactivateFailed"), "error");
      }
    };

    const handleReleaseLifecycleAction = async (release) => {
      if (release?.is_active) {
        await deactivateRelease(release);
        return;
      }
      await rollbackRelease(release);
    };

    const syncRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/sync", {
          release_id: release.id,
        });
        handleApiResponse(
          res,
          tm("skills.neoSyncSuccess"),
          tm("skills.neoSyncFailed"),
          async () => {
            await fetchSkills();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoSyncFailed"), "error");
      }
    };

    const viewPayload = async (payloadRef) => {
      if (!payloadRef) return;
      try {
        const res = await axios.get("/api/skills/neo/payload", {
          params: { payload_ref: payloadRef },
        });
        if (res?.data?.status !== "ok") {
          showMessage(
            res?.data?.message || tm("skills.neoPayloadFailed"),
            "error",
          );
          return;
        }
        const payload = res?.data?.data || {};
        payloadDialog.content = JSON.stringify(payload, null, 2);
        payloadDialog.show = true;
      } catch (_err) {
        showMessage(tm("skills.neoPayloadFailed"), "error");
      }
    };

    const deleteCandidate = async (candidate) => {
      try {
        const res = await axios.post("/api/skills/neo/delete-candidate", {
          candidate_id: candidate.id,
          reason: "deleted_from_webui",
        });
        handleApiResponse(
          res,
          tm("skills.neoDeleteSuccess"),
          tm("skills.neoDeleteFailed"),
          async () => {
            await fetchNeoData();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoDeleteFailed"), "error");
      }
    };

    const deleteRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/delete-release", {
          release_id: release.id,
          reason: "deleted_from_webui",
        });
        handleApiResponse(
          res,
          tm("skills.neoDeleteSuccess"),
          tm("skills.neoDeleteFailed"),
          async () => {
            await fetchNeoData();
          },
        );
      } catch (_err) {
        showMessage(tm("skills.neoDeleteFailed"), "error");
      }
    };

    const refreshCurrentMode = async () => {
      if (mode.value === "neo") {
        await loadNeoAvailability();
        if (neoEnabled.value) {
          await fetchNeoData();
        } else {
          showMessage(tm("skills.neoRuntimeRequired"), "warning");
        }
      } else {
        await fetchSkills();
      }
    };

    watch(mode, async (nextMode) => {
      if (nextMode === "neo") {
        await loadNeoAvailability();
        if (neoEnabled.value) {
          await fetchNeoData();
        }
      } else {
        await fetchSkills();
      }
    });

    watch(uploadDialog, (isOpen) => {
      if (!isOpen && !uploading.value) {
        resetUploadState();
      }
    });

    onMounted(async () => {
      await Promise.all([fetchSkills(), loadNeoAvailability()]);
      if (neoEnabled.value) {
        await fetchNeoData();
      }
    });

    return {
      t,
      tm,
      mode,
      skills,
      loading,
      runtime,
      sandboxCache,
      uploadDialog,
      uploadInput,
      uploadItems,
      uploadStateCounts,
      hasUploadableItems,
      isUploadDragging,
      uploading,
      itemLoading,
      deleteDialog,
      deleting,
      snackbar,
      neoEnabled,
      neoUnavailableMessage,
      neoLoading,
      neoCandidates,
      neoReleases,
      neoFilters,
      candidateStatusItems,
      releaseStageItems,
      activeReleaseCount,
      candidateHeaders,
      releaseHeaders,
      payloadDialog,
      editorDialog,
      editorLanguage,
      editorTheme,
      editorOptions,
      formatFileSize,
      uploadStatusLabel,
      statusChipClass,
      openUploadDialog,
      closeUploadDialog,
      openUploadPicker,
      handleUploadSelection,
      handleUploadDrop,
      removeUploadItem,
      refreshCurrentMode,
      fetchNeoData,
      uploadSkillBatch,
      downloadSkill,
      openSkillEditor,
      closeSkillEditor,
      openSkillEntry,
      openParentSkillDir,
      saveSkillFile,
      toggleSkill,
      confirmDelete,
      deleteSkill,
      evaluateCandidate,
      promoteCandidate,
      isCandidatePromoteLoading,
      isCandidatePromoting,
      rollbackRelease,
      deactivateRelease,
      handleReleaseLifecycleAction,
      syncRelease,
      viewPayload,
      deleteCandidate,
      deleteRelease,
      sourceTypeLabel,
      sourceTypeColor,
      isSandboxPresetSkill,
      isPluginProvidedSkill,
      isReadOnlySourceSkill,
    };
  },
};
</script>

<style scoped>
.skills-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.list-action-icon-btn {
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.list-action-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.skills-fab-stack {
  align-items: center;
  bottom: 52px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: fixed;
  right: 52px;
  z-index: 10000;
}

.skills-fab {
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.skills-fab:hover {
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
  transform: translateY(-4px) scale(1.05);
}

.skill-description {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-path {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  margin-top: 6px;
  overflow: hidden;
  word-break: break-all;
}

.skill-editor-dialog {
  max-height: min(88vh, 980px);
  overflow: hidden;
}

.skill-editor-dialog__header {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px 14px;
}

.skill-editor-dialog__body {
  min-height: 0;
  padding: 16px 22px;
}

.skill-editor-dialog__actions {
  border-top: 1px solid var(--v-theme-border);
  padding: 12px 22px;
}

.skill-editor {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 16px;
  min-height: 560px;
}

.skill-editor__files {
  border: 1px solid rgba(128, 128, 128, 0.28);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.skill-editor__files-header {
  align-items: center;
  border-bottom: 1px solid rgba(128, 128, 128, 0.28);
  display: flex;
  gap: 8px;
  min-height: 44px;
  padding: 6px 10px;
}

.skill-editor__files-header span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-editor__file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  padding: 6px;
}

.skill-editor__file-row {
  align-items: center;
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  display: grid;
  gap: 8px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  min-height: 34px;
  padding: 6px 8px;
  text-align: left;
}

.skill-editor__file-row:hover,
.skill-editor__file-row--active {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.skill-editor__file-row--active {
  background: rgba(var(--v-theme-on-surface), 0.1);
}

.skill-editor__file-row span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-editor__content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.skill-editor__content-header {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  min-height: 34px;
}

.skill-editor__path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-editor__monaco {
  border: 1px solid rgba(128, 128, 128, 0.28);
  border-radius: 10px;
  flex: 1 1 auto;
  margin-top: 12px;
  min-height: 520px;
  overflow: hidden;
  position: relative;
}

.skills-upload-dialog {
  display: flex;
  flex-direction: column;
  max-height: min(88vh, 960px);
  border-radius: 24px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid var(--v-theme-border);
  outline: 1px solid rgba(var(--v-theme-primary), 0.1);
  outline-offset: -1px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  overflow: hidden;
}

.skills-upload-dialog__header {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 16px;
  white-space: normal;
  overflow: visible;
}

.skills-upload-dialog__heading {
  min-width: 0;
  padding-right: 0;
  white-space: normal;
}

.skills-upload-dialog__description {
  max-width: 100%;
  color: var(--v-theme-secondaryText);
  line-height: 1.7;
  word-break: break-word;
  white-space: normal;
  overflow-wrap: anywhere;
}

.skills-upload-dialog__description--body {
  margin: 0 0 14px;
  font-size: 15px;
  line-height: 1.6;
}

.skills-upload-dialog__close {
  align-self: flex-start;
}

.skills-upload-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.skills-upload-dialog__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--v-theme-border);
  background: rgba(var(--v-theme-surface), 0.98);
}

.skills-upload-dialog__action-btn {
  min-width: 96px;
  height: 38px;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
}

.skills-upload-structure-note {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
  background: rgba(var(--v-theme-surface), 0.96);
  color: var(--v-theme-secondaryText);
  line-height: 1.6;
}

.skills-upload-capabilities {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.skills-upload-capability {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 0 14px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  background: rgba(var(--v-theme-surface), 0.96);
  color: var(--v-theme-secondaryText);
}

.skills-upload-capability__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgba(var(--v-theme-primary), 0.95);
}

.skills-dropzone {
  padding: 36px 24px;
  border-radius: 22px;
  border: 1.5px dashed rgba(var(--v-theme-primary), 0.24);
  background: rgba(var(--v-theme-surface), 0.94);
  text-align: center;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease,
    background-color 0.2s ease;
}

.skills-dropzone:hover,
.skills-dropzone--dragover {
  border-color: rgba(var(--v-theme-primary), 0.52);
  background: rgba(var(--v-theme-primary), 0.05);
  transform: translateY(-1px);
}

.skills-dropzone__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 66px;
  height: 66px;
  margin: 0 auto 18px;
  border-radius: 20px;
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgba(var(--v-theme-primary), 0.96);
}

.skills-dropzone__subtitle {
  margin-top: 10px;
  color: var(--v-theme-secondaryText);
}

.skills-dropzone__hint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--v-theme-secondaryText);
  opacity: 0.82;
}

.skills-upload-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}

.skills-upload-summary__chip {
  background: rgba(var(--v-theme-surface), 0.96);
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  color: var(--v-theme-secondaryText);
}

.skills-upload-summary__chip--success {
  background: rgba(var(--v-theme-primary), 0.18);
  color: var(--v-theme-primaryText);
}

.skills-upload-summary__chip--error {
  background: #f2e6e2;
  color: #8b5d54;
}

.skills-upload-list {
  margin-top: 16px;
  border-radius: 20px;
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
  background: rgba(var(--v-theme-surface), 0.94);
  overflow: hidden;
}

.skills-upload-list__header {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(var(--v-theme-primary), 0.14);
  color: var(--v-theme-primaryText);
  font-weight: 600;
}

.skills-upload-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
}

.skills-upload-row + .skills-upload-row {
  border-top: 1px solid rgba(var(--v-theme-primary), 0.12);
}

.skills-upload-row__meta {
  min-width: 0;
  flex: 1;
}

.skills-upload-row__name {
  font-weight: 600;
  color: var(--v-theme-primaryText);
  word-break: break-all;
}

.skills-upload-row__size {
  margin-top: 4px;
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  opacity: 0.82;
}

.skills-upload-row__message {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--v-theme-secondaryText);
}

.skills-upload-row__actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.skills-status-chip {
  min-width: 74px;
  justify-content: center;
  font-weight: 600;
}

.skills-status-chip--waiting {
  background: rgba(var(--v-theme-surface), 0.96);
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  color: var(--v-theme-secondaryText);
}

.skills-status-chip--uploading {
  background: rgba(var(--v-theme-primary), 0.14);
  color: var(--v-theme-primaryText);
}

.skills-status-chip--success {
  background: rgba(var(--v-theme-primary), 0.2);
  color: var(--v-theme-primaryText);
}

.skills-status-chip--error {
  background: #f2e6e2;
  color: #8a5a50;
}

.skills-status-chip--skipped {
  background: rgba(var(--v-theme-surface), 0.96);
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  color: var(--v-theme-secondaryText);
}

.skills-upload-empty {
  margin-top: 16px;
  padding: 20px 18px;
  border-radius: 20px;
  border: 1px dashed rgba(var(--v-theme-primary), 0.24);
  background: rgba(var(--v-theme-surface), 0.94);
  text-align: center;
  color: var(--v-theme-secondaryText);
}

.payload-preview {
  max-height: 480px;
  overflow: auto;
  background: #111;
  color: #ececec;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
}

.neo-filter-card {
  border-radius: 14px;
  border-color: rgba(var(--v-theme-primary), 0.25);
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-primary), 0.03),
    rgba(var(--v-theme-surface), 1)
  );
}

.neo-table-card {
  border-radius: 14px;
}

.neo-data-table :deep(.v-data-table-header__content) {
  font-weight: 700;
}

.neo-data-table :deep(tbody tr:hover) {
  background: rgba(var(--v-theme-primary), 0.04);
}

@media (max-width: 860px) {
  .skills-upload-capabilities {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .skills-upload-dialog {
    max-height: 92vh;
  }

  .skills-upload-dialog__header {
    gap: 12px;
  }

  .skills-upload-dialog__heading {
    padding-right: 0;
  }

  .skills-upload-row {
    flex-direction: column;
  }

  .skills-upload-row__actions {
    justify-content: space-between;
    align-items: center;
  }

  .skills-upload-dialog__description--body {
    font-size: 14px;
  }
}
</style>

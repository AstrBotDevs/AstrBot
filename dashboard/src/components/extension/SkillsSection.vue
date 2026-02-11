<template>
  <div class="skills-page">
    <v-container fluid class="pa-0" elevation="0">
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-4">
        <div>
          <v-btn
            v-if="mode === 'local'"
            color="success"
            prepend-icon="mdi-upload"
            class="me-2"
            variant="tonal"
            @click="uploadDialog = true"
          >
            {{ tm("skills.upload") }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="refreshCurrentMode">
            {{ tm("skills.refresh") }}
          </v-btn>
        </div>
        <v-btn-toggle v-model="mode" mandatory divided density="comfortable">
          <v-btn value="local">{{ tm("skills.modeLocal") }}</v-btn>
          <v-btn value="neo">{{ tm("skills.modeNeo") }}</v-btn>
        </v-btn-toggle>
      </v-row>

      <div v-if="mode === 'local'" class="px-2 pb-2">
        <small style="color: grey;">{{ tm("skills.runtimeHint") }}</small>
      </div>

      <template v-if="mode === 'local'">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>

        <div v-else-if="skills.length === 0" class="text-center pa-8">
          <v-icon size="64" color="grey-lighten-1">mdi-folder-open</v-icon>
          <p class="text-grey mt-4">{{ tm("skills.empty") }}</p>
          <small class="text-grey">{{ tm("skills.emptyHint") }}</small>
        </div>

        <v-row v-else>
          <v-col v-for="skill in skills" :key="skill.name" cols="12" md="6" lg="4" xl="3">
            <item-card
              :item="skill"
              title-field="name"
              enabled-field="active"
              :loading="itemLoading[skill.name] || false"
              :show-edit-button="false"
              @toggle-enabled="toggleSkill"
              @delete="confirmDelete"
            >
              <template #item-details="{ item }">
                <div class="text-caption text-medium-emphasis mb-2 skill-description">
                  <v-icon size="small" class="me-1">mdi-text</v-icon>
                  {{ item.description || tm("skills.noDescription") }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  <v-icon size="small" class="me-1">mdi-file-document</v-icon>
                  {{ tm("skills.path") }}: {{ item.path }}
                </div>
              </template>
            </item-card>
          </v-col>
        </v-row>
      </template>

      <template v-else>
        <v-card class="mx-3 mb-4 pa-3" variant="outlined">
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field
                v-model="neoFilters.skill_key"
                :label="tm('skills.neoSkillKey')"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="neoFilters.status"
                :label="tm('skills.neoStatus')"
                :items="candidateStatusItems"
                item-title="title"
                item-value="value"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="neoFilters.stage"
                :label="tm('skills.neoStage')"
                :items="releaseStageItems"
                item-title="title"
                item-value="value"
                density="comfortable"
                hide-details
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="2" class="d-flex align-center">
              <v-btn color="primary" block @click="fetchNeoData">{{ tm("skills.refresh") }}</v-btn>
            </v-col>
          </v-row>
        </v-card>

        <v-progress-linear v-if="neoLoading" indeterminate color="primary"></v-progress-linear>

        <v-card class="mx-3 mb-4" variant="outlined">
          <v-card-title>{{ tm("skills.neoCandidates") }}</v-card-title>
          <v-data-table
            :headers="candidateHeaders"
            :items="neoCandidates"
            density="compact"
            :items-per-page="10"
          >
            <template #item.latest_score="{ item }">
              {{ item.latest_score ?? "-" }}
            </template>
            <template #item.actions="{ item }">
              <div class="d-flex ga-1 flex-wrap">
                <v-btn size="x-small" color="success" variant="tonal" @click="evaluateCandidate(item, true)">
                  {{ tm("skills.neoPass") }}
                </v-btn>
                <v-btn size="x-small" color="warning" variant="tonal" @click="evaluateCandidate(item, false)">
                  {{ tm("skills.neoReject") }}
                </v-btn>
                <v-btn size="x-small" color="primary" variant="tonal" @click="promoteCandidate(item, 'canary')">
                  Canary
                </v-btn>
                <v-btn size="x-small" color="primary" variant="tonal" @click="promoteCandidate(item, 'stable')">
                  Stable
                </v-btn>
                <v-btn
                  size="x-small"
                  variant="tonal"
                  @click="viewPayload(item.payload_ref)"
                  :disabled="!item.payload_ref"
                >
                  Payload
                </v-btn>
              </div>
            </template>
          </v-data-table>
        </v-card>

        <v-card class="mx-3 mb-4" variant="outlined">
          <v-card-title>{{ tm("skills.neoReleases") }}</v-card-title>
          <v-data-table
            :headers="releaseHeaders"
            :items="neoReleases"
            density="compact"
            :items-per-page="10"
          >
            <template #item.is_active="{ item }">
              <v-chip size="small" :color="item.is_active ? 'success' : 'default'" variant="tonal">
                {{ item.is_active ? "active" : "inactive" }}
              </v-chip>
            </template>
            <template #item.actions="{ item }">
              <div class="d-flex ga-1 flex-wrap">
                <v-btn size="x-small" color="warning" variant="tonal" @click="rollbackRelease(item)">
                  {{ tm("skills.neoRollback") }}
                </v-btn>
                <v-btn size="x-small" color="primary" variant="tonal" @click="syncRelease(item)">
                  {{ tm("skills.neoSync") }}
                </v-btn>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </template>
    </v-container>

    <v-dialog v-model="uploadDialog" max-width="520px">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm("skills.uploadDialogTitle") }}</v-card-title>
        <v-card-text>
          <small class="text-grey">{{ tm("skills.uploadHint") }}</small>
          <v-file-input
            v-model="uploadFile"
            accept=".zip"
            :label="tm('skills.selectFile')"
            prepend-icon="mdi-folder-zip-outline"
            variant="outlined"
            class="mt-4"
            :multiple="false"
          />
        </v-card-text>
        <v-card-actions class="d-flex justify-end">
          <v-btn variant="text" @click="uploadDialog = false">{{ tm("skills.cancel") }}</v-btn>
          <v-btn color="primary" :loading="uploading" :disabled="!uploadFile" @click="uploadSkill">
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
          <v-btn variant="text" @click="deleteDialog = false">{{ tm("skills.cancel") }}</v-btn>
          <v-btn color="error" :loading="deleting" @click="deleteSkill">
            {{ t("core.common.itemCard.delete") }}
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
          <v-btn variant="text" @click="payloadDialog.show = false">{{ tm("skills.cancel") }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :timeout="3500" :color="snackbar.color" elevation="24">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from "axios";
import { computed, onMounted, reactive, ref, watch } from "vue";
import ItemCard from "@/components/shared/ItemCard.vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";

export default {
  name: "SkillsSection",
  components: { ItemCard },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n("features/extension");

    const mode = ref("local");
    const skills = ref([]);
    const loading = ref(false);
    const uploading = ref(false);
    const uploadDialog = ref(false);
    const uploadFile = ref(null);
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
    const payloadDialog = reactive({
      show: false,
      content: "",
    });

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

    const candidateHeaders = computed(() => [
      { title: "ID", key: "id", width: "180px" },
      { title: "skill_key", key: "skill_key" },
      { title: "status", key: "status", width: "130px" },
      { title: "score", key: "latest_score", width: "90px" },
      { title: tm("skills.actions"), key: "actions", sortable: false, width: "420px" },
    ]);

    const releaseHeaders = computed(() => [
      { title: "ID", key: "id", width: "180px" },
      { title: "skill_key", key: "skill_key" },
      { title: "stage", key: "stage", width: "100px" },
      { title: "version", key: "version", width: "90px" },
      { title: "active", key: "is_active", width: "110px" },
      { title: tm("skills.actions"), key: "actions", sortable: false, width: "220px" },
    ]);

    const showMessage = (message, color = "success") => {
      snackbar.message = message;
      snackbar.color = color;
      snackbar.show = true;
    };

    const normalizeSkillsPayload = (res) => {
      const payload = res?.data?.data || [];
      if (Array.isArray(payload)) return payload;
      return payload.skills || [];
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

    const handleApiResponse = (res, successMessage, failureMessageDefault, onSuccess) => {
      if (res && res.data && res.data.status === "ok") {
        showMessage(successMessage, "success");
        if (onSuccess) onSuccess();
      } else {
        const msg = (res && res.data && res.data.message) || failureMessageDefault;
        showMessage(msg, "error");
      }
    };

    const uploadSkill = async () => {
      if (!uploadFile.value) return;
      uploading.value = true;
      try {
        const formData = new FormData();
        const file = Array.isArray(uploadFile.value) ? uploadFile.value[0] : uploadFile.value;
        if (!file) {
          uploading.value = false;
          return;
        }
        formData.append("file", file);
        const res = await axios.post("/api/skills/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        handleApiResponse(res, tm("skills.uploadSuccess"), tm("skills.uploadFailed"), async () => {
          uploadDialog.value = false;
          uploadFile.value = null;
          await fetchSkills();
        });
      } catch (_err) {
        showMessage(tm("skills.uploadFailed"), "error");
      } finally {
        uploading.value = false;
      }
    };

    const toggleSkill = async (skill) => {
      const nextActive = !skill.active;
      itemLoading[skill.name] = true;
      try {
        const res = await axios.post("/api/skills/update", {
          name: skill.name,
          active: nextActive,
        });
        handleApiResponse(res, tm("skills.updateSuccess"), tm("skills.updateFailed"), () => {
          skill.active = nextActive;
        });
      } catch (_err) {
        showMessage(tm("skills.updateFailed"), "error");
      } finally {
        itemLoading[skill.name] = false;
      }
    };

    const confirmDelete = (skill) => {
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
        handleApiResponse(res, tm("skills.deleteSuccess"), tm("skills.deleteFailed"), async () => {
          deleteDialog.value = false;
          await fetchSkills();
        });
      } catch (_err) {
        showMessage(tm("skills.deleteFailed"), "error");
      } finally {
        deleting.value = false;
      }
    };

    const fetchNeoCandidates = async () => {
      const params = {
        skill_key: neoFilters.skill_key || undefined,
        status: neoFilters.status || undefined,
      };
      const res = await axios.get("/api/skills/neo/candidates", { params });
      const payload = res?.data?.data || {};
      neoCandidates.value = payload.items || [];
    };

    const fetchNeoReleases = async () => {
      const params = {
        skill_key: neoFilters.skill_key || undefined,
        stage: neoFilters.stage || undefined,
      };
      const res = await axios.get("/api/skills/neo/releases", { params });
      const payload = res?.data?.data || {};
      neoReleases.value = payload.items || [];
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
        handleApiResponse(res, tm("skills.neoEvaluateSuccess"), tm("skills.neoEvaluateFailed"), async () => {
          await fetchNeoCandidates();
        });
      } catch (_err) {
        showMessage(tm("skills.neoEvaluateFailed"), "error");
      }
    };

    const promoteCandidate = async (candidate, stage) => {
      try {
        const res = await axios.post("/api/skills/neo/promote", {
          candidate_id: candidate.id,
          stage,
          sync_to_local: true,
        });
        const ok = res?.data?.status === "ok";
        if (!ok) {
          showMessage(res?.data?.message || tm("skills.neoPromoteFailed"), "error");
        } else {
          showMessage(tm("skills.neoPromoteSuccess"), "success");
        }
        await fetchNeoData();
        if (stage === "stable") {
          await fetchSkills();
        }
      } catch (_err) {
        showMessage(tm("skills.neoPromoteFailed"), "error");
      }
    };

    const rollbackRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/rollback", {
          release_id: release.id,
        });
        handleApiResponse(res, tm("skills.neoRollbackSuccess"), tm("skills.neoRollbackFailed"), async () => {
          await fetchNeoData();
        });
      } catch (_err) {
        showMessage(tm("skills.neoRollbackFailed"), "error");
      }
    };

    const syncRelease = async (release) => {
      try {
        const res = await axios.post("/api/skills/neo/sync", {
          release_id: release.id,
        });
        handleApiResponse(res, tm("skills.neoSyncSuccess"), tm("skills.neoSyncFailed"), async () => {
          await fetchSkills();
        });
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
          showMessage(res?.data?.message || tm("skills.neoPayloadFailed"), "error");
          return;
        }
        const payload = res?.data?.data || {};
        payloadDialog.content = JSON.stringify(payload, null, 2);
        payloadDialog.show = true;
      } catch (_err) {
        showMessage(tm("skills.neoPayloadFailed"), "error");
      }
    };

    const refreshCurrentMode = async () => {
      if (mode.value === "neo") {
        await fetchNeoData();
      } else {
        await fetchSkills();
      }
    };

    watch(mode, async (nextMode) => {
      if (nextMode === "neo") {
        await fetchNeoData();
      } else {
        await fetchSkills();
      }
    });

    onMounted(async () => {
      await Promise.all([fetchSkills(), fetchNeoData()]);
    });

    return {
      t,
      tm,
      mode,
      skills,
      loading,
      uploadDialog,
      uploadFile,
      uploading,
      itemLoading,
      deleteDialog,
      deleting,
      snackbar,
      neoLoading,
      neoCandidates,
      neoReleases,
      neoFilters,
      candidateStatusItems,
      releaseStageItems,
      candidateHeaders,
      releaseHeaders,
      payloadDialog,
      refreshCurrentMode,
      fetchNeoData,
      uploadSkill,
      toggleSkill,
      confirmDelete,
      deleteSkill,
      evaluateCandidate,
      promoteCandidate,
      rollbackRelease,
      syncRelease,
      viewPayload,
    };
  },
};
</script>

<style scoped>
.skill-description {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
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
</style>

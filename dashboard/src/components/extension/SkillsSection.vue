<template>
  <div class="skills-page">
    <v-container fluid class="pa-0" elevation="0">
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
        <div>
          <v-btn color="success" prepend-icon="mdi-upload" class="me-2" variant="tonal" @click="uploadDialog = true">
            {{ tm('skills.upload') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="fetchSkills">
            {{ tm('skills.refresh') }}
          </v-btn>
        </div>
      </v-row>

      <div class="px-2 pb-2">
        <small style="color: grey;">{{ tm('skills.runtimeHint') }}</small>
      </div>

      <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>

      <div v-else-if="skills.length === 0" class="text-center pa-8">
        <v-icon size="64" color="grey-lighten-1">mdi-folder-open</v-icon>
        <p class="text-grey mt-4">{{ tm('skills.empty') }}</p>
        <small class="text-grey">{{ tm('skills.emptyHint') }}</small>
      </div>

      <v-row v-else>
        <v-col v-for="skill in skills" :key="skill.name" cols="12" md="6" lg="4" xl="3">
          <item-card :item="skill" title-field="name" enabled-field="active" :loading="itemLoading[skill.name] || false"
            :show-edit-button="false" @toggle-enabled="toggleSkill" @delete="confirmDelete">
            <template v-slot:item-details="{ item }">
              <div class="text-caption text-medium-emphasis mb-2 skill-description">
                <v-icon size="small" class="me-1">mdi-text</v-icon>
                {{ item.description || tm('skills.noDescription') }}
              </div>
              <div class="text-caption text-medium-emphasis">
                <v-icon size="small" class="me-1">mdi-file-document</v-icon>
                {{ tm('skills.path') }}: {{ item.path }}
              </div>
            </template>
          </item-card>
        </v-col>
      </v-row>
    </v-container>

    <v-dialog v-model="uploadDialog" max-width="520px">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('skills.uploadDialogTitle') }}</v-card-title>
        <v-card-text>
          <small class="text-grey">{{ tm('skills.uploadHint') }}</small>
          <v-file-input v-model="uploadFile" accept=".zip" :label="tm('skills.selectFile')"
            prepend-icon="mdi-folder-zip-outline" variant="outlined" class="mt-4" :multiple="false" />
        </v-card-text>
        <v-card-actions class="d-flex justify-end">
          <v-btn variant="text" @click="uploadDialog = false">{{ tm('skills.cancel') }}</v-btn>
          <v-btn color="primary" :loading="uploading" :disabled="!uploadFile" @click="uploadSkill">
            {{ tm('skills.confirmUpload') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('skills.deleteTitle') }}</v-card-title>
        <v-card-text>{{ tm('skills.deleteMessage') }}</v-card-text>
        <v-card-actions class="d-flex justify-end">
          <v-btn variant="text" @click="deleteDialog = false">{{ tm('skills.cancel') }}</v-btn>
          <v-btn color="error" :loading="deleting" @click="deleteSkill">
            {{ t('core.common.itemCard.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :timeout="3000" :color="snackbar.color" elevation="24">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from "axios";
import { ref, reactive, onMounted } from "vue";
import ItemCard from "@/components/shared/ItemCard.vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";

export default {
  name: "SkillsSection",
  components: { ItemCard },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n("features/extension");

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

    const showMessage = (message, color = "success") => {
      snackbar.message = message;
      snackbar.color = color;
      snackbar.show = true;
    };

    const fetchSkills = async () => {
      loading.value = true;
      try {
        const res = await axios.get("/api/skills");
        const payload = res.data?.data || [];
        if (Array.isArray(payload)) {
          skills.value = payload;
        } else {
          skills.value = payload.skills || [];
        }
      } catch (err) {
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
        const file = Array.isArray(uploadFile.value)
          ? uploadFile.value[0]
          : uploadFile.value;
        if (!file) {
          uploading.value = false;
          return;
        }
        formData.append("file", file);
        const res = await axios.post("/api/skills/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        handleApiResponse(
          res,
          tm("skills.uploadSuccess"),
          tm("skills.uploadFailed"),
          async () => {
            uploadDialog.value = false;
            uploadFile.value = null;
            await fetchSkills();
          }
        );
      } catch (err) {
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
        handleApiResponse(
          res,
          tm("skills.updateSuccess"),
          tm("skills.updateFailed"),
          () => {
            skill.active = nextActive;
          }
        );
      } catch (err) {
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
        handleApiResponse(
          res,
          tm("skills.deleteSuccess"),
          tm("skills.deleteFailed"),
          async () => {
            deleteDialog.value = false;
            await fetchSkills();
          }
        );
      } catch (err) {
        showMessage(tm("skills.deleteFailed"), "error");
      } finally {
        deleting.value = false;
      }
    };

    onMounted(fetchSkills);

    return {
      t,
      tm,
      skills,
      loading,
      uploadDialog,
      uploadFile,
      uploading,
      itemLoading,
      deleteDialog,
      deleting,
      snackbar,
      fetchSkills,
      uploadSkill,
      toggleSkill,
      confirmDelete,
      deleteSkill,
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
</style>

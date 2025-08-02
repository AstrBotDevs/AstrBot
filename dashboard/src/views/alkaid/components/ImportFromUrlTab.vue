<template>
  <div class="from-url-container pa-4">
    <v-alert type="info" variant="tonal" class="mb-4" border>
      {{ tm('importFromUrl.preRequisite') }}
    </v-alert>
    <v-text-field v-model="importUrl" :label="tm('importFromUrl.urlLabel')"
      :placeholder="tm('importFromUrl.urlPlaceholder')" variant="outlined" class="mb-4" hide-details></v-text-field>

    <v-card class="mb-4" variant="outlined" color="grey-lighten-4">
      <v-card-title class="pa-4 pb-0 d-flex align-center">
        <v-icon color="primary" class="mr-2">mdi-cog-outline</v-icon>
        <span class="text-subtitle-1 font-weight-bold">{{ tm('importFromUrl.optionsTitle') }}</span>
        <v-tooltip location="top">
          <template v-slot:activator="{ props }">
            <v-icon v-bind="props" class="ml-2" size="small" color="grey">mdi-information-outline</v-icon>
          </template>
          <span>{{ tm('importFromUrl.tooltip') }}</span>
        </v-tooltip>
      </v-card-title>
      <v-card-text class="pa-4 pt-2">
        <v-row>
          <v-col cols="12" md="6">
            <v-switch v-model="importOptions.use_llm_repair" :label="tm('importFromUrl.useLlmRepairLabel')"
              color="primary" inset></v-switch>
          </v-col>
          <v-col cols="12" md="6">
            <v-switch v-model="importOptions.use_clustering_summary"
              :label="tm('importFromUrl.useClusteringSummaryLabel')" color="primary" inset></v-switch>
          </v-col>
          <v-row>
            <!-- Optional Repair Selector -->
            <v-col v-if="importOptions.use_llm_repair" :md="optionalSelectorColWidth" cols="12">
              <v-select v-model="importOptions.repair_llm_provider_id" :items="llmProviderConfigs" item-value="id"
                :item-props="llmModelProps" :label="tm('importFromUrl.repairLlmProviderIdLabel')" variant="outlined"
                clearable></v-select>
            </v-col>

            <!-- Optional Summary Selector -->
            <v-col v-if="importOptions.use_clustering_summary" :md="optionalSelectorColWidth" cols="12">
              <v-select v-model="importOptions.summarize_llm_provider_id" :items="llmProviderConfigs" item-value="id"
                :item-props="llmModelProps" :label="tm('importFromUrl.summarizeLlmProviderIdLabel')" variant="outlined"
                clearable></v-select>
            </v-col>

            <!-- This is the fixed layout group that will wrap automatically -->
            <v-col cols="12" md="6">
              <v-select v-model="importOptions.embedding_provider_id" :items="embeddingProviderConfigs" item-value="id"
                :item-props="embeddingModelProps" :label="tm('importFromUrl.embeddingProviderIdLabel')"
                variant="outlined" clearable></v-select>
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="importOptions.chunk_size" :label="tm('importFromUrl.chunkSizeLabel')" type="number"
                variant="outlined" clearable></v-text-field>
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="importOptions.chunk_overlap" :label="tm('importFromUrl.chunkOverlapLabel')"
                type="number" variant="outlined" clearable></v-text-field>
            </v-col>
          </v-row>
        </v-row>
      </v-card-text>
    </v-card>

    <div class="text-center">
      <v-btn color="primary" variant="elevated" :loading="importing" :disabled="!importUrl" @click="startImportFromUrl">
        {{ tm('importFromUrl.startImport') }}
      </v-btn>
    </div>


   <v-snackbar v-model="snackbar" :timeout="3000" :color="snackbarColor">
     {{ snackbarText }}
   </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'ImportFromUrlTab',
  props: {
    currentKB: {
      type: Object,
      required: true
    },
    llmProviderConfigs: {
      type: Array,
      default: () => []
    },
    embeddingProviderConfigs: {
      type: Array,
      default: () => []
    }
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base');
    return { tm };
  },
  computed: {
    optionalSelectorColWidth() {
      const repairOn = this.importOptions.use_llm_repair;
      const summaryOn = this.importOptions.use_clustering_summary;
      if (repairOn && summaryOn) {
        return 6; // Both on, each takes half
      }
      return 12; // Only one is on, it takes full width
    }
  },
  data() {
    return {
      importUrl: '',
      importOptions: {
        use_llm_repair: true,
        use_clustering_summary: false,
        repair_llm_provider_id: null,
        summarize_llm_provider_id: null,
        embedding_provider_id: null,
        chunk_size: 300,
        chunk_overlap: 50,
      },
      importing: false,
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
      pollingInterval: null,
    };
  },
  watch: {
    llmProviderConfigs: {
      handler(newVal) {
        if (newVal && newVal.length > 0) {
          if (!this.importOptions.repair_llm_provider_id) {
            this.importOptions.repair_llm_provider_id = newVal[0].id;
          }
          if (!this.importOptions.summarize_llm_provider_id) {
            this.importOptions.summarize_llm_provider_id = newVal[0].id;
          }
        }
      },
      immediate: true,
      deep: true
    },
    embeddingProviderConfigs: {
      handler(newVal) {
        if (newVal && newVal.length > 0) {
          if (!this.importOptions.embedding_provider_id) {
            this.importOptions.embedding_provider_id = newVal[0].id;
          }
        }
      },
      immediate: true,
      deep: true
    }
  },
  methods: {
    llmModelProps(providerConfig) {
      return {
        title: providerConfig.llm_model || providerConfig.id,
        subtitle: `Provider ID: ${providerConfig.id}`,
      }
    },
    embeddingModelProps(providerConfig) {
      return {
        title: providerConfig.embedding_model,
        subtitle: this.tm('createDialog.providerInfo', {
          id: providerConfig.id,
          dimensions: providerConfig.embedding_dimensions
        }),
      }
    },
    showSnackbar(text, color = 'success') {
     this.snackbarText = text;
     this.snackbarColor = color;
     this.snackbar = true;
    },
    async startImportFromUrl() {
      if (!this.importUrl) {
        this.showSnackbar('Please enter a URL', 'warning');
        return;
      }

      this.importing = true;

      try {
        const payload = {
          url: this.importUrl,
          ...Object.fromEntries(Object.entries(this.importOptions).filter(([_, v]) => v !== '' && v !== null && v !== undefined))
        };


        console.log('Starting URL import with payload:', JSON.stringify(payload, null, 2));
        const addTaskResponse = await axios.post('/api/plug/url_2_kb/add', payload);

        if (!addTaskResponse.data.task_id) {
          throw new Error(addTaskResponse.data.message || 'Failed to start import task: No task_id received.');
        }

        const taskId = addTaskResponse.data.task_id;
        this.pollTaskStatus(taskId);

      } catch (error) {
        const errorMessage = error.response?.data?.message || error.message || 'An unknown error occurred.';
        this.showSnackbar(`Error: ${errorMessage}`, 'error');
        this.importing = false;
      }
    },
    pollTaskStatus(taskId) {
      this.pollingInterval = setInterval(async () => {
        try {
          const statusResponse = await axios.post(`/api/plug/url_2_kb/status`, { task_id: taskId });

          const taskData = statusResponse.data;
          const taskStatus = taskData.status;


          if (taskStatus === 'completed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.showSnackbar(this.tm('importFromUrl.uploadingChunks'), 'info');
            this.handleImportResult(taskData);
          } else if (taskStatus === 'failed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            const failureReason = taskData.result || 'Unknown reason.';
            this.showSnackbar(`${this.tm('importFromUrl.importFailed')}: ${failureReason}`, 'error');
            this.importing = false;
          }
        } catch (error) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          const errorMessage = error.response?.data?.message || error.message || 'An unknown error occurred during polling.';
          this.showSnackbar(`Polling Error: ${errorMessage}`, 'error');
          this.importing = false;
        }
      }, 3000);
    },
    async handleImportResult(data) {
      const chunks = [];
      const result = data.result;

      // 1. Handle overall summary
      if (result.overall_summary) {
        chunks.push({ content: result.overall_summary, filename: 'overall_summary.txt' });
      }

      // 2. Handle topic summaries
      if (result.topics && result.topics.length > 0) {
        result.topics.forEach(topic => {
          if (topic.topic_summary) {
            chunks.push({ content: topic.topic_summary, filename: `topic_${topic.topic_id}_summary.txt` });
          }
        });
      }

      // 3. Handle noise points
      if (result.noise_points && result.noise_points.length > 0) {
        result.noise_points.forEach((point, index) => {
          const content = typeof point === 'object' && point.text ? point.text : point;
          chunks.push({ content: content, filename: `noise_${index + 1}.txt` });
        });
      }

      if (chunks.length === 0) {
        this.showSnackbar('URL processed, but no text chunks were extracted.', 'info');
        this.importing = false;
        return;
      }


      let successCount = 0;
      let failCount = 0;

      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        try {
          await this.uploadChunkAsFile(chunk.content, chunk.filename);
          successCount++;
        } catch (error) {
          failCount++;
        }
      }


      if (failCount === 0) {
        this.showSnackbar(this.tm('importFromUrl.allChunksUploaded'), 'success');
      } else if (successCount > 0) {
        this.showSnackbar('Import partially complete. See console for details.', 'warning');
      } else {
        this.showSnackbar('Import failed. No chunks were uploaded.', 'error');
      }

      this.importing = false;
      this.$emit('refresh-collections');
    },
    async uploadChunkAsFile(content, filename) {
      const blob = new Blob([content], { type: 'text/plain' });
      const file = new File([blob], filename, { type: 'text/plain' });

      const formData = new FormData();
      formData.append('file', file);
      formData.append('collection_name', this.currentKB.collection_name);

      if (this.importOptions.chunk_size && this.importOptions.chunk_size > 0) {
        formData.append('chunk_size', this.importOptions.chunk_size);
      }
      if (this.importOptions.chunk_overlap && this.importOptions.chunk_overlap >= 0) {
        formData.append('chunk_overlap', this.importOptions.chunk_overlap);
      }

      const response = await axios.post('/api/plug/alkaid/kb/collection/add_file', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message || 'Chunk upload failed');
      }
      return response.data;
    },
  },
 beforeUnmount() {
   if (this.pollingInterval) {
     clearInterval(this.pollingInterval);
   }
 },
}
</script>
<style scoped>
/* Animations can be added back here later */
</style>
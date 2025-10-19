<template>
  <div class="search-panel">
    <v-card variant="outlined" class="mb-4">
      <v-card-text>
        <v-text-field
          v-model="searchQuery"
          :label="tm('search.queryLabel')"
          :placeholder="tm('search.queryPlaceholder')"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          clearable
          @keyup.enter="performSearch"
        ></v-text-field>

        <v-row class="mt-2">
          <v-col cols="12" md="6">
            <v-select
              v-model="topK"
              :items="[3, 5, 10, 20]"
              :label="tm('search.topKLabel')"
              variant="outlined"
              density="compact"
            ></v-select>
          </v-col>
          <v-col cols="12" md="6">
            <v-switch
              v-model="enableRerank"
              :label="tm('search.enableRerankLabel')"
              color="primary"
              hide-details
            ></v-switch>
          </v-col>
        </v-row>

        <div class="text-center mt-4">
          <v-btn
            color="primary"
            prepend-icon="mdi-magnify"
            @click="performSearch"
            :loading="searching"
            :disabled="!searchQuery"
          >
            {{ tm('search.search') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- 搜索结果 -->
    <div v-if="searching" class="text-center py-8">
      <v-progress-circular indeterminate color="primary"></v-progress-circular>
      <p class="mt-4">{{ tm('search.searching') }}</p>
    </div>

    <div v-else-if="searchPerformed && searchResults.length === 0" class="text-center py-8">
      <v-icon size="64" color="grey-lighten-2">mdi-file-search-outline</v-icon>
      <p class="text-medium-emphasis mt-4">{{ tm('search.noResults') }}</p>
    </div>

    <div v-else-if="searchResults.length > 0">
      <div class="d-flex justify-space-between align-center mb-4">
        <h4>{{ tm('search.resultsTitle', { count: searchResults.length }) }}</h4>
        <small class="text-medium-emphasis">{{ tm('search.searchTime', { time: searchTime }) }}</small>
      </div>

      <v-card
        v-for="(result, index) in searchResults"
        :key="index"
        variant="outlined"
        class="mb-3 result-card"
      >
        <v-card-text>
          <div class="d-flex justify-space-between align-center mb-2">
            <div class="d-flex align-center">
              <v-icon size="small" color="primary" class="mr-1">mdi-file-document-outline</v-icon>
              <span class="text-caption">{{ result.doc_name || result.metadata?.source }}</span>
            </div>
            <v-chip v-if="result.score" size="small" color="primary" variant="tonal">
              {{ tm('search.relevance') }}: {{ Math.round(result.score * 100) }}%
            </v-chip>
          </div>
          <div class="result-content">{{ result.content }}</div>
          <div class="text-caption text-medium-emphasis mt-2">
            {{ tm('search.chunkInfo', { index: result.metadata?.chunk_index, chars: result.char_count }) }}
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'SearchPanel',
  props: {
    kb: {
      type: Object,
      required: true,
    },
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base-v2/search');
    return { tm };
  },
  data() {
    return {
      searchQuery: '',
      topK: 5,
      enableRerank: true,
      searching: false,
      searchPerformed: false,
      searchResults: [],
      searchTime: 0,
      snackbar: {
        show: false,
        text: '',
        color: 'success',
      },
    };
  },
  methods: {
    async performSearch() {
      if (!this.searchQuery || !this.searchQuery.trim()) {
        this.showSnackbar(this.tm('messages.queryRequired'), 'warning');
        return;
      }

      this.searching = true;
      this.searchPerformed = true;
      const startTime = Date.now();

      try {
        const response = await axios.post('/api/kb/retrieve', {
          query: this.searchQuery,
          kb_ids: [this.kb.kb_id],
          top_k: this.topK,
          enable_rerank: this.enableRerank,
        });

        if (response.data.status === 'ok') {
          this.searchResults = response.data.data.results || [];
          this.searchTime = ((Date.now() - startTime) / 1000).toFixed(2);

          if (this.searchResults.length === 0) {
            this.showSnackbar(this.tm('messages.noResults'), 'info');
          }
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.searchFailed'), 'error');
        }
      } catch (error) {
        console.error('Error searching knowledge base:', error);
        this.showSnackbar(this.tm('messages.searchError'), 'error');
      } finally {
        this.searching = false;
      }
    },
    showSnackbar(text, color = 'success') {
      this.snackbar.text = text;
      this.snackbar.color = color;
      this.snackbar.show = true;
    },
  },
};
</script>

<style scoped>
.result-card {
  transition: all 0.2s ease;
}

.result-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}

.result-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.95rem;
  line-height: 1.6;
  padding: 12px;
  background-color: rgba(0, 0, 0, 0.02);
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}
</style>

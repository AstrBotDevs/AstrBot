<template>
  <v-dialog v-model="dialogVisible" max-width="1100px" scrollable>
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        <v-icon class="me-2">mdi-eye-outline</v-icon>
        <span>{{
          tm("mcpServers.resources.title", { name: serverName })
        }}</span>
      </v-card-title>

      <v-card-text class="pa-6">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          {{ tm("mcpServers.resources.applicationControlled") }}
        </v-alert>

        <v-tabs v-model="activeTab" color="primary" class="mb-4">
          <v-tab value="resources">
            {{ tm("mcpServers.resources.tabs.resources") }}
          </v-tab>
          <v-tab value="templates">
            {{ tm("mcpServers.resources.tabs.templates") }}
          </v-tab>
        </v-tabs>

        <v-window v-model="activeTab">
          <v-window-item value="resources">
            <v-row>
              <v-col cols="12" md="5">
                <div class="text-h4 mb-3">
                  {{ tm("mcpServers.resources.catalogTitle") }}
                </div>

                <v-progress-linear
                  v-if="resourcesLoading && resources.length === 0"
                  color="primary"
                  indeterminate
                  class="mb-3"
                />
                <v-alert
                  v-if="resourcesError"
                  type="error"
                  variant="tonal"
                  density="compact"
                  class="mb-3"
                >
                  {{ resourcesError }}
                </v-alert>
                <div
                  v-if="
                    !resourcesLoading &&
                    resources.length === 0 &&
                    !resourcesError
                  "
                  class="text-medium-emphasis text-center pa-6"
                >
                  {{ tm("mcpServers.resources.empty") }}
                </div>

                <v-list
                  v-if="resources.length > 0"
                  class="resource-list"
                  border
                  density="compact"
                  rounded
                >
                  <v-list-item
                    v-for="resource in resources"
                    :key="resource.uri"
                    :active="selectedResource?.uri === resource.uri"
                    color="primary"
                    @click="readResource(resource)"
                  >
                    <v-list-item-title>
                      {{ resource.title || resource.name || resource.uri }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="resource-uri">
                      {{ resource.uri }}
                    </v-list-item-subtitle>
                    <v-list-item-subtitle v-if="resource.description">
                      {{ resource.description }}
                    </v-list-item-subtitle>
                    <template #append>
                      <v-chip
                        v-if="resource.mime_type"
                        size="x-small"
                        variant="tonal"
                      >
                        {{ resource.mime_type }}
                      </v-chip>
                    </template>
                  </v-list-item>
                </v-list>

                <div v-if="resourcesNextCursor" class="text-center mt-3">
                  <v-btn
                    color="primary"
                    size="small"
                    variant="text"
                    :loading="resourcesLoading"
                    @click="loadResources(resourcesNextCursor)"
                  >
                    {{ tm("mcpServers.resources.loadMore") }}
                  </v-btn>
                </div>
              </v-col>

              <v-col cols="12" md="7" class="preview-column">
                <div class="text-h4 mb-3">
                  {{ tm("mcpServers.resources.previewTitle") }}
                </div>
                <div
                  v-if="!selectedResource"
                  class="text-medium-emphasis text-center pa-8"
                >
                  <v-icon size="40" class="mb-2">
                    mdi-information-outline
                  </v-icon>
                  <div>{{ tm("mcpServers.resources.selectPrompt") }}</div>
                </div>

                <template v-else>
                  <div class="mb-4">
                    <div class="text-h5">
                      {{
                        selectedResource.title ||
                        selectedResource.name ||
                        selectedResource.uri
                      }}
                    </div>
                    <div
                      class="resource-uri text-caption text-medium-emphasis mt-1"
                    >
                      {{ selectedResource.uri }}
                    </div>
                    <div class="d-flex flex-wrap ga-2 mt-2">
                      <v-chip
                        v-if="selectedResource.mime_type"
                        size="small"
                        variant="tonal"
                      >
                        {{ selectedResource.mime_type }}
                      </v-chip>
                      <v-chip
                        v-if="selectedResource.size != null"
                        size="small"
                        variant="tonal"
                      >
                        {{ formatSize(selectedResource.size) }}
                      </v-chip>
                    </div>
                  </div>

                  <v-progress-linear
                    v-if="readLoading"
                    color="primary"
                    indeterminate
                    class="mb-3"
                  />
                  <v-alert
                    v-if="readError"
                    type="error"
                    variant="tonal"
                    density="compact"
                    class="mb-3"
                  >
                    {{ readError }}
                  </v-alert>
                  <div
                    v-if="!readLoading && !readError && contents.length === 0"
                    class="text-medium-emphasis text-center pa-6"
                  >
                    {{ tm("mcpServers.resources.noContents") }}
                  </div>

                  <div
                    v-for="(content, index) in contents"
                    :key="`${content.uri}-${index}`"
                    class="mb-4"
                  >
                    <div class="d-flex flex-wrap ga-2 mb-2">
                      <v-chip
                        v-if="content.mime_type"
                        size="x-small"
                        variant="tonal"
                      >
                        {{ content.mime_type }}
                      </v-chip>
                      <v-chip size="x-small" variant="tonal">
                        {{ formatSize(content.size) }}
                      </v-chip>
                    </div>

                    <template v-if="content.type === 'text'">
                      <v-alert
                        v-if="content.truncated"
                        type="warning"
                        variant="tonal"
                        density="compact"
                        class="mb-2"
                      >
                        {{ tm("mcpServers.resources.truncated") }}
                      </v-alert>
                      <pre class="preview-text">{{ content.text }}</pre>
                    </template>
                    <v-alert
                      v-else
                      type="info"
                      variant="tonal"
                      density="compact"
                    >
                      {{ tm("mcpServers.resources.binaryUnavailable") }}
                    </v-alert>
                  </div>
                </template>
              </v-col>
            </v-row>
          </v-window-item>

          <v-window-item value="templates">
            <v-progress-linear
              v-if="templatesLoading && templates.length === 0"
              color="primary"
              indeterminate
              class="mb-3"
            />
            <v-alert
              v-if="templatesError"
              type="error"
              variant="tonal"
              density="compact"
              class="mb-3"
            >
              {{ templatesError }}
            </v-alert>
            <div
              v-if="
                !templatesLoading && templates.length === 0 && !templatesError
              "
              class="text-medium-emphasis text-center pa-6"
            >
              {{ tm("mcpServers.resources.templatesEmpty") }}
            </div>

            <v-list
              v-if="templates.length > 0"
              class="resource-list"
              border
              rounded
            >
              <v-list-item
                v-for="template in templates"
                :key="template.uri_template"
              >
                <v-list-item-title>
                  {{ template.title || template.name || template.uri_template }}
                </v-list-item-title>
                <v-list-item-subtitle class="resource-uri">
                  {{ template.uri_template }}
                </v-list-item-subtitle>
                <v-list-item-subtitle v-if="template.description">
                  {{ template.description }}
                </v-list-item-subtitle>
                <template #append>
                  <v-chip
                    v-if="template.mime_type"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ template.mime_type }}
                  </v-chip>
                </template>
              </v-list-item>
            </v-list>

            <div v-if="templatesNextCursor" class="text-center mt-3">
              <v-btn
                color="primary"
                size="small"
                variant="text"
                :loading="templatesLoading"
                @click="loadTemplates(templatesNextCursor)"
              >
                {{ tm("mcpServers.resources.loadMore") }}
              </v-btn>
            </div>
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn color="primary" variant="text" @click="dialogVisible = false">
          {{ tm("mcpServers.resources.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import { mcpApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

export default {
  name: "McpResourceBrowserDialog",
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
    serverName: {
      type: String,
      default: "",
    },
  },
  emits: ["update:modelValue"],
  setup() {
    const { tm } = useModuleI18n("features/tooluse");
    return { tm };
  },
  data() {
    return {
      activeTab: "resources",
      generation: 0,
      resources: [],
      resourcesNextCursor: null,
      resourcesLoading: false,
      resourcesError: "",
      templates: [],
      templatesNextCursor: null,
      templatesLoading: false,
      templatesError: "",
      selectedResource: null,
      contents: [],
      readLoading: false,
      readError: "",
      readRequestId: 0,
    };
  },
  computed: {
    dialogVisible: {
      get() {
        return this.modelValue;
      },
      set(value) {
        this.$emit("update:modelValue", value);
      },
    },
  },
  watch: {
    modelValue: {
      immediate: true,
      handler(visible) {
        if (visible) {
          this.openBrowser();
        } else {
          this.resetState();
        }
      },
    },
  },
  beforeUnmount() {
    this.resetState();
  },
  methods: {
    async openBrowser() {
      if (!this.serverName) {
        return;
      }
      this.resetState();
      await Promise.all([this.loadResources(), this.loadTemplates()]);
    },
    cancelRequests() {
      this.generation += 1;
      this.readRequestId += 1;
      this.resourcesLoading = false;
      this.templatesLoading = false;
      this.readLoading = false;
    },
    resetState() {
      this.cancelRequests();
      this.activeTab = "resources";
      this.resources = [];
      this.resourcesNextCursor = null;
      this.resourcesError = "";
      this.templates = [];
      this.templatesNextCursor = null;
      this.templatesError = "";
      this.selectedResource = null;
      this.contents = [];
      this.readError = "";
    },
    async loadResources(cursor = null) {
      const generation = this.generation;
      const append = Boolean(cursor);
      this.resourcesLoading = true;
      this.resourcesError = "";
      try {
        const response = await mcpApi.listResources(
          this.serverName,
          cursor || undefined,
        );
        if (generation !== this.generation) {
          return;
        }
        if (response.data.status === "error") {
          throw new Error(response.data.message || this.unknownError());
        }
        const data = response.data.data || {};
        const items = Array.isArray(data.resources) ? data.resources : [];
        this.resources = append ? [...this.resources, ...items] : items;
        this.resourcesNextCursor = data.next_cursor || null;
      } catch (error) {
        if (generation === this.generation) {
          this.resourcesError = this.tm("mcpServers.resources.errors.list", {
            error: this.errorMessage(error),
          });
        }
      } finally {
        if (generation === this.generation) {
          this.resourcesLoading = false;
        }
      }
    },
    async loadTemplates(cursor = null) {
      const generation = this.generation;
      const append = Boolean(cursor);
      this.templatesLoading = true;
      this.templatesError = "";
      try {
        const response = await mcpApi.listResourceTemplates(
          this.serverName,
          cursor || undefined,
        );
        if (generation !== this.generation) {
          return;
        }
        if (response.data.status === "error") {
          throw new Error(response.data.message || this.unknownError());
        }
        const data = response.data.data || {};
        const items = Array.isArray(data.resource_templates)
          ? data.resource_templates
          : [];
        this.templates = append ? [...this.templates, ...items] : items;
        this.templatesNextCursor = data.next_cursor || null;
      } catch (error) {
        if (generation === this.generation) {
          this.templatesError = this.tm(
            "mcpServers.resources.errors.templates",
            {
              error: this.errorMessage(error),
            },
          );
        }
      } finally {
        if (generation === this.generation) {
          this.templatesLoading = false;
        }
      }
    },
    async readResource(resource) {
      const generation = this.generation;
      const requestId = ++this.readRequestId;
      this.selectedResource = resource;
      this.contents = [];
      this.readError = "";
      this.readLoading = true;
      try {
        const response = await mcpApi.readResource(
          this.serverName,
          resource.uri,
        );
        if (
          generation !== this.generation ||
          requestId !== this.readRequestId
        ) {
          return;
        }
        if (response.data.status === "error") {
          throw new Error(response.data.message || this.unknownError());
        }
        const contents = response.data.data?.contents;
        this.contents = Array.isArray(contents) ? contents : [];
      } catch (error) {
        if (
          generation === this.generation &&
          requestId === this.readRequestId
        ) {
          this.readError = this.tm("mcpServers.resources.errors.read", {
            error: this.errorMessage(error),
          });
        }
      } finally {
        if (
          generation === this.generation &&
          requestId === this.readRequestId
        ) {
          this.readLoading = false;
        }
      }
    },
    unknownError() {
      return this.tm("mcpServers.resources.errors.unknown");
    },
    errorMessage(error) {
      if (typeof error === "string") {
        return error;
      }
      return (
        error?.response?.data?.message || error?.message || this.unknownError()
      );
    },
    formatSize(size) {
      const bytes = Number(size);
      if (!Number.isFinite(bytes) || bytes < 0) {
        return `${size} B`;
      }
      if (bytes < 1024) {
        return `${bytes} B`;
      }
      const units = ["KB", "MB", "GB", "TB"];
      const index = Math.min(
        Math.floor(Math.log(bytes) / Math.log(1024)) - 1,
        units.length - 1,
      );
      const value = bytes / Math.pow(1024, index + 1);
      return `${Number(value.toFixed(value >= 10 ? 1 : 2))} ${units[index]}`;
    },
  },
};
</script>

<style scoped>
.resource-list {
  max-height: 440px;
  overflow-y: auto;
}

.resource-uri {
  overflow-wrap: anywhere;
  white-space: normal;
}

.preview-text {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  font-family: monospace;
  font-size: 0.875rem;
  line-height: 1.5;
  margin: 0;
  max-height: 480px;
  overflow: auto;
  padding: 16px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (min-width: 960px) {
  .preview-column {
    border-left: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  }
}
</style>

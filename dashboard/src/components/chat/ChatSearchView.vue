<template>
    <div class="chat-search-container fade-in">
        <div class="chat-search-header">
            <div class="chat-search-header-info">
                <h2 class="chat-search-header-title">{{ tm('search.title') }}</h2>
            </div>
        </div>

        <div class="chat-search-input">
            <v-text-field
                v-model="query"
                :placeholder="tm('search.placeholder')"
                prepend-inner-icon="mdi-magnify"
                variant="outlined"
                rounded="xl"
                density="comfortable"
                clearable
                flat
                hide-details
                :loading="isLoading"
                @keyup.enter="handleSearch"
                @click:clear="handleClear"
            />
        </div>

        <v-card flat class="chat-search-results">
            <v-list v-if="results.length > 0">
                <v-list-item
                    v-for="item in results"
                    :key="item.session_id"
                    class="chat-search-result-item"
                    rounded="lg"
                    @click="emit('selectSession', item.session_id)"
                >
                    <v-list-item-title style="font-weight: bold;">
                        {{ item.title || tm('conversation.newConversation') }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="chat-search-snippet">
                        <span>{{ getSnippetParts(item).before }}</span>
                        <span class="chat-search-highlight">{{ getSnippetParts(item).match }}</span>
                        <span>{{ getSnippetParts(item).after }}</span>
                    </v-list-item-subtitle>
                    <v-list-item-subtitle class="chat-search-meta">
                        <!-- {{ getMatchFieldLabel(item) }} -->
                        <!-- · {{ tm('search.matchPosition') }} {{ item.match_index + 1 }} -->
                        {{ tm('search.createdAt') }} {{ formatDate(item.created_at) }}
                        · {{ tm('search.updatedAt') }} {{ formatDate(item.updated_at) }}
                    </v-list-item-subtitle>
                </v-list-item>
            </v-list>
            <div v-else class="chat-search-empty">
                <v-icon icon="mdi-text-box-search-outline" size="large" color="grey-lighten-1"></v-icon>
                <p>
                    {{ searchPerformed ? tm('search.noResults') : tm('search.hint') }}
                </p>
            </div>
        </v-card>

        <div v-if="pagination.total > 0" class="chat-search-pagination">
            <div class="chat-search-page-size">
                <span class="chat-search-page-label">{{ tm('search.pageSize') }}</span>
                <v-select
                    v-model="pageSizeProxy"
                    :items="pageSizeOptions"
                    variant="outlined"
                    density="compact"
                    hide-details
                    :disabled="isLoading"
                />
            </div>
            <v-pagination
                v-model="pageProxy"
                :length="pagination.total_pages"
                :disabled="isLoading"
                rounded="circle"
                :total-visible="7"
            />
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useChatSearchStore, type ChatSearchResult } from '@/stores/chatSearch';

const emit = defineEmits<{
    close: [];
    selectSession: [sessionId: string];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const chatSearchStore = useChatSearchStore();
const { query, results, pagination, isLoading, searchPerformed } = storeToRefs(chatSearchStore);

const pageSizeOptions = [10, 20, 50];
const searchTimeout = ref<ReturnType<typeof setTimeout> | null>(null);
const debounceDelay = 400;

const pageProxy = computed({
    get: () => pagination.value.page,
    set: (value) => chatSearchStore.setPage(value)
});

const pageSizeProxy = computed({
    get: () => pagination.value.page_size,
    set: (value) => chatSearchStore.setPageSize(value)
});

function handleSearch() {
    chatSearchStore.runNewSearch();
}

function handleClear() {
    chatSearchStore.search();
}

function scheduleSearch() {
    if (searchTimeout.value) {
        clearTimeout(searchTimeout.value);
    }
    searchTimeout.value = setTimeout(() => {
        chatSearchStore.runNewSearch();
    }, debounceDelay);
}

watch(query, (value) => {
    if (!value || !value.trim()) {
        if (searchTimeout.value) {
            clearTimeout(searchTimeout.value);
        }
        chatSearchStore.search();
        return;
    }
    scheduleSearch();
});

onBeforeUnmount(() => {
    if (searchTimeout.value) {
        clearTimeout(searchTimeout.value);
    }
});

function formatDate(dateString: string): string {
    return new Date(dateString).toLocaleString();
}

function getSnippetParts(item: ChatSearchResult) {
    const localIndex = Math.max(0, item.match_index - item.snippet_start);
    return {
        before: item.snippet.slice(0, localIndex),
        match: item.snippet.slice(localIndex, localIndex + item.match_length),
        after: item.snippet.slice(localIndex + item.match_length)
    };
}

function getMatchFieldLabel(item: ChatSearchResult) {
    return item.match_field === 'title' ? tm('search.matchTitle') : tm('search.matchContent');
}
</script>

<style scoped>
.chat-search-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 32px;
    overflow-y: auto;
}

.chat-search-header {
    text-align: center;
    margin-bottom: 24px;
    max-width: 640px;
}

.chat-search-header-info {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin-bottom: 12px;
}

.chat-search-header-emoji {
    font-size: 44px;
}

.chat-search-header-title {
    font-size: 30px;
    font-weight: 600;
}

.chat-search-header-description {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    margin: 0 0 12px;
}

.chat-search-input {
    width: 100%;
    max-width: 730px;
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 20px;
}

.chat-search-results {
    width: 100%;
    max-width: 760px;
    background-color: transparent !important;
}

.chat-search-result-item {
    margin-bottom: 8px;
    border-radius: 12px !important;
    cursor: pointer;
}

.chat-search-result-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.chat-search-snippet {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    margin-top: 4px;
}

.chat-search-highlight {
    background-color: rgba(255, 204, 102, 0.45);
    padding: 0 2px;
    border-radius: 4px;
}

.chat-search-meta {
    font-size: 12px;
    margin-top: 6px;
    opacity: 1;
}

.chat-search-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px;
    opacity: 0.6;
}

.chat-search-empty p {
    margin-top: 12px;
    font-size: 14px;
}

.chat-search-pagination {
    width: 100%;
    max-width: 760px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 4px 0;
}

.chat-search-page-size {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 200px;
}

.chat-search-page-label {
    font-size: 12px;
    color: var(--v-theme-secondaryText);
}

.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (max-width: 768px) {
    .chat-search-container {
        padding: 24px 16px;
    }

    .chat-search-input {
        flex-direction: column;
    }

    .chat-search-pagination {
        flex-direction: column;
        align-items: flex-start;
    }
}
</style>

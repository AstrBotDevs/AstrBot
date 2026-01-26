import { defineStore } from 'pinia';
import { ref } from 'vue';
import axios from 'axios';

export interface ChatSearchResult {
    session_id: string;
    title: string | null;
    match_field: 'title' | 'content';
    match_index: number;
    match_length: number;
    snippet: string;
    snippet_start: number;
    created_at: string;
    updated_at: string;
}

interface ChatSearchPagination {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
}

const defaultPagination: ChatSearchPagination = {
    page: 1,
    page_size: 10,
    total: 0,
    total_pages: 1
};

export const useChatSearchStore = defineStore('chatSearch', () => {
    const active = ref(false);
    const query = ref('');
    const results = ref<ChatSearchResult[]>([]);
    const pagination = ref<ChatSearchPagination>({ ...defaultPagination });
    const isLoading = ref(false);
    const searchPerformed = ref(false);
    const contextLength = ref(40);

    function openSearch() {
        active.value = true;
    }

    function closeSearch() {
        active.value = false;
    }

    async function search() {
        const trimmedQuery = query.value.trim();
        if (!trimmedQuery) {
            results.value = [];
            pagination.value = { ...defaultPagination };
            searchPerformed.value = false;
            return;
        }

        searchPerformed.value = true;
        isLoading.value = true;

        try {
            const response = await axios.get('/api/chat/search', {
                params: {
                    query: trimmedQuery,
                    page: pagination.value.page,
                    page_size: pagination.value.page_size,
                    context: contextLength.value
                }
            });

            const data = response.data?.data || {};
            results.value = data.results || [];
            pagination.value = data.pagination || { ...defaultPagination };
        } catch (error) {
            console.error('Search sessions failed:', error);
            results.value = [];
        } finally {
            isLoading.value = false;
        }
    }

    async function setPage(page: number) {
        pagination.value.page = page;
        await search();
    }

    async function setPageSize(pageSize: number) {
        pagination.value.page_size = pageSize;
        pagination.value.page = 1;
        await search();
    }

    async function runNewSearch() {
        pagination.value.page = 1;
        await search();
    }

    return {
        active,
        query,
        results,
        pagination,
        isLoading,
        searchPerformed,
        contextLength,
        openSearch,
        closeSearch,
        search,
        setPage,
        setPageSize,
        runNewSearch
    };
});

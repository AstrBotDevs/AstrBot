<template>
    <div v-if="refs && refs.used && refs.used.length > 0" class="refs-container" @click="handleClick">
        <div class="refs-avatars">
            <div v-for="(ref, refIdx) in refs.used.slice(0, 3)" :key="refIdx" class="ref-avatar"
                :style="{ zIndex: 3 - refIdx }">
                <img v-if="ref.favicon" :src="ref.favicon" class="ref-favicon"
                    @error="(e) => e.target.style.display = 'none'" />
                <span v-else class="ref-initial">{{ getRefInitial(ref.title) }}</span>
            </div>
            <span v-if="refs.used.length > 3" class="refs-more">
                +{{ refs.used.length - 3 }}
            </span>
            <span class="ml-2" style="color: gray;">
                {{ tm('refs.sources') }}
            </span>
        </div>
    </div>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';

export default {
    name: 'ActionRef',
    props: {
        refs: {
            type: Object,
            default: null
        }
    },
    emits: ['open-refs'],
    setup() {
        const { tm } = useModuleI18n('features/chat');
        return { tm };
    },
    methods: {
        // Get first character of ref title for fallback display
        getRefInitial(title) {
            if (!title) return '?';
            return title.charAt(0).toUpperCase();
        },

        // Handle click to open refs sidebar
        handleClick() {
            this.$emit('open-refs', this.refs);
        }
    }
}
</script>

<style scoped>
.refs-container {
    display: flex;
    align-items: center;
    margin-left: 8px;
    padding: 4px 8px;
    border-radius: 12px;
    cursor: pointer;
    transition: background-color;
}

.refs-container:hover {
    background-color: rgba(103, 58, 183, 0.08);
}

.refs-avatars {
    display: flex;
    align-items: center;
    position: relative;
}

.ref-avatar {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    opacity: 0.9;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
}

.ref-avatar:not(:first-child) {
    margin-left: -8px;
}

.ref-favicon {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.ref-initial {
    font-size: 10px;
    font-weight: 600;
    color: white;
    user-select: none;
}

.refs-more {
    margin-left: 6px;
    font-size: 11px;
    color: var(--v-theme-secondaryText);
    opacity: 0.7;
    font-weight: 500;
}
</style>

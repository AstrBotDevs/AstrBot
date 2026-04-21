<template>
    <v-card>
        <v-card-title>
            <v-icon start size="small">mdi-message-text</v-icon>
            {{ tm('advancedPersona.tabs.dialogs') }}
        </v-card-title>
        <v-card-text>
            <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                {{ tm('advancedPersona.dialogs.help') }}
            </v-alert>

            <div v-for="(dialog, index) in localDialogs" :key="index" class="mb-4">
                <div class="d-flex align-center justify-space-between mb-2">
                    <v-chip :color="index % 2 === 0 ? 'primary' : 'secondary'" variant="tonal" size="small">
                        {{ index % 2 === 0 ? tm('advancedPersona.dialogs.userMessage') : tm('advancedPersona.dialogs.assistantMessage') }}
                    </v-chip>
                    <v-btn icon="mdi-delete" variant="text" size="small" color="error"
                        @click="removeDialog(index)" />
                </div>
                <v-textarea v-model="localDialogs[index]"
                    :label="index % 2 === 0 ? tm('advancedPersona.dialogs.userMessage') : tm('advancedPersona.dialogs.assistantMessage')"
                    variant="outlined"
                    rows="2"
                    density="comfortable" />
            </div>

            <v-btn variant="outlined" prepend-icon="mdi-plus" @click="addDialogPair" block>
                {{ tm('advancedPersona.dialogs.addPair') }}
            </v-btn>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

export default defineComponent({
    name: 'DialogsSection',
    props: {
        modelValue: {
            type: Array as () => string[],
            default: () => []
        }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
        const { tm } = useModuleI18n('features/persona');

        const localDialogs = ref<string[]>([...props.modelValue]);

        // 监听输入变化
        watch(localDialogs, (newVal) => {
            emit('update:modelValue', newVal);
        }, { deep: true });

        // 监听props变化（仅在外部重置时同步，避免递归）
        watch(() => props.modelValue, (newVal) => {
            if (JSON.stringify(newVal) !== JSON.stringify(localDialogs.value)) {
                localDialogs.value = [...newVal];
            }
        }, { deep: true });

        const addDialogPair = () => {
            localDialogs.value.push('', '');
        };

        const removeDialog = (index: number) => {
            // 如果是偶数索引（用户消息），删除用户消息和对应的助手消息
            if (index % 2 === 0 && index + 1 < localDialogs.value.length) {
                localDialogs.value.splice(index, 2);
            }
            // 如果是奇数索引（助手消息），删除助手消息和对应的用户消息
            else if (index % 2 === 1 && index - 1 >= 0) {
                localDialogs.value.splice(index - 1, 2);
            }
        };

        return {
            tm,
            localDialogs,
            addDialogPair,
            removeDialog
        };
    }
});
</script>

<template>
    <v-card>
        <v-card-title>
            <v-icon start size="small">mdi-chat</v-icon>
            {{ tm('advancedPersona.tabs.chat') }}
        </v-card-title>
        <v-card-text>
            <v-row>
                <!-- 聊天频率 -->
                <v-col cols="12" md="6">
                    <v-select v-model="localConfig.chat_frequency"
                        :items="chatFrequencyOptions"
                        :label="tm('advancedPersona.chat.chatFrequency')"
                        :hint="tm('advancedPersona.chat.chatFrequencyHint')"
                        variant="outlined"
                        persistent-hint />
                </v-col>

                <!-- 动态发言频率 -->
                <v-col cols="12" md="6">
                    <v-select v-model="localConfig.dynamic_frequency"
                        :items="dynamicFrequencyOptions"
                        :label="tm('advancedPersona.chat.dynamicFrequency')"
                        :hint="tm('advancedPersona.chat.dynamicFrequencyHint')"
                        variant="outlined"
                        persistent-hint />
                </v-col>

                <!-- 根据时间选择 -->
                <v-col cols="12" md="6">
                    <v-switch v-model="localConfig.time_based_mode"
                        :label="tm('advancedPersona.chat.timeBasedMode')"
                        :hint="tm('advancedPersona.chat.timeBasedModeHint')"
                        color="primary"
                        persistent-hint />
                </v-col>

                <!-- 消息条数长度 -->
                <v-col cols="12" md="6">
                    <v-text-field v-model.number="localConfig.message_length"
                        :label="tm('advancedPersona.chat.messageLength')"
                        :hint="tm('advancedPersona.chat.messageLengthHint')"
                        type="number"
                        min="1"
                        max="100"
                        variant="outlined"
                        persistent-hint />
                </v-col>
            </v-row>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

interface ChatConfig {
    chat_frequency: string;
    dynamic_frequency: string;
    time_based_mode: boolean;
    message_length: number;
}

export default defineComponent({
    name: 'ChatSection',
    props: {
        modelValue: {
            type: Object as () => ChatConfig,
            default: () => ({
                chat_frequency: 'normal',
                dynamic_frequency: 'auto',
                time_based_mode: false,
                message_length: 10
            })
        }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
        const { tm } = useModuleI18n('features/persona');

        const localConfig = ref<ChatConfig>({ ...props.modelValue });

        // 聊天频率选项
        const chatFrequencyOptions = [
            { title: tm('advancedPersona.chat.frequencyOptions.silent'), value: 'silent' },
            { title: tm('advancedPersona.chat.frequencyOptions.low'), value: 'low' },
            { title: tm('advancedPersona.chat.frequencyOptions.normal'), value: 'normal' },
            { title: tm('advancedPersona.chat.frequencyOptions.high'), value: 'high' },
            { title: tm('advancedPersona.chat.frequencyOptions.veryHigh'), value: 'very_high' }
        ];

        // 动态发言频率选项
        const dynamicFrequencyOptions = [
            { title: tm('advancedPersona.chat.dynamicOptions.auto'), value: 'auto' },
            { title: tm('advancedPersona.chat.dynamicOptions.fixed'), value: 'fixed' },
            { title: tm('advancedPersona.chat.dynamicOptions.random'), value: 'random' }
        ];

        // 监听输入变化
        watch(localConfig, (newVal) => {
            emit('update:modelValue', newVal);
        }, { deep: true });

        // 监听props变化（仅在外部重置时同步，避免递归）
        watch(() => props.modelValue, (newVal) => {
            if (JSON.stringify(newVal) !== JSON.stringify(localConfig.value)) {
                localConfig.value = { ...newVal };
            }
        }, { deep: true });

        return {
            tm,
            localConfig,
            chatFrequencyOptions,
            dynamicFrequencyOptions
        };
    }
});
</script>

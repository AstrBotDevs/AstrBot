<template>
    <v-card>
        <v-card-title>
            <v-icon start size="small">mdi-robot</v-icon>
            {{ tm('advancedPersona.tabs.robot') }}
        </v-card-title>
        <v-card-text>
            <v-row>
                <!-- 昵称 -->
                <v-col cols="12" md="6">
                    <v-text-field v-model="localConfig.nickname"
                        :label="tm('advancedPersona.robot.nickname')"
                        :hint="tm('advancedPersona.robot.nicknameHint')"
                        variant="outlined"
                        persistent-hint />
                </v-col>

                <!-- 别名 -->
                <v-col cols="12" md="6">
                    <div class="mb-2">
                        <div class="d-flex justify-space-between align-center mb-2">
                            <label class="text-body-1">{{ tm('advancedPersona.robot.aliases') }}</label>
                            <v-btn size="small" variant="text" prepend-icon="mdi-plus" @click="addAlias">
                                {{ tm('advancedPersona.robot.addAlias') }}
                            </v-btn>
                        </div>
                        <p class="text-caption text-medium-emphasis mb-2">
                            {{ tm('advancedPersona.robot.aliasesHint') }}
                        </p>
                    </div>

                    <div v-for="(alias, index) in localConfig.aliases" :key="index"
                        class="d-flex align-center ga-2 mb-2">
                        <v-text-field v-model="localConfig.aliases[index]"
                            :label="tm('advancedPersona.robot.alias')"
                            variant="outlined"
                            density="compact"
                            hide-details
                            style="flex: 1" />
                        <v-btn icon="mdi-delete" variant="text" size="small" color="error"
                            @click="removeAlias(index)" />
                    </div>
                </v-col>

                <!-- 启用的平台 -->
                <v-col cols="12">
                    <v-select v-model="localConfig.platforms"
                        :items="platformOptions"
                        :label="tm('advancedPersona.robot.platforms')"
                        :hint="tm('advancedPersona.robot.platformsHint')"
                        variant="outlined"
                        persistent-hint
                        multiple
                        chips
                        closable-chips />
                </v-col>
            </v-row>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

interface RobotConfig {
    nickname: string;
    aliases: string[];
    platforms: string[];
}

export default defineComponent({
    name: 'RobotSection',
    props: {
        modelValue: {
            type: Object as () => RobotConfig,
            default: () => ({
                nickname: '',
                aliases: [],
                platforms: []
            })
        }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
        const { tm } = useModuleI18n('features/persona');

        const localConfig = ref<RobotConfig>({ ...props.modelValue });

        // 平台选项 - 从后端获取或使用默认选项
        const platformOptions = [
            { title: 'Telegram', value: 'telegram' },
            { title: 'QQ', value: 'qq' },
            { title: 'Discord', value: 'discord' },
            { title: 'Slack', value: 'slack' },
            { title: '微信', value: 'wechat' },
            { title: 'Web', value: 'web' }
        ];

        // 监听输入变化
        watch(localConfig, (newVal) => {
            emit('update:modelValue', newVal);
        }, { deep: true });

        // 监听props变化
        watch(() => props.modelValue, (newVal) => {
            localConfig.value = { ...newVal };
        }, { deep: true });

        const addAlias = () => {
            localConfig.value.aliases.push('');
        };

        const removeAlias = (index: number) => {
            localConfig.value.aliases.splice(index, 1);
        };

        return {
            tm,
            localConfig,
            platformOptions,
            addAlias,
            removeAlias
        };
    }
});
</script>

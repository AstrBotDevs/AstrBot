<template>
    <v-card>
        <v-card-title>
            <v-icon start size="small">mdi-account-heart</v-icon>
            {{ tm('advancedPersona.tabs.personality') }}
        </v-card-title>
        <v-card-text>
            <v-row>
                <!-- 人格特质 -->
                <v-col cols="12" md="6">
                    <v-textarea v-model="localConfig.traits"
                        :label="tm('advancedPersona.personality.traits')"
                        :hint="tm('advancedPersona.personality.traitsHint')"
                        variant="outlined"
                        rows="4"
                        persistent-hint />
                </v-col>

                <!-- 表达风格 -->
                <v-col cols="12" md="6">
                    <v-textarea v-model="localConfig.expression_style"
                        :label="tm('advancedPersona.personality.expressionStyle')"
                        :hint="tm('advancedPersona.personality.expressionStyleHint')"
                        variant="outlined"
                        rows="4"
                        persistent-hint />
                </v-col>

                <!-- 识别规则 -->
                <v-col cols="12" md="6">
                    <v-textarea v-model="localConfig.recognition_rules"
                        :label="tm('advancedPersona.personality.recognitionRules')"
                        :hint="tm('advancedPersona.personality.recognitionRulesHint')"
                        variant="outlined"
                        rows="4"
                        persistent-hint />
                </v-col>

                <!-- 心情标签 -->
                <v-col cols="12" md="6">
                    <div class="mb-2">
                        <div class="d-flex justify-space-between align-center mb-2">
                            <label class="text-body-1">{{ tm('advancedPersona.personality.moodTags') }}</label>
                            <v-btn size="small" variant="text" prepend-icon="mdi-plus" @click="addMoodTag">
                                {{ tm('advancedPersona.personality.addMoodTag') }}
                            </v-btn>
                        </div>
                        <p class="text-caption text-medium-emphasis mb-2">
                            {{ tm('advancedPersona.personality.moodTagsHint') }}
                        </p>
                    </div>

                    <div v-for="(tag, index) in localConfig.mood_tags" :key="index"
                        class="d-flex align-center ga-2 mb-2">
                        <v-text-field v-model="tag.name"
                            :label="tm('advancedPersona.personality.tagName')"
                            variant="outlined"
                            density="compact"
                            hide-details
                            style="flex: 1" />
                        <v-text-field v-model.number="tag.weight"
                            :label="tm('advancedPersona.personality.tagWeight')"
                            type="number"
                            variant="outlined"
                            density="compact"
                            hide-details
                            style="width: 100px"
                            suffix="%" />
                        <v-btn icon="mdi-delete" variant="text" size="small" color="error"
                            @click="removeMoodTag(index)" />
                    </div>

                    <!-- 权重总计显示 -->
                    <div class="text-caption mt-2" :class="totalWeight === 100 ? 'text-success' : 'text-warning'">
                        {{ tm('advancedPersona.personality.totalWeight') }}: {{ totalWeight }}%
                        <span v-if="totalWeight !== 100">
                            ({{ tm('advancedPersona.personality.weightWarning') }})
                        </span>
                    </div>
                </v-col>
            </v-row>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

interface MoodTag {
    name: string;
    weight: number;
}

interface PersonalityConfig {
    traits: string;
    expression_style: string;
    recognition_rules: string;
    mood_tags: MoodTag[];
}

export default defineComponent({
    name: 'PersonalitySection',
    props: {
        modelValue: {
            type: Object as () => PersonalityConfig,
            default: () => ({
                traits: '',
                expression_style: '',
                recognition_rules: '',
                mood_tags: []
            })
        }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
        const { tm } = useModuleI18n('features/persona');

        const localConfig = ref<PersonalityConfig>({
            ...props.modelValue,
            mood_tags: [...(props.modelValue.mood_tags || [])]
        });

        // 监听输入变化
        watch(localConfig, (newVal) => {
            emit('update:modelValue', newVal);
        }, { deep: true });

        // 监听props变化（仅在外部重置时同步，避免递归）
        watch(() => props.modelValue, (newVal) => {
            if (JSON.stringify(newVal) !== JSON.stringify(localConfig.value)) {
                localConfig.value = { ...newVal, mood_tags: [...(newVal.mood_tags || [])] };
            }
        }, { deep: true });

        const totalWeight = computed(() => {
            return localConfig.value.mood_tags.reduce((sum, tag) => sum + (tag.weight || 0), 0);
        });

        const addMoodTag = () => {
            localConfig.value.mood_tags.push({ name: '', weight: 0 });
        };

        const removeMoodTag = (index: number) => {
            localConfig.value.mood_tags.splice(index, 1);
        };

        return {
            tm,
            localConfig,
            totalWeight,
            addMoodTag,
            removeMoodTag
        };
    }
});
</script>

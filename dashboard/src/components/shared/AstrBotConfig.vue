<template>
    <div class="config-section" v-if="iterable && metadata[metadataKey]?.type === 'object'">
        <v-list-item-title class="config-title">
            {{ metadata[metadataKey]?.description }} <span class="key-name">({{ metadataKey }})</span>
        </v-list-item-title>
        <v-list-item-subtitle class="config-hint">
            <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint" class="hint-icon">‼️</span>
            {{ metadata[metadataKey]?.hint }}
        </v-list-item-subtitle>
    </div>

    <v-card-text class="config-container">
        <div v-for="(val, key, index) in iterable" :key="key" class="config-item"
            v-if="metadata[metadataKey]?.type === 'object' || metadata[metadataKey]?.config_template">

            <div v-if="metadata[metadataKey].items[key]?.type === 'object'" class="nested-object">
                <div v-if="metadata[metadataKey].items[key] && !metadata[metadataKey].items[key]?.invisible"
                    class="nested-object-container">
                    <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[key]" :metadataKey="key">
                    </AstrBotConfig>
                </div>
            </div>

            <v-row v-else class="config-row">
                <v-col cols="6" class="label-col">
                    <v-list-item>
                        <v-list-item-title class="item-title">
                            <span v-if="metadata[metadataKey].items[key]?.description">
                                {{ metadata[metadataKey].items[key]?.description }}
                                <span class="key-name">({{ key }})</span>
                            </span>
                            <span v-else>{{ key }}</span>
                        </v-list-item-title>

                        <v-list-item-subtitle class="item-hint">
                            <span
                                v-if="metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint"
                                class="hint-icon">‼️</span>
                            {{ metadata[metadataKey].items[key]?.hint }}
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-col>

                <v-col cols="1" class="type-col">
                    <v-chip v-if="!metadata[metadataKey].items[key]?.invisible" 
                           color="primary" label size="x-small"
                           class="type-chip">
                        {{ metadata[metadataKey].items[key]?.type || 'string' }}
                    </v-chip>
                </v-col>

                <v-col cols="5" class="input-col">
                    <div v-if="metadata[metadataKey].items[key]" class="input-wrapper">
                        <v-fade-transition>
                            <v-select
                                v-if="metadata[metadataKey].items[key]?.options && !metadata[metadataKey].items[key]?.invisible"
                                v-model="iterable[key]" 
                                variant="outlined"
                                :items="metadata[metadataKey].items[key]?.options"
                                :disabled="metadata[metadataKey].items[key]?.readonly" 
                                density="compact" flat 
                                hide-details
                                class="config-input"
                                ></v-select>
                            <v-text-field
                                v-else-if="metadata[metadataKey].items[key]?.type === 'string' && !metadata[metadataKey].items[key]?.invisible"
                                v-model="iterable[key]" 
                                variant="outlined"
                                density="compact" flat 
                                hide-details
                                class="config-input"
                                ></v-text-field>
                            <v-text-field
                                v-else-if="(metadata[metadataKey].items[key]?.type === 'int' || metadata[metadataKey].items[key]?.type === 'float') && !metadata[metadataKey].items[key]?.invisible"
                                v-model="iterable[key]" 
                                variant="outlined"
                                density="compact" flat 
                                hide-details
                                class="config-input"
                                ></v-text-field>
                            <v-textarea
                                v-else-if="metadata[metadataKey].items[key]?.type === 'text' && !metadata[metadataKey].items[key]?.invisible"
                                v-model="iterable[key]" 
                                variant="outlined" 
                                auto-grow
                                rows="2"
                                flat 
                                hide-details
                                class="config-input"
                                ></v-textarea>
                            <v-switch
                                v-else-if="metadata[metadataKey].items[key]?.type === 'bool' && !metadata[metadataKey].items[key]?.invisible"
                                v-model="iterable[key]" 
                                color="primary" 
                                hide-details
                                class="config-switch"
                                ></v-switch>
                            <ListConfigItem
                                v-else-if="metadata[metadataKey].items[key]?.type === 'list' && !metadata[metadataKey].items[key]?.invisible"
                                :value="iterable[key]" />
                        </v-fade-transition>
                    </div>
                    <div v-else class="input-wrapper">
                        <!-- 在 metadata 中没有 key -->
                        <v-text-field 
                            v-model="iterable[key]" 
                            :label="key" 
                            variant="outlined" 
                            density="compact" 
                            flat 
                            hide-details
                            class="config-input"
                            ></v-text-field>
                    </div>
                </v-col>
            </v-row>

            <v-divider class="item-divider" 
                      v-if="index !== Object.keys(iterable).length - 1 && !metadata[metadataKey].items[key]?.invisible"></v-divider>

        </div>
        <div v-else>
            <v-row class="config-row">
                <v-col cols="6" class="label-col">
                    <v-list-item>
                        <v-list-item-title class="item-title">
                            {{ metadata[metadataKey]?.description }}
                            <span class="key-name">({{ metadataKey }})</span>
                        </v-list-item-title>

                        <v-list-item-subtitle class="item-hint">
                            <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint" class="hint-icon">‼️</span>
                            {{ metadata[metadataKey]?.hint }}
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-col>

                <v-col cols="1" class="type-col">
                    <v-chip v-if="!metadata[metadataKey]?.invisible" 
                           color="primary" 
                           label 
                           size="x-small"
                           class="type-chip">
                        {{ metadata[metadataKey]?.type }}
                    </v-chip>
                </v-col>

                <v-col cols="5" class="input-col">
                    <div class="input-wrapper">
                        <v-fade-transition>
                            <v-select v-if="metadata[metadataKey]?.options && !metadata[metadataKey]?.invisible"
                                v-model="iterable[metadataKey]" 
                                variant="outlined" 
                                :items="metadata[metadataKey]?.options"
                                :disabled="metadata[metadataKey]?.readonly" 
                                density="compact" 
                                flat 
                                hide-details
                                class="config-input"
                                ></v-select>
                            <v-text-field
                                v-else-if="metadata[metadataKey]?.type === 'string' && !metadata[metadataKey]?.invisible"
                                v-model="iterable[metadataKey]" 
                                variant="outlined" 
                                density="compact" 
                                flat 
                                hide-details
                                class="config-input"
                                ></v-text-field>
                            <v-text-field
                                v-else-if="(metadata[metadataKey]?.type === 'int' || metadata[metadataKey]?.type === 'float') && !metadata[metadataKey]?.invisible"
                                v-model="iterable[metadataKey]" 
                                variant="outlined" 
                                density="compact" 
                                flat 
                                hide-details
                                class="config-input"
                                ></v-text-field>
                            <v-textarea
                                v-else-if="metadata[metadataKey]?.type === 'text' && !metadata[metadataKey]?.invisible"
                                v-model="iterable[metadataKey]" 
                                variant="outlined" 
                                auto-grow
                                rows="2"
                                flat 
                                hide-details
                                class="config-input"
                                ></v-textarea>
                            <v-switch
                                v-else-if="metadata[metadataKey]?.type === 'bool' && !metadata[metadataKey]?.invisible"
                                v-model="iterable[metadataKey]" 
                                color="primary" 
                                hide-details
                                class="config-switch"
                                ></v-switch>
                            <ListConfigItem
                                v-else-if="metadata[metadataKey]?.type === 'list' && !metadata[metadataKey]?.invisible"
                                :value="iterable[metadataKey]" />
                        </v-fade-transition>
                    </div>
                </v-col>
            </v-row>

            <v-divider class="main-divider"></v-divider>
        </div>
    </v-card-text>
</template>

<script>
import ListConfigItem from './ListConfigItem.vue';

export default {
    components: {
        ListConfigItem
    },
    props: {
        metadata: Object,
        iterable: Object,
        metadataKey: String
    }
}
</script>

<style scoped>
.config-section {
    margin-bottom: 12px;
}

.config-title {
    font-weight: 600;
    font-size: 16px;
    color: #1a1a1a;
}

.config-hint {
    font-size: 12px;
    color: #666;
    margin-top: 2px;
}

.hint-icon {
    opacity: 1.0;
    margin-right: 4px;
}

.key-name {
    color: #666;
    font-size: 0.9em;
    font-weight: normal;
}

.config-container {
    padding: 0;
}

.config-item {
    margin-bottom: 4px;
    transition: background-color 0.2s;
}

.config-item:hover {
    background-color: rgba(0, 0, 0, 0.02);
}

.nested-object {
    padding-left: 16px;
}

.nested-object-container {
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 12px;
    margin: 16px 0;
    background-color: rgba(250, 250, 250, 0.5);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.config-row {
    margin: 0;
    align-items: center;
    padding: 6px 4px;
    border-radius: 8px;
}

.label-col {
    padding: 0;
}

.item-title {
    font-size: 14px;
    font-weight: 600;
    color: #333;
}

.item-hint {
    font-size: 12px;
    color: #666;
    margin-top: 2px;
}

.type-col {
    display: flex;
    justify-content: center;
}

.type-chip {
    font-size: 10px !important;
    text-transform: lowercase;
    font-weight: 500;
}

.input-col {
    padding-top: 4px;
    padding-bottom: 4px;
}

.input-wrapper {
    width: 100%;
}

.config-input {
    border-radius: 6px;
    transition: box-shadow 0.2s;
}

.config-input:hover {
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.config-switch {
    margin-top: 8px;
}

.item-divider {
    border-color: #eee;
    margin: 4px 0;
}

.main-divider {
    border-color: #ddd;
    margin: 8px 0;
}
</style>
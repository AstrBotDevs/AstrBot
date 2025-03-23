<template>
    <div style="margin-bottom: 6px;" v-if="iterable && metadata[metadataKey]?.type === 'object'">
        <v-list-item-title style="font-weight: bold;">
            {{ metadata[metadataKey]?.description }} ({{ metadataKey }})
        </v-list-item-title>
        <v-list-item-subtitle style="font-size: 12px;">
            <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint"
                style="opacity: 1.0;">‼️</span>
            {{ metadata[metadataKey]?.hint }}
        </v-list-item-subtitle>
    </div>

    <v-card-text style="padding: 0px;">
        <div v-for="(val, key, index) in iterable" :key="key" style="margin-bottom: 0.5px;"
            v-if="metadata[metadataKey]?.type === 'object' || metadata[metadataKey]?.config_template">

            <div v-if="metadata[metadataKey].items[key]?.type === 'object'" style="padding-left: 16px;">
                <div v-if="metadata[metadataKey].items[key] && !metadata[metadataKey].items[key]?.invisible"
                    style="border: 1px solid #e0e0e0; padding: 8px; margin-bottom: 16px; border-radius: 10px; margin-top: 16px">
                    <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[key]" :metadataKey=key>
                    </AstrBotConfig>
                </div>
            </div>

            <v-row v-else style="margin: 0; align-items: center;">
                <v-col cols="6" style="padding: 0px;">
                    <v-list-item>
                        <v-list-item-title style="font-size: 14px; font-weight: bold;">
                            <span v-if="metadata[metadataKey].items[key]?.description">{{ metadata[metadataKey].items[key]?.description + '(' + key + ')' }}</span>
                            <span v-else>{{ key }}</span>
                        </v-list-item-title>

                        <v-list-item-subtitle style="font-size: 12px;">
                            <span
                                v-if="metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint"
                                style="opacity: 1.0;">‼️</span>
                            {{ metadata[metadataKey].items[key]?.hint }}
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-col>

                <v-col cols="1">
                    <v-chip v-if="!metadata[metadataKey].items[key]?.invisible" color="primary" label size="x-small"
                        class="mb-1">{{
                            metadata[metadataKey].items[key]?.type || 'string' }}
                    </v-chip>
                </v-col>

                <v-col cols="5">
                    <div style="width: 100%;" v-if="metadata[metadataKey].items[key]">
                        <v-select
                            v-if="metadata[metadataKey].items[key]?.options && !metadata[metadataKey].items[key]?.invisible"
                            v-model="iterable[key]" variant="outlined"
                            :items="metadata[metadataKey].items[key]?.options" dense
                            :disabled="metadata[metadataKey].items[key]?.readonly" density="compact" flat hide-details
                            single-line></v-select>
                        <v-text-field
                            v-else-if="metadata[metadataKey].items[key]?.type === 'string' && !metadata[metadataKey].items[key]?.invisible"
                            v-model="iterable[key]" variant="outlined" dense density="compact" flat hide-details
                            single-line></v-text-field>
                        <v-text-field
                            v-else-if="(metadata[metadataKey].items[key]?.type === 'int' || metadata[metadataKey].items[key]?.type === 'float') && !metadata[metadataKey].items[key]?.invisible"
                            v-model="iterable[key]" variant="outlined" dense density="compact" flat hide-details
                            single-line></v-text-field>
                        <v-textarea
                            v-else-if="metadata[metadataKey].items[key]?.type === 'text' && !metadata[metadataKey].items[key]?.invisible"
                            v-model="iterable[key]" variant="outlined" dense flat hide-details single-line></v-textarea>
                        <v-switch
                            v-else-if="metadata[metadataKey].items[key]?.type === 'bool' && !metadata[metadataKey].items[key]?.invisible"
                            v-model="iterable[key]" color="primary" hide-details></v-switch>
                        <ListConfigItem
                            v-else-if="metadata[metadataKey].items[key]?.type === 'list' && !metadata[metadataKey].items[key]?.invisible"
                            :value="iterable[key]" />
                    </div>
                    <div style="width: 100%;" v-else>
                        <!-- 在 metadata 中没有 key -->
                        <v-text-field v-model="iterable[key]" :label="key" variant="outlined" dense density="compact" flat hide-details
                        single-line></v-text-field>
                    </div>
                </v-col>

            </v-row>

            <v-divider style="border-color: #ccc;" v-if="index !== Object.keys(iterable).length - 1 && !metadata[metadataKey].items[key]?.invisible "></v-divider>

        </div>
        <div v-else>

            <v-row style="margin: 0; align-items: center;">
                <v-col cols="6" style="padding: 0px;">
                    <v-list-item>
                        <v-list-item-title style="font-size: 14px; font-weight: bold">
                            {{ metadata[metadataKey]?.description + '(' + metadataKey + ')' }}
                        </v-list-item-title>

                        <v-list-item-subtitle style="font-size: 12px;">
                            <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint">‼️</span>
                            {{ metadata[metadataKey]?.hint }}
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-col>

                <v-col cols="1">
                    <v-chip v-if="!metadata[metadataKey]?.invisible" color="primary" label size="x-small"
                        class="mb-1">{{
                            metadata[metadataKey]?.type }}
                    </v-chip>
                </v-col>

                <v-col cols="5">
                    <div style="width: 100%;">
                        <v-select v-if="metadata[metadataKey]?.options && !metadata[metadataKey]?.invisible"
                            v-model="iterable[metadataKey]" variant="outlined" :items="metadata[metadataKey]?.options"
                            dense :disabled="metadata[metadataKey]?.readonly" density="compact" flat hide-details
                            single-line></v-select>
                        <v-text-field
                            v-else-if="metadata[metadataKey]?.type === 'string' && !metadata[metadataKey]?.invisible"
                            v-model="iterable[metadataKey]" variant="outlined" dense density="compact" flat hide-details
                            single-line></v-text-field>
                        <v-text-field
                            v-else-if="(metadata[metadataKey]?.type === 'int' || metadata[metadataKey]?.type === 'float') && !metadata[metadataKey]?.invisible"
                            v-model="iterable[metadataKey]" variant="outlined" dense density="compact" flat hide-details
                            single-line></v-text-field>
                        <v-textarea
                            v-else-if="metadata[metadataKey]?.type === 'text' && !metadata[metadataKey]?.invisible"
                            v-model="iterable[metadataKey]" variant="outlined" dense density="compact" flat hide-details
                            single-line></v-textarea>
                        <v-switch
                            v-else-if="metadata[metadataKey]?.type === 'bool' && !metadata[metadataKey]?.invisible"
                            v-model="iterable[metadataKey]" color="primary" hide-details></v-switch>
                        <ListConfigItem
                            v-else-if="metadata[metadataKey]?.type === 'list' && !metadata[metadataKey]?.invisible"
                            :value="iterable[metadataKey]" />
                    </div>
                </v-col>
            </v-row>

            <v-divider style="border-color: #ddd;"></v-divider>
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
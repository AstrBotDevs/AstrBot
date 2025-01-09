<template>
    <h3 style="margin-bottom: 8px;" v-if="iterable && metadata[metadataKey]?.type === 'object'">
        {{metadata[metadataKey]?.description }}
    </h3>
    <v-card-text>
        <div v-for="(index, key) in iterable" :key="key" style="margin-bottom: 0.5px;" v-if="metadata[metadataKey]?.type === 'object' || metadata[metadataKey]?.config_template">
            <v-alert v-if="metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint && metadata[metadataKey].items[key]?.type !== 'object'" style="margin-bottom: 16px"
                :text="metadata[metadataKey].items[key]?.hint" :title="'💡 关于' + metadata[metadataKey].items[key]?.description"
                type="info" variant="tonal">
            </v-alert>

            <div style="display: flex; align-items: center; justify-content: center; gap: 16px">
                <div style="width: 100%;" v-if="metadata[metadataKey].items[key]">
                    <v-select v-if="metadata[metadataKey].items[key]?.options && !metadata[metadataKey].items[key]?.invisible" v-model="iterable[key]"
                        variant="outlined" :items="metadata[metadataKey].items[key]?.options"
                        :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'" dense :disabled="metadata[metadataKey].items[key]?.readonly"></v-select>
                    <v-text-field v-else-if="metadata[metadataKey].items[key]?.type === 'string' && !metadata[metadataKey].items[key]?.invisible"
                        v-model="iterable[key]" :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'"
                        variant="outlined" dense ></v-text-field>
                    <v-text-field
                        v-else-if="(metadata[metadataKey].items[key]?.type === 'int' || metadata[metadataKey].items[key]?.type === 'float') && !metadata[metadataKey].items[key]?.invisible"
                        v-model="iterable[key]" :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'"
                        variant="outlined" dense></v-text-field>
                    <v-textarea v-else-if="metadata[metadataKey].items[key]?.type === 'text' && !metadata[metadataKey].items[key]?.invisible" v-model="iterable[key]"
                        :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'" variant="outlined"
                        dense></v-textarea>
                    <v-switch v-else-if="metadata[metadataKey].items[key]?.type === 'bool' && !metadata[metadataKey].items[key]?.invisible" v-model="iterable[key]"
                        :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'" color="primary"
                        inset></v-switch>
                    <v-combobox variant="outlined" v-else-if="metadata[metadataKey].items[key]?.type === 'list' && !metadata[metadataKey].items[key]?.invisible"
                        v-model="iterable[key]" chips clearable
                        :label="metadata[metadataKey].items[key]?.description + '(' + key + ')'" multiple
                        prepend-icon="mdi-tag-multiple-outline">
                        <template v-slot:selection="{ attrs, item, select, selected }">
                            <v-chip v-bind="attrs" :model-value="selected" closable @click="select"
                                @click:close="remove(item)">
                                <strong>{{ item }}</strong>
                            </v-chip>
                        </template>
                    </v-combobox>
                    <div v-else-if="metadata[metadataKey].items[key]?.type === 'object' && !metadata[metadataKey].items[key]?.invisible"
                        style="border: 1px solid #e0e0e0; padding: 8px; margin-bottom: 16px; border-radius: 10px;">
                        <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[key]"
                            :metadataKey=key>
                        </AstrBotConfig>
                    </div>
                </div>

                <div style="width: 100%;" v-else>
                    <!-- 在 metadata 中没有 key -->
                    <v-text-field v-model="iterable[key]" :label="key" variant="outlined" dense></v-text-field>
                </div>

                <div
                    v-if="!metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint && metadata[metadataKey].items[key]?.type !== 'object' && !metadata[metadataKey].items[key]?.invisible">
                    <v-btn icon size="x-small" style="margin-bottom: 22px;">
                        <v-icon size="x-small">mdi-help</v-icon>
                        <v-tooltip activator="parent" location="start">{{ metadata[metadataKey].items[key]?.hint
                            }}</v-tooltip>
                    </v-btn>
                </div>
            </div>
        
        </div>
        <div v-else>
            <v-alert v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint && metadata[metadataKey]?.type !== 'object'" style="margin-bottom: 16px"
                :text="metadata[metadataKey]?.hint" :title="'💡 关于' + metadata[metadataKey]?.description"
                type="info" variant="tonal">
            </v-alert>

            <div style="display: flex; align-items: center; justify-content: center; gap: 16px">
                <div style="width: 100%;">
                    <v-select v-if="metadata[metadataKey]?.options && !metadata[metadataKey]?.invisible" v-model="iterable[metadataKey]"
                        variant="outlined" :items="metadata[metadataKey]?.options"
                        :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'" dense :disabled="metadata[metadataKey]?.readonly"></v-select>
                    <v-text-field v-else-if="metadata[metadataKey]?.type === 'string' && !metadata[metadataKey]?.invisible"
                        v-model="iterable[metadataKey]" :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'"
                        variant="outlined" dense ></v-text-field>
                    <v-text-field
                        v-else-if="(metadata[metadataKey]?.type === 'int' || metadata[metadataKey]?.type === 'float') && !metadata[metadataKey]?.invisible"
                        v-model="iterable[metadataKey]" :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'"
                        variant="outlined" dense></v-text-field>
                    <v-textarea v-else-if="metadata[metadataKey]?.type === 'text' && !metadata[metadataKey]?.invisible" v-model="iterable[metadataKey]"
                        :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'" variant="outlined"
                        dense></v-textarea>
                    <v-switch v-else-if="metadata[metadataKey]?.type === 'bool' && !metadata[metadataKey]?.invisible" v-model="iterable[metadataKey]"
                        :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'" color="primary"
                        inset></v-switch>
                    <v-combobox variant="outlined" v-else-if="metadata[metadataKey]?.type === 'list' && !metadata[metadataKey]?.invisible"
                        v-model="iterable[metadataKey]" chips clearable
                        :label="metadata[metadataKey]?.description + '(' + metadataKey+ ')'" multiple
                        prepend-icon="mdi-tag-multiple-outline">
                        <template v-slot:selection="{ attrs, item, select, selected }">
                            <v-chip v-bind="attrs" :model-value="selected" closable @click="select"
                                @click:close="remove(item)">
                                <strong>{{ item }}</strong>
                            </v-chip>
                        </template>
                    </v-combobox>
                    <div v-else-if="metadata[metadataKey]?.type === 'object' && !metadata[metadataKey]?.invisible"
                        style="border: 1px solid #e0e0e0; padding: 8px; margin-bottom: 16px; border-radius: 10px;">
                        <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[metadataKey]"
                            :metadataKey=key>
                        </AstrBotConfig>
                    </div>
                </div>

                <div
                    v-if="!metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint && metadata[metadataKey]?.type !== 'object' && !metadata[metadataKey]?.invisible">
                    <v-btn icon size="x-small" style="margin-bottom: 22px;">
                        <v-icon size="x-small">mdi-help</v-icon>
                        <v-tooltip activator="parent" location="start">{{ metadata[metadataKey]?.hint
                            }}</v-tooltip>
                    </v-btn>
                </div>
            </div>
        </div>
    </v-card-text>
</template>

<script>
import { readonly } from 'vue';

export default {
    props: {
        metadata: Object,
        iterable: Object,
        metadataKey: String
    }
}
</script>
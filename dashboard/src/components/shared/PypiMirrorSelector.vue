<template>
    <div class="pypi-mirror">
        <div class="pypi-mirror__header">
            <h5 class="pypi-mirror__title">{{ tm('network.pypiMirror.label') }}</h5>
            <v-btn class="pypi-mirror__test-button" size="x-small" variant="tonal"
                :loading="testingConnections" @click="testAllMirrors">
                {{ tm('network.pypiMirror.testConnection') }}
            </v-btn>
        </div>
        <v-radio-group class="mt-2" :model-value="activeKey" hide-details="true"
            @update:model-value="onSelectionChange">
            <v-radio value="none">
                <template v-slot:label>
                    <div class="pypi-mirror__option-label">
                        <span>{{ tm('network.pypiMirror.none') }}</span>
                        <v-chip v-if="status.official" :color="status.official.available ? 'success' : 'error'"
                            size="x-small">
                            {{ status.official.available ? `${status.official.latency}ms` : tm('network.pypiMirror.unavailable') }}
                        </v-chip>
                    </div>
                </template>
            </v-radio>
            <v-radio color="success" v-for="mirror in mirrors" :key="mirror.key" :value="mirror.key">
                <template v-slot:label>
                    <div class="pypi-mirror__option-label">
                        <span class="pypi-mirror__name">{{ tm(`network.pypiMirror.presets.${mirror.key}`) }}</span>
                        <span class="pypi-mirror__url">{{ mirror.url }}</span>
                        <v-chip v-if="status[mirror.key]" :color="status[mirror.key].available ? 'success' : 'error'"
                            size="x-small">
                            {{ status[mirror.key].available ? `${status[mirror.key].latency}ms` : tm('network.pypiMirror.unavailable') }}
                        </v-chip>
                    </div>
                </template>
            </v-radio>
            <v-radio color="primary" value="custom">
                <template v-slot:label>
                    <div class="pypi-mirror__option-label">
                        <span v-if="activeKey !== 'custom'">{{ tm('network.pypiMirror.custom') }}</span>
                        <v-text-field v-else class="pypi-mirror__custom-input" density="compact" :model-value="customUrl"
                            variant="outlined" :placeholder="tm('network.pypiMirror.customPlaceholder')"
                            hide-details="true" @update:model-value="onCustomInput">
                        </v-text-field>
                        <v-chip v-if="status.custom" :color="status.custom.available ? 'success' : 'error'"
                            size="x-small">
                            {{ status.custom.available ? `${status.custom.latency}ms` : tm('network.pypiMirror.unavailable') }}
                        </v-chip>
                    </div>
                </template>
            </v-radio>
        </v-radio-group>
    </div>
</template>

<script>
import { statsApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

// "No mirror" resolves to the official index, which is what pip uses by default.
const OFFICIAL_INDEX_URL = "https://pypi.org/simple";

export default {
    props: {
        modelValue: {
            type: String,
            default: "",
        },
    },
    emits: ["update:modelValue"],
    setup() {
        const { tm } = useModuleI18n('features/settings');
        return { tm };
    },
    data() {
        return {
            mirrors: [
                { key: "aliyun", url: "https://mirrors.aliyun.com/pypi/simple/" },
                { key: "tencent", url: "https://mirrors.cloud.tencent.com/pypi/simple" },
                { key: "tsinghua", url: "https://pypi.tuna.tsinghua.edu.cn/simple" },
                { key: "ustc", url: "https://pypi.mirrors.ustc.edu.cn/simple" },
            ],
            activeKey: "none",
            customUrl: "",
            status: {},
            testingConnections: false,
        }
    },
    watch: {
        modelValue: {
            immediate: true,
            handler(value) {
                this.syncFromValue(value);
            },
        },
    },
    methods: {
        normalizeUrl(value) {
            return String(value || "").trim().replace(/\/+$/, "");
        },
        syncFromValue(value) {
            const current = this.normalizeUrl(value);
            if (!current) {
                this.activeKey = "none";
                this.customUrl = "";
                return;
            }
            const preset = this.mirrors.find(
                (mirror) => this.normalizeUrl(mirror.url) === current
            );
            if (preset) {
                this.activeKey = preset.key;
                this.customUrl = "";
                return;
            }
            this.activeKey = "custom";
            this.customUrl = String(value).trim();
        },
        onSelectionChange(key) {
            this.activeKey = key;
            if (key === "none") {
                this.$emit("update:modelValue", "");
                return;
            }
            const preset = this.mirrors.find((mirror) => mirror.key === key);
            if (preset) {
                this.$emit("update:modelValue", preset.url);
            }
            // A custom URL is only emitted once the user types one, so picking
            // this option does not wipe the value that is already saved.
        },
        onCustomInput(value) {
            this.customUrl = value;
            this.$emit("update:modelValue", String(value || "").trim());
        },
        async testMirror(indexUrl, statusKey) {
            try {
                const response = await statsApi.testPypiIndex({
                    index_url: indexUrl
                });
                if (response.status === 200) {
                    this.status[statusKey] = {
                        available: true,
                        latency: Math.round(response.data.data.latency)
                    };
                } else {
                    this.status[statusKey] = {
                        available: false,
                        latency: 0
                    };
                }
            } catch (error) {
                this.status[statusKey] = {
                    available: false,
                    latency: 0
                };
            }
        },
        async testAllMirrors() {
            this.testingConnections = true;

            try {
                const promises = this.mirrors.map((mirror) =>
                    this.testMirror(mirror.url, mirror.key)
                );
                promises.push(this.testMirror(OFFICIAL_INDEX_URL, "official"));

                if (this.activeKey === "custom") {
                    const customIndex = this.normalizeUrl(this.customUrl);
                    if (/^https?:\/\//i.test(customIndex)) {
                        promises.push(this.testMirror(customIndex, "custom"));
                    }
                }

                await Promise.all(promises);
            } finally {
                this.testingConnections = false;
            }
        },
    },
}
</script>

<style scoped>
.pypi-mirror {
    width: 100%;
    min-width: 0;
}

.pypi-mirror__header {
    display: flex;
    align-items: center;
    gap: 8px;
}

.pypi-mirror__test-button {
    flex: 0 0 auto;
}

.pypi-mirror__title {
    margin: 0;
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.88rem;
    font-weight: 700;
    line-height: 1.4;
}

.pypi-mirror :deep(.v-label) {
    min-width: 0;
    font-size: 0.875rem;
    line-height: 1.35;
    white-space: normal;
}

.pypi-mirror__option-label {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-width: 0;
    max-width: 100%;
}

.pypi-mirror__name {
    font-weight: 600;
}

.pypi-mirror__url {
    color: rgba(var(--v-theme-on-surface), 0.68);
    font-size: 0.78rem;
    overflow-wrap: anywhere;
}

.pypi-mirror__custom-input {
    width: min(100%, 420px);
}
</style>

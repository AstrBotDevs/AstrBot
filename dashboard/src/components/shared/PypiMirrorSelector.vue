<template>
    <div class="pypi-mirror">
        <div class="pypi-mirror__header">
            <h5 class="pypi-mirror__title">{{ tm('network.pypiMirror.label') }}</h5>
            <v-btn class="pypi-mirror__test-button" size="x-small" variant="tonal"
                :loading="testingConnections" @click="testAllMirrors">
                {{ tm('network.pypiMirror.testConnection') }}
            </v-btn>
            <v-btn class="pypi-mirror__test-button" size="x-small" variant="tonal"
                :loading="testingSpeed" @click="testAllSpeeds">
                {{ tm('network.pypiMirror.testSpeed') }}
            </v-btn>
        </div>
        <v-radio-group class="mt-2" :model-value="activeKey" hide-details="true"
            @update:model-value="onSelectionChange">
            <v-radio color="success" v-for="mirror in mirrors" :key="mirror.key" :value="mirror.key">
                <template v-slot:label>
                    <div class="pypi-mirror__option-label">
                        <span class="pypi-mirror__name">{{ tm(`network.pypiMirror.presets.${mirror.key}`) }}</span>
                        <span class="pypi-mirror__url">{{ mirror.url }}</span>
                        <v-chip v-if="status[mirror.key]"
                            :color="status[mirror.key].available ? 'success' : 'error'" size="x-small">
                            {{ status[mirror.key].available ? status[mirror.key].latency + 'ms' : tm('network.pypiMirror.unavailable') }}
                        </v-chip>
                        <v-chip v-if="speed[mirror.key]" color="info" size="x-small">
                            {{ speed[mirror.key] }}MB/s
                        </v-chip>
                    </div>
                </template>
            </v-radio>
            <v-radio color="primary" value="custom">
                <template v-slot:label>
                    <div class="pypi-mirror__option-label">
                        <span class="pypi-mirror__name">{{ tm('network.pypiMirror.custom') }}</span>
                        <v-text-field class="pypi-mirror__custom-input" density="compact" :model-value="customUrl"
                            variant="outlined" :placeholder="tm('network.pypiMirror.customPlaceholder')"
                            hide-details="true" @update:model-value="onCustomInput">
                        </v-text-field>
                        <v-chip v-if="status.custom"
                            :color="status.custom.available ? 'success' : 'error'" size="x-small">
                            {{ status.custom.available ? status.custom.latency + 'ms' : tm('network.pypiMirror.unavailable') }}
                        </v-chip>
                        <v-chip v-if="speed.custom" color="info" size="x-small">
                            {{ speed.custom }}MB/s
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

// The official index is what pip falls back to, so it is listed first like any
// other preset instead of being a separate "no mirror" option.
const OFFICIAL_INDEX_URL = "https://pypi.org/simple";
// The typed custom URL is remembered separately from the saved config value, so
// it stays visible (and testable) after a reload even while a preset is active.
const CUSTOM_STORAGE_KEY = "selectedPypiMirrorCustom";

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
                { key: "official", url: OFFICIAL_INDEX_URL },
                { key: "aliyun", url: "https://mirrors.aliyun.com/pypi/simple" },
                { key: "tencent", url: "https://mirrors.cloud.tencent.com/pypi/simple" },
                { key: "ustc", url: "https://pypi.mirrors.ustc.edu.cn/simple" },
                { key: "tsinghua", url: "https://pypi.tuna.tsinghua.edu.cn/simple" },
            ],
            activeKey: "official",
            customUrl: localStorage.getItem(CUSTOM_STORAGE_KEY) || "",
            status: {},
            speed: {},
            testingConnections: false,
            testingSpeed: false,
        }
    },
    watch: {
        modelValue: {
            immediate: true,
            handler(value) {
                this.syncFromValue(value);
            },
        },
        customUrl(newVal) {
            localStorage.setItem(CUSTOM_STORAGE_KEY, newVal || "");
        },
    },
    methods: {
        normalizeUrl(value) {
            return String(value || "").trim().replace(/\/+$/, "");
        },
        syncFromValue(value) {
            const current = this.normalizeUrl(value);
            // An empty value means pip uses its default, i.e. the official index.
            const preset = current
                ? this.mirrors.find(
                    (mirror) => this.normalizeUrl(mirror.url) === current
                )
                : this.mirrors[0];
            if (preset) {
                // The custom box keeps whatever is typed in it, so that URL can
                // still be read and tested while it is not the selected source.
                this.activeKey = preset.key;
                return;
            }
            this.activeKey = "custom";
            this.customUrl = String(value).trim();
        },
        onSelectionChange(key) {
            this.activeKey = key;
            const preset = this.mirrors.find((mirror) => mirror.key === key);
            if (preset) {
                this.$emit("update:modelValue", preset.url);
                return;
            }
            // Picking the custom option applies the URL already typed, and an
            // empty box leaves the saved source untouched.
            const custom = String(this.customUrl || "").trim();
            if (/^https?:\/\//i.test(custom)) {
                this.$emit("update:modelValue", custom);
            }
        },
        onCustomInput(value) {
            this.customUrl = value;
            if (this.activeKey !== "custom") {
                // Keep the saved source until the option itself is picked.
                return;
            }
            const trimmed = String(value || "").trim();
            if (!trimmed) {
                // Keep the saved value while the field is temporarily empty.
                return;
            }
            this.$emit("update:modelValue", trimmed);
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

                const customIndex = this.normalizeUrl(this.customUrl);
                if (/^https?:\/\//i.test(customIndex)) {
                    promises.push(this.testMirror(customIndex, "custom"));
                }

                await Promise.all(promises);
            } finally {
                this.testingConnections = false;
            }
        },
        // Real download throughput in MB/s, measured by pulling an actual wheel
        // the way pip would, instead of timing a round trip.
        async measureMirror(indexUrl, speedKey) {
            try {
                const response = await statsApi.measurePypiIndexSpeed({
                    index_url: indexUrl
                });
                this.speed[speedKey] =
                    response.status === 200
                        ? Number(response.data.data.speed) || 0
                        : 0;
            } catch (error) {
                this.speed[speedKey] = 0;
            }
        },
        async testAllSpeeds() {
            this.testingSpeed = true;

            try {
                const promises = this.mirrors.map((mirror) =>
                    this.measureMirror(mirror.url, mirror.key)
                );

                const customIndex = this.normalizeUrl(this.customUrl);
                if (/^https?:\/\//i.test(customIndex)) {
                    promises.push(this.measureMirror(customIndex, "custom"));
                }

                await Promise.all(promises);
            } finally {
                this.testingSpeed = false;
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
    flex-wrap: wrap;
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

/* A fixed width keeps the box as long as the longest mirror URL, and stops
   percentage sizing from collapsing it inside the flex label. */
.pypi-mirror__custom-input {
    flex: 0 0 auto;
    width: 272px;
}
</style>

<template>
    <div class="proxy-selector">
        <div class="proxy-selector__header">
            <h5 class="proxy-selector__title">{{ tm('network.proxySelector.title') }}</h5>
            <v-btn
                class="proxy-selector__test-button"
                size="x-small"
                variant="tonal"
                :loading="loadingTestingConnection"
                @click="testAllProxies">
                {{ tm('network.proxySelector.testConnection') }}
            </v-btn>
            <v-btn
                class="proxy-selector__test-button"
                size="x-small"
                variant="tonal"
                :loading="loadingTestingSpeed"
                @click="testAllSpeeds">
                {{ tm('network.proxySelector.testSpeed') }}
            </v-btn>
        </div>
        <v-radio-group class="proxy-selector__options mt-2" v-model="selection" hide-details="true">
            <v-radio value="none">
                <template v-slot:label>
                    <div class="proxy-selector__option-label">
                        <span>{{ tm('network.proxySelector.noProxy') }}</span>
                        <div class="proxy-selector__status">
                            <v-chip v-if="proxyStatus.direct"
                                :color="proxyStatus.direct.available ? 'success' : 'error'"
                                size="x-small">
                                {{ proxyStatus.direct.available ? proxyStatus.direct.latency + 'ms' : tm('network.proxySelector.unavailable') }}
                            </v-chip>
                            <v-chip v-if="proxySpeed.direct" color="info" size="x-small">
                                {{ proxySpeed.direct }}MB/s
                            </v-chip>
                        </div>
                    </div>
                </template>
            </v-radio>
            <v-radio color="success" v-for="(proxy, idx) in githubProxies" :key="proxy" :value="String(idx)">
                <template v-slot:label>
                    <div class="proxy-selector__option-label">
                        <span class="proxy-selector__url">{{ proxy }}</span>
                        <div class="proxy-selector__status">
                            <v-chip v-if="proxyStatus[idx]"
                                :color="proxyStatus[idx].available ? 'success' : 'error'"
                                size="x-small">
                                {{ proxyStatus[idx].available ? proxyStatus[idx].latency + 'ms' : tm('network.proxySelector.unavailable') }}
                            </v-chip>
                            <v-chip v-if="proxySpeed[idx]" color="info" size="x-small">
                                {{ proxySpeed[idx] }}MB/s
                            </v-chip>
                        </div>
                    </div>
                </template>
            </v-radio>
            <v-radio color="primary" value="custom">
                <template v-slot:label>
                    <div class="proxy-selector__option-label">
                        <span>{{ tm('network.proxySelector.custom') }}</span>
                        <v-text-field class="proxy-selector__custom-input" density="compact"
                            :model-value="customProxyValue" variant="outlined"
                            :placeholder="tm('network.proxySelector.customPlaceholder')" hide-details="true"
                            @update:model-value="onCustomInput">
                        </v-text-field>
                        <div class="proxy-selector__status">
                            <v-chip v-if="proxyStatus.custom"
                                :color="proxyStatus.custom.available ? 'success' : 'error'"
                                size="x-small">
                                {{ proxyStatus.custom.available ? proxyStatus.custom.latency + 'ms' : tm('network.proxySelector.unavailable') }}
                            </v-chip>
                            <v-chip v-if="proxySpeed.custom" color="info" size="x-small">
                                {{ proxySpeed.custom }}MB/s
                            </v-chip>
                        </div>
                    </div>
                </template>
            </v-radio>
        </v-radio-group>
    </div>
</template>


<script>
import { statsApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

export default {
    setup() {
        const { tm } = useModuleI18n('features/settings');
        return { tm };
    },
    data() {
        return {
            githubProxies: [
                "https://gh.dpik.top",
                "https://gh-proxy.com",
                "https://hk.gh-proxy.com",
                "https://edgeone.gh-proxy.com",
            ],
            githubProxyRadioControl: "0", // the index of the selected proxy
            selectedGitHubProxy: "",
            // Kept apart from selectedGitHubProxy so a typed URL survives preset
            // switches and can still be read and tested while it is not selected.
            customProxyValue: "",
            radioValue: "0", // 0: 不使用, 1: 使用
            loadingTestingConnection: false,
            loadingTestingSpeed: false,
            testingProxies: {},
            proxyStatus: {},
            proxySpeed: {},
            initializing: true,
        }
    },
    computed: {
        // The radio list is flat: "none", an index of githubProxies, or "custom".
        // It is projected onto the persisted radioValue / githubProxyRadioControl
        // pair that other pages still read from localStorage.
        selection: {
            get() {
                if (String(this.radioValue) === "0") {
                    return "none";
                }
                const control = String(this.githubProxyRadioControl);
                return control === "-1" ? "custom" : control;
            },
            set(value) {
                const normalized = String(value);
                if (normalized === "none") {
                    this.radioValue = "0";
                    return;
                }
                this.radioValue = "1";
                this.githubProxyRadioControl = normalized === "custom" ? "-1" : normalized;
            },
        },
    },
    methods: {
        getProxyByControl(control) {
            const normalizedControl = String(control);
            if (normalizedControl === "-1") {
                return "";
            }
            const index = Number.parseInt(normalizedControl, 10);
            if (Number.isNaN(index)) {
                return "";
            }
            return this.githubProxies[index] || "";
        },
        onCustomInput(value) {
            this.customProxyValue = value;
            // Only a selected custom option feeds the saved setting; otherwise
            // the box is just a place to keep and test a URL.
            if (this.selection === "custom") {
                this.selectedGitHubProxy = String(value || "").trim();
            }
        },
        // statusKey groups one probe result: an index of githubProxies, "direct"
        // for the no-acceleration route, or "custom" for a user supplied URL.
        async testProxy(proxyUrl, statusKey) {
            this.testingProxies[statusKey] = true;

            try {
                const response = await statsApi.testGhproxy({
                    proxy_url: proxyUrl || ""
                });
                if (response.status === 200) {
                    this.proxyStatus[statusKey] = {
                        available: true,
                        latency: Math.round(response.data.data.latency)
                    };
                } else {
                    this.proxyStatus[statusKey] = {
                        available: false,
                        latency: 0
                    };
                }
            } catch (error) {
                this.proxyStatus[statusKey] = {
                    available: false,
                    latency: 0
                };
            } finally {
                this.testingProxies[statusKey] = false;
            }
        },

        async testAllProxies() {
            this.loadingTestingConnection = true;

            try {
                const promises = this.githubProxies.map((proxy, idx) =>
                    this.testProxy(proxy, idx)
                );
                // An empty proxy_url tests the direct route, so "no proxy" is
                // measured on the same footing as the mirrors.
                promises.push(this.testProxy("", "direct"));

                const customProxy = (this.customProxyValue || "")
                    .trim()
                    .replace(/\/+$/, "");
                if (/^https?:\/\//i.test(customProxy)) {
                    promises.push(this.testProxy(customProxy, "custom"));
                }

                await Promise.all(promises);
            } finally {
                this.loadingTestingConnection = false;
            }
        },
        // Real download throughput of a repository asset in MB/s, so the number
        // reflects the bandwidth a route delivers instead of its round trip.
        async measureProxy(proxyUrl, speedKey) {
            try {
                const response = await statsApi.measureGhproxySpeed({
                    proxy_url: proxyUrl || ""
                });
                this.proxySpeed[speedKey] =
                    response.status === 200
                        ? Number(response.data.data.speed) || 0
                        : 0;
            } catch (error) {
                this.proxySpeed[speedKey] = 0;
            }
        },
        async testAllSpeeds() {
            this.loadingTestingSpeed = true;

            try {
                const promises = this.githubProxies.map((proxy, idx) =>
                    this.measureProxy(proxy, String(idx))
                );
                // An empty proxy_url tests the direct route, so "no proxy" is
                // measured on the same footing as the mirrors.
                promises.push(this.measureProxy("", "direct"));

                const customProxy = (this.customProxyValue || "")
                    .trim()
                    .replace(/\/+$/, "");
                if (/^https?:\/\//i.test(customProxy)) {
                    promises.push(this.measureProxy(customProxy, "custom"));
                }

                await Promise.all(promises);
            } finally {
                this.loadingTestingSpeed = false;
            }
        },
    },
    mounted() {
        this.initializing = true;

        const savedProxy = localStorage.getItem('selectedGitHubProxy') || "";
        const savedRadio = localStorage.getItem('githubProxyRadioValue') || "0";
        const savedControl = String(localStorage.getItem('githubProxyRadioControl') || "0");
        const savedCustom = localStorage.getItem('selectedGitHubProxyCustom') || "";

        this.radioValue = savedRadio;
        this.githubProxyRadioControl = savedControl;

        if (savedRadio === "1") {
            if (savedControl !== "-1") {
                this.selectedGitHubProxy = this.getProxyByControl(savedControl);
            } else {
                this.selectedGitHubProxy = savedProxy;
            }
        } else {
            this.selectedGitHubProxy = "";
        }

        this.customProxyValue =
            savedCustom || (savedControl === "-1" ? savedProxy : "");

        this.initializing = false;
    },
    watch: {
        selectedGitHubProxy: function (newVal, oldVal) {
            if (this.initializing) {
                return;
            }
            if (!newVal) {
                newVal = ""
            }
            localStorage.setItem('selectedGitHubProxy', newVal);
        },
        customProxyValue: function (newVal) {
            if (this.initializing) {
                return;
            }
            localStorage.setItem('selectedGitHubProxyCustom', newVal || "");
        },
        radioValue: function (newVal) {
            if (this.initializing) {
                return;
            }
            localStorage.setItem('githubProxyRadioValue', newVal);
            if (String(newVal) === "0") {
                this.selectedGitHubProxy = "";
            } else if (String(this.githubProxyRadioControl) !== "-1") {
                this.selectedGitHubProxy = this.getProxyByControl(this.githubProxyRadioControl);
            }
        },
        githubProxyRadioControl: function (newVal) {
            if (this.initializing) {
                return;
            }
            const normalizedVal = String(newVal);
            localStorage.setItem('githubProxyRadioControl', normalizedVal);
            if (String(this.radioValue) !== "1") {
                this.selectedGitHubProxy = "";
                return;
            }
            if (normalizedVal === "-1") {
                this.selectedGitHubProxy = String(this.customProxyValue || "").trim();
                return;
            }
            this.selectedGitHubProxy = this.getProxyByControl(normalizedVal);
        }
    }
}
</script>

<style scoped>
.proxy-selector {
    width: 100%;
    min-width: 0;
}

.proxy-selector__header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}

.proxy-selector__test-button {
    flex: 0 0 auto;
}

.proxy-selector__title {
    margin: 0;
    color: rgb(var(--v-theme-on-surface));
    font-size: 0.88rem;
    font-weight: 700;
    line-height: 1.4;
}

.proxy-selector :deep(.v-label) {
    min-width: 0;
    font-size: 0.875rem;
    line-height: 1.35;
    white-space: normal;
}

.proxy-selector__option-label {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    min-width: 0;
    max-width: 100%;
}

.proxy-selector__url {
    overflow-wrap: anywhere;
    word-break: normal;
}

.proxy-selector__status {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
}

/* A fixed width keeps this box as long as the PyPI one, and stops percentage
   sizing from collapsing it inside the flex label. */
.proxy-selector__custom-input {
    flex: 0 0 auto;
    width: 272px;
}
</style>

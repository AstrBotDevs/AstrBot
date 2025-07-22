<template>
    <h5>GitHub 加速</h5>
    <v-radio-group class="mt-2" v-model="radioValue" hide-details="true">
        <v-radio label="不使用 GitHub 加速" value="0"></v-radio>
        <v-radio value="1">
            <template v-slot:label>
                <span>使用 GitHub 加速</span>
                <v-btn v-if="radioValue === '1'" class="ml-2" @click="testAllProxies" size="x-small"
                    variant="tonal" :loading="loadingTestingConnection">
                    测试代理连通性
                </v-btn>
            </template>
        </v-radio>
    </v-radio-group>
    <div v-if="radioValue === '1'" style="margin-left: 16px;">
        <v-radio-group v-model="githubProxyRadioControl" class="mt-2" hide-details="true">
            <v-radio color="success" v-for="(proxy, idx) in githubProxies" :key="proxy" :value="idx">
                <template v-slot:label>
                    <div class="d-flex align-center">
                        <span class="mr-2">{{ proxy }}</span>
                        <div v-if="proxyStatus[idx]">
                            <v-chip 
                                :color="proxyStatus[idx].available ? 'success' : 'error'" 
                                size="x-small" 
                                class="mr-1">
                                {{ proxyStatus[idx].available ? '可用' : '不可用' }}
                            </v-chip>
                            <v-chip 
                                v-if="proxyStatus[idx].available" 
                                color="info" 
                                size="x-small">
                                {{ proxyStatus[idx].latency }}ms
                            </v-chip>
                        </div>
                    </div>
                </template>
            </v-radio>
            <v-radio color="primary" value="-1" label="自定义">
                <template v-slot:label v-if="githubProxyRadioControl === '-1'">
                    <v-text-field density="compact" v-model="selectedGitHubProxy" variant="outlined"
                        style="width: 100vw;" placeholder="自定义" hide-details="true">
                    </v-text-field>
                </template>
            </v-radio>
        </v-radio-group>
    </div>
</template>


<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
    setup() {
        const { tm } = useModuleI18n('features/settings');
        return { tm };
    },
    data() {
        return {
            githubProxies: [
                "https://edgeone.gh-proxy.com",
                "https://hk.gh-proxy.com/",
                "https://gh-proxy.com/",
                "https://gh.llkk.cc",
            ],
            githubProxyRadioControl: "0", // the index of the selected proxy
            selectedGitHubProxy: "",
            radioValue: "0", // 0: 不使用, 1: 使用
            loadingTestingConnection: false,
            testingProxies: {},
            proxyStatus: {},
        }
    },
    methods: {
        async testSingleProxy(idx) {
            this.testingProxies[idx] = true;
            
            const proxy = this.githubProxies[idx];
            
            try {
                const response = await axios.post('/api/stat/test-ghproxy-connection', {
                    proxy_url: proxy
                });
                console.log(response.data);
                if (response.status === 200) {
                    this.proxyStatus[idx] = {
                        available: true,
                        latency: Math.round(response.data.data.latency)
                    };
                } else {
                    this.proxyStatus[idx] = {
                        available: false,
                        latency: 0
                    };
                }
            } catch (error) {
                this.proxyStatus[idx] = {
                    available: false,
                    latency: 0
                };
            } finally {
                this.testingProxies[idx] = false;
            }
        },
        
        async testAllProxies() {
            this.loadingTestingConnection = true;
            
            const promises = this.githubProxies.map((proxy, idx) => 
                this.testSingleProxy(idx)
            );
            
            await Promise.all(promises);
            this.loadingTestingConnection = false;
        },
    },
    mounted() {
        this.selectedGitHubProxy = localStorage.getItem('selectedGitHubProxy') || "";
        this.radioValue = localStorage.getItem('githubProxyRadioValue') || "0";
        this.githubProxyRadioControl = localStorage.getItem('githubProxyRadioControl') || "0";
    },
    watch: {
        selectedGitHubProxy: function (newVal, oldVal) {
            if (!newVal) {
                newVal = ""
            }
            localStorage.setItem('selectedGitHubProxy', newVal);
        },
        radioValue: function (newVal) {
            localStorage.setItem('githubProxyRadioValue', newVal);
            if (newVal === "0") {
                this.selectedGitHubProxy = "";
            }
        },
        githubProxyRadioControl: function (newVal) {
            localStorage.setItem('githubProxyRadioControl', newVal);
            if (newVal !== "-1") {
                this.selectedGitHubProxy = this.githubProxies[newVal] || "";
            } else {
                this.selectedGitHubProxy = "";
            }
        }
    }
}
</script>

<style>
.v-label {
    font-size: 0.875rem;
}
</style>
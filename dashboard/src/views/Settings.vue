<template>

    <div style="background-color: var(--v-theme-surface, #fff); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">

        <v-list lines="two">
            <v-list-subheader>{{ tm('network.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('network.githubProxy.subtitle')" :title="tm('network.githubProxy.title')">

                <v-combobox variant="outlined" style="width: 100%; margin-top: 16px;" v-model="selectedGitHubProxy" :items="githubProxies"
                    :label="tm('network.githubProxy.label')">
                </v-combobox>
            </v-list-item>

            <v-list-subheader>{{ tm('system.title') }}</v-list-subheader>

            <v-list-item :subtitle="tm('system.restart.subtitle')" :title="tm('system.restart.title')">
                <v-btn style="margin-top: 16px;" color="error" @click="restartAstrBot">{{ tm('system.restart.button') }}</v-btn>
            </v-list-item>

            


        </v-list>

    </div>

    <WaitingForRestart ref="wfr"></WaitingForRestart>


</template>

<script>
import axios from 'axios';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import { useModuleI18n } from '@/i18n/composables';

export default {
    components: {
        WaitingForRestart,
    },
    setup() {
        const { tm } = useModuleI18n('features/settings');
        return { tm };
    },
    data() {
        return {
            githubProxies: [
                "https://gh.llkk.cc",
                "https://gitproxy.click",
            ],
            selectedGitHubProxy: "",
        }
    },
    methods: {
        restartAstrBot() {
            axios.post('/api/stat/restart-core').then(() => {
                this.$refs.wfr.check();
            })
        }
    },
    mounted() {
        this.selectedGitHubProxy = localStorage.getItem('selectedGitHubProxy') || "";
    },
    watch: {
        selectedGitHubProxy: function (newVal, oldVal) {
            if (!newVal) {
                newVal = ""
            }
            localStorage.setItem('selectedGitHubProxy', newVal);
        }
    }
}
</script>
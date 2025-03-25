<template>

    <div style="background-color: white; padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">

        <v-list lines="two">
            <v-list-subheader>网络</v-list-subheader>

            <v-list-item subtitle="设置下载插件或者更新 AstrBot 时所用的 GitHub 加速地址。这在中国大陆的网络环境有效。可以自定义，输入结果实时生效。所有地址均不保证稳定性，如果在更新插件/项目时出现报错，请首先检查加速地址是否能正常使用。" title="GitHub 加速地址">

                <v-combobox variant="outlined" style="width: 100%; margin-top: 16px;" v-model="selectedGitHubProxy" :items="githubProxies"
                    label="选择 GitHub 加速地址">
                </v-combobox>
            </v-list-item>

            <v-list-subheader>系统</v-list-subheader>

            <v-list-item subtitle="重启 AstrBot" title="重启">
                <v-btn style="margin-top: 16px;" color="error" @click="restartAstrBot">重启</v-btn>
            </v-list-item>

            


        </v-list>

    </div>

    <WaitingForRestart ref="wfr"></WaitingForRestart>


</template>

<script>
import axios from 'axios';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';

export default {
    components: {
        WaitingForRestart,
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
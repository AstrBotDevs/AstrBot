<template>

    <div style="background-color: white; padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">

        <v-list lines="two">
            <v-list-subheader>网络</v-list-subheader>

            <v-list-item subtitle="设置下载插件时所用的 GitHub 加速地址。这在中国大陆的网络环境有效。可以自定义，输入结果实时生效" title="GitHub 加速地址">

                <v-combobox variant="outlined" style="width: 100%; margin-top: 16px;" v-model="selectedGitHubProxy" :items="githubProxies"
                    label="选择 GitHub 加速地址">
                </v-combobox>
            </v-list-item>


        </v-list>

    </div>


</template>

<script>
export default {
    data() {
        return {
            githubProxies: [
                "https://ghproxy.cn",
                "https://gh.llkk.cc",
                "https://ghproxy.net",
                "https://gitproxy.click",
                "https://github.tbedu.top"
            ],
            selectedGitHubProxy: "",
        }
    },
    methods: {

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
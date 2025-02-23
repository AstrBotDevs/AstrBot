<template>
    <v-card style="height: 100%;">
        <v-card-text style="padding: 0; height: 100%; overflow-y: auto;">
            <div
                style="display: flex; justify-content: center; align-items: center; height: 100%; flex-direction: column;">
                <div @click="selectedLogo = selectedLogo == 0 ? 1 : 0" style="height: 300px;">
                    <img v-if="selectedLogo == 0" width="300" src="@/assets/images/logo-waifu.png" alt="AstrBot Logo"
                        class="fade-in">
                    <img v-if="selectedLogo == 1" width="300" src="@/assets/images/logo-normal.svg" alt="AstrBot Logo"
                        class="fade-in">
                </div>

                <h1 class="mt-8">AstrBot</h1>

                <span class="mt-2" style="color: #777;">A project out of interests and loves ❤️</span>

                <span style="color: #777; margin-left: 32px; margin-right: 32px" class="mt-4">By <a
                        href="https://soulter.top">Soulter</a>, <a
                        href="https://github.com/Soulter/AstrBot/graphs/contributors">AstrBot Contributors</a>
                    and <a href="https://github.com/Soulter/AstrBot_Plugins_Collection/graphs/contributors">AstrBot
                        Plugin Authors</a>
                </span>

                <!-- Copy-paste in your Readme.md file -->

                <img style="margin-top: 16px; width: 50%; max-width: 500px; margin-left: 32px; margin-right: 32px"
                    alt="Active Contributors of Soulter/AstrBot - Last 28 days"
                    src="https://next.ossinsight.io/widgets/official/compose-recent-active-contributors/thumbnail.png?repo_id=575865240&limit=365&image_size=auto&color_scheme=light">

                <img style="margin-top: 16px; width: 50%; max-width: 500px; margin-left: 32px; margin-right: 32px"
                    alt="Active Contributors of Soulter/AstrBot - Last 28 days"
                    src="https://next.ossinsight.io/widgets/official/analyze-repo-stars-map/thumbnail.png?activity=stars&repo_id=575865240&image_size=auto&color_scheme=light
">

                
                <!-- Made with [OSS Insight](https://ossinsight.io/) -->

                <v-btn class="text-primary mt-8" @click="open('https://github.com/Soulter/AstrBot')"
                    color="lightprimary" variant="flat" rounded="sm">
                    Star 这个项目! 🌟
                </v-btn>

                <v-btn class="text-primary mt-4" @click="open('https://github.com/Soulter/AstrBot/issues')"
                    color="lightprimary" variant="flat" rounded="sm">
                    有使用问题或者功能建议？提交 Issue！
                </v-btn>
            </div>

        </v-card-text>
    </v-card>
</template>
<script>
export default {
    name: 'AboutPage',
    data() {
        return {
            selectedLogo: 0
        }
    },

    methods: {
        open(url) {
            window.open(url, '_blank');
        }
    }
}

</script>

<style>
@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

.fade-in {
    animation: fadeIn 0.2s ease-in-out;
}
</style>
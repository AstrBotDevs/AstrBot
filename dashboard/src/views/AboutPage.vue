<template>
    <v-card style="height: 100%;">
        <v-card-text style="padding: 0; height: 100%;">
            <div
                style="display: flex; justify-content: center; align-items: center; height: 100%; flex-direction: column;">
                <div @click="selectedLogo = selectedLogo == 0 ? 1 : 0" style="height: 300px;">
                    <img v-if="selectedLogo == 0" width="300" src="@/assets/images/logo-waifu.png" alt="AstrBot Logo" class="fade-in">
                    <img v-if="selectedLogo == 1" width="300" src="@/assets/images/logo-normal.svg" alt="AstrBot Logo" class="fade-in">
                </div>

                <h1 class="mt-8">AstrBot</h1>

                <span style="color: #777;" class="mt-4">By <a href="https://soulter.top">Soulter</a> And <a href="https://github.com/Soulter/AstrBot/graphs/contributors">AstrBot Contributors</a></span>

                <v-btn class="text-primary mt-16" @click="open('https://github.com/Soulter/AstrBot')"
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
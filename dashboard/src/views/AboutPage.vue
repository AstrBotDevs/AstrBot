<template>
    <v-card style="height: 100%;" elevation="0" class="bg-surface">
        <v-card-text style="padding: 0; height: 100%; overflow-y: hidden;">
            <div class="about-wrapper">
                <!-- Hero Section -->
                <section class="hero-section">
                    <div class="logo-title-container">
                        <div @click="selectedLogo = selectedLogo == 0 ? 1 : 0" class="logo-container">
                            <img v-if="selectedLogo == 0" width="280" src="@/assets/images/logo-waifu.png" alt="AstrBot Logo" class="fade-in">
                            <img v-if="selectedLogo == 1" width="280" src="@/assets/images/logo-normal.svg" alt="AstrBot Logo" class="fade-in">
                        </div>
                        <div class="title-container">
                            <h1 class="text-h2 font-weight-bold">{{ tm('hero.title') }}</h1>
                            <p class="text-subtitle-1" style="color: var(--v-theme-secondaryText);">{{ tm('hero.subtitle') }}</p>
                            <div class="action-buttons">
                                <v-btn @click="open('https://github.com/Soulter/AstrBot')"
                                    color="primary" variant="elevated" prepend-icon="mdi-star">
                                    {{ tm('hero.starButton') }}
                                </v-btn>
                                <v-btn class="ml-4" @click="open('https://github.com/Soulter/AstrBot/issues')"
                                    color="secondary" variant="elevated" prepend-icon="mdi-comment-question">
                                    {{ tm('hero.issueButton') }}
                                </v-btn>
                            </div>
                        </div>
                    </div>
                </section>

                <!-- Contributors Section -->
                <section class="contributors-section">
                    <v-container>
                        <v-row justify="center" align="center">
                            <v-col cols="12" md="6" class="pr-md-8 contributors-info">
                                <h2 class="text-h4 font-weight-medium">{{ tm('contributors.title') }}</h2>
                                <p class="mb-4 text-body-1" style="color: var(--v-theme-secondaryText);">
                                    {{ tm('contributors.description') }}
                                </p>
                                <p class="text-body-1" style="color: var(--v-theme-secondaryText);">
                                    <a href="https://github.com/Soulter/AstrBot/graphs/contributors" class="text-decoration-none custom-link">{{ tm('contributors.viewLink') }}</a>
                                </p>
                            </v-col>
                            <v-col cols="12" md="6">
                                <v-card variant="outlined" class="overflow-hidden" elevation="2">
                                    <v-img v-if="useCustomizerStore().uiTheme==='PurpleThemeDark'"
                                        alt="Active Contributors of Soulter/AstrBot"
                                        src="https://next.ossinsight.io/widgets/official/compose-recent-active-contributors/thumbnail.png?repo_id=575865240&limit=365&image_size=auto&color_scheme=dark">
                                    </v-img>
                                    <v-img v-else
                                        alt="Active Contributors of Soulter/AstrBot"
                                        src="https://next.ossinsight.io/widgets/official/compose-recent-active-contributors/thumbnail.png?repo_id=575865240&limit=365&image_size=auto&color_scheme=light">
                                    </v-img>
                                </v-card>
                            </v-col>
                        </v-row>
                    </v-container>
                </section>

                <!-- Stats Section -->
                <section class="stats-section">
                    <v-container>
                        <v-row justify="center" align="center" class="flex-md-row-reverse">
                            <v-col cols="12" md="6" class="pl-md-8 stats-info">
                                <h2 class="text-h4 font-weight-medium">{{ tm('stats.title') }}</h2>
                                
                                <div class="license-container mt-8">
                                    <img v-bind="props" src="https://www.gnu.org/graphics/agplv3-with-text-100x42.png" style="cursor: pointer;"/>
                                    <p class="text-caption mt-2" style="color: var(--v-theme-secondaryText);">{{ tm('stats.license') }}</p>
                                </div>
                            </v-col>
                            <v-col cols="12" md="6">
                                <v-card variant="outlined" class="overflow-hidden" elevation="2">
                                    <v-img v-if="useCustomizerStore().uiTheme==='PurpleThemeDark'"
                                        alt="Stars Map of Soulter/AstrBot"
                                        src="https://next.ossinsight.io/widgets/official/analyze-repo-stars-map/thumbnail.png?activity=stars&repo_id=575865240&image_size=auto&color_scheme=dark">
                                    </v-img>
                                    <v-img v-else
                                        alt="Stars Map of Soulter/AstrBot"
                                        src="https://next.ossinsight.io/widgets/official/analyze-repo-stars-map/thumbnail.png?activity=stars&repo_id=575865240&image_size=auto&color_scheme=light">
                                    </v-img>
                                </v-card>
                            </v-col>
                        </v-row>
                    </v-container>
                </section>
            </div>
        </v-card-text>
    </v-card>
</template>

<script>
import {useCustomizerStore} from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';

export default {
    name: 'AboutPage',
    setup() {
        const { tm } = useModuleI18n('features/about');
        return { tm };
    },
    data() {
        return {
            selectedLogo: 0
        }
    },

    methods: {
      useCustomizerStore,
        open(url) {
            window.open(url, '_blank');
        }
    }
}
</script>

<style scoped>
.about-wrapper {
    min-height: 100%;
}

.hero-section {
    padding: 40px 20px;
    background: linear-gradient(to right bottom, rgba(255,255,255,0.7), rgba(240,240,250,0.3));
    display: flex;
    justify-content: center;
    align-items: center;
    text-align: center;
}

.logo-title-container {
    display: flex;
    align-items: center;
    flex-direction: row;
    max-width: 900px;
    gap: 20px;
}

.logo-container {
    cursor: pointer;
    transition: all 0.3s ease;
    flex-shrink: 0;
}

.logo-container:hover {
    transform: scale(1.05);
}

.title-container {
    text-align: left;
}

.contributors-section, .stats-section {
    padding: 60px 20px;
}

.contributors-section {
    background-color: var(--v-theme-containerBg, #f9f9fb);
}

.contributors-info, .stats-info {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.custom-link {
    display: inline-block;
    padding: 5px 0;
    position: relative;
    color: var(--v-primary-base);
    font-weight: 500;
}

.custom-link::after {
    content: '';
    position: absolute;
    width: 100%;
    transform: scaleX(0);
    height: 2px;
    bottom: 0;
    left: 0;
    background-color: var(--v-primary-base);
    transform-origin: bottom right;
    transition: transform 0.25s ease-out;
}

.custom-link:hover::after {
    transform: scaleX(1);
    transform-origin: bottom left;
}

.license-container {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}

.action-buttons {
    display: flex;
    margin-top: 24px;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.fade-in {
    animation: fadeIn 0.2s ease-in-out;
}

@media (max-width: 960px) {
    .logo-title-container {
        flex-direction: column;
        text-align: center;
    }
    
    .title-container {
        text-align: center;
    }
    
    .action-buttons {
        justify-content: center;
    }
    
    .license-container {
        align-items: center;
    }
    
    .contributors-section, .stats-section {
        padding: 40px 20px;
    }
}

@media (max-width: 600px) {
    .action-buttons {
        flex-direction: column;
        gap: 12px;
    }
    
    .action-buttons .v-btn + .v-btn {
        margin-left: 0 !important;
    }
}
</style>
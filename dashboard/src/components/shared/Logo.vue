<template>
  <div class="logo-container">
    <div class="logo-content">
      <div class="logo-image">
        <div class="logo-glow-ring" />
        <img
          width="110"
          src="@/assets/images/astrbot_logo_mini.webp"
          alt="AstrBot Logo"
          class="logo-img"
        />
      </div>
      <div class="logo-text">
        <h2
          class="logo-title"
          v-html="formatTitle(title || t('core.header.logoTitle'))"
        />
        <h4 class="hint-text">
          {{ subtitle || t("core.header.accountDialog.title") }}
        </h4>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "@/i18n/composables";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
  }>(),
  {
    title: "",
    subtitle: "",
  },
);

const formatTitle = (title: string) => {
  if (title.includes("AstrBot ") || title.includes("AstrBot")) {
    return title.replace(/(AstrBot)\s+(.+)/, "$1<br> $2");
  }
  return title;
};
</script>

<style scoped>
.logo-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  margin-bottom: 10px;
}

.logo-content {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px;
  max-width: 100%;
  overflow: visible;
}

.logo-image {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}

/* Radial glow beneath the logo */
.logo-glow-ring {
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  background: radial-gradient(
    ellipse 70% 50% at 50% 60%,
    rgba(0, 242, 255, 0.12) 0%,
    rgba(0, 100, 180, 0.06) 40%,
    transparent 70%
  );
  pointer-events: none;
  animation: logoBreath 4s ease-in-out infinite;
}

.logo-img {
  position: relative;
  z-index: 1;
  filter: brightness(1.6) drop-shadow(0 0 8px rgba(0, 242, 255, 0.5))
    drop-shadow(0 0 20px rgba(0, 242, 255, 0.2));
  animation: logoBreath 4s ease-in-out infinite;
}

@keyframes logoBreath {
  0%, 100% { opacity: 0.75; }
  50% { opacity: 1; }
}

.logo-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}

.logo-title {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
  letter-spacing: 1px;
  white-space: nowrap;
  min-width: fit-content;
  font-family: "JetBrains Mono", "Fira Code", monospace;
}

/* Dark mode: cyan glow */
.v-theme--bluebusinessdarktheme .logo-title {
  color: rgba(0, 242, 255, 0.95) !important;
  text-shadow: 0 0 12px rgba(0, 242, 255, 0.5),
    0 0 30px rgba(0, 242, 255, 0.2);
}

/* Light mode: prussian blue, subtle shadow */
.v-theme--bluebusinesstheme .logo-title {
  color: #003153 !important;
  text-shadow: 0 0 8px rgba(0, 49, 83, 0.2);
}

.hint-text {
  margin: 4px 0 0 0;
  font-size: 1rem;
  font-weight: 400;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

/* Dark: faint gray text; Light: dark prussian */
.v-theme--bluebusinessdarktheme .hint-text {
  color: rgba(228, 225, 230, 0.45) !important;
}

.v-theme--bluebusinesstheme .hint-text {
  color: rgba(0, 49, 83, 0.5) !important;
}

@media (max-width: 420px) {
  .logo-title {
    line-height: 1.3;
  }
}


@media (max-width: 520px) {
  .logo-content {
    gap: 15px;
  }

  .logo-title {
    font-size: 1.6rem;
  }

  .hint-text {
    font-size: 0.9rem;
  }

  .logo-img {
    width: 90px;
  }
}
</style>

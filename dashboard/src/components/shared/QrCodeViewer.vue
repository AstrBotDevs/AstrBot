<template>
  <div class="qr-code-viewer">
    <img v-if="imageSrc" :src="imageSrc" :alt="alt" class="qr-code-image" />
    <div v-else class="qr-code-empty">
      {{ emptyHint }}
    </div>
  </div>
</template>

<script lang="ts">
import QRCode from "qrcode";

export default {
  name: "QrCodeViewer",
  props: {
    value: {
      type: String,
      default: "",
    },
    alt: {
      type: String,
      default: "QR Code",
    },
    size: {
      type: Number,
      default: 260,
    },
    emptyHint: {
      type: String,
      default: "暂无可用二维码",
    },
  },
  data() {
    return {
      imageSrc: "",
    };
  },
  watch: {
    value: {
      immediate: true,
      handler: "renderQRCode",
    },
  },
  methods: {
    async renderQRCode(rawValue) {
      const value = String(rawValue || "").trim();
      if (!value) {
        this.imageSrc = "";
        return;
      }

      try {
        this.imageSrc = await QRCode.toDataURL(value, {
          margin: 2,
          width: this.size,
          errorCorrectionLevel: "M",
        });
      } catch {
        this.imageSrc = "";
      }
    },
  },
};
</script>

<style scoped>
.qr-code-viewer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.qr-code-image {
  display: block;
  width: 180px;
  max-width: 100%;
  border-radius: 8px;
}

.qr-code-empty {
  color: rgba(0, 0, 0, 0.6);
  font-size: 12px;
}
</style>

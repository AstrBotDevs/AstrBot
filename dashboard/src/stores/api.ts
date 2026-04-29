import { defineStore } from "pinia";
import { getApiBaseUrl, setApiBaseUrl, normalizeConfiguredApiBaseUrl } from "@/utils/request";

export type ApiPreset = {
  name: string;
  url: string;
};

export const useApiStore = defineStore("api", {
  state: () => ({
    // 优先从 localStorage 读取用户手动设置的地址
    apiBaseUrl: localStorage.getItem("apiBaseUrl") || getApiBaseUrl() || "",
    configPresets: [] as ApiPreset[],
    customPresets: JSON.parse(
      localStorage.getItem("customPresets") || "[]",
    ) as ApiPreset[],
  }),
  getters: {
    presets: (state): ApiPreset[] => [
      ...state.configPresets,
      ...state.customPresets,
    ],
  },
  actions: {
    setPresets(presets: ApiPreset[]) {
      this.configPresets = presets;
    },

    addPreset(preset: ApiPreset) {
      this.customPresets.push(preset);
      localStorage.setItem("customPresets", JSON.stringify(this.customPresets));
    },

    removePreset(name: string) {
      this.customPresets = this.customPresets.filter((p) => p.name !== name);
      localStorage.setItem("customPresets", JSON.stringify(this.customPresets));
    },

    /**
     * 设置 API 基础地址
     * @param url 后端地址，例如 http://localhost:6185
     */
    setApiBaseUrl(url: string) {
      // Normalize: prepend https:// if missing, strip trailing slashes
      const normalized = normalizeConfiguredApiBaseUrl(url);

      this.apiBaseUrl = normalized;

      if (normalized) {
        localStorage.setItem("apiBaseUrl", normalized);
      } else {
        localStorage.removeItem("apiBaseUrl");
      }

      setApiBaseUrl(normalized);
    },

    /**
     * 初始化 API 配置
     * 通常在应用启动时调用，同步 localStorage 到 axios
     */
    init() {
      if (this.apiBaseUrl) {
        this.apiBaseUrl = setApiBaseUrl(this.apiBaseUrl);
      }
    },
  },
});

import { defineStore } from "pinia";
import { router } from "@/router";
import axios from "@/utils/request";
import { createLoginProof, type LoginChallenge } from "@/utils/authLoginProof";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    username: "",
    returnUrl: null as string | null,
  }),
  actions: {
    async login(username: string, password: string): Promise<void> {
      try {
        const challengeRes = await axios.post("/api/auth/login/challenge");
        const challenge = challengeRes.data?.data as LoginChallenge | undefined;
        if (!challenge) {
          return Promise.reject("Failed to initialize secure login");
        }

        let res;
        if (challenge.algorithm === "argon2") {
          res = await axios.post("/api/auth/login", {
            username: username,
            password: password,
          });
        } else {
          const passwordProof = await createLoginProof(password, challenge);
          res = await axios.post("/api/auth/login", {
            username: username,
            challenge_id: challenge.challenge_id,
            password_proof: passwordProof,
          });
        }

        if (res.data.status === "error") {
          return Promise.reject(res.data.message);
        }

        this.username = res.data.data.username;
        localStorage.setItem("user", this.username);
        localStorage.setItem("token", res.data.data.token);
        if (res.data.data?.change_pwd_hint || res.data.data?.legacy_pwd_hint) {
          localStorage.setItem("change_pwd_hint", "true");
          if (res.data.data?.legacy_pwd_hint) {
            localStorage.setItem("legacy_pwd_hint", "true");
          } else {
            localStorage.removeItem("legacy_pwd_hint");
          }
        } else {
          localStorage.removeItem("change_pwd_hint");
          localStorage.removeItem("legacy_pwd_hint");
        }

        const onboardingCompleted = await this.checkOnboardingCompleted();
        this.returnUrl = null;
        if (onboardingCompleted) {
          router.push("/dashboard/default");
        } else {
          router.push("/welcome");
        }
      } catch (error) {
        return Promise.reject(error);
      }
    },
    async checkOnboardingCompleted(): Promise<boolean> {
      try {
        // 1. 检查平台配置
        const platformRes = await axios.get("/api/config/get");
        const hasPlatform =
          (platformRes.data.data.config.platform || []).length > 0;
        if (!hasPlatform) return false;

        // 2. 检查提供者配置
        const providerRes = await axios.get("/api/config/provider/template");
        const providers = providerRes.data.data?.providers || [];
        const sources = providerRes.data.data?.provider_sources || [];
        const sourceMap = new Map();
        sources.forEach((s: any) => sourceMap.set(s.id, s.provider_type));

        const hasProvider = providers.some((provider: any) => {
          if (provider.provider_type)
            return provider.provider_type === "chat_completion";
          if (provider.provider_source_id) {
            const type = sourceMap.get(provider.provider_source_id);
            if (type === "chat_completion") return true;
          }
          return String(provider.type || "").includes("chat_completion");
        });

        return hasProvider;
      } catch (e) {
        console.error("Failed to check onboarding status:", e);
        return false;
      }
    },
    logout() {
      this.username = "";
      localStorage.removeItem("user");
      localStorage.removeItem("token");
      localStorage.removeItem("change_pwd_hint");
      localStorage.removeItem("legacy_pwd_hint");
      router.push("/auth/login");
    },
    has_token(): boolean {
      return !!localStorage.getItem("token");
    },
  },
});

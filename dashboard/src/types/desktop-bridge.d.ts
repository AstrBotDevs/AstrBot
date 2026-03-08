export {};

declare global {
  interface AstrBotDesktopAppUpdateCheckResult {
    ok: boolean;
    reason?: string | null;
    currentVersion?: string;
    latestVersion?: string | null;
    hasUpdate: boolean;
  }

  interface AstrBotDesktopAppUpdateResult {
    ok: boolean;
    reason?: string | null;
  }

  interface AstrBotAppUpdaterBridge {
    checkForAppUpdate: () => Promise<AstrBotDesktopAppUpdateCheckResult>;
    installAppUpdate: () => Promise<AstrBotDesktopAppUpdateResult>;
  }

  interface Window {
    astrbotAppUpdater?: AstrBotAppUpdaterBridge;
    astrbotDesktop?: {
      isDesktop: boolean;
      isDesktopRuntime: () => Promise<boolean>;
      getBackendState: () => Promise<{
        running: boolean;
        spawning: boolean;
        restarting: boolean;
        canManage: boolean;
      }>;
      restartBackend: (authToken?: string | null) => Promise<{
        ok: boolean;
        reason: string | null;
      }>;
      stopBackend: () => Promise<{
        ok: boolean;
        reason: string | null;
      }>;
      onTrayRestartBackend?: (callback: () => void) => () => void;
    };
  }
}

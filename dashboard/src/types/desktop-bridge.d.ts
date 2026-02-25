export {};

declare global {
  interface AstrBotAppUpdaterBridge {
    checkForAppUpdate: () => Promise<{
      ok: boolean;
      reason: string | null;
      currentVersion: string;
      latestVersion: string | null;
      hasUpdate: boolean;
    }>;
    installAppUpdate: () => Promise<{
      ok: boolean;
      reason: string | null;
    }>;
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
      checkDesktopAppUpdate: () => Promise<{
        ok: boolean;
        reason: string | null;
        currentVersion: string;
        latestVersion: string | null;
        hasUpdate: boolean;
      }>;
      installDesktopAppUpdate: () => Promise<{
        ok: boolean;
        reason: string | null;
      }>;
      onTrayRestartBackend?: (callback: () => void) => () => void;
    };
  }
}

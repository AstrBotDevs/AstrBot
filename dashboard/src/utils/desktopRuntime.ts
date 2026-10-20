export type DesktopRuntimeInfo = {
  bridge: Window['astrbotDesktop'] | undefined
  hasDesktopRuntimeProbe: boolean
  hasDesktopRestartCapability: boolean
  isDesktopRuntime: boolean
}

export async function getDesktopRuntimeInfo(): Promise<DesktopRuntimeInfo> {
  const bridge = window.astrbotDesktop
  const hasDesktopRuntimeProbe =
    !!bridge && typeof bridge.isDesktopRuntime === 'function'
  const hasDesktopRestartCapability =
    !!bridge &&
    typeof bridge.restartBackend === 'function' &&
    hasDesktopRuntimeProbe

  let isDesktopRuntime = !!bridge?.isDesktop
  if (hasDesktopRuntimeProbe) {
    try {
      isDesktopRuntime = isDesktopRuntime || !!(await bridge.isDesktopRuntime())
    } catch (error) {
      console.warn('[desktop-runtime] Failed to detect desktop runtime.', error)
    }
  }

  return {
    bridge,
    hasDesktopRuntimeProbe,
    hasDesktopRestartCapability,
    isDesktopRuntime,
  }
}

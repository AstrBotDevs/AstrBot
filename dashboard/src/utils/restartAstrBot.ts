import axios from 'axios'

type WaitingForRestartRef = {
  check: () => void
}

function triggerWaiting(waitingRef?: WaitingForRestartRef | null) {
  if (!waitingRef) return
  waitingRef.check()
}

export async function restartAstrBot(
  waitingRef?: WaitingForRestartRef | null
): Promise<void> {
  const desktopBridge = window.astrbotDesktop

  if (desktopBridge?.isElectron) {
    const result = await desktopBridge.restartBackend()
    if (!result.ok) {
      throw new Error(result.reason || 'Failed to restart backend.')
    }
    triggerWaiting(waitingRef)
    return
  }

  await axios.post('/api/stat/restart-core')
  triggerWaiting(waitingRef)
}

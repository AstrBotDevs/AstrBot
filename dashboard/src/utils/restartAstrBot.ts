import axios from 'axios'

type WaitingForRestartRef = {
  check: () => void | Promise<void>
}

async function triggerWaiting(waitingRef?: WaitingForRestartRef | null) {
  if (!waitingRef) return
  await waitingRef.check()
}

export async function restartAstrBot(
  waitingRef?: WaitingForRestartRef | null
): Promise<void> {
  const desktopBridge = window.astrbotDesktop

  if (desktopBridge?.isElectron) {
    await triggerWaiting(waitingRef)
    const result = await desktopBridge.restartBackend()
    if (!result.ok) {
      throw new Error(result.reason || 'Failed to restart backend.')
    }
    if (!waitingRef) {
      window.location.reload()
    }
    return
  }

  await axios.post('/api/stat/restart-core')
  await triggerWaiting(waitingRef)
  if (!waitingRef) {
    window.location.reload()
  }
}

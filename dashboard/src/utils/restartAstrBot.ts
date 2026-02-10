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
    const authToken = localStorage.getItem('token')
    const result = await desktopBridge.restartBackend(authToken)
    if (!result.ok) {
      throw new Error(result.reason || 'Failed to restart backend.')
    }
    await triggerWaiting(waitingRef)
    return
  }

  await axios.post('/api/stat/restart-core')
  await triggerWaiting(waitingRef)
}

import axios from 'axios'

type WaitingForRestartRef = {
  check: () => void | Promise<void>
  stop?: () => void
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
    const authToken = localStorage.getItem('token')
    const result = await desktopBridge.restartBackend(authToken)
    if (!result.ok) {
      waitingRef?.stop?.()
      throw new Error(result.reason || 'Failed to restart backend.')
    }
    return
  }

  await axios.post('/api/stat/restart-core')
  await triggerWaiting(waitingRef)
}

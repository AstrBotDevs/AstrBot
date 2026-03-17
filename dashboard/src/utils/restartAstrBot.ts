import axios from 'axios'
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime'

type WaitingForRestartRef = {
  check: (initialStartTime?: number | null) => void | Promise<void>
  stop?: () => void
}

async function triggerWaiting(
  waitingRef?: WaitingForRestartRef | null,
  initialStartTime?: number | null
) {
  if (!waitingRef) return
  await waitingRef.check(initialStartTime)
}

async function fetchCurrentStartTime(): Promise<number | null> {
  try {
    const response = await axios.get('/api/stat/start-time', { timeout: 1500 })
    const rawStartTime = response?.data?.data?.start_time
    const numericStartTime = Number(rawStartTime)
    return Number.isFinite(numericStartTime) ? numericStartTime : null
  } catch (_error) {
    return null
  }
}

export async function restartAstrBot(
  waitingRef?: WaitingForRestartRef | null
): Promise<void> {
  const { bridge: desktopBridge, hasDesktopRestartCapability, isDesktopRuntime } =
    await getDesktopRuntimeInfo()

  if (desktopBridge && hasDesktopRestartCapability && isDesktopRuntime) {
    const authToken = localStorage.getItem('token')
    const initialStartTime = await fetchCurrentStartTime()
    try {
      const restartPromise = desktopBridge.restartBackend(authToken)
      await triggerWaiting(waitingRef, initialStartTime)
      const result = await restartPromise
      if (!result.ok) {
        waitingRef?.stop?.()
        throw new Error(result.reason || 'Failed to restart backend.')
      }
    } catch (error) {
      waitingRef?.stop?.()
      throw error
    }
    return
  }

  await axios.post('/api/stat/restart-core')
  await triggerWaiting(waitingRef)
}

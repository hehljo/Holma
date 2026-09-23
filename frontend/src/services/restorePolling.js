import { restoreAPI } from './api'

const ACTIVE_STATUSES = new Set(['queued', 'running'])

const wait = (milliseconds, signal) => new Promise((resolve, reject) => {
  const timeout = window.setTimeout(resolve, milliseconds)
  signal?.addEventListener('abort', () => {
    window.clearTimeout(timeout)
    reject(new DOMException('Restore polling aborted', 'AbortError'))
  }, { once: true })
})

export async function pollRestoreStatus(
  restoreId,
  { onUpdate, signal, intervalMs = 2000, timeoutMs = 24 * 60 * 60 * 1000 } = {},
) {
  const deadline = Date.now() + timeoutMs
  let consecutiveFailures = 0

  while (Date.now() < deadline) {
    if (signal?.aborted) {
      throw new DOMException('Restore polling aborted', 'AbortError')
    }

    try {
      const response = await restoreAPI.getStatus(restoreId, { signal })
      const status = response.data
      consecutiveFailures = 0
      onUpdate?.(status)
      if (!ACTIVE_STATUSES.has(status.status)) return status
    } catch (error) {
      if (error.name === 'CanceledError' || error.name === 'AbortError') throw error
      consecutiveFailures += 1
      if (error.response?.status === 404 || consecutiveFailures >= 5) throw error
    }

    await wait(intervalMs, signal)
  }

  throw new Error('Restore status polling timed out')
}

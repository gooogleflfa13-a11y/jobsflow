/** Shared bounded-network policy for portal CLIs. */

export const REQUEST_TIMEOUT_MS = 15_000
export const MAX_RETRY_DELAY_MS = 30_000

export function requestSignal(timeoutMs = REQUEST_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(timeoutMs)
}

export function retryDelayMs(response: Response, fallbackMs: number): number {
  const raw = response.headers.get("retry-after")
  if (!raw) return Math.min(fallbackMs, MAX_RETRY_DELAY_MS)
  const seconds = Number(raw)
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.min(seconds * 1000, MAX_RETRY_DELAY_MS)
  }
  const at = Date.parse(raw)
  if (Number.isFinite(at)) {
    return Math.min(Math.max(0, at - Date.now()), MAX_RETRY_DELAY_MS)
  }
  return Math.min(fallbackMs, MAX_RETRY_DELAY_MS)
}

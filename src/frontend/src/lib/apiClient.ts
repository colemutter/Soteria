const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined

let warnedNoApiBaseUrl = false

function apiBaseUrl(): string | null {
  const trimmed = configuredApiBaseUrl?.trim()
  if (!trimmed) {
    if (!warnedNoApiBaseUrl) {
      warnedNoApiBaseUrl = true
      console.warn(
        '[api] VITE_API_BASE_URL is not set - backend satellite sync is disabled.',
      )
    }
    return null
  }
  return trimmed.replace(/\/+$/, '')
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T | null> {
  const base = apiBaseUrl()
  if (!base) return null

  const response = await fetch(`${base}${path}`, init)
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(
      `Backend request failed: ${response.status} ${response.statusText}${
        body ? ` - ${body}` : ''
      }`,
    )
  }

  return (await response.json()) as T
}

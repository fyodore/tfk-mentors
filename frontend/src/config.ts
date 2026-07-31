/** Public URL where the React app is served (set in .env.production). */
export const APP_URL = (import.meta.env.VITE_APP_URL ?? '').replace(/\/$/, '')

/** Backend API base URL (set in .env.production). Empty in dev — uses Vite proxy. */
export const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export function apiPath(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return API_URL ? `${API_URL}${normalized}` : normalized
}

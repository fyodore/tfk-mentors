import { useEffect, useState } from 'react'

import { fetchServerConfig } from '../api'
import { setDisplayTimeZone } from '../timezone.js'

export function TimezoneProvider({ children }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false

    Promise.resolve().then(async () => {
      try {
        const config = await fetchServerConfig()
        if (!cancelled && config?.time_zone) {
          setDisplayTimeZone(config.time_zone)
        }
      } catch (e) {
        if (!cancelled) {
          console.warn('Using UTC fallback; server timezone unavailable.', e)
        }
      } finally {
        if (!cancelled) setReady(true)
      }
    })

    return () => {
      cancelled = true
    }
  }, [])

  if (!ready) {
    return (
      <main className="panel">
        <p className="muted">Loading…</p>
      </main>
    )
  }

  return children
}

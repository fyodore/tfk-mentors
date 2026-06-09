import { SiteNav } from './SiteNav.jsx'

/** @param {{ title?: string }} props */
export function AppHeader({ title = 'TFK Mentors' }) {
  return (
    <header className="app-header">
      <h1>{title}</h1>
      <SiteNav />
    </header>
  )
}

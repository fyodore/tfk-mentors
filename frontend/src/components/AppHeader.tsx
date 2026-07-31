import { SiteNav } from './SiteNav.tsx'

type AppHeaderProps = {
  title?: string
}

export function AppHeader({ title = 'TFK Mentors' }: AppHeaderProps) {
  return (
    <header className="app-header">
      <h1>{title}</h1>
      <SiteNav />
    </header>
  )
}

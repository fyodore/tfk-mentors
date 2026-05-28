import { Link } from 'react-router-dom'

const SITE_PAGES = [
  {
    path: '/seasons',
    title: 'Seasons',
    description: 'View, create, edit, and delete seasons.',
  },
  {
    path: '/practices',
    title: 'Practices',
    description: 'List practices, filter by season, add, edit, or remove.',
  },
  {
    path: '/coaches',
    title: 'Coaches',
    description: 'Manage coaches and their season assignment.',
  },
  {
    path: '/mentors',
    title: 'Mentors',
    description: 'Manage mentors with season, type, and pace assignments.',
  },
  {
    path: '/emails',
    title: 'Emails',
    description:
      'Schedule mentor emails with practices; view upcoming and completed sends.',
  },
]

export default function HomePage() {
  return (
    <>
      <header className="app-header">
        <h1>TFK Mentors</h1>
        <p className="tagline">React UI · API proxied to Django</p>
      </header>

      <main className="panel home-panel">
        <h2 id="pages-heading">Site pages</h2>
        <p className="home-intro muted">
          Choose a destination below. Links open inside this app (no full page reload).
        </p>

        <nav className="home-nav" aria-labelledby="pages-heading">
          <ul className="home-page-list">
            {SITE_PAGES.map((page) => (
              <li key={page.path}>
                <Link className="home-page-card" to={page.path}>
                  <span className="home-page-card-title">{page.title}</span>
                  <span className="home-page-card-desc muted">
                    {page.description}
                  </span>
                  <span className="home-page-card-path" aria-hidden>
                    {page.path}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </main>
    </>
  )
}
